# LTX-Video 2B distilled — Target-Machine Setup & First-Video Runbook

For the production workstation (RTX 3050 Laptop 4 GB, 16 GB RAM, Windows,
Python 3.11, FFmpeg at `D:\Deathbound\tools\ffmpeg`). This sandbox has no
GPU, so the generation steps run there, not here.

## 0. Prerequisites check (PowerShell, from repo root)

```powershell
python --version                # expect 3.11.x
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
ffmpeg -version                 # or set DEATHBOUND_FFMPEG=D:\Deathbound\tools\ffmpeg\bin\ffmpeg.exe
git status                      # clean tree
```

## 1. Isolated environment (does not disturb other Python setups)

```powershell
python -m venv D:\Deathbound\tools\ltx-env
D:\Deathbound\tools\ltx-env\Scripts\python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu121
pip install diffusers transformers accelerate "imageio[ffmpeg]" sentencepiece
```

Estimated install: ~3-5 GB disk (torch CUDA wheels ~2.5 GB dominate).

## 2. Model weights — download ONLY this one checkpoint

**Verified source of truth (live HF API, 2026-09):** the 2B 0.9.6-distilled
weights ship ONLY as the single-file checkpoint
`ltxv-2b-0.9.6-distilled-04-25.safetensors` (6,340,744,028 bytes ≈ 5.9 GB)
inside the public `Lightricks/LTX-Video` repo. It is loaded with
diffusers' `from_single_file`, which auto-resolves the matching diffusers
config. (There is no `Lightricks/ltxv-2b-0.9.6-distilled` repo — that dead ID
was the original production blocker — and the 0.9.7-distilled diffusers repos
are 13B-only.)

| Component | Size | Notes |
|---|---|---|
| `ltxv-2b-0.9.6-distilled-04-25.safetensors` | ~5.9 GB | the 2B DiT (single file) |
| T5-XXL text encoder config components (auto-pulled, fp16) | ~9-10 GB | resolved by from_single_file |
| VAE | ~1-2 GB | included in resolved config |

**Expected total download: ~14-17 GB.** Destination: the HF cache
(`D:\Deathbound\cache\huggingface` when HF_HOME is set by
`scripts/setup_ltx_windows.ps1`, else `%USERPROFILE%\.cache\huggingface`).
Free disk needed: **≥ 20 GB**. Weights are auto-downloaded on first
`ensure_loaded()`; or pre-fetch with:

```powershell
D:\Deathbound\tools\ltx-env\Scripts\python -c "from diffusers import LTXPipeline; import torch; LTXPipeline.from_single_file('https://huggingface.co/Lightricks/LTX-Video/resolve/main/ltxv-2b-0.9.6-distilled-04-25.safetensors', torch_dtype=torch.float16); print('weights cached')"
```

Do NOT download any other checkpoint. Weights are gitignored
(`*.safetensors`, `models/`) — they will never be committed.

## 3. Generic smoke test (Step 5 of the task — no Deathbound shot)

```powershell
$env:DEATHBOUND_ROOT="D:\Deathbound"
D:\Deathbound\tools\ltx-env\Scripts\python -c "
from automation.video.ltx_provider import LTXLocalProvider
from automation.video.provider_adapter import GenerationRequest
p = LTXLocalProvider()
r = p.generate(GenerationRequest(
    shot_id='LTX-SMOKE-001', prompt='slow cinematic push-in on a luxury city bedroom at night, moody motivated lighting',
    duration_seconds=2.0, fps=24, resolution='512x320'))
print(r.output_artifact)
"
```

Success = a real `production/generation/artifacts/LTX-SMOKE-001/clip.mp4`,
ffprobe-validated (the provider does this internally before returning), with
`simulated: false`, duration ≈ 2 s, fps = 24, plus final-frame extraction via
the existing media pipeline. Then verify with:

```powershell
ffprobe -v error -show_entries stream=width,height,r_frame_rate,duration -of default production\generation\artifacts\LTX-SMOKE-001\clip.mp4
```

If it OOMs: the provider already clamps to 512×320×49 frames; drop to
`resolution='480x288'` and `duration_seconds=1.5`. If it still OOMs, STOP and
report — do not retry blindly (4 GB is the hard wall; see Step 10 conditions).

## 4. Riven references (Step 6 gate)

Before any Riven clip, real reference images must exist:

```
assets/characters/riven/references/
  riven_face_01.png        # REQUIRED — chest-up, face unobstructed, neutral expression
  riven_fullbody_01.png    # REQUIRED — full body, wardrobe visible head to boots
  (optional: riven_3q_*.png, riven_profile_*.png, riven_expression_*.png)
```

Catalog + verify:

```powershell
D:\Deathbound\tools\ltx-env\Scripts\python -c "from automation.video.reference_catalog import catalog_references; c=catalog_references(); print(c['reference_count'], 'references')"
```

If none exist → the pipeline correctly reports `REAL_RIVEN_REFERENCE_REQUIRED`
and stops. Do NOT generate placeholder "Riven" images and do NOT treat them as
canon references.

## 5. First Riven clip (Step 7) — only after references exist

```powershell
D:\Deathbound\tools\ltx-env\Scripts\python -c "
from automation.video.ltx_provider import LTXLocalProvider
from automation.video.provider_adapter import GenerationRequest
p = LTXLocalProvider()
r = p.generate(GenerationRequest(
    shot_id='RIVEN-TEST-001',
    prompt='Riven standing in a dim luxury bedroom at night, subtle idle movement, slow push-in',
    duration_seconds=2.0, fps=24, resolution='512x320',
    reference_images=[{'path': 'assets/characters/riven/references/riven_face_01.png'}],
    negative_prompt=None, seed=1234))
print(r.output_artifact)
"
```

The provider appends the canonical Riven identity lock and negative canon
automatically when the prompt mentions Riven (see `RIVEN_POSITIVE_BASE` /
`RIVEN_NEGATIVE_BASE` — sourced from the existing canon configs, never
modified).

## 6. Three-shot chain (Step 8) — uses the existing executor, no bypass

```powershell
D:\Deathbound\tools\ltx-env\Scripts\python -m automation.video.run --provider ltx-local --shots S01-SHOT-001 S01-SHOT-002 S01-SHOT-003
```

The executor conditions S01-SHOT-002 on the real extracted final frame of
SHOT-001 (`final_frame.png`, ffprobe-validated, SHA256-hashed) and SHOT-003
on SHOT-002's — the architecture is unchanged. Manifests record real media
(`simulated: false`) with generation parameters, seed, timings, and VRAM.

Keep it conservative: 512×320, ≤ 2 s per sub-clip. Long shots (e.g.
S01-SHOT-001's 14.5 s audio slot) are generated as chained sub-clips and
stitched by FFmpeg in a later task; for this first pass set conservative
expectations and let the executor report per-shot results.

## 7. Acceptance before production use

```powershell
D:\Deathbound\tools\ltx-env\Scripts\python -m automation.video.tests.test_provider_acceptance --provider ltx-local
```

All tests must pass (the 4 previously GPU-skipped media tests will also run
here since FFmpeg exists on the target machine).

## 8. Stop conditions (do not retry blindly)

- OOM twice at 480×288×41 frames → 4 GB wall confirmed; report VRAM/RAM and stop.
- Text-encoder offload exceeding ~14 GB system RAM → stop (16 GB machine).
- Any `requires_payment`/credential requirement appearing upstream → policy violation, stop.
- Corrupt/unverifiable output → stop, do not fake success.
