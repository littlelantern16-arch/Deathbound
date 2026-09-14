"""Generation manifest construction, validation and persistence.

One manifest records one shot's full generation story: input visual state,
previous shot, previous final frame, character references, prompt, provider,
model, parameters, output artifact, final-frame artifact, validation result,
retry count, timestamps and errors (config/GENERATION_MANIFEST_SCHEMA.json).

Validation is strict about simulation: a manifest whose artifacts are
simulated is valid *as a dry-run* and is flagged ``dry_run: true`` — it can
never be mistaken for a real-media manifest.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .paths import generation_paths, find_project_root, load_json, write_json

REQUIRED_FIELDS = [
    "manifest_version",
    "episode",
    "scene_id",
    "shot_id",
    "run_id",
    "input_visual_state",
    "previous_shot",
    "previous_final_frame",
    "character_references",
    "prompt",
    "provider",
    "model",
    "generation_parameters",
    "output_artifact",
    "final_frame_artifact",
    "validation_result",
    "retry_count",
    "timestamps",
    "errors",
]


class ManifestError(ValueError):
    """Raised when a manifest is malformed or fails integrity checks."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GenerationManifestManager:
    """Builds, validates and persists one machine-readable manifest per shot."""

    def __init__(
        self,
        project_root: Optional[Any] = None,
        output_root: Optional[Any] = None,
        episode: str = "EP001",
    ) -> None:
        self.project_root = find_project_root(project_root)
        paths = generation_paths(self.project_root, output_root)
        self.manifests_dir = paths["manifests"]
        self.episode = episode

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        scene_id: str,
        shot_id: str,
        run_id: str,
        input_visual_state: Dict[str, Any],
        previous_shot: Optional[str],
        previous_final_frame: Optional[Dict[str, Any]],
        character_references: Dict[str, Any],
        prompt: str,
        provider: str,
        model: Optional[str],
        generation_parameters: Dict[str, Any],
        output_artifact: Optional[Dict[str, Any]],
        final_frame_artifact: Optional[Dict[str, Any]],
        validation_result: Dict[str, Any],
        retry_count: int,
        errors: List[str],
        created_utc: Optional[str] = None,
        generation_started_utc: Optional[str] = None,
        generation_finished_utc: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Assemble a manifest document from executor data."""
        manifest: Dict[str, Any] = {
            "manifest_version": "1.0",
            "episode": self.episode,
            "scene_id": scene_id,
            "shot_id": shot_id,
            "run_id": run_id,
            "input_visual_state": deepcopy(input_visual_state),
            "previous_shot": previous_shot,
            "previous_final_frame": deepcopy(previous_final_frame),
            "character_references": deepcopy(character_references),
            "prompt": prompt,
            "provider": provider,
            "model": model,
            "generation_parameters": deepcopy(generation_parameters),
            "output_artifact": deepcopy(output_artifact),
            "final_frame_artifact": deepcopy(final_frame_artifact),
            "validation_result": deepcopy(validation_result),
            "retry_count": int(retry_count),
            "timestamps": {
                "created_utc": created_utc or utc_now(),
                "generation_started_utc": generation_started_utc,
                "generation_finished_utc": generation_finished_utc,
            },
            "errors": list(errors),
        }
        artifacts = [manifest["output_artifact"], manifest["final_frame_artifact"]]
        manifest["dry_run"] = any(
            a is not None and a.get("simulated") for a in artifacts
        )
        return manifest

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def manifest_path(self, shot_id: str) -> Any:
        return self.manifests_dir / f"{shot_id}.manifest.json"

    def save(self, manifest: Dict[str, Any]) -> Any:
        errors = self.validate(manifest)
        if not errors["valid"]:
            raise ManifestError(
                f"Refusing to save invalid manifest for {manifest.get('shot_id')}: "
                + "; ".join(errors["errors"])
            )
        path = self.manifest_path(manifest["shot_id"])
        write_json(path, manifest)
        return path

    def load(self, shot_id: str) -> Optional[Dict[str, Any]]:
        path = self.manifest_path(shot_id)
        if not path.exists():
            return None
        return load_json(path)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, manifest: Any) -> Dict[str, Any]:
        """Check manifest integrity against the generation manifest schema."""
        errors: List[str] = []
        if not isinstance(manifest, dict):
            return {"valid": False, "errors": ["Manifest is not an object."]}

        for field_name in REQUIRED_FIELDS:
            if field_name not in manifest:
                errors.append(f"Missing required field: {field_name}")
        if errors:
            return {"valid": False, "errors": errors}

        if not manifest.get("shot_id"):
            errors.append("shot_id must be non-empty.")
        if not manifest.get("prompt"):
            errors.append("prompt must be non-empty.")
        if not manifest.get("provider"):
            errors.append("provider must be non-empty.")

        # Artifact integrity: both artifacts present, honest about simulation.
        output_artifact = manifest.get("output_artifact")
        final_frame = manifest.get("final_frame_artifact")
        if not isinstance(output_artifact, dict) or not output_artifact.get("artifact_id"):
            errors.append("output_artifact missing or has no artifact_id.")
        if not isinstance(final_frame, dict) or not final_frame.get("artifact_id"):
            errors.append("final_frame_artifact missing or has no artifact_id.")
        for artifact, label in (
            (output_artifact, "output_artifact"),
            (final_frame, "final_frame_artifact"),
        ):
            if isinstance(artifact, dict) and "simulated" not in artifact:
                errors.append(f"{label} must declare its simulated flag.")

        # Validation result integrity.
        validation = manifest.get("validation_result")
        if not isinstance(validation, dict) or "valid" not in validation:
            errors.append("validation_result must include a 'valid' flag.")

        # Retry bookkeeping.
        retry_count = manifest.get("retry_count")
        if not isinstance(retry_count, int) or retry_count < 0:
            errors.append("retry_count must be a non-negative integer.")

        # Error/valid coherence: errors list non-empty but validation passed.
        if manifest.get("errors") and manifest.get("validation_result", {}).get("valid"):
            errors.append("manifest records errors but validation_result.valid is true.")

        # Dry-run honesty: simulated artifacts must be flagged dry_run.
        artifacts_simulated = any(
            isinstance(a, dict) and a.get("simulated")
            for a in (manifest.get("output_artifact"), manifest.get("final_frame_artifact"))
        )
        if artifacts_simulated and not manifest.get("dry_run"):
            errors.append("simulated artifacts present but dry_run flag missing.")

        return {"valid": not errors, "errors": errors}
