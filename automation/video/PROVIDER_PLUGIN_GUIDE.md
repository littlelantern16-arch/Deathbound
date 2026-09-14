# Provider Plug-In Guide (₹0 backend)

The continuity engine is finished. Adding the real video backend later should
require **one new adapter file** — no changes to the executor, state manager,
reference bank, continuity manager, manifests, QA, or CLI.

## The one rule

```
production_cost_policy = "ZERO_RUPEE_ONLY"
```

A provider whose `capabilities` declare `requires_payment: true` is refused
for production execution. A provider that does not declare cost status is
also refused (no guessing, no silent paid fallback). This gate runs before
any generation and again in preflight.

## What a new provider must implement

Create one file, e.g. `automation/video/providers/<name>.py`:

```python
from automation.video.provider_adapter import (
    GenerationRequest, GenerationResult, VideoProvider, register_provider,
)

@register_provider
class MyFreeProvider(VideoProvider):
    provider_id = "my-free-provider"

    capabilities = {
        # Which generation modes the backend supports:
        "text_to_video": True,
        "image_to_video": True,
        "reference_images": True,          # reference-image conditioning
        "first_frame_conditioning": True,  # image/previous-frame as first frame
        "last_frame_conditioning": False,  # if backend supports end frames
        "video_extension": False,
        # Generation controls:
        "seed_control": True,
        "negative_prompt": True,
        "width_height_control": True,
        "fps_control": True,
        "duration_control": True,
        # Where it runs / what it costs (policy-critical):
        "local_execution": True,           # or remote_execution: True
        "remote_execution": False,
        "requires_credentials": False,     # local model => none
        "requires_payment": False,         # ZERO_RUPEE_ONLY gate reads this
    }

    def generate(self, request: GenerationRequest) -> GenerationResult:
        # request carries: shot_id, prompt, negative_prompt, duration_seconds,
        # fps, resolution, reference_images, previous_final_frame,
        # first_frame, last_frame, seed
        ...
        # MUST return a real, local, non-simulated artifact:
        return GenerationResult(
            shot_id=request.shot_id,
            output_artifact={
                "artifact_id": f"{request.shot_id}-clip",
                "kind": "video_clip",
                "path": f"artifacts/{request.shot_id}/clip.mp4",  # RELATIVE to production/generation/
                "simulated": False,            # real media
                "media_type": "video/mp4",
                "sha256": "<hash of the file>",
            },
            poll_count=0,                      # or your polling count
            generation_parameters={...},       # exactly what was sent
        )
```

### Contract rules (checked by the acceptance suite)

1. **Artifact path** — relative to `production/generation/`, must point at a
   real video file (`.mp4`/`.mov`/`.webm`/`.mkv`), written **atomically** or
   written elsewhere and renamed.
2. **`simulated: false`** — only DryRun providers may set `simulated: true`.
   Lying here produces manifests that fail the QA gate.
3. **Executor automation** — after `generate`, the executor automatically:
   validates the MP4 with ffprobe (duration ≈ shot duration, fps = 24,
   resolution = 1280×720), extracts the **real last frame** to
   `artifacts/<shot>/final_frame.png` (atomic write), hashes it (SHA256),
   registers it with `TemporalContinuityManager`, and conditions the next
   connected shot on it. You write none of this.
4. **Polling providers** — implement `poll(job_id)` (and optionally
   `retrieve_artifact`); set `"polling": True`. The executor's bounded retry
   wraps `generate`; transient `ProviderError`s are retried with backoff.
5. **Conditioning inputs** — the executor passes
   `request.previous_final_frame` (the previous shot's registered frame) and
   `request.reference_images` (from the reference bank). Use them if the
   backend supports them; declare the corresponding capabilities honestly.

## Registering and running

```bash
# In automation/video/providers/<name>.py the @register_provider decorator
# makes it visible; ensure the module is imported once at startup, e.g.:
#   python -c "import automation.video.providers.<name>"

# Preflight (no generation):
python3 -m automation.video.run preflight --provider my-free-provider --shots S01-SHOT-001 S01-SHOT-002 S01-SHOT-003

# Acceptance suite (must pass before production use):
python3 -m automation.video.tests.test_provider_acceptance --provider my-free-provider

# Execute the 3-shot vertical slice:
python3 -m automation.video.run --provider my-free-provider --shots S01-SHOT-001 S01-SHOT-002 S01-SHOT-003

# Full 58-shot episode:
python3 -m automation.video.run --provider my-free-provider
```

## Reference images for identity lock

Real Riven reference images go in:

```
assets/characters/riven/references/
  riven_face_01.png              # FACE
  riven_fullbody_01.png          # FULL_BODY
  riven_3q_left.png              # THREE_QUARTER / PROFILE / WARDROBE / EXPRESSION
```

Naming (or a sidecar `<name>.json` with `type/pose_view/wardrobe/expression/
source/canonical_status`) determines classification. Then:

```bash
python3 -c "from automation.video.reference_catalog import catalog_references; print(catalog_references()['reference_count'], 'references cataloged')"
```

The catalog stores `reference_id, path, sha256, type, pose_view, wardrobe,
expression, source, canonical_status` in
`assets/characters/riven/references/references_catalog.json`. Canon files are
never modified. No placeholder images are ever generated.

## FFmpeg

Discovery order (never a single hard-coded path):
1. `DEATHBOUND_FFMPEG` / `DEATHBOUND_FFPROBE` env vars
2. `PATH`
3. the existing `config/paths.json` entry (Windows workstation)

If FFmpeg is absent, dry-run still works; real-media validation/extraction
refuse loudly instead of producing unverified artifacts.

## What must NOT change

- `config/DEATHBOUND_RULES.json`, `DEATHBOUND_VISUAL_STYLE_DNA.json`,
  canon files under `projects/EP001/`
- the 58-shot production package and its schema
- the `VideoProvider` interface and the ZERO_RUPEE_ONLY gate
- the continuity chain semantics (N → final frame → N+1)
