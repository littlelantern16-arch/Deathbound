"""Machine diagnostics for the RTX 3050 LTX execution package.

Detects, without faking anything:
- insufficient disk (before any model download)
- missing/incompatible torch (CPU-only build vs CUDA build)
- missing CUDA / GPU
- insufficient VRAM
- missing FFmpeg
- missing model weights (local HF cache scan — no network)
- missing Riven reference images

Runs anywhere: on the GPU-less sandbox it reports honest blockers; on the
Windows target machine it gates the first real generation. Used by
``python3 -m automation.video.run preflight`` and by scripts/test_ltx_local.ps1.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from .ltx_provider import LTX_CHECKPOINT_FILE, LTX_MODEL_ID, T5_ENCODER_REPO, resolve_t5_encoder_source
from .media import MediaToolkit
from .paths import find_project_root

# Minimums for the LTX 2B-distilled first test (from the Task #3 report).
MIN_DISK_GB = 20.0          # ~14 GB weights + torch env + headroom
MIN_VRAM_GB = 3.5           # 4 GB card minus display overhead
MIN_CUDA_MAJOR = 11         # torch cu121 wheels need driver >= CUDA 11.2-ish
MIN_TORCH = (2, 0)

HF_CACHE_ENV_VARS = ["HF_HOME", "HUGGINGFACE_HUB_CACHE", "TRANSFORMERS_CACHE"]


def _free_gb(path: Path) -> float:
    try:
        import shutil as _shutil

        return round(_shutil.disk_usage(str(path)).free / 1024**3, 1)
    except Exception:
        return 0.0


def _torch_probe() -> Dict[str, Any]:
    """Import torch and report build/cuda facts; never raises."""
    try:
        import torch
    except Exception as exc:
        return {"installed": False, "error": str(exc), "version": None,
                "cuda_build": None, "cuda_available": False, "vram_gb": None,
                "device_name": None, "driver_cuda": None}
    version = tuple(int(x) for x in torch.__version__.split("+")[0].split(".")[:2])
    cuda_build = torch.__version__.split("+")[1] if "+" in torch.__version__ else None
    cuda_available = bool(torch.cuda.is_available())
    vram_gb = None
    device_name = None
    driver_cuda = None
    if cuda_available:
        props = torch.cuda.get_device_properties(0)
        vram_gb = round(props.total_memory / 1024**3, 2)
        device_name = props.name
        try:
            driver_cuda = torch.cuda.get_device_capability(0)  # compute capability
        except Exception:
            driver_cuda = None
    return {
        "installed": True,
        "version": torch.__version__,
        "version_tuple": version,
        "cuda_build": cuda_build,
        "cuda_available": cuda_available,
        "vram_gb": vram_gb,
        "device_name": device_name,
        "compute_capability": driver_cuda,
    }


def model_cache_dir() -> Optional[Path]:
    """Where HF weights would land (respecting Deathbound D:-cache overrides)."""
    for var in HF_CACHE_ENV_VARS:
        value = os.environ.get(var)
        if value:
            return Path(value)
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    return hub


def t5_encoder_present() -> Dict[str, Any]:
    """Scan the local caches for the Phase A T5-XXL encoder weights. No network.

    Checks, in order, the pinned ``DEATHBOUND_T5_LOCAL_PATH`` directory, then
    the HF cache (config.json + model.safetensors from the city96 encoder
    repo — never google/t5-v1_1-xxl and never an fp32 text_encoder/ folder).
    """
    result = {
        "present": False,
        "source": T5_ENCODER_REPO,
        "local_path": os.environ.get("DEATHBOUND_T5_LOCAL_PATH") or None,
        "cache": str(model_cache_dir()) if model_cache_dir() else None,
        "size_gb": 0.0,
        "file": None,
    }
    # A misconfigured pin must not crash this no-network scan; surface it.
    try:
        result["source"] = resolve_t5_encoder_source()
    except Exception as exc:  # pin set but directory missing/invalid
        result["pin_error"] = str(exc)

    local = os.environ.get("DEATHBOUND_T5_LOCAL_PATH")
    if local:
        if os.path.isdir(local):
            marker = Path(local) / "model.safetensors"
            if marker.exists():
                result.update(
                    present=True,
                    size_gb=round(marker.stat().st_size / 1024**3, 2),
                    file=marker.name,
                )
        return result
    cache = model_cache_dir()
    if cache and cache.exists():
        for path in cache.rglob("model.safetensors"):
            if not (path.parent / "config.json").exists():
                continue  # sharded fp32 text_encoder/ dirs have an index, not this pair
            size_gb = round(path.stat().st_size / 1024**3, 2)
            # Phase A uses the ~9.5 GB bf16 single-file encoder. A ~19 GB
            # fp32 pair would be the forbidden Lightricks text_encoder/ dir.
            if 8.0 <= size_gb <= 11.0:
                result.update(present=True, size_gb=size_gb, file=str(path))
                break
    return result


def model_present() -> Dict[str, Any]:
    """Scan the local HF cache for the selected checkpoint. No network."""
    cache = model_cache_dir()
    if cache is None or not cache.exists():
        return {
            "present": False,
            "cache": str(cache) if cache else None,
            "size_gb": 0.0,
            "model_id": LTX_MODEL_ID,
            "checkpoint": LTX_CHECKPOINT_FILE,
        }
    # Match the checkpoint file inside the hosting repo's cache folder
    # (LTX_MODEL_ID hosts ltxv-2b-0.9.6-distilled-04-25.safetensors).
    needle = LTX_CHECKPOINT_FILE.lower().replace(".safetensors", "")
    total = 0
    found = False
    for path in cache.rglob("*"):
        if path.is_file():
            total += path.stat().st_size
            if needle in path.name.lower() and path.suffix in (".safetensors", ".bin"):
                found = True
    return {
        "present": found,
        "cache": str(cache),
        "size_gb": round(total / 1024**3, 1),
        "model_id": LTX_MODEL_ID,
        "checkpoint": LTX_CHECKPOINT_FILE,
    }


def riven_references() -> Dict[str, Any]:
    root = find_project_root()
    ref_dir = root / "assets" / "characters" / "riven" / "references"
    images = [
        p for p in ref_dir.glob("*")
        if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
    ] if ref_dir.exists() else []
    required = {"riven_face_01.png", "riven_fullbody_01.png"}
    names = {p.name.lower() for p in images}
    return {
        "count": len(images),
        "files": sorted(names),
        "required_present": sorted(required & names),
        "required_missing": sorted(required - names),
        "sufficient": bool(required & names),
    }


def run_diagnostics(*, min_disk_gb: float = MIN_DISK_GB) -> Dict[str, Any]:
    """Full preflight diagnostic. Returns machine-readable report."""
    root = find_project_root()
    blockers: List[str] = []
    warnings: List[str] = []

    disk_gb = _free_gb(root if Path(root).drive else Path.cwd())
    disk_ok = disk_gb >= min_disk_gb
    if not disk_ok:
        blockers.append(
            f"insufficient disk: {disk_gb} GB free, need >= {min_disk_gb} GB "
            "(weights ~14 GB + torch env + headroom)"
        )

    torch_info = _torch_probe()
    if not torch_info["installed"]:
        blockers.append(f"torch not installed in this environment: {torch_info['error']}")
    else:
        if torch_info["version_tuple"] < MIN_TORCH:
            blockers.append(f"torch too old: {torch_info['version']} (need >= 2.0)")
        if torch_info["cuda_build"] in (None, "cpu"):
            blockers.append(
                f"torch build has no CUDA support ({torch_info['version']}); "
                "install a CUDA wheel (see scripts/setup_ltx_windows.ps1)"
            )
        elif not torch_info["cuda_available"]:
            blockers.append("torch is CUDA-built but CUDA is not visible (driver/GPU missing?)")
        else:
            if (torch_info["vram_gb"] or 0) < MIN_VRAM_GB:
                blockers.append(
                    f"insufficient VRAM: {torch_info['vram_gb']} GB (need >= {MIN_VRAM_GB})"
                )

    ffmpeg = shutil.which("ffmpeg") or os.environ.get("DEATHBOUND_FFMPEG")
    if not ffmpeg:
        # config/paths.json fallback (Windows workstation location)
        ffmpeg = MediaToolkit(root).resolve_ffmpeg()
    if not ffmpeg:
        blockers.append(
            "FFmpeg not found (set DEATHBOUND_FFMPEG=D:\\Deathbound\\tools\\ffmpeg\\bin\\ffmpeg.exe "
            "or add to PATH)"
        )

    weights = model_present()
    if not weights["present"]:
        warnings.append(
            f"checkpoint {weights.get('checkpoint')} not found in cache ({weights['cache']}); "
            f"it will be downloaded on first generation (~15.5 GB: 5.9 GB checkpoint + "
            f"9.5 GB city96 T5 encoder) from {weights['model_id']}"
        )

    t5 = t5_encoder_present()
    if not t5["present"]:
        warnings.append(
            "T5-XXL encoder not found yet (Phase A will download ~9.5 GB bf16 from "
            f"{t5['source']} on first generation; NEVER google/t5-v1_1-xxl 44.54 GB "
            "nor Lightricks' fp32 text_encoder/ 19.05 GB). Pre-fetch per "
            "automation/video/LTX_SETUP.md section 2."
        )

    refs = riven_references()
    if not refs["sufficient"]:
        warnings.append(
            "REAL_RIVEN_REFERENCE_REQUIRED: "
            f"missing {refs['required_missing']} in assets/characters/riven/references/"
        )

    return {
        "schema_version": "1.0",
        "kind": "DEATHBOUND_LTX_MACHINE_DIAGNOSTICS",
        "disk_free_gb": disk_gb,
        "disk_ok": disk_ok,
        "torch": torch_info,
        "ffmpeg_path": ffmpeg,
        "model_weights": weights,
        "t5_encoder": t5,
        "riven_references": refs,
        "blocking_errors": blockers,
        "warnings": warnings,
        "ready_for_smoke_test": not blockers,
    }
