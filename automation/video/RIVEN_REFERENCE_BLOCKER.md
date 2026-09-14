# BLOCKER: REAL_RIVEN_REFERENCE_REQUIRED

Status: **BLOCKING** for Steps 7–8 (first Riven clip, three-shot chain).
Date: 2026-09-14. Repo state: clean, `main` at `edbf126` (pre-commit of Task #4 code).

## Why blocked

`assets/characters/riven/references/` contains **zero real image files**
(catalog: `reference_count: 0`, verified via
`automation.video.reference_catalog.catalog_references()`).

Per task rules and canon policy, no placeholder or AI-generated "Riven"
images may be invented and passed off as references
(`no_fake_references_generated: true` in the catalog policy). The LTX
provider will therefore not attempt a Riven-conditioned generation.

## What must be supplied (exact requirement)

All images: real photographs or previously approved Riven renders that the
rights-holder supplies; PNG/JPG/WebP; ≥ 512 px on the short side.

| Priority | File | Spec |
|---|---|---|
| REQUIRED | `riven_face_01.png` | Chest-up or head-and-shoulders, face unobstructed, eyes visible, neutral/calm expression, even lighting, simple background. Matches DEATHBOUND_VISUAL_STYLE_DNA `reference_policy`. |
| REQUIRED | `riven_fullbody_01.png` | Full body head-to-boots, wardrobe fully visible: charcoal-black hooded coat, dark fitted shirt, black trousers, practical black boots, subtle silver details. |
| Optional | `riven_3q_01.png` | Three-quarter view. |
| Optional | `riven_profile_01.png` | Clean profile. |
| Optional | `riven_wardrobe_01.png` | Wardrobe/costume detail (coat + silver details). |
| Optional | `riven_expression_conflicted.png` | Expression reference for hero shots. |

Optional per-file sidecar metadata `<name>.json`:
`{"type": "FACE", "pose_view": "...", "wardrobe": "...", "expression": "...", "source": "...", "canonical_status": "approved"}`.

After adding files:

```powershell
python -c "from automation.video.reference_catalog import catalog_references; c=catalog_references(); print(c['reference_count'], 'references cataloged')"
```

Then run the first Riven I2V test per `automation/video/LTX_SETUP.md` §5.

## Upstream blocker (this sandbox)

The generic smoke test (Step 5) could not run in the Freebuff workspace
sandbox: it has **no NVIDIA GPU, no CUDA runtime, 4.0 GB total disk, Python
3.10, and no ffmpeg** — it is not the target RTX 3050 machine. Model weights
(≈13–15 GB) cannot even fit on its disk. Everything GPU-dependent is
implemented, tested (machine-independent parts), and documented in
`automation/video/LTX_SETUP.md` for execution on the target Windows machine.
No fake generation was performed or claimed.
