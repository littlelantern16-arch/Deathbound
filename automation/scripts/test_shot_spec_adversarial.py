import json
import sys
import tempfile
from copy import deepcopy
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

ENGINE_PATH = (
    ROOT
    / "automation"
    / "scripts"
    / "shot_spec_engine.py"
)

BIBLE_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "story_bible.json"
)

ARCHITECTURE_PATH = (
    ROOT
    / "config"
    / "ANIMATION_ARCHITECTURE.json"
)


def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8-sig"
    ) as f:
        return json.load(f)


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def load_engine():

    namespace = {}

    source = ENGINE_PATH.read_text(
        encoding="utf-8-sig"
    )

    # The engine has no external dependencies
    # beyond Python standard library.
    exec(
        compile(
            source,
            str(ENGINE_PATH),
            "exec"
        ),
        namespace
    )

    return namespace


def build_qa_bible():

    bible = load_json(
        BIBLE_PATH
    )

    bible = deepcopy(
        bible
    )

    # ------------------------------------------------------------
    # TEMPORARY QA-ONLY SCENE
    # ------------------------------------------------------------

    bible["scene_registry"] = {
        "scene-qa-001": {
            "id": "scene-qa-001",
            "name": "QA Bedroom Scene",
            "status": "qa_only",
            "characters": ["riven"],
            "location": "loc-daniel-bedroom",
            "props": ["prop-reapers-ledger"]
        }
    }

    # ------------------------------------------------------------
    # TEMPORARY QA-ONLY CAUSAL EVENT
    # ------------------------------------------------------------

    bible["causal_events"] = [
        {
            "event_id": "event-qa-001",
            "scene_id": "scene-qa-001",
            "shot_id": "shot-qa-001",
            "actor": "riven",
            "action": "observes",
            "cause": "QA structural test",
            "state_change": {},
            "consequences": [],
            "timestamp": "QA"
        }
    ]

    return bible


def build_valid_shot(engine, bible):

    return engine["create_shot"](
        shot_id="shot-qa-001",
        scene_id="scene-qa-001",
        sequence_id="seq-qa-001",
        duration_seconds=5.0,
        animation_tier="standard",
        purpose="QA structural validation",
        characters=["riven"],
        location="loc-daniel-bedroom",
        props=["prop-reapers-ledger"],
        camera={
            "shot_type": "medium",
            "movement": "static"
        },
        character_performance={
            "body": ["idle"],
            "face": ["neutral"],
            "speech": {
                "required_when_dialogue": True,
                "lip_sync_required": True
            }
        },
        environment_motion="subtle",
        lighting={
            "continuity_required": True,
            "changes_require_cause": True
        },
        effects={
            "effects": [],
            "effects_require_narrative_justification": True
        },
        audio={
            "dialogue": [],
            "sfx": [],
            "music": None
        },
        state_before={
            "riven": {
                "emotional_state": "neutral"
            }
        },
        state_after={
            "riven": {
                "emotional_state": "neutral"
            }
        },
        causal_event_ids=["event-qa-001"]
    )


def expect_rejection(
    label,
    corrupted_shot,
    engine,
    bible,
    architecture
):

    errors = engine["validate_shot"](
        corrupted_shot,
        bible,
        architecture
    )

    if errors:
        print(
            f"PASS  {label}"
        )
        return True

    print(
        f"FAIL  {label} "
        "(corrupted shot was accepted)"
    )

    return False


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — SHOT SPECIFICATION"
    )
    print(
        "ADVERSARIAL QA"
    )
    print("=" * 60)

    engine = load_engine()

    bible = build_qa_bible()

    architecture = load_json(
        ARCHITECTURE_PATH
    )

    valid_shot = build_valid_shot(
        engine,
        bible
    )

    # ------------------------------------------------------------
    # BASELINE
    # ------------------------------------------------------------

    baseline_errors = engine[
        "validate_shot"
    ](
        valid_shot,
        bible,
        architecture
    )

    if baseline_errors:

        print(
            "FAIL  Baseline valid shot was rejected:"
        )

        for error in baseline_errors:
            print(
                f"       {error}"
            )

        sys.exit(1)

    print(
        "PASS  Baseline valid shot accepted."
    )

    tests = []

    # ------------------------------------------------------------
    # INVALID 001 — UNKNOWN CHARACTER
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["characters"] = [
        "character-does-not-exist"
    ]

    tests.append(
        (
            "INVALID-001 — Unknown character",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 002 — UNKNOWN LOCATION
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["location"] = (
        "location-does-not-exist"
    )

    tests.append(
        (
            "INVALID-002 — Unknown location",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 003 — UNKNOWN PROP
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["props"] = [
        "prop-does-not-exist"
    ]

    tests.append(
        (
            "INVALID-003 — Unknown prop",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 004 — UNKNOWN SCENE
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["scene_id"] = (
        "scene-does-not-exist"
    )

    tests.append(
        (
            "INVALID-004 — Unknown scene",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 005 — UNKNOWN CAUSAL EVENT
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["causal_event_ids"] = [
        "event-does-not-exist"
    ]

    tests.append(
        (
            "INVALID-005 — Unknown causal event",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 006 — INVALID ANIMATION TIER
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["animation_tier"] = (
        "impossible-tier"
    )

    tests.append(
        (
            "INVALID-006 — Invalid animation tier",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 007 — INVALID CAMERA TYPE
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["camera"]["shot_type"] = (
        "impossible-shot"
    )

    tests.append(
        (
            "INVALID-007 — Invalid camera shot type",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 008 — INVALID CAMERA MOVEMENT
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["camera"]["movement"] = (
        "teleport-camera"
    )

    tests.append(
        (
            "INVALID-008 — Invalid camera movement",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 009 — INVALID ENVIRONMENT MOTION
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["environment_motion"] = (
        "impossible-motion"
    )

    tests.append(
        (
            "INVALID-009 — Invalid environment motion",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 010 — BROKEN CHARACTER CONTINUITY
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["continuity"][
        "character_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-010 — Character continuity unlocked",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 011 — BROKEN ENVIRONMENT CONTINUITY
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["continuity"][
        "environment_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-011 — Environment continuity unlocked",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 012 — BROKEN PROP CONTINUITY
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["continuity"][
        "prop_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-012 — Prop continuity unlocked",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 013 — ZERO DURATION
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["duration_seconds"] = 0

    tests.append(
        (
            "INVALID-013 — Zero duration",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 014 — NEGATIVE DURATION
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["duration_seconds"] = -4

    tests.append(
        (
            "INVALID-014 — Negative duration",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 015 — MISSING SPEECH CONTRACT
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    del shot[
        "character_performance"
    ]["speech"]

    tests.append(
        (
            "INVALID-015 — Missing speech contract",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 016 — LIP SYNC DISABLED
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot[
        "character_performance"
    ]["speech"][
        "lip_sync_required"
    ] = False

    tests.append(
        (
            "INVALID-016 — Lip-sync contract disabled",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 017 — MISSING CAUSAL EVENT LIST
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot.pop(
        "causal_event_ids"
    )

    tests.append(
        (
            "INVALID-017 — Missing causal event field",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 018 — MISSING REQUIRED FIELD
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot.pop(
        "lighting"
    )

    tests.append(
        (
            "INVALID-018 — Missing lighting field",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 019 — INVALID SHOT ID
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["shot_id"] = ""

    tests.append(
        (
            "INVALID-019 — Missing shot ID",
            shot
        )
    )

    # ------------------------------------------------------------
    # INVALID 020 — MULTIPLE CONTRADICTIONS
    # ------------------------------------------------------------

    shot = deepcopy(valid_shot)

    shot["characters"] = [
        "fake-character"
    ]

    shot["location"] = (
        "fake-location"
    )

    shot["animation_tier"] = (
        "fake-tier"
    )

    shot["duration_seconds"] = -1

    shot["camera"]["movement"] = (
        "fake-movement"
    )

    shot["causal_event_ids"] = [
        "fake-event"
    ]

    shot["continuity"][
        "character_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-020 — Multi-contradiction shot",
            shot
        )
    )

    # ------------------------------------------------------------
    # EXECUTE
    # ------------------------------------------------------------

    passed = 0
    failed = 0

    print("-" * 60)

    for label, corrupted_shot in tests:

        if expect_rejection(
            label,
            corrupted_shot,
            engine,
            bible,
            architecture
        ):
            passed += 1
        else:
            failed += 1

    print("-" * 60)

    print(
        f"TESTS: {len(tests)}"
    )

    print(
        f"PASS:  {passed}"
    )

    print(
        f"FAIL:  {failed}"
    )

    print("-" * 60)

    if (
        failed == 0
        and passed == len(tests)
    ):

        print(
            "OVERALL: PASS"
        )

        print()
        print(
            "All adversarial shot contradictions "
            "were rejected."
        )

        sys.exit(0)

    print(
        "OVERALL: FAIL"
    )

    sys.exit(1)


if __name__ == "__main__":
    main()
