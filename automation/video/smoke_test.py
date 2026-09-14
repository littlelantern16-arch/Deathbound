"""Smallest real LTX generation test + validation + failure classification.

Invoked on the target machine by scripts/test_ltx_local.ps1:

    python -m automation.video.smoke_test --shot-id LTX-SMOKE-001

Performs, in order, with NO fake success path:
1. machine diagnostics (must be clean before touching the GPU)
2. one real generation via the existing LTXLocalProvider
3. ffprobe validation through the existing MediaToolkit
4. real final-frame extraction via MediaToolkit
5. prints generation time, resolution/FPS/duration, VRAM, and output path

Exit codes: 0 = real clip produced and validated; 1 = classified failure
(DIAGNOSTICS | GPU | VRAM | MODEL | GENERATION | MEDIA | DEPENDENCIES).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

from .diagnostics import run_diagnostics
from .media import MediaError, MediaToolkit
from .paths import find_project_root

FAILURE_CLASSES = {
    "DEPENDENCIES": "torch/diffusers missing or wrong build",
    "GPU": "no usable CUDA GPU",
    "VRAM": "GPU memory insufficient for the smallest test",
    "MODEL": "model weights unavailable/corrupt",
    "GENERATION": "inference failed (see traceback)",
    "MEDIA": "output missing/unverifiable/corrupt",
    "DIAGNOSTICS": "machine prerequisites not met",
}


def classify_exception(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "compiled with" in text or "not compiled" in text:
        return "DEPENDENCIES"  # CPU-only torch build installed
    if "cuda" in text and ("no " in text or "not " in text or "unavailable" in text or "driver" in text):
        return "GPU"
    if "out of memory" in text or "oom" in text or "torch.cuda.mem" in text:
        return "VRAM"
    if "safetensors" in text or "weights" in text or "checkpoint" in text or "huggingface" in text:
        return "MODEL"
    if "modulenotfounderror" in text or "importerror" in text:
        return "DEPENDENCIES"
    return "GENERATION"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m automation.video.smoke_test",
        description="Smallest real LTX generation test (no fake success).",
    )
    parser.add_argument("--shot-id", default="LTX-SMOKE-001")
    parser.add_argument("--prompt", default="slow cinematic push-in on a luxury city bedroom at night, moody motivated lighting")
    parser.add_argument("--duration", type=float, default=2.0)
    parser.add_argument("--resolution", default="512x320")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--seed", type=int, default=1234)
    args = parser.parse_args(argv)

    started = time.time()
    print("=== DEATHBOUND LTX SMOKE TEST ===", flush=True)

    # 1. Diagnostics gate -------------------------------------------------
    diag = run_diagnostics()
    print(json.dumps(diag, indent=2, default=str), flush=True)
    if not diag["ready_for_smoke_test"]:
        print("FAILURE CLASS: DIAGNOSTICS")
        for error in diag["blocking_errors"]:
            print("  BLOCKER:", error)
        return 1

    # 2. One real generation ----------------------------------------------
    from .provider_adapter import GenerationRequest
    from .ltx_provider import LTXLocalProvider

    provider = LTXLocalProvider()
    if not provider.is_available():
        print("FAILURE CLASS: GPU — torch CUDA unavailable at provider level")
        return 1

    request = GenerationRequest(
        shot_id=args.shot_id,
        prompt=args.prompt,
        duration_seconds=args.duration,
        fps=args.fps,
        resolution=args.resolution,
        seed=args.seed,
    )
    try:
        result = provider.generate(request)
    except Exception as exc:  # noqa: BLE001 — classified, never faked
        traceback.print_exc()
        print(f"FAILURE CLASS: {classify_exception(exc)}")
        return 1

    artifact = result.output_artifact

    # 3-4. Validate + extract final frame via existing media tools ---------
    root = find_project_root()
    toolkit = MediaToolkit(root)
    clip_path = root / "production" / "generation" / artifact["path"]
    try:
        info = toolkit.probe(clip_path)
    except MediaError as exc:
        print(f"FAILURE CLASS: MEDIA — {exc}")
        return 1
    frame_path = clip_path.parent / "final_frame.png"
    try:
        frame_info = toolkit.extract_last_frame(clip_path, frame_path)
    except MediaError as exc:
        print(f"FAILURE CLASS: MEDIA — final-frame extraction failed: {exc}")
        return 1

    elapsed = time.time() - started
    print("=== SMOKE TEST RESULT: SUCCESS (real media) ===")
    print(json.dumps({
        "clip": str(clip_path),
        "final_frame": str(frame_path),
        "final_frame_sha256": frame_info["sha256"],
        "resolution": f"{info['width']}x{info['height']}",
        "fps": info["fps"],
        "duration_seconds": info["duration_seconds"],
        "size_bytes": artifact["size_bytes"],
        "generation_time_seconds": artifact["generation_time_seconds"],
        "total_wall_seconds": round(elapsed, 1),
        "peak_vram_gb": artifact.get("peak_vram_gb"),
        "seed": artifact["seed"],
        "model": artifact["model_id"],
        "simulated": artifact["simulated"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
