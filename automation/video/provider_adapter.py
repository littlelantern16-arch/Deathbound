"""Provider-neutral video generator adapter interface.

The adapter isolates every provider behind one contract so no provider is
hard-coded anywhere in the pipeline (tool-agnostic architecture,
DEATHBOUND_RULES.json -> toolAgnosticArchitecture). The first implementation
is a deterministic dry-run provider that requires no API key, no GPU and no
network — while every artifact it produces is marked ``simulated: true`` so
placeholder media can never pass as real output.

A real provider later implements the same ``VideoProvider`` methods and
registers itself; nothing else in the pipeline changes.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, List, Optional

from .paths import generation_paths, find_project_root, write_json


class ProviderError(RuntimeError):
    """Raised when a provider fails or is misconfigured."""


class GenerationRequest:
    """Provider-neutral generation request.

    Supports text-to-video, image-to-video, reference-image conditioning,
    previous-frame conditioning, and first/last-frame conditioning where the
    provider declares support.
    """

    def __init__(
        self,
        shot_id: str,
        prompt: str,
        duration_seconds: float,
        fps: int,
        resolution: str,
        *,
        reference_images: Optional[List[Dict[str, Any]]] = None,
        previous_final_frame: Optional[Dict[str, Any]] = None,
        first_frame: Optional[Dict[str, Any]] = None,
        last_frame: Optional[Dict[str, Any]] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
    ) -> None:
        self.shot_id = shot_id
        self.prompt = prompt
        self.negative_prompt = negative_prompt
        self.duration_seconds = duration_seconds
        self.fps = fps
        self.resolution = resolution
        self.reference_images = list(reference_images or [])
        self.previous_final_frame = previous_final_frame
        self.first_frame = first_frame
        self.last_frame = last_frame
        self.seed = seed

    def to_payload(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "duration_seconds": self.duration_seconds,
            "fps": self.fps,
            "resolution": self.resolution,
            "reference_images": self.reference_images,
            "previous_final_frame": self.previous_final_frame,
            "first_frame": self.first_frame,
            "last_frame": self.last_frame,
            "seed": self.seed,
        }


class GenerationResult:
    """Provider-neutral generation result + artifact references."""

    def __init__(
        self,
        shot_id: str,
        output_artifact: Dict[str, Any],
        poll_count: int,
        generation_parameters: Dict[str, Any],
        errors: Optional[List[str]] = None,
    ) -> None:
        self.shot_id = shot_id
        self.output_artifact = output_artifact
        self.poll_count = poll_count
        self.generation_parameters = generation_parameters
        self.errors = list(errors or [])

    def to_payload(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "output_artifact": self.output_artifact,
            "poll_count": self.poll_count,
            "generation_parameters": self.generation_parameters,
            "errors": self.errors,
        }


class VideoProvider:
    """Contract every video provider must implement.

    ``capabilities`` drives conditioning negotiation: the executor only sends
    conditioning a provider declares support for, and records in the manifest
    which conditioning was requested vs supported.
    """

    provider_id: str = "abstract"
    capabilities: Dict[str, Any] = {
        "text_to_video": True,
        "image_to_video": False,
        "reference_image_conditioning": False,
        "previous_frame_conditioning": False,
        "first_last_frame_conditioning": False,
        "polling": False,
    }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        raise NotImplementedError

    # Optional hooks -------------------------------------------------

    def poll(self, job_id: str) -> Dict[str, Any]:
        raise ProviderError(f"Provider {self.provider_id} does not support polling.")

    def retrieve_artifact(self, artifact_ref: Dict[str, Any]) -> Optional[bytes]:
        raise ProviderError(
            f"Provider {self.provider_id} does not support artifact retrieval."
        )


# ----------------------------------------------------------------------
# Registry (provider neutrality: nothing hard-codes a provider)
# ----------------------------------------------------------------------

_REGISTRY: Dict[str, type] = {}


def register_provider(provider_class: type) -> type:
    _REGISTRY[provider_class.provider_id] = provider_class
    return provider_class


def get_provider(provider_id: str) -> VideoProvider:
    if provider_id not in _REGISTRY:
        raise ProviderError(
            f"Unknown video provider '{provider_id}'. Registered: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[provider_id]()


def registered_providers() -> List[str]:
    return sorted(_REGISTRY)


# ----------------------------------------------------------------------
# Dry-run provider
# ----------------------------------------------------------------------

@register_provider
class DryRunProvider(VideoProvider):
    """Deterministic dry-run provider. No API key, GPU or network required.

    Produces simulated artifacts (JSON stubs on disk) that are always marked
    ``simulated: true``. Generation is instant but still flows through the
    full adapter contract so manifests and QA behave identically to a real
    provider.
    """

    provider_id = "dryrun"
    capabilities = {
        "text_to_video": True,
        "image_to_video": True,
        "reference_images": True,
        "reference_image_conditioning": True,
        "previous_frame_conditioning": True,
        "first_frame_conditioning": True,
        "last_frame_conditioning": True,
        "video_extension": False,
        "seed_control": True,
        "negative_prompt": True,
        "width_height_control": True,
        "fps_control": True,
        "duration_control": True,
        "local_execution": True,
        "remote_execution": False,
        "requires_credentials": False,
        "requires_payment": False,
        "polling": False,
    }

    def __init__(
        self,
        project_root: Optional[Any] = None,
        output_root: Optional[Any] = None,
        episode: str = "EP001",
        fail_first_attempt_for: Optional[List[str]] = None,
    ) -> None:
        self.project_root = find_project_root(project_root)
        paths = generation_paths(self.project_root, output_root)
        self.artifacts_dir = paths["artifacts"]
        self.episode = episode
        # Test hook: deterministic failures to exercise bounded retry.
        self._fail_first_attempt_for = set(fail_first_attempt_for or [])
        self._attempt_counts: Dict[str, int] = {}

    def generate(self, request: GenerationRequest) -> GenerationResult:
        shot_id = request.shot_id
        self._attempt_counts[shot_id] = self._attempt_counts.get(shot_id, 0) + 1
        attempt = self._attempt_counts[shot_id]
        errors: List[str] = []
        if shot_id in self._fail_first_attempt_for and attempt == 1:
            errors.append(
                f"{self.provider_id}: simulated transient provider failure on attempt 1 for {shot_id}"
            )
            raise ProviderError(errors[0])

        clip_id = f"{shot_id}-clip"
        digest = hashlib.sha256(
            json.dumps(request.to_payload(), sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        artifact = {
            "artifact_id": clip_id,
            "kind": "video_clip",
            "path": f"artifacts/{shot_id}/clip.json",
            "simulated": True,
            "digest": digest,
            "provider": self.provider_id,
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        # Write the simulated clip stub so the artifact physically exists.
        stub = {
            "artifact_id": clip_id,
            "kind": "video_clip",
            "simulated": True,
            "note": (
                "Dry-run placeholder. This is NOT real generated media. "
                "A real provider must replace this artifact."
            ),
            "digest": digest,
            "request": request.to_payload(),
        }
        write_json(self.artifacts_dir / shot_id / "clip.json", stub)
        return GenerationResult(
            shot_id=shot_id,
            output_artifact=artifact,
            poll_count=0,
            generation_parameters={
                **request.to_payload(),
                "provider": self.provider_id,
                "simulated": True,
            },
        )


@register_provider
class PollingDryRunProvider(DryRunProvider):
    """Dry-run provider that exercises the poll/retrieve contract.

    Identical artifacts to DryRunProvider, but generation goes through an
    explicit job -> poll -> retrieve cycle so the adapter's async path is
    testable without credentials.
    """

    provider_id = "dryrun-polling"
    capabilities = {
        **DryRunProvider.capabilities,
        "polling": True,
    }  # inherits requires_payment=False / requires_credentials=False

    def generate(self, request: GenerationRequest) -> GenerationResult:
        job_id = f"job-{request.shot_id}"
        poll_count = 0
        status = "queued"
        while status != "succeeded":
            poll_count += 1
            status = self.poll(job_id)["status"]
        payload = {
            "job_id": job_id,
            "request": request.to_payload(),
        }
        # Route through the base deterministic clip creation.
        base_result = super().generate(request)
        base_result.poll_count = poll_count
        base_result.generation_parameters["job_id"] = job_id
        base_result.generation_parameters["poll_count"] = poll_count
        return base_result

    def poll(self, job_id: str) -> Dict[str, Any]:
        # Deterministic two-step job lifecycle; a real provider would query
        # its remote job endpoint here.
        count = getattr(self, "_poll_counts", {})
        count[job_id] = count.get(job_id, 0) + 1
        self._poll_counts = count
        if count[job_id] >= 2:
            return {"job_id": job_id, "status": "succeeded"}
        return {"job_id": job_id, "status": "running"}

    def retrieve_artifact(self, artifact_ref: Dict[str, Any]) -> Optional[bytes]:
        path = self.project_root / "production" / "generation" / artifact_ref.get("path", "")
        if path.exists():
            return path.read_bytes()
        return None
