import copy
import sys
from pathlib import Path

BASE = Path(r"D:\Deathbound")
sys.path.insert(0, str(BASE / "automation" / "scripts"))

from camera_repetition_engine import (
    load_schema,
    validate_repetition
)

SCHEMA = load_schema()


def shot(
    shot_type,
    movement,
    focus,
    intent,
    priority="primary_character",
    depth="moderate"
):
    return {
        "camera": {
            "shot_type": shot_type,
            "movement": movement
        },
        "composition": {
            "subject_priority": priority,
            "framing_intent": intent,
            "visual_focus": focus,
            "depth_strategy": depth
        }
    }


BASELINE = [
    shot("wide", "static", "environment", "establish", "environment", "deep"),
    shot("medium", "tracking", "character", "follow"),
    shot("medium_close", "static", "face", "converse"),
    shot("close", "push_in", "eyes", "emphasize"),
    shot("medium", "pan", "relationship", "discover"),
    shot("close", "pull_out", "negative_space", "isolate", "negative_space", "deep")
]


def run(name, sequence, expected_reject):
    result = validate_repetition(
        sequence,
        schema=SCHEMA
    )

    rejected = not result["accepted"]

    if rejected == expected_reject:
        print(f"PASS  {name}")
        return True

    print(f"FAIL  {name}")
    print(f"      {result}")
    return False


tests = []


tests.append((
    "VALID-001 — Diverse six-shot sequence",
    BASELINE,
    False
))


tests.append((
    "VALID-002 — Intentional visual motif",
    [
        {
            **shot(
                "close",
                "static",
                "eyes",
                "emphasize"
            ),
            "visual_motif": {
                "id": "RIVEN_EYES",
                "intent": "recurring supernatural warning"
            }
        },
        {
            **shot(
                "close",
                "static",
                "eyes",
                "emphasize"
            ),
            "visual_motif": {
                "id": "RIVEN_EYES",
                "intent": "recurring supernatural warning"
            }
        },
        {
            **shot(
                "close",
                "static",
                "eyes",
                "emphasize"
            ),
            "visual_motif": {
                "id": "RIVEN_EYES",
                "intent": "recurring supernatural warning"
            }
        }
    ],
    False
))


tests.append((
    "INVALID-001 — Excessive identical full signatures",
    [
        shot("medium_close", "static", "face", "converse"),
        shot("medium_close", "static", "face", "converse"),
        shot("medium_close", "static", "face", "converse"),
        shot("medium_close", "static", "face", "converse")
    ],
    True
))


tests.append((
    "INVALID-002 — Same camera signature repeated four times",
    [
        shot("medium", "tracking", "character", "follow"),
        shot("medium", "tracking", "character", "follow"),
        shot("medium", "tracking", "character", "follow"),
        shot("close", "tracking", "face", "follow")
    ],
    True
))


tests.append((
    "INVALID-003 — Same movement across entire sequence",
    [
        shot("wide", "push_in", "environment", "establish", "environment"),
        shot("medium", "push_in", "character", "observe"),
        shot("medium_close", "push_in", "face", "emphasize"),
        shot("close", "push_in", "eyes", "emphasize")
    ],
    True
))


tests.append((
    "INVALID-004 — Same shot type across entire sequence",
    [
        shot("medium", "static", "character", "observe"),
        shot("medium", "tracking", "character", "follow"),
        shot("medium", "pan", "relationship", "discover"),
        shot("medium", "push_in", "face", "emphasize")
    ],
    True
))


tests.append((
    "INVALID-005 — Monotonic zoom ladder",
    [
        shot("extreme_wide", "static", "environment", "establish", "environment"),
        shot("wide", "push_in", "environment", "reveal", "environment"),
        shot("medium", "push_in", "character", "observe"),
        shot("medium_close", "push_in", "face", "emphasize")
    ],
    True
))


tests.append((
    "INVALID-006 — Repeating camera cycle",
    [
        shot("wide", "static", "environment", "establish", "environment"),
        shot("medium", "tracking", "character", "follow"),
        shot("close", "push_in", "face", "emphasize"),
        shot("wide", "static", "environment", "establish", "environment"),
        shot("medium", "tracking", "character", "follow"),
        shot("close", "push_in", "face", "emphasize")
    ],
    True
))


tests.append((
    "INVALID-007 — Repeating composition cycle",
    [
        shot("medium", "static", "character", "observe"),
        shot("close", "push_in", "eyes", "emphasize"),
        shot("wide", "pull_out", "environment", "aftermath", "environment"),
        shot("medium", "pan", "character", "observe"),
        shot("close", "tilt", "eyes", "emphasize"),
        shot("wide", "crane", "environment", "aftermath", "environment")
    ],
    True
))


tests.append((
    "INVALID-008 — Six-shot sequence lacks camera diversity",
    [
        shot("medium", "static", "character", "observe"),
        shot("medium", "static", "character", "observe"),
        shot("medium", "static", "character", "observe"),
        shot("medium", "static", "character", "observe"),
        shot("medium", "static", "character", "observe"),
        shot("medium", "static", "character", "observe")
    ],
    True
))


tests.append((
    "INVALID-009 — Eight-shot sequence lacks composition diversity",
    [
        shot("wide", "static", "environment", "establish", "environment"),
        shot("wide", "push_in", "environment", "reveal", "environment"),
        shot("wide", "pull_out", "environment", "scale", "environment"),
        shot("wide", "pan", "environment", "discover", "environment"),
        shot("wide", "tilt", "environment", "scale", "environment"),
        shot("wide", "crane", "environment", "transition", "environment"),
        shot("wide", "orbit", "environment", "reveal", "environment"),
        shot("wide", "handheld", "environment", "confront", "environment")
    ],
    True
))


tests.append((
    "VALID-003 — Non-identical recurring motif is permitted",
    [
        {
            **shot("close", "static", "eyes", "emphasize"),
            "visual_motif": {
                "id": "EYE_MOTIF",
                "intent": "supernatural foreshadowing"
            }
        },
        shot("medium", "tracking", "character", "follow"),
        shot("wide", "pull_out", "environment", "aftermath", "environment"),
        {
            **shot("close", "push_in", "eyes", "emphasize"),
            "visual_motif": {
                "id": "EYE_MOTIF",
                "intent": "supernatural foreshadowing"
            }
        }
    ],
    False
))


passed = 0

print("=" * 60)
print("DEATHBOUND — PHASE 5G-4")
print("CINEMATIC REPETITION & ANTI-TEMPLATE ADVERSARIAL QA")
print("=" * 60)

for name, sequence, expected in tests:
    if run(name, copy.deepcopy(sequence), expected):
        passed += 1

print("-" * 60)
print(f"TESTS: {len(tests)}")
print(f"PASS:  {passed}")
print(f"FAIL:  {len(tests) - passed}")
print("-" * 60)

if passed == len(tests):
    print("OVERALL: PASS")
    print("Cinematic repetition and template patterns were controlled.")
else:
    print("OVERALL: FAIL")
    raise SystemExit(1)
