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

**TIERED MEMORY ARCHITECTURE (4 GB VRAM / 16 GB RAM — read this first):**
the provider NEVER lets a text encoder enter the pipeline. Phase A loads the
T5-XXL encoder ALONE on CPU, encodes the prompts into `prompt_embeds`, frees
the encoder; Phase B then builds the pipeline from the single-file checkpoint
with `text_encoder=None` and streams the transformer to the GPU with
block-level group offload while the VAE sits resident on CUDA, excluded from
group offloading (see the VAE device-safety note below). Full derivation in
the `ltx_provider.py` module docstring.

> **VAE DEVICE-SAFETY (the "CUDABFloat16Type vs CPUBFloat16Type" decode fix,
> verified against diffusers 0.40.0 source):** both LTX pipelines call
> `vae.decode(...)` directly, but diffusers' pipeline-level group offload
> only hooks components through `nn.Module.__call__` — so a group-offloaded
> VAE never onloads its weights and decoding dies with
> `Input type (CUDABFloat16Type) and weight type (CPUBFloat16Type)`.
> The provider therefore passes `exclude_modules=["vae"]` to
> `enable_group_offload`: the hook-free VAE is placed on CUDA (bf16, ~2.3 GB,
> tiled decode) while the transformer keeps streaming block-by-block.
> Manually calling `pipeline.vae.to("cuda")` afterwards is a logged NO-OP
> while the VAE still carries its group hook — do not "patch" it that way.
> On diffusers without `exclude_modules` support the provider refuses the
> group path entirely and uses `enable_model_cpu_offload`, whose accelerate
> hook fires correctly on `decode()` (`@apply_forward_hook`).
> `DEATHBOUND_VAE_OFFLOAD=0` restores upstream group-offload-everything
> behavior (not recommended for LTX).

| Component | Size | Source | Notes |
|---|---|---|---|
| `ltxv-2b-0.9.6-distilled-04-25.safetensors` | ~5.9 GB | `Lightricks/LTX-Video` (blob/main link) | the 2B DiT + VAE configs (single file) — **already downloaded** |
| T5-XXL encoder, bf16, encoder-only | ~9.52 GB | `city96/t5-v1_1-xxl-encoder-bf16` | pulled by Phase A (`ensure_text_encoder`), never by from_single_file |

> **DO NOT download `google/t5-v1_1-xxl`** — its `pytorch_model.bin` is
> 44,541,587,809 bytes (≈ 44.54 GB) and will never fit this workflow.
> Also never pull `Lightricks/LTX-Video`'s own `text_encoder/` folder
> (fp32 sharded, 19.05 GB). The city96 bf16 encoder-only repo is the
> verified ₹0-compatible source: config matches LTX's `text_encoder/config.json`
> exactly (d_model 4096, 24 layers, gated-gelu, untied embeddings).

**Expected total download: ~15.5 GB** (checkpoint 6,340,744,028 bytes ≈ 5.9 GB
+ city96 T5 `model.safetensors` 9,524,648,592 bytes ≈ 9.52 GB).
Destination: the HF cache (`D:\Deathbound\cache\huggingface` when HF_HOME is
set by `scripts/setup_ltx_windows.ps1`, else `%USERPROFILE%\.cache\huggingface`).
Free disk needed: **≥ 20 GB**. Pre-fetch both pieces once (Phase B requires
the `/blob/main/` link form — a `/resolve/main/` link builds a doubled URL
and 404s in diffusers 0.40.0):

```powershell
# 1. The 2B checkpoint (already downloaded on this machine — verify only).
D:\Deathbound\tools\ltx-env\Scripts\python -c "from diffusers import LTXPipeline; import torch; LTXPipeline.from_single_file('https://huggingface.co/Lightricks/LTX-Video/blob/main/ltxv-2b-0.9.6-distilled-04-25.safetensors', torch_dtype=torch.float16, text_encoder=None, tokenizer=None); print('checkpoint cached')"

# 2. The city96 T5 encoder (Phase A source — one-time ~9.5 GB).
D:\Deathbound\tools\ltx-env\Scripts\python -c "from transformers import T5EncoderModel, AutoTokenizer; import torch; src='city96/t5-v1_1-xxl-encoder-bf16'; AutoTokenizer.from_pretrained(src); T5EncoderModel.from_pretrained(src, torch_dtype=torch.bfloat16); print('T5 encoder cached')"
```

Optional (recommended after the first download): pin both weights for every
later run via explicit local paths, which bypasses Hub resolution entirely
(the provider validates declared paths and never silently re-downloads):

```powershell
copy-item (gci D:\Deathbound\cache\huggingface -Recurse -Filter ltxv-2b-0.9.6-distilled-04-25.safetensors | select -First 1).FullName D:\Deathbound\cache\ltxv-2b-0.9.6-distilled-04-25.safetensors
setx DEATHBOUND_LTX_LOCAL_CHECKPOINT "D:\Deathbound\cache\ltxv-2b-0.9.6-distilled-04-25.safetensors"

setx DEATHBOUND_T5_LOCAL_PATH "D:\Deathbound\cache\t5-v1_1-xxl-encoder-bf16"
# (create that folder by copying config.json + model.safetensors out of the
#  city96 snapshot inside the HF cache; then Phase A never touches the net)
```

Do NOT download any other checkpoint or text encoder. Weights are gitignored
(`*.safetensors`, `models/`) — they will never be committed.

## 3. Generic smoke test (Step 5 of the task — no Deathbound shot)

The FIRST real GPU run is deliberately tiny: 512×320 native, 9 frames
(8n+1 constraint, 0.4 s at 24 fps), the distilled 8-step schedule, one shot,
real CUDA, real MP4. Escalate only after each run passes:
`--duration 0.4` (9 frames) → `--duration 0.7` (17 frames) → `--duration 2.0`
(49 frames) → then, and only then, the 3-shot chain in section 6.

```powershell
$env:DEATHBOUND_ROOT="D:\Deathbound"
D:\Deathbound\tools\ltx-env\Scripts\python -c "
from automation.video.ltx_provider import LTXLocalProvider
from automation.video.provider_adapter import GenerationRequest
p = LTXLocalProvider()
r = p.generate(GenerationRequest(
    shot_id='LTX-SMOKE-001', prompt='slow cinematic push-in on a luxury city bedroom at night, moody motivated lighting',
    duration_seconds=0.4, fps=24, resolution='512x320'))
print(r.output_artifact)
"
```

Success = a real `production/generation/artifacts/LTX-SMOKE-001/clip.mp4`,
ffprobe-validated (the provider does this internally before returning), with
`simulated: false`, 9 frames / duration ≈ 0.4 s, fps = 24, plus final-frame
extraction via the existing media pipeline. Then verify with:

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
