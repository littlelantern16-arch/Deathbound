"""LTX-Video 2B distilled local provider — Deathbound's first real video engine.

Implements the existing provider-neutral VideoProvider contract with LOCAL,
₹0 inference (Lightricks LTX-Video 2B distilled via the official diffusers
pipelines). No paid API, no credentials, no cloud. Gated by ZERO_RUPEE_ONLY.

Honesty rules enforced here:
- ``requires_payment: false`` / ``requires_credentials: false`` / local only.
- Capabilities reflect what the diffusers 2B pipelines actually support;
  unsupported features are declared False, never faked.
- Generation NEVER returns a fake success: either a real MP4 artifact with
  ffprobe-validated metadata, or an exception (which the executor's bounded
  retry/QA handles).

Heavy imports (torch/diffusers) are lazy: the module imports cleanly in
environments without torch (CI, repo validation) and only loads the model
inside ``ensure_loaded`` during a real run.

Model: Lightricks/ltxv-2b-0.9.6-distilled (LTXV OpenRail-M, commercial use
permitted, ₹0). fp16 + CPU offload for the 4 GB RTX 3050 target (no FP8 —
Ampere lacks FP8 compute).
"""

from __future__ import annotations

import gc
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .media import MediaError, MediaToolkit
from .provider_adapter import (
    GenerationRequest,
    GenerationResult,
    VideoProvider,
    register_provider,
)
from .paths import find_project_root, generation_paths

# The selected backend (Task #3 feasibility decision).
LTX_MODEL_ID = os.environ.get("DEATHBOUND_LTX_MODEL", "Lightricks/ltxv-2b-0.9.6-distilled")

# 4 GB VRAM target: conservative defaults, divisible by 32 as LTX requires.
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 320
DEFAULT_FPS = 24
DEFAULT_STEPS = 8  # distilled schedule
DEFAULT_NUM_FRAMES = 49  # ~2s at 24fps (8n+1 constraint)

# Canonical Riven visual lock (config/DEATHBOUND_RULES.json +
# DEATHBOUND_VISUAL_STYLE_DNA.json). Never altered by this provider.
RIVEN_POSITIVE_BASE = (
    "realistic young adult man, 19-22, slim lean build, pale slightly "
    "desaturated skin with natural texture, messy black hair, dark eyes, "
    "calm observant expression, charcoal-black hooded coat, dark fitted "
    "shirt, black trousers, practical black boots, subtle silver details, "
    "cinematic motivated lighting, atmospheric depth, natural human anatomy, "
    "restrained cinematic stylization, premium supernatural drama"
)
RIVEN_NEGATIVE_BASE = (
    "anime, manga, cartoon, oversized eyes, chibi, 3D render, game avatar, "
    "roblox, voxel, low-poly, plastic skin, fashion model glamour, generic "
    "grim reaper, skull face, giant scythe, fantasy armor, ornate robes, "
    "giant cloak, medieval fantasy, extra limbs, malformed hands, distorted face"
)


class LTXNotAvailableError(RuntimeError):
    """Raised when LTX/torch is unavailable or the model is not local yet."""


@register_provider
class LTXLocalProvider(VideoProvider):
    """Local LTX-Video 2B distilled provider (diffusers, fp16 + CPU offload)."""

    provider_id = "ltx-local"
    capabilities = {
        # Generation modes (honest per diffusers 2B pipelines):
        "text_to_video": True,             # LTXPipeline
        "image_to_video": True,            # LTXImageToVideoPipeline
        "reference_images": True,          # consumed as conditioning inputs
        "first_frame_conditioning": True,  # I2V: image = first frame
        "last_frame_conditioning": False,  # no 2B last-frame endpoint
        "video_extension": False,          # present in LTXV repo scripts, not diffusers 2B
        # Controls:
        "seed_control": True,
        "negative_prompt": True,
        "width_height_control": True,
        "fps_control": True,
        "duration_control": True,
        # Execution / cost (policy-critical):
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
        model_id: Optional[str] = None,
    ) -> None:
        self.project_root = find_project_root(project_root)
        self.output_root = output_root
        self.model_id = model_id or LTX_MODEL_ID
        self.toolkit = MediaToolkit(self.project_root)
        gen_paths = generation_paths(self.project_root, output_root)
        self.artifacts_dir = gen_paths["artifacts"]
        self._pipeline: Optional[Any] = None
        self._loaded: bool = False

    # ------------------------------------------------------------------
    # Model loading (lazy; fp16 + CPU offload for 4 GB VRAM)
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        """True only if torch+CUDA and diffusers import AND a GPU exists."""
        try:
            import torch

            if not torch.cuda.is_available():
                return False
            import diffusers  # noqa: F401

            return True
        except Exception:
            return False

    def ensure_loaded(self) -> None:
        """Load the distilled 2B pipeline once (fp16, CPU offload)."""
        if self._loaded:
            return
        try:
            import torch
            from diffusers import LTXPipeline
        except Exception as exc:  # pragma: no cover - environment-specific
            raise LTXNotAvailableError(
                "LTX dependencies unavailable (torch/diffusers). Install the "
                "LTX environment per automation/video/LTX_SETUP.md."
            ) from exc
        if not torch.cuda.is_available():
            raise LTXNotAvailableError(
                "CUDA is not available; LTX local inference requires the "
                "NVIDIA GPU. Refusing to fake a generation."
            )

        dtype = torch.float16  # NO FP8: RTX 3050 (Ampere) has no FP8 compute.
        self._pipeline = LTXPipeline.from_pretrained(self.model_id, torch_dtype=dtype)
        # 4 GB VRAM strategy: keep params on CPU, stream components to GPU.
        self._pipeline.enable_model_cpu_offload()
        try:
            self._pipeline.enable_vae_tiling()  # decode large frames in tiles
        except Exception:
            pass
        self._loaded = True

    def unload(self) -> None:
        self._pipeline = None
        self._loaded = False
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Prompt handling (visual-state aware, canon-locked)
    # ------------------------------------------------------------------

    @staticmethod
    def _mentions_riven(prompt: str) -> bool:
        return "riven" in prompt.lower()

    def build_prompt(self, request: GenerationRequest) -> str:
        prompt = request.prompt or ""
        if self._mentions_riven(prompt):
            # Canon lock: append canonical identity terms so a bare visual
            # state summary still produces canonical Riven.
            prompt = f"{prompt}, {RIVEN_POSITIVE_BASE}"
        return prompt

    def build_negative_prompt(self, request: GenerationRequest) -> str:
        negative = request.negative_prompt or ""
        if self._mentions_riven(request.prompt or ""):
            negative = f"{negative}, {RIVEN_NEGATIVE_BASE}" if negative else RIVEN_NEGATIVE_BASE
        return negative

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.ensure_loaded()
        import torch

        started = time.time()
        shot_id = request.shot_id
        shot_dir = self.artifacts_dir / shot_id
        shot_dir.mkdir(parents=True, exist_ok=True)
        clip_path = shot_dir / "clip.mp4"

        # --- Conditioning inputs --------------------------------------
        # Previous final frame (chain) or reference image becomes the I2V
        # first frame, honoring the visual-state-driven prompt.
        conditioning_path: Optional[Path] = None
        if request.previous_final_frame:
            frame_ref = request.previous_final_frame.get("path")
            if frame_ref:
                candidate = generation_paths(self.project_root, self.output_root)["root"] / frame_ref
                if candidate.exists() and candidate.stat().st_size > 0:
                    conditioning_path = candidate
        if conditioning_path is None and request.reference_images:
            for ref in request.reference_images:
                ref_path = ref.get("path") if isinstance(ref, dict) else None
                if ref_path and Path(ref_path).exists():
                    conditioning_path = Path(ref_path)
                    break

        width, height = self._target_resolution(request)
        num_frames = self._target_frames(request)

        seed = request.seed if request.seed is not None else int(time.time())
        generator = torch.Generator(device="cpu").manual_seed(seed)

        prompt = self.build_prompt(request)
        negative = self.build_negative_prompt(request)

        try:
            if conditioning_path is not None:
                from diffusers import LTXConditionPipeline  # keyframe conditioning
                from diffusers.utils import load_image

                # LTXConditionPipeline accepts first-frame keyframe at 0.0.
                pipeline = self._condition_pipeline()
                conditionings = [
                    {"image": load_image(str(conditioning_path)), "frame_index": 0}
                ]
                video_frames = pipeline(
                    prompt=prompt,
                    negative_prompt=negative,
                    conditions=conditionings,
                    width=width,
                    height=height,
                    num_frames=num_frames,
                    num_inference_steps=DEFAULT_STEPS,
                    generator=generator,
                ).frames[0]
            else:
                pipeline = self._pipeline or self._text_pipeline()
                video_frames = pipeline(
                    prompt=prompt,
                    negative_prompt=negative,
                    width=width,
                    height=height,
                    num_frames=num_frames,
                    num_inference_steps=DEFAULT_STEPS,
                    generator=generator,
                ).frames[0]
        except Exception as exc:
            raise RuntimeError(
                f"LTX generation failed for {shot_id}: {exc}"
            ) from exc

        # --- Export + validate (real media only) -----------------------
        from diffusers.utils import export_to_video

        export_to_video(video_frames, str(clip_path), fps=request.fps or DEFAULT_FPS)
        if not clip_path.exists() or clip_path.stat().st_size == 0:
            raise MediaError(f"LTX produced no usable file for {shot_id}")

        info = self.toolkit.probe(clip_path)  # ffprobe validation gate
        generation_time = time.time() - started
        artifact = {
            "artifact_id": f"{shot_id}-clip",
            "kind": "video_clip",
            "path": f"artifacts/{shot_id}/clip.mp4",
            "simulated": False,
            "media_type": "video/mp4",
            "sha256": self.toolkit.sha256_file(clip_path),
            "size_bytes": info["size_bytes"],
            "width": info["width"],
            "height": info["height"],
            "fps": info["fps"],
            "duration_seconds": info["duration_seconds"],
            "frame_count": int(round((info["duration_seconds"] or 0) * (info["fps"] or 0))),
            "generation_time_seconds": round(generation_time, 2),
            "seed": seed,
            "model_id": self.model_id,
            "conditioning_frame": str(conditioning_path) if conditioning_path else None,
            "peak_vram_gb": self._peak_vram_gb(),
        }
        return GenerationResult(
            shot_id=shot_id,
            output_artifact=artifact,
            poll_count=0,
            generation_parameters={
                "provider": self.provider_id,
                "model": self.model_id,
                "width": width,
                "height": height,
                "num_frames": num_frames,
                "steps": DEFAULT_STEPS,
                "fps": request.fps or DEFAULT_FPS,
                "seed": seed,
                "conditioning": "i2v_first_frame" if conditioning_path else "t2v",
                "simulated": False,
            },
        )

    # ------------------------------------------------------------------
    # Pipeline helpers
    # ------------------------------------------------------------------

    def _text_pipeline(self) -> Any:
        from diffusers import LTXPipeline
        import torch

        self._pipeline = LTXPipeline.from_pretrained(self.model_id, torch_dtype=torch.float16)
        self._pipeline.enable_model_cpu_offload()
        try:
            self._pipeline.enable_vae_tiling()
        except Exception:
            pass
        return self._pipeline

    def _condition_pipeline(self) -> Any:
        from diffusers import LTXConditionPipeline

        if getattr(self, "_condition_pipeline_instance", None) is None:
            pipeline = LTXConditionPipeline.from_pretrained(
                self.model_id, torch_dtype=torch.float16
            )
            pipeline.enable_model_cpu_offload()
            self._condition_pipeline_instance = pipeline
        return self._condition_pipeline_instance

    # ------------------------------------------------------------------
    # Geometry helpers (4 GB conservative, /32 constraint)
    # ------------------------------------------------------------------

    @staticmethod
    def _target_resolution(request: GenerationRequest) -> tuple:
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
        if request.resolution and "x" in request.resolution:
            try:
                width, height = (int(x) for x in request.resolution.lower().split("x"))
            except ValueError:
                pass
        # Clamp to 4 GB-viable ceiling and round down to /32.
        width = max(256, min(width, 768)) // 32 * 32
        height = max(256, min(height, 512)) // 32 * 32
        return width, height

    @staticmethod
    def _target_frames(request: GenerationRequest) -> int:
        fps = request.fps or DEFAULT_FPS
        duration = request.duration_seconds or 2.0
        frames = int(round(fps * duration))
        # LTX constraint: num_frames = 8n + 1; clamp for 4 GB.
        frames = max(9, min(frames, 97))
        frames = ((frames - 1) // 8) * 8 + 1
        return frames

    def _peak_vram_gb(self) -> Optional[float]:
        try:
            import torch

            allocated = torch.cuda.max_memory_allocated()
            reserved = torch.cuda.max_memory_reserved()
            peak = max(allocated, reserved)
            return round(peak / 1024**3, 2) if peak else None
        except Exception:
            return None
