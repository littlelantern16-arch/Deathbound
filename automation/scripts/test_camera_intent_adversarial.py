import copy
import sys
from pathlib import Path

BASE = Path(r"D:\Deathbound")
sys.path.insert(0, str(BASE / "automation" / "scripts"))

from camera_intent_engine import (
    load_schema,
    validate_camera_intent
)


SCHEMA = load_schema()


def baseline():
    return {
        "shot_id": "TEST-INTENT-001",
        "role": "dialogue",
        "purpose": "character realization",
        "camera": {
            "shot_type": "medium_close",
            "movement": "static"
        },
        "composition": {
            "subject_priority": "primary_character",
            "framing_intent": "converse",
            "visual_focus": "face",
            "depth_strategy": "moderate"
        }
    }


def run(name, mutation, expected_reject=True):
    shot = copy.deepcopy(BASELINE)
    mutation(shot)

    result = validate_camera_intent(
        shot,
        schema=SCHEMA
    )

    rejected = not result["accepted"]

    if rejected == expected_reject:
        print(f"PASS  {name}")
        return True

    print(f"FAIL  {name}")
    print(f"      {result}")
    return False


BASELINE = baseline()

tests = [

    (
        "VALID-001 — Dialogue face composition",
        lambda s: None,
        False
    ),

    (
        "VALID-002 — Dialogue eyes emphasis",
        lambda s: s["composition"].update({
            "visual_focus": "eyes",
            "framing_intent": "emphasize"
        }),
        False
    ),

    (
        "VALID-003 — Reaction close-up",
        lambda s: s.update({
            "role": "reaction",
            "purpose": "reaction to revelation",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "composition": {
                "subject_priority": "primary_character",
                "framing_intent": "react",
                "visual_focus": "face",
                "depth_strategy": "shallow"
            }
        }),
        False
    ),

    (
        "VALID-004 — Establishing environment",
        lambda s: s.update({
            "role": "establishing",
            "purpose": "establish location",
            "camera": {
                "shot_type": "wide",
                "movement": "push_in"
            },
            "composition": {
                "subject_priority": "environment",
                "framing_intent": "establish",
                "visual_focus": "environment",
                "depth_strategy": "deep"
            }
        }),
        False
    ),

    (
        "VALID-005 — Supernatural reveal",
        lambda s: s.update({
            "role": "supernatural_payoff",
            "purpose": "reveal supernatural event",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "composition": {
                "subject_priority": "supernatural_effect",
                "framing_intent": "reveal",
                "visual_focus": "supernatural_effect",
                "depth_strategy": "shallow"
            }
        }),
        False
    ),

    (
        "VALID-006 — Emotional negative space",
        lambda s: s.update({
            "role": "emotional_resolution",
            "purpose": "isolate character after loss",
            "camera": {
                "shot_type": "medium_close",
                "movement": "static"
            },
            "composition": {
                "subject_priority": "negative_space",
                "framing_intent": "isolate",
                "visual_focus": "negative_space",
                "depth_strategy": "deep"
            }
        }),
        False
    ),

    (
        "INVALID-001 — Missing composition",
        lambda s: s.pop("composition"),
        True
    ),

    (
        "INVALID-002 — Invalid subject priority",
        lambda s: s["composition"].update({
            "subject_priority": "everything"
        }),
        True
    ),

    (
        "INVALID-003 — Dialogue ignores character",
        lambda s: s["composition"].update({
            "subject_priority": "environment",
            "visual_focus": "environment"
        }),
        True
    ),

    (
        "INVALID-004 — Reaction focuses on environment",
        lambda s: s.update({
            "role": "reaction",
            "purpose": "reaction",
            "camera": {
                "shot_type": "close",
                "movement": "static"
            },
            "composition": {
                "subject_priority": "environment",
                "framing_intent": "react",
                "visual_focus": "environment",
                "depth_strategy": "moderate"
            }
        }),
        True
    ),

    (
        "INVALID-005 — Establishing focuses on eyes",
        lambda s: s.update({
            "role": "establishing",
            "purpose": "establish",
            "camera": {
                "shot_type": "wide",
                "movement": "static"
            },
            "composition": {
                "subject_priority": "primary_character",
                "framing_intent": "establish",
                "visual_focus": "eyes",
                "depth_strategy": "deep"
            }
        }),
        True
    ),

    (
        "INVALID-006 — Supernatural payoff ignores effect",
        lambda s: s.update({
            "role": "supernatural_payoff",
            "purpose": "supernatural reveal",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "composition": {
                "subject_priority": "environment",
                "framing_intent": "reveal",
                "visual_focus": "hands",
                "depth_strategy": "shallow"
            }
        }),
        True
    ),

    (
        "INVALID-007 — Negative space without isolation intent",
        lambda s: s["composition"].update({
            "subject_priority": "negative_space",
            "framing_intent": "converse",
            "visual_focus": "negative_space"
        }),
        True
    ),

    (
        "INVALID-008 — Invalid framing intent",
        lambda s: s["composition"].update({
            "framing_intent": "random_cinematic"
        }),
        True
    ),

    (
        "INVALID-009 — Missing purpose",
        lambda s: s.pop("purpose"),
        True
    ),

    (
        "INVALID-010 — Close-up environment focus",
        lambda s: s["composition"].update({
            "visual_focus": "environment"
        }),
        True
    ),

    (
        "INVALID-011 — Emotional resolution ignores emotion",
        lambda s: s.update({
            "role": "emotional_resolution",
            "purpose": "emotional aftermath",
            "camera": {
                "shot_type": "medium_close",
                "movement": "static"
            },
            "composition": {
                "subject_priority": "prop",
                "framing_intent": "transition",
                "visual_focus": "prop",
                "depth_strategy": "deep"
            }
        }),
        True
    )
]


passed = 0

print("=" * 60)
print("DEATHBOUND — PHASE 5G-3")
print("CINEMATIC CAMERA INTENT ADVERSARIAL QA")
print("=" * 60)

for name, mutation, expected in tests:
    if run(name, mutation, expected):
        passed += 1

print("-" * 60)
print(f"TESTS: {len(tests)}")
print(f"PASS:  {passed}")
print(f"FAIL:  {len(tests) - passed}")
print("-" * 60)

if passed == len(tests):
    print("OVERALL: PASS")
    print("Cinematic intent contradictions were rejected.")
else:
    print("OVERALL: FAIL")
    raise SystemExit(1)
