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

Model: LTX-Video 2B 0.9.6-distilled (LTXV OpenRail-M license, commercial use
permitted, ₹0). fp16 + group offload for the 4 GB RTX 3050 target (no FP8 —
Ampere lacks FP8 compute).

Model source (verified against the live Hugging Face API, 2026-09):
- ``Lightricks/ltxv-2b-0.9.6-distilled`` does NOT resolve (HTTP 401) — it was
  never a real repo, which was the production blocker this module fixes.
- The 2B 0.9.6-distilled weights ship ONLY as a single-file safetensors,
  ``ltxv-2b-0.9.6-distilled-04-25.safetensors`` (6,340,744,028 bytes, HTTP 200
  verified), inside the public ``Lightricks/LTX-Video`` repo. The
  ``LTX-Video-2B-0.9.6-{Dev,Distilled}-04-25`` repos are empty license shells
  (3 files: LICENSE/README/.gitattributes), and the ``0.9.7-distilled``/
  ``0.9.7-dev`` diffusers-format repos are 13B-only (48-layer transformer,
  ~24 GB) — unusable on 4 GB VRAM.
- Diffusers' ``from_single_file`` (available on LTXPipeline and
  LTXConditionPipeline in the installed diffusers) detects the checkpoint
  architecture from tensor keys and resolves the matching diffusers-format
  config repo, so both pipelines load the intended 2B distilled model.

MEMORY ARCHITECTURE (the 4 GB / 16 GB feasibility fix)
------------------------------------------------------
The naive ``from_single_file`` + ``enable_model_cpu_offload`` route cannot run
on this machine. Measured/verified component footprints (fp16/bf16):

    T5-XXL encoder (24L, d_model 4096)   ~9.5 GB
    2B distilled transformer (fp16)      ~4.4 GB
    LTX VAE (fp16)                       ~2.3 GB
    -------------------------------------------
    resident total                       ~16.2 GB  > 16 GB RAM

and ``enable_model_cpu_offload`` (diffusers 0.40.0, pipeline_utils.py) moves
whole components to the GPU in ``model_cpu_offload_seq = "text_encoder->
transformer->vae"`` order, so the 9.5 GB T5 encoder would land on the 4 GB
card during prompt encoding -> guaranteed CUDA OOM.

This provider therefore runs TWO phases with explicit memory boundaries:

Phase A (per request): load ONLY the tokenizer + T5 encoder on CPU, encode the
positive/negative prompts into ``prompt_embeds`` tensors, free the encoder.
Peak RAM ~10-11 GB (9.5 GB bf16 T5 + torch overhead), VRAM untouched.

Phase B: build the pipeline from the single-file checkpoint with
``text_encoder=None`` (diffusers 0.40.0 drops passed-None components cleanly:
loaders/single_file.py ``load_module`` + the
``missing_modules <= passed_modules + optional_modules`` branch), so nothing
T5-shaped ever enters the pipeline or the GPU. The transformer+VAE (~6.7 GB)
stay CPU-resident and stream to the GPU per block-group via
``enable_group_offload`` (block-level), keeping peak VRAM ~2-3.5 GB. The
precomputed embeds are moved to CUDA right before the call.

Peak RAM overall: ~10-11 GB during Phase A (transient), ~7-8 GB steady state
during Phase B. Both fit the 16 GB machine with the desktop closed.

T5 ENCODER SOURCE (the "no 44 GB download" fix)
-----------------------------------------------
``Lightricks/LTX-Video`` stores its ``text_encoder/`` folder in fp32 sharded
safetensors — 19.05 GB of downloads (verified via the HF paths-info API) — and
``google/t5-v1_1-xxl`` is a 44.54 GB pytorch_model.bin. Neither is acceptable.
The default encoder repo is ``city96/t5-v1_1-xxl-encoder-bf16``: a single
encoder-only bf16 safetensors (~9.5 GB), ungated public repo, whose config
matches LTX's ``text_encoder/config.json`` exactly (d_model 4096, d_ff 10240,
24 layers, 64 heads, gated-gelu, no tied embeddings). The encoder is
inference-only here — embedding equivalence with the fp32 weights holds to
bf16 precision, and LTX's own transformers loading path accepts any
T5EncoderModel-compatible folder via ``text_encoder=[...]``.
"""

from __future__ import annotations

import gc
import math
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .media import MediaError, MediaToolkit
from .provider_adapter import (
    GenerationRequest,
    GenerationResult,
    VideoProvider,
    register_provider,
)
from .paths import find_project_root, generation_paths

# The selected backend (Task #3 feasibility decision).
#
# LTX_MODEL_ID is the public repo that HOLDS the checkpoint. The intended
# model — 2B 0.9.6-distilled — is identified by LTX_CHECKPOINT_FILE below.
LTX_MODEL_ID = os.environ.get("DEATHBOUND_LTX_MODEL", "Lightricks/LTX-Video")
LTX_CHECKPOINT_FILE = os.environ.get(
    "DEATHBOUND_LTX_CHECKPOINT", "ltxv-2b-0.9.6-distilled-04-25.safetensors"
)
# Diffusers 0.40.0 `from_single_file()` accepts a Hub link ONLY in the
# documented /blob/main/ form. Verified against the installed 0.40.0 source
# (loaders/single_file_utils.py): `_extract_repo_id_and_weights_name` strips
# the host prefix and matches an optional `blob/main/` segment but NOT
# `resolve/main/`, so a /resolve/main/ link yields
# weights_name="resolve/main/<file>" and hf_hub_download builds
# .../resolve/main/resolve/main/<file> -> HTTP 404 (the RTX 3050 runtime bug).
# A plain local file path bypasses URL parsing entirely (os.path.isfile branch
# is checked first) and is therefore the preferred, Windows-safe source.
LTX_SINGLE_FILE_URL = (
    f"https://huggingface.co/{LTX_MODEL_ID}/blob/main/{LTX_CHECKPOINT_FILE}"
)

# T5-XXL encoder-only source (see module docstring for the full derivation).
T5_ENCODER_REPO = os.environ.get(
    "DEATHBOUND_T5_ENCODER", "city96/t5-v1_1-xxl-encoder-bf16"
)
# Optional: a pre-downloaded local T5 encoder directory (contains config.json
# + model.safetensors). When set, Phase A never touches the network.
T5_LOCAL_PATH = os.environ.get("DEATHBOUND_T5_LOCAL_PATH", "")
# Group offload (block-level) streams the transformer/VAE block-by-block onto
# the GPU. Set DEATHBOUND_GROUP_OFFLOAD=0 only on GPUs with >12 GB VRAM.
GROUP_OFFLOAD_ENABLED = os.environ.get("DEATHBOUND_GROUP_OFFLOAD", "1") != "0"
# Number of transformer blocks per offload group. Smaller groups = lower VRAM
# peaks, more CPU<->GPU traffic. NOTE: diffusers >=0.33 (hooks/group_offloading
# `_apply_group_offloading_block_level`) silently forces num_blocks_per_group=1
# whenever use_stream=True, so DEATHBOUND_GROUP_OFFLOAD_USE_STREAM defaults to
# 0 — the configured block grouping is what actually runs on the 4 GB card.
GROUP_OFFLOAD_NUM_BLOCKS = int(os.environ.get("DEATHBOUND_GROUP_OFFLOAD_BLOCKS", "4"))
GROUP_OFFLOAD_USE_STREAM = os.environ.get("DEATHBOUND_GROUP_OFFLOAD_USE_STREAM", "0") == "1"
# Keep the T5 encoder resident in RAM between requests (faster shot chains,
# ~9.5 GB steady RAM). Default off: free it after every encode so the 16 GB
# machine keeps ≥6 GB headroom during Phase B.
T5_KEEP_RESIDENT = os.environ.get("DEATHBOUND_T5_KEEP_RESIDENT", "0") == "1"

# Native inference geometry ceiling (AREA BUDGET), tuned for 4 GB VRAM with
# block group offload: ~768x432 = 331,776 px. The 2B model is natively
# 16:9-aligned; the largest exact-16:9 AND /32-divisible canvas inside this
# budget is 512x288 (768x432 itself is not /32-divisible), so 16:9 delivery
# requests infer natively at 512x288 and upscale same-aspect via FFmpeg.
DEFAULT_MAX_NATIVE_AREA = int(
    os.environ.get("DEATHBOUND_MAX_NATIVE_AREA", str(768 * 432))
)


def resolve_ltx_checkpoint_source() -> str:
    """Checkpoint source for ``from_single_file()``.

    Priority:
    1. ``DEATHBOUND_LTX_LOCAL_CHECKPOINT`` — path to the already-downloaded
       ``.safetensors`` file (no Hub access for the weights). A declared but
       missing path raises instead of silently falling back to a ~6 GB
       re-download.
    2. The documented Hub ``/blob/main/`` link (diffusers resolves, caches,
       and reuses it — Xet-backed files included).
    """
    local = os.environ.get("DEATHBOUND_LTX_LOCAL_CHECKPOINT")
    if local:
        if os.path.isfile(local):
            return local
        raise LTXNotAvailableError(
            "DEATHBOUND_LTX_LOCAL_CHECKPOINT is set but the file does not "
            f"exist: {local}. Fix the path or unset the variable to download "
            "the checkpoint from the Hub."
        )
    return LTX_SINGLE_FILE_URL


def resolve_t5_encoder_source() -> str:
    """T5 encoder source for Phase A (local dir when declared, else the repo)."""
    local = os.environ.get("DEATHBOUND_T5_LOCAL_PATH")
    if local:
        if os.path.isdir(local):
            return local
        raise LTXNotAvailableError(
            "DEATHBOUND_T5_LOCAL_PATH is set but the directory does not "
            f"exist: {local}. Fix the path or unset the variable to download "
            f"the encoder from {T5_ENCODER_REPO}."
        )
    return T5_ENCODER_REPO


# 4 GB VRAM target: conservative defaults, divisible by 32 as LTX requires.
DEFAULT_WIDTH = 512
DEFAULT_HEIGHT = 320
DEFAULT_FPS = 24
DEFAULT_STEPS = 8  # distilled schedule
DEFAULT_NUM_FRAMES = 49  # ~2s at 24fps (8n+1 constraint)
DEFAULT_GUIDANCE_SCALE = 3.0
DEFAULT_T5_SEQUENCE_LENGTH = 256  # cond pipeline max; 128 for plain t2v

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
    """Local LTX-Video 2B distilled provider.

    Tiered memory architecture for 4 GB VRAM / 16 GB RAM: CPU T5 prompt
    pre-encoding (Phase A) + a text-encoder-free checkpoint pipeline with
    block-level group offload (Phase B). See the module docstring.
    """

    provider_id = "ltx-local"
    capabilities = {
        # Generation modes (honest per diffusers 2B pipelines):
        "text_to_video": True,             # LTXPipeline
        "image_to_video": True,            # LTXConditionPipeline (first-frame)
        "reference_images": True,          # consumed as conditioning inputs
        "first_frame_conditioning": True,  # conditions frame_index=0
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
        self._condition_pipeline_instance: Optional[Any] = None
        self._loaded: bool = False
        # Phase A state (freed by default after each encode).
        self._text_encoder: Optional[Any] = None
        self._tokenizer: Optional[Any] = None

    # ------------------------------------------------------------------
    # Availability / loading
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

    # ---- Phase A: text encoder (CPU) ---------------------------------

    def ensure_text_encoder(self) -> Tuple[Any, Any]:
        """Load (tokenizer, T5EncoderModel) on CPU, bf16. Cached per provider."""
        if self._text_encoder is not None and self._tokenizer is not None:
            return self._tokenizer, self._text_encoder
        try:
            import torch
            from transformers import T5EncoderModel, AutoTokenizer
        except Exception as exc:  # pragma: no cover - environment-specific
            raise LTXNotAvailableError(
                "LTX dependencies unavailable (torch/transformers). Install "
                "the LTX environment per automation/video/LTX_SETUP.md."
            ) from exc
        source = resolve_t5_encoder_source()
        self._tokenizer = AutoTokenizer.from_pretrained(source)
        self._text_encoder = T5EncoderModel.from_pretrained(
            source, torch_dtype=torch.bfloat16
        )
        self._text_encoder.eval()
        return self._tokenizer, self._text_encoder

    def free_text_encoder(self) -> None:
        """Drop Phase A memory (~9.5 GB RAM) before Phase B runs."""
        self._text_encoder = None
        self._tokenizer = None
        gc.collect()
        try:
            import torch

            torch.cuda.empty_cache()
        except Exception:
            pass

    @staticmethod
    def _run_t5(encoder: Any, input_ids: Any, attention_mask: Any) -> Any:
        """T5 forward on CPU. Isolated for tests (records device movement)."""
        outputs = encoder(input_ids=input_ids, attention_mask=attention_mask)
        return outputs[0]

    def _encode_prompts(
        self,
        positive: str,
        negative: str,
        *,
        max_length: int = DEFAULT_T5_SEQUENCE_LENGTH,
    ) -> Tuple[Any, Any, Any, Any]:
        """Phase A: encode (positive, negative) into LTX prompt embeds.

        Returns ``(prompt_embeds, prompt_attention_mask,
        negative_prompt_embeds, negative_attention_mask)`` as CPU fp16
        tensors (batch 1), ready to hand to either LTX pipeline __call__ and
        to be moved to CUDA immediately before inference.
        """
        import torch

        tokenizer, encoder = self.ensure_text_encoder()
        with torch.no_grad():
            pos = tokenizer(
                positive,
                padding="max_length",
                max_length=max_length,
                truncation=True,
                return_tensors="pt",
            )
            neg = tokenizer(
                negative,
                padding="max_length",
                max_length=max_length,
                truncation=True,
                return_tensors="pt",
            )
            # Keep the encoder's native dtype (bf16); the caller converts to
            # the pipeline dtype on CUDA right before inference.
            pos_embeds = self._run_t5(encoder, pos.input_ids, pos.attention_mask)
            neg_embeds = self._run_t5(encoder, neg.input_ids, neg.attention_mask)
        pos_mask = pos.attention_mask.bool()
        neg_mask = neg.attention_mask.bool()
        if not T5_KEEP_RESIDENT:
            # Free the ~9.5 GB encoder BEFORE the checkpoint pipeline loads.
            self.free_text_encoder()
        return pos_embeds, pos_mask, neg_embeds, neg_mask

    # ---- Phase B: text-encoder-free pipeline -------------------------

    @staticmethod
    def _tiered_pipeline(pipeline_cls: Any, source: str) -> Any:
        """Build a pipeline WITHOUT its text encoder (Phase B).

        Verified against diffusers 0.40.0 ``loaders/single_file.py``:
        ``from_single_file(..., text_encoder=None)`` lands the component in
        ``passed_class_obj`` as None, ``load_module`` filters it out, and the
        remaining missing module is satisfied via the
        ``missing_modules <= passed_modules + optional_modules`` branch — so
        the T5 weights are never downloaded or instantiated here.
        """
        import torch

        return pipeline_cls.from_single_file(
            source, torch_dtype=torch.bfloat16, text_encoder=None, tokenizer=None
        )

    def _apply_group_offload(self, pipeline: Any) -> None:
        """Stream transformer/VAE block groups onto the 4 GB GPU.

        ``enable_group_offload`` (diffusers >= 0.31) onloads one block group
        at a time, so peak VRAM ~= largest group + activations instead of the
        whole 6.7 GB component set.
        """
        import torch

        if not GROUP_OFFLOAD_ENABLED:
            pipeline.to("cuda")
            return
        try:
            pipeline.enable_group_offload(
                onload_device=torch.device("cuda"),
                offload_device=torch.device("cpu"),
                offload_type="block_level",
                num_blocks_per_group=GROUP_OFFLOAD_NUM_BLOCKS,
                use_stream=GROUP_OFFLOAD_USE_STREAM,
                low_cpu_mem_usage=True,
            )
        except Exception:
            # Older diffusers or an offload incompatibility: fall back to the
            # whole-component offloader. Still never loads the T5 to GPU.
            pipeline.enable_model_cpu_offload()

    def ensure_loaded(self) -> None:
        """Load the tiered text pipeline once (Phase B; no T5 resident)."""
        self._ensure_pipeline(kind="text")

    def _ensure_pipeline(self, kind: str) -> Any:
        if kind == "condition" and self._condition_pipeline_instance is not None:
            return self._condition_pipeline_instance
        if kind == "text" and self._loaded and self._pipeline is not None:
            return self._pipeline
        try:
            import torch
            from diffusers import LTXConditionPipeline, LTXPipeline
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

        source = resolve_ltx_checkpoint_source()
        if kind == "condition":
            pipeline = self._tiered_pipeline(LTXConditionPipeline, source)
        else:
            pipeline = self._tiered_pipeline(LTXPipeline, source)
        self._apply_group_offload(pipeline)
        try:
            pipeline.vae.enable_tiling()  # tiled decode keeps VRAM bounded
        except Exception:
            pass
        if kind == "condition":
            self._condition_pipeline_instance = pipeline
        else:
            self._pipeline = pipeline
            self._loaded = True
        return pipeline

    def unload(self) -> None:
        self._pipeline = None
        self._condition_pipeline_instance = None
        self._text_encoder = None
        self._tokenizer = None
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
        # NOTE: the Phase-B pipeline is deliberately loaded AFTER Phase A
        # (prompt encoding). Loading it first would put the ~6.7 GB
        # transformer+VAE in RAM at the same time as the ~9.5 GB T5 encoder
        # — the exact 16 GB RAM collision this tiered design exists to avoid.
        import torch

        started = time.time()
        shot_id = request.shot_id
        shot_dir = self.artifacts_dir / shot_id
        shot_dir.mkdir(parents=True, exist_ok=True)
        native_path = shot_dir / "clip_native.mp4"
        clip_path = shot_dir / "clip.mp4"

        # --- Conditioning inputs --------------------------------------
        # Previous final frame (chain) or reference image becomes the
        # first-frame conditioning, honoring the visual-state prompt.
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

        deliverable_w, deliverable_h = self._deliverable_resolution(request)
        native_w, native_h = self._native_resolution(deliverable_w, deliverable_h)
        num_frames = self._target_frames(request)

        seed = request.seed if request.seed is not None else int(time.time())
        generator = torch.Generator(device="cpu").manual_seed(seed)

        prompt = self.build_prompt(request)
        negative = self.build_negative_prompt(request)

        # --- Phase A: prompts -> embeddings (CPU; then encoder freed) ---
        try:
            pos_embeds, pos_mask, neg_embeds, neg_mask = self._encode_prompts(
                prompt, negative, max_length=DEFAULT_T5_SEQUENCE_LENGTH
            )
        except LTXNotAvailableError:
            raise
        except Exception as exc:
            raise RuntimeError(
                f"LTX prompt encoding failed for {shot_id}: {exc}"
            ) from exc

        # --- Phase B: video latents on the 4 GB GPU ---------------------
        # Pipeline dtype (bf16) decides the embeds' device-side dtype.
        try:
            from diffusers.utils import load_image

            if conditioning_path is not None:
                # LTXVideoCondition is not re-exported at diffusers top level
                # in 0.40.0; the official import path is the pipeline module.
                from diffusers.pipelines.ltx.pipeline_ltx_condition import (
                    LTXVideoCondition,
                )

                pipeline = self._ensure_pipeline(kind="condition")
                embed_dtype = pipeline.transformer.dtype
                image = load_image(str(conditioning_path)).resize(
                    (native_w, native_h)
                )
                conditionings = [LTXVideoCondition(image=image, frame_index=0)]
                video_frames = pipeline(
                    prompt_embeds=pos_embeds.to(
                        device="cuda", dtype=embed_dtype
                    ),
                    prompt_attention_mask=pos_mask.to("cuda"),
                    negative_prompt_embeds=neg_embeds.to(
                        device="cuda", dtype=embed_dtype
                    ),
                    negative_prompt_attention_mask=neg_mask.to("cuda"),
                    conditions=conditionings,
                    width=native_w,
                    height=native_h,
                    num_frames=num_frames,
                    num_inference_steps=DEFAULT_STEPS,
                    guidance_scale=DEFAULT_GUIDANCE_SCALE,
                    generator=generator,
                ).frames[0]
            else:
                pipeline = self._ensure_pipeline(kind="text")
                embed_dtype = pipeline.transformer.dtype
                video_frames = pipeline(
                    prompt_embeds=pos_embeds.to(
                        device="cuda", dtype=embed_dtype
                    ),
                    prompt_attention_mask=pos_mask.to("cuda"),
                    negative_prompt_embeds=neg_embeds.to(
                        device="cuda", dtype=embed_dtype
                    ),
                    negative_prompt_attention_mask=neg_mask.to("cuda"),
                    width=native_w,
                    height=native_h,
                    num_frames=num_frames,
                    num_inference_steps=DEFAULT_STEPS,
                    guidance_scale=DEFAULT_GUIDANCE_SCALE,
                    generator=generator,
                ).frames[0]
        except Exception as exc:
            raise RuntimeError(
                f"LTX generation failed for {shot_id}: {exc}"
            ) from exc

        # --- Export + validate (real media only) -----------------------
        from diffusers.utils import export_to_video

        export_to_video(video_frames, str(native_path), fps=request.fps or DEFAULT_FPS)
        if not native_path.exists() or native_path.stat().st_size == 0:
            raise MediaError(f"LTX produced no usable file for {shot_id}")

        # Aspect-preserving upscale to the delivery resolution when the
        # request demands more than native (e.g. the executor's 1280x720).
        # Never stretches between aspect ratios: native is derived from the
        # delivery geometry itself (same aspect, /32), so this is a pure
        # same-aspect scale.
        final_info = self._finalize_delivery(
            native_path, clip_path, deliverable_w, deliverable_h
        )
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
            "native_resolution": f"{native_w}x{native_h}",
            "delivery_resolution": f"{deliverable_w}x{deliverable_h}",
            "upscaled": bool(
                (info["width"], info["height"]) != (native_w, native_h)
            ),
            "memory_architecture": "tiered_cpu_t5+group_offload",
        }
        return GenerationResult(
            shot_id=shot_id,
            output_artifact=artifact,
            poll_count=0,
            generation_parameters={
                "provider": self.provider_id,
                "model": self.model_id,
                "width": deliverable_w,
                "height": deliverable_h,
                "native_width": native_w,
                "native_height": native_h,
                "num_frames": num_frames,
                "steps": DEFAULT_STEPS,
                "fps": request.fps or DEFAULT_FPS,
                "seed": seed,
                "guidance_scale": DEFAULT_GUIDANCE_SCALE,
                "t5_encoder": resolve_t5_encoder_source(),
                "conditioning": "i2v_first_frame" if conditioning_path else "t2v",
                "simulated": False,
            },
        )

    # ------------------------------------------------------------------
    # Delivery geometry + upscale (aspect-safe FFmpeg post-process)
    # ------------------------------------------------------------------

    def _finalize_delivery(
        self,
        native_path: Path,
        clip_path: Path,
        deliverable_w: int,
        deliverable_h: int,
    ) -> Dict[str, Any]:
        """Scale native output to the delivery resolution, same aspect only."""
        if (deliverable_w, deliverable_h) == self._probe_size(native_path):
            native_path.replace(clip_path)
            return {"upscaled": False}
        ffmpeg = self.toolkit.resolve_ffmpeg()
        if not ffmpeg:
            raise MediaError(
                "FFmpeg not available; cannot deliver the requested "
                f"{deliverable_w}x{deliverable_h} upscale. Set DEATHBOUND_FFMPEG."
            )
        command = [
            ffmpeg,
            "-y",
            "-i",
            str(native_path),
            "-vf",
            (
                f"scale={deliverable_w}:{deliverable_h}:flags=lanczos,"
                "setsar=1"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            str(clip_path),
        ]
        import subprocess

        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode != 0 or not clip_path.exists() or clip_path.stat().st_size == 0:
            raise MediaError(
                f"delivery upscale failed for {native_path}: "
                f"{result.stderr.strip()[:400]}"
            )
        return {"upscaled": True}

    def _probe_size(self, path: Path) -> Tuple[int, int]:
        info = self.toolkit.probe(path)
        return int(info["width"]), int(info["height"])

    # ------------------------------------------------------------------
    # Geometry helpers (4 GB conservative, /32, aspect-correct)
    # ------------------------------------------------------------------

    @staticmethod
    def _aspect_preserving_sizes(
        width: int, height: int, max_area: int = DEFAULT_MAX_NATIVE_AREA
    ) -> Tuple[int, int]:
        """Largest (w, h) with w/h == width/height, /32, area <= max_area,
        and never larger than the deliverable itself.

        The executor requests 1280x720 (16:9) while the 4 GB GPU produces
        512x288 natively — the largest exact-16:9 /32-divisible canvas inside
        the area budget — so the FFmpeg delivery upscale is a pure
        same-aspect scale (no distortion). The default 512x320 smoke geometry
        (8:5) passes through unchanged, and sub-floor requests (e.g. 64x64
        after the 256px delivery floor) never balloon to the area ceiling.
        """
        # Aspect-exact base pair is (k*ratio_w, k*ratio_h); /32 canvas grid.
        gcd = math.gcd(width, height)
        ratio_w, ratio_h = width // gcd, height // gcd

        def area_of(k: int) -> int:
            return (k * ratio_w) * (k * ratio_h)

        # Bound k by the area cap AND by the deliverable size itself
        # (native inference is never larger than the delivery frame).
        k = max(
            1,
            min(
                int(math.isqrt(max_area // (ratio_w * ratio_h))),
                width // ratio_w,
                height // ratio_h,
            ),
        )
        while k > 1 and area_of(k) > max_area:
            k -= 1
        w, h = k * ratio_w, k * ratio_h
        # Snap each side to the /32 grid while preserving the aspect to
        # within half a pixel (s_rtol = half-pixel / side):
        s_rtol = 0.5 / max(w, h)
        for candidate_w in range(w + 32, 255, -32):
            if candidate_w > width:
                continue
            candidate_h = round(candidate_w * height / width / 32) * 32
            if candidate_h < 256 or candidate_h > height:
                continue
            if candidate_w * candidate_h > max_area:
                continue
            if (
                abs(candidate_w * height - candidate_h * width)
                / (candidate_w * height)
            ) <= s_rtol:
                return candidate_w, candidate_h
        # Degenerate aspect that the /32 grid cannot represent within the
        # half-pixel rule (e.g. extreme ratios): fall back to a centered
        # exact-aspect scale with independent /32 rounding — the caller's
        # FFmpeg step still delivers the exact requested frame size.
        scale = min(1.0, w / width, h / height)
        return max(256, int(width * scale) // 32 * 32), max(
            256, int(height * scale) // 32 * 32
        )

    @classmethod
    def _deliverable_resolution(cls, request: GenerationRequest) -> Tuple[int, int]:
        """Aspect-corrected delivery resolution (what ffprobe must report)."""
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
        if request.resolution and "x" in request.resolution:
            try:
                width, height = (int(x) for x in request.resolution.lower().split("x"))
            except ValueError:
                pass
        # Delivery ceiling: 1920x1080 (YouTube-ready); floor: 256x256.
        # The delivery resolution is exact (YouTube 1920x1080 / executor
        # 1280x720 / smoke 512x320): ffprobe must report precisely what was
        # requested, so no rounding here. The /32 constraint applies to the
        # NATIVE inference geometry instead (_native_resolution).
        width = max(256, min(width, 1920))
        height = max(256, min(height, 1080))
        return width, height

    @classmethod
    def _native_resolution(
        cls, deliverable_w: int, deliverable_h: int
    ) -> Tuple[int, int]:
        """Native inference geometry: same aspect, within the 4 GB area cap."""
        return cls._aspect_preserving_sizes(
            deliverable_w, deliverable_h, DEFAULT_MAX_NATIVE_AREA
        )

    @classmethod
    def _target_resolution(cls, request: GenerationRequest) -> Tuple[int, int]:
        """Backward-compatible hook: native resolution for a request.

        (The legacy name returned a 3:2-clamped canvas that could not deliver
        16:9 without distortion; new code paths use the deliverable/native
        pair explicitly.)
        """
        w, h = cls._deliverable_resolution(request)
        return cls._native_resolution(w, h)

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
