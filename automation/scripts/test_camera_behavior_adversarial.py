import json
import copy
import sys
from pathlib import Path

BASE = Path(r"D:\Deathbound")
sys.path.insert(0, str(BASE / "automation" / "scripts"))

from camera_behavior_engine import (
    validate_camera_behavior,
    load_schema
)


def baseline():
    return {
        "shot_id": "TEST-SHOT-001",
        "role": "dialogue",
        "purpose": "dialogue",
        "duration_seconds": 5.0,
        "camera": {
            "shot_type": "medium_close",
            "movement": "static"
        },
        "character_performance": {
            "active": True,
            "emotion": "concerned",
            "locomotion": "idle"
        },
        "environment_motion": "subtle",
        "dialogue": {
            "active": True
        }
    }


def run(name, mutation, expected_reject=True):
    shot = copy.deepcopy(BASELINE)
    mutation(shot)

    result = validate_camera_behavior(
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


SCHEMA = load_schema()
BASELINE = baseline()

tests = []


tests.append((
    "VALID-001 — Static dialogue camera",
    lambda s: None,
    False
))

tests.append((
    "VALID-002 — Dialogue push-in with performance",
    lambda s: s.update({
        "camera": {
            "shot_type": "close",
            "movement": "push_in"
        },
        "purpose": "realization"
    }),
    False
))

tests.append((
    "VALID-003 — Tracking with locomotion",
    lambda s: s.update({
        "role": "character_coverage",
        "purpose": "character_movement",
        "camera": {
            "shot_type": "medium",
            "movement": "tracking"
        },
        "character_performance": {
            "active": True,
            "emotion": "neutral",
            "locomotion": "walking"
        },
        "dialogue": {
            "active": False
        }
    }),
    False
))

tests.append((
    "VALID-004 — Slow push-in alias normalization",
    lambda s: s.update({
        "camera": {
            "shot_type": "wide",
            "movement": "slow_push_in"
        },
        "role": "establishing",
        "purpose": "establishing"
    }),
    False
))

tests.append((
    "INVALID-001 — Tracking without moving subject",
    lambda s: s.update({
        "role": "character_coverage",
        "camera": {
            "shot_type": "medium",
            "movement": "tracking"
        },
        "character_performance": {
            "active": True,
            "emotion": "neutral",
            "locomotion": "idle"
        }
    }),
    True
))

tests.append((
    "INVALID-002 — Action with static-only camera and no motion",
    lambda s: s.update({
        "role": "action",
        "purpose": "action",
        "camera": {
            "shot_type": "wide",
            "movement": "static"
        },
        "character_performance": {},
        "dialogue": {
            "active": False
        },
        "camera_only_animation": True
    }),
    True
))

tests.append((
    "INVALID-003 — Camera-only animation",
    lambda s: s.update({
        "camera": {
            "shot_type": "close",
            "movement": "push_in"
        },
        "camera_only_animation": True,
        "character_performance": {},
        "environment_motion": "none"
    }),
    True
))

tests.append((
    "INVALID-004 — Dialogue with no character performance",
    lambda s: s.update({
        "character_performance": {},
        "dialogue": {
            "active": True
        }
    }),
    True
))

tests.append((
    "INVALID-005 — Tracking with no subject",
    lambda s: s.update({
        "role": "action",
        "camera": {
            "shot_type": "wide",
            "movement": "tracking"
        },
        "character_performance": {
            "active": True,
            "locomotion": "idle"
        },
        "tracking_subject": None
    }),
    True
))

tests.append((
    "INVALID-006 — Excessive camera duration",
    lambda s: s.update({
        "duration_seconds": 16.0
    }),
    True
))

tests.append((
    "INVALID-007 — Invalid camera movement",
    lambda s: s.update({
        "camera": {
            "shot_type": "medium_close",
            "movement": "zoom_forever"
        }
    }),
    True
))

tests.append((
    "INVALID-008 — Invalid shot type",
    lambda s: s.update({
        "camera": {
            "shot_type": "cinematic",
            "movement": "static"
        }
    }),
    True
))

tests.append((
    "INVALID-009 — Role movement mismatch",
    lambda s: s.update({
        "role": "action",
        "camera": {
            "shot_type": "wide",
            "movement": "static"
        }
    }),
    True
))

tests.append((
    "INVALID-010 — Camera-only dialogue replacement",
    lambda s: s.update({
        "camera": {
            "shot_type": "medium_close",
            "movement": "push_in"
        },
        "camera_replaces_performance": True,
        "dialogue": {
            "active": True
        }
    }),
    True
))

tests.append((
    "INVALID-011 — Tracking below minimum duration",
    lambda s: s.update({
        "role": "character_coverage",
        "camera": {
            "shot_type": "medium",
            "movement": "tracking"
        },
        "duration_seconds": 0.5,
        "character_performance": {
            "active": True,
            "locomotion": "walking"
        }
    }),
    True
))


passed = 0

print("=" * 60)
print("DEATHBOUND — PHASE 5G-1")
print("CAMERA BEHAVIOR ADVERSARIAL QA")
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
    print("Camera behavior contradictions were rejected.")
else:
    print("OVERALL: FAIL")
    raise SystemExit(1)
