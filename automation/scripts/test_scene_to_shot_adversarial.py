import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

DIRECTOR_PATH = (
    ROOT
    / "automation"
    / "scripts"
    / "scene_to_shot_director.py"
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

SHOT_ENGINE_PATH = (
    ROOT
    / "automation"
    / "scripts"
    / "shot_spec_engine.py"
)


def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8-sig"
    ) as f:
        return json.load(f)


def load_module_namespace(path):

    namespace = {}

    source = Path(path).read_text(
        encoding="utf-8-sig"
    )

    exec(
        compile(
            source,
            str(path),
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

    bible["scene_registry"] = {
        "scene-qa-director": {
            "id": "scene-qa-director",
            "name": "Director QA Scene",
            "status": "qa_only",
            "characters": [
                "riven"
            ],
            "location": "loc-daniel-bedroom",
            "props": [
                "prop-reapers-ledger"
            ]
        }
    }

    bible["causal_events"] = [
        {
            "event_id": "event-qa-director",
            "scene_id": "scene-qa-director",
            "shot_id": None,
            "actor": "riven",
            "action": "observes",
            "cause": "QA director test",
            "state_change": {},
            "consequences": [],
            "timestamp": "QA"
        }
    ]

    return bible


def create_valid_plan(director):

    scene = director[
        "create_scene_brief"
    ](
        scene_id="scene-qa-director",
        narrative_purpose=(
            "QA sequence with dialogue, "
            "supernatural escalation and "
            "emotional resolution."
        ),
        emotional_start="neutral",
        emotional_end="conflicted",
        characters=["riven"],
        location="loc-daniel-bedroom",
        props=["prop-reapers-ledger"],
        dialogue_present=True,
        action_present=False,
        supernatural_present=True,
        causal_event_ids=[
            "event-qa-director"
        ]
    )

    shot_engine = load_module_namespace(
        SHOT_ENGINE_PATH
    )

    architecture = load_json(
        ARCHITECTURE_PATH
    )

    plan = director[
        "generate_director_plan"
    ](
        scene,
        qa_bible,
        architecture,
        shot_engine
    )

    return plan, shot_engine, architecture


def validate(
    director,
    plan,
    shot_engine,
    architecture
):

    return director[
        "validate_sequence"
    ](
        plan,
        qa_bible,
        architecture,
        shot_engine
    )


def expect_rejection(
    label,
    corrupted,
    director,
    shot_engine,
    architecture
):

    errors = validate(
        director,
        corrupted,
        shot_engine,
        architecture
    )

    if errors:

        print(
            f"PASS  {label}"
        )

        return True

    print(
        f"FAIL  {label} "
        "(corrupted sequence was accepted)"
    )

    return False


def main():

    global qa_bible

    print("=" * 60)
    print(
        "DEATHBOUND — PHASE 5C"
    )
    print(
        "SCENE-TO-SHOT DIRECTOR"
    )
    print(
        "ADVERSARIAL QA"
    )
    print("=" * 60)

    qa_bible = build_qa_bible()

    director = load_module_namespace(
        DIRECTOR_PATH
    )

    plan, shot_engine, architecture = (
        create_valid_plan(
            director
        )
    )

    baseline_errors = validate(
        director,
        plan,
        shot_engine,
        architecture
    )

    if baseline_errors:

        print(
            "FAIL  Baseline director sequence "
            "was rejected:"
        )

        for error in baseline_errors:

            print(
                f"       {error}"
            )

        sys.exit(1)

    print(
        "PASS  Baseline valid sequence accepted."
    )

    tests = []

    # ------------------------------------------------------------
    # INVALID 001 — SCENE CHANGES MID-SEQUENCE
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][2][
        "scene_id"
    ] = "scene-fake"

    tests.append(
        (
            "INVALID-001 — Scene changes mid-sequence",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 002 — LOCATION CHANGES
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][3][
        "location"
    ] = "loc-fake"

    tests.append(
        (
            "INVALID-002 — Location changes mid-sequence",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 003 — STATE INHERITANCE BROKEN
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][2][
        "continuity"
    ][
        "inherits_previous_shot_state"
    ] = False

    tests.append(
        (
            "INVALID-003 — State inheritance broken",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 004 — REMOVE ESTABLISHING SHOT
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"] = [
        shot
        for shot in corrupted["shots"]
        if shot["purpose"]
        != "establishing"
    ]

    tests.append(
        (
            "INVALID-004 — Missing establishing coverage",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 005 — REMOVE DIALOGUE COVERAGE
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"] = [
        shot
        for shot in corrupted["shots"]
        if shot["purpose"]
        != "dialogue"
    ]

    tests.append(
        (
            "INVALID-005 — Missing dialogue coverage",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 006 — REMOVE EMOTIONAL RESOLUTION
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"] = [
        shot
        for shot in corrupted["shots"]
        if shot["purpose"]
        != "emotional_resolution"
    ]

    tests.append(
        (
            "INVALID-006 — Missing emotional resolution",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 007 — REMOVE SUPERNATURAL PAYOFF
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"] = [
        shot
        for shot in corrupted["shots"]
        if shot["purpose"]
        != "supernatural_payoff"
    ]

    tests.append(
        (
            "INVALID-007 — Missing supernatural payoff",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 008 — BREAK CAUSAL REFERENCES
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][1][
        "causal_event_ids"
    ] = []

    tests.append(
        (
            "INVALID-008 — Missing causal reference",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 009 — EXCESSIVE REPETITION
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    for shot in corrupted["shots"]:

        shot["animation_tier"] = "standard"

        shot["camera"]["shot_type"] = "medium"

        shot["camera"]["movement"] = "static"

    tests.append(
        (
            "INVALID-009 — Excessive shot repetition",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 010 — ZERO SHOT SCENE
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"] = []

    tests.append(
        (
            "INVALID-010 — Zero-shot scene",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 011 — UNKNOWN CHARACTER
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][1][
        "characters"
    ] = [
        "unknown-character"
    ]

    tests.append(
        (
            "INVALID-011 — Unknown character in sequence",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 012 — UNKNOWN CAUSAL EVENT
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][2][
        "causal_event_ids"
    ] = [
        "unknown-event"
    ]

    tests.append(
        (
            "INVALID-012 — Unknown causal event",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 013 — BROKEN PROP CONTINUITY
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][3][
        "props"
    ] = []

    tests.append(
        (
            "INVALID-013 — Prop continuity broken",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 014 — EMOTIONAL ARC CLAIMS CHANGE
    # BUT NO RESOLUTION SHOT
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["director_strategy"][
        "emotional_arc"
    ] = {
        "start": "neutral",
        "end": "fear"
    }

    corrupted["shots"] = [
        shot
        for shot in corrupted["shots"]
        if shot["purpose"]
        != "emotional_resolution"
    ]

    tests.append(
        (
            "INVALID-014 — Emotional arc without resolution",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 015 — INVALID CAMERA INSIDE VALID SEQUENCE
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][2][
        "camera"
    ][
        "movement"
    ] = "impossible-camera"

    tests.append(
        (
            "INVALID-015 — Invalid camera inside sequence",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 016 — BROKEN CHARACTER LOCK
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][1][
        "continuity"
    ][
        "character_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-016 — Character lock broken",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 017 — BROKEN ENVIRONMENT LOCK
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][1][
        "continuity"
    ][
        "environment_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-017 — Environment lock broken",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # INVALID 018 — MULTIPLE CONTRADICTIONS
    # ------------------------------------------------------------

    corrupted = deepcopy(plan)

    corrupted["shots"][2][
        "scene_id"
    ] = "fake-scene"

    corrupted["shots"][2][
        "location"
    ] = "fake-location"

    corrupted["shots"][2][
        "characters"
    ] = ["fake-character"]

    corrupted["shots"][2][
        "causal_event_ids"
    ] = ["fake-event"]

    corrupted["shots"][2][
        "camera"
    ][
        "movement"
    ] = "fake-camera"

    corrupted["shots"][2][
        "continuity"
    ][
        "character_identity_locked"
    ] = False

    tests.append(
        (
            "INVALID-018 — Multi-contradiction sequence",
            corrupted
        )
    )

    # ------------------------------------------------------------
    # EXECUTE TESTS
    # ------------------------------------------------------------

    passed = 0
    failed = 0

    print("-" * 60)

    for label, corrupted in tests:

        if expect_rejection(
            label,
            corrupted,
            director,
            shot_engine,
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
        passed == len(tests)
        and failed == 0
    ):

        print(
            "OVERALL: PASS"
        )

        print()
        print(
            "All adversarial sequence contradictions "
            "were rejected."
        )

        sys.exit(0)

    print(
        "OVERALL: FAIL"
    )

    sys.exit(1)


if __name__ == "__main__":
    main()
