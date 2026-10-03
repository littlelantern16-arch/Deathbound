# Deathbound — Visual State + Temporal Continuity Engine

Provider-neutral AI video pipeline built **on top of** the existing Deathbound
story/shot architecture (58-shot EP001 schema, story bible, canon rules). It
adds the missing temporal-continuity layer without redesigning anything.

## Architecture

```
VisualStateManager        per-shot provider-neutral visual state derived from
  (visual_state.py)      EP001_production_shots.json + story_bible + riven.json
                           |
CharacterReferenceBank    persistent canon-preserving references per character
  (reference_bank.py)    (identity/wardrobe locked; simulated refs for dry-run)
                           |
TemporalContinuityManager shot chaining: extract final frame -> register ->
  (continuity.py)        condition next shot (production/generation/state/)
                           |
VideoProvider (adapter)   provider-neutral contract: t2v, i2v, reference
  (provider_adapter.py)  conditioning, previous-frame conditioning, polling,
                           |      artifact retrieval. Registry — no hard-coding.
                           |    First implementation: DryRunProvider (no keys,
                           |    no GPU, no network; artifacts marked simulated).
                           v
EpisodeExecutor           load EP001 -> resolve order -> build state ->
  (executor.py)           resolve refs -> generate -> QA validate ->
                          extract final frame -> register -> next shot ->
                          write manifests -> resume support -> run report
                           |
GenerationManifestManager one manifest per shot: state, previous shot,
  (manifest.py)           previous final frame, references, prompt, provider,
                           |    model, params, artifacts, validation, retries,
                           |    timestamps, errors (all machine-readable)
                           v
QA + bounded retry        8 checks incl. broken-chain, transition, identity;
  (qa.py)                 RetryPolicy with exponential backoff
```

Chaining principle (OpenX Flow), applied to the existing shot chain:

```
S01-SHOT-001 -> clip -> final frame artifact -> registered
    -> conditions S01-SHOT-002 -> clip -> final frame artifact -> registered
        -> conditions S01-SHOT-003 -> ...
```

Shots are never regenerated independently; a connected shot without its
previous final frame is a hard QA failure (`broken continuity chain`).

## Location of outputs

```
production/generation/
  manifests/<shot_id>.manifest.json     one per shot
  artifacts/<shot_id>/clip.json         simulated clip stubs (dry-run)
  state/continuity_chain.json           registered final frames per shot
  state/run_state.json                  resume bookkeeping
  reports/<run_id>.report.json          machine-readable run report
```

## Commands

```bash
# 3-shot vertical slice dry-run (the success condition):
python3 -m automation.video.run --shots S01-SHOT-001 S01-SHOT-002 S01-SHOT-003

# Full 58-shot episode dry-run:
python3 -m automation.video.run

# Resume after failure (completed shots are skipped):
python3 -m automation.video.run --resume

# Full test suite (44 tests):
python3 -m automation.video.tests.test_video_pipeline

# EP001 V1 assembly (audio + final mux) regression tests:
python3 -m automation.video.tests.test_build_ep001_v1
```

Exit code 0 + `OVERALL: PASS` means ordering, state propagation, identity
continuity, final-frame propagation, manifests, and link integrity all passed.

## EP001 V1 final assembly (audio + mux)

```bash
# Rebuild narration from the ORIGINAL line WAVs, mux onto the existing visual
# master, then validate projects/EP001/08_output/EP001_V1.mp4:
python3 -m automation.video.build_ep001_v1

# Re-validate an already-assembled file only:
python3 -m automation.video.build_ep001_v1 --validate-only
```

Reads `projects/EP001/04_audio/EP001_AUDIO_TIMELINE.json`, writes
`08_output/_v1_work/narration.wav` as a real **PCM** WAV (each line placed at
its exact `start_seconds`, then `loudnorm`), and muxes it onto
`EP001_visual_v1.mp4` with `-c:v copy` + silence padding. `-shortest` is never
used: the full 357.331 s visual timeline is preserved and only the audio is
extended. Post-assembly validation requires h264, 1920x1080, the full duration,
a valid AAC track covering the timeline, and a zero-error decode pass.
Exit 0 = assembled and validated; exit 1 = failure (never a fake success).

## Dry-run honesty

Every simulated artifact carries `"simulated": true`, manifests carry
`"dry_run": true`, and stub files say `NOT real generated media`. A real
provider must replace these; no placeholder can ever pass as real output.

## Adding a real provider (later)

1. Create a `VideoProvider` subclass implementing `generate` (and optionally
   `poll`, `retrieve_artifact`).
2. Declare `capabilities` (t2v / i2v / reference / previous-frame /
   first-last-frame / polling).
3. Register it with `@register_provider` in `provider_adapter.py`.
4. Run `python3 -m automation.video.run --provider <your-provider-id>`.

No pipeline code changes required; the executor, QA, chaining and manifests
are provider-agnostic. API keys belong in environment config, never in code.
