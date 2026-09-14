import copy
import sys
from pathlib import Path

BASE = Path(r"D:\Deathbound")
sys.path.insert(0, str(BASE / "automation" / "scripts"))

from camera_performance_engine import (
    load_schema,
    validate_camera_performance
)

SCHEMA = load_schema()


def baseline():
    return {
        "shot_id": "TEST-PERF-CAM-001",
        "performance_intent": "speak",
        "camera": {
            "shot_type": "medium_close",
            "movement": "static"
        },
        "character_performance": {
            "performance_intent": "speak",
            "emotion": "concerned",
            "locomotion": "idle",
            "performance_change": True
        },
        "dialogue": {
            "active": True
        }
    }


def run(name, mutation, expected_reject=True):
    shot = copy.deepcopy(BASELINE)
    mutation(shot)

    result = validate_camera_performance(
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
        "VALID-001 — Speaking with static camera",
        lambda s: None,
        False
    ),

    (
        "VALID-002 — Emotional realization with push-in",
        lambda s: s.update({
            "performance_intent": "decide",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "character_performance": {
                "performance_intent": "decide",
                "emotion": "determined",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        False
    ),

    (
        "VALID-003 — Walking with tracking",
        lambda s: s.update({
            "performance_intent": "observe",
            "camera": {
                "shot_type": "medium",
                "movement": "tracking"
            },
            "character_performance": {
                "performance_intent": "observe",
                "emotion": "curious",
                "locomotion": "walking",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        False
    ),

    (
        "VALID-004 — Running with handheld",
        lambda s: s.update({
            "performance_intent": "protect",
            "camera": {
                "shot_type": "wide",
                "movement": "handheld"
            },
            "character_performance": {
                "performance_intent": "protect",
                "emotion": "afraid",
                "locomotion": "running",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        False
    ),

    (
        "VALID-005 — Supernatural activation with push-in",
        lambda s: s.update({
            "performance_intent": "supernatural_activation",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "character_performance": {
                "performance_intent": "supernatural_activation",
                "emotion": "determined",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            },
            "supernatural": {
                "active": True
            }
        }),
        False
    ),

    (
        "VALID-006 — Reaction with facial change",
        lambda s: s.update({
            "performance_intent": "react",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "character_performance": {
                "performance_intent": "react",
                "emotion": "surprised",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        False
    ),

    (
        "INVALID-001 — Tracking while idle",
        lambda s: s.update({
            "performance_intent": "observe",
            "camera": {
                "shot_type": "medium",
                "movement": "tracking"
            },
            "character_performance": {
                "performance_intent": "observe",
                "emotion": "neutral",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        True
    ),

    (
        "INVALID-002 — Tracking with speaking intent",
        lambda s: s.update({
            "performance_intent": "speak",
            "camera": {
                "shot_type": "medium_close",
                "movement": "tracking"
            },
            "character_performance": {
                "performance_intent": "speak",
                "emotion": "concerned",
                "locomotion": "idle",
                "performance_change": True
            }
        }),
        True
    ),

    (
        "INVALID-003 — Reaction without performance change",
        lambda s: s.update({
            "performance_intent": "react",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "character_performance": {
                "performance_intent": "react",
                "emotion": "surprised",
                "locomotion": "idle",
                "performance_change": False
            },
            "dialogue": {
                "active": False
            }
        }),
        True
    ),

    (
        "INVALID-004 — Speaking without dialogue",
        lambda s: s.update({
            "performance_intent": "speak",
            "character_performance": {
                "performance_intent": "speak",
                "emotion": "neutral",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        True
    ),

    (
        "INVALID-005 — Supernatural camera without supernatural state",
        lambda s: s.update({
            "performance_intent": "supernatural_activation",
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "character_performance": {
                "performance_intent": "supernatural_activation",
                "emotion": "determined",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            },
            "supernatural": {
                "active": False
            }
        }),
        True
    ),

    (
        "INVALID-006 — Camera replaces performance",
        lambda s: s.update({
            "camera": {
                "shot_type": "close",
                "movement": "push_in"
            },
            "camera_replaces_performance": True
        }),
        True
    ),

    (
        "INVALID-007 — Camera-only animation",
        lambda s: s.update({
            "camera_only_animation": True
        }),
        True
    ),

    (
        "INVALID-008 — Running with static camera",
        lambda s: s.update({
            "performance_intent": "protect",
            "camera": {
                "shot_type": "wide",
                "movement": "static"
            },
            "character_performance": {
                "performance_intent": "protect",
                "emotion": "determined",
                "locomotion": "running",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            }
        }),
        True
    ),

    (
        "INVALID-009 — Invalid performance intent",
        lambda s: s.update({
            "performance_intent": "random_action",
            "character_performance": {
                "performance_intent": "random_action",
                "emotion": "neutral",
                "locomotion": "idle",
                "performance_change": True
            }
        }),
        True
    ),

    (
        "INVALID-010 — Supernatural activation with unrelated camera",
        lambda s: s.update({
            "performance_intent": "supernatural_activation",
            "camera": {
                "shot_type": "medium",
                "movement": "pan"
            },
            "character_performance": {
                "performance_intent": "supernatural_activation",
                "emotion": "determined",
                "locomotion": "idle",
                "performance_change": True
            },
            "dialogue": {
                "active": False
            },
            "supernatural": {
                "active": True
            }
        }),
        True
    )
]


passed = 0

print("=" * 60)
print("DEATHBOUND — PHASE 5G-5")
print("CAMERA ↔ CHARACTER PERFORMANCE ADVERSARIAL QA")
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
    print("Camera/performance contradictions were rejected.")
else:
    print("OVERALL: FAIL")
    raise SystemExit(1)
