import copy
import sys
from pathlib import Path

BASE = Path(r"D:\Deathbound")
sys.path.insert(0, str(BASE / "automation" / "scripts"))

from camera_continuity_engine import (
    load_schema,
    validate_camera_continuity
)


SCHEMA = load_schema()


def base_camera(
    movement="static",
    position=None,
    target=None
):
    return {
        "shot_type": "medium",
        "movement": movement,
        "position": position or {
            "x": 0.0,
            "y": 2.0,
            "z": 5.0
        },
        "target": target or {
            "x": 0.0,
            "y": 1.5,
            "z": 0.0
        }
    }


def base_shot(
    movement="static",
    position=None,
    target=None
):
    return {
        "shot_id": "TEST",
        "camera": base_camera(
            movement,
            position,
            target
        )
    }


def moving_shot(
    movement,
    start,
    end,
    target=None,
    duration=2.0,
    transition=None
):
    shot = base_shot(
        movement,
        end,
        target
    )

    shot["camera"]["trajectory"] = {
        "start": start,
        "end": end,
        "duration_seconds": duration
    }

    if transition:
        shot["camera_transition"] = transition

    return shot


def run(name, shot, previous=None, expected_reject=True):
    result = validate_camera_continuity(
        shot,
        previous_shot=previous,
        schema=SCHEMA
    )

    rejected = not result["accepted"]

    if rejected == expected_reject:
        print(f"PASS  {name}")
        return True

    print(f"FAIL  {name}")
    print(f"      {result}")
    return False


P0 = {
    "x": 0.0,
    "y": 2.0,
    "z": 5.0
}

P1 = {
    "x": 0.0,
    "y": 2.0,
    "z": 4.0
}

P2 = {
    "x": 0.0,
    "y": 2.0,
    "z": 3.0
}

T0 = {
    "x": 0.0,
    "y": 1.5,
    "z": 0.0
}


tests = []


tests.append((
    "VALID-001 — First static camera",
    base_shot(),
    None,
    False
))

tests.append((
    "VALID-002 — Connected static camera continuity",
    base_shot(position=P0),
    base_shot(position=P0),
    False
))

tests.append((
    "VALID-003 — Valid push-in trajectory",
    moving_shot(
        "push_in",
        P0,
        P1,
        T0
    ),
    base_shot(position=P0),
    False
))

tests.append((
    "VALID-004 — Valid tracking trajectory",
    moving_shot(
        "tracking",
        P0,
        P1,
        T0
    ),
    base_shot(position=P0),
    False
))

tests.append((
    "VALID-005 — Intentional cut permits composition change",
    {
        **base_shot(
            position={
                "x": 40.0,
                "y": 8.0,
                "z": -20.0
            }
        ),
        "intentional_cut": True
    },
    base_shot(position=P0),
    False
))

tests.append((
    "VALID-006 — Explicit movement transition",
    moving_shot(
        "pan",
        P1,
        P2,
        T0,
        transition="tracking_to_pan"
    ),
    moving_shot(
        "tracking",
        P0,
        P1,
        T0
    ),
    False
))

tests.append((
    "INVALID-001 — Missing camera position",
    {
        "camera": {
            "shot_type": "medium",
            "movement": "static",
            "target": T0
        }
    },
    None,
    True
))

tests.append((
    "INVALID-002 — Invalid camera vector",
    {
        "camera": {
            "shot_type": "medium",
            "movement": "static",
            "position": {
                "x": "teleport",
                "y": 2.0,
                "z": 5.0
            },
            "target": T0
        }
    },
    None,
    True
))

tests.append((
    "INVALID-003 — Moving camera without trajectory",
    base_shot(
        movement="push_in",
        position=P1
    ),
    base_shot(position=P0),
    True
))

tests.append((
    "INVALID-004 — Zero-length moving trajectory",
    moving_shot(
        "push_in",
        P0,
        P0,
        T0
    ),
    base_shot(position=P0),
    True
))

tests.append((
    "INVALID-005 — Camera trajectory starts elsewhere",
    moving_shot(
        "push_in",
        P2,
        P1,
        T0
    ),
    base_shot(position=P0),
    True
))

tests.append((
    "INVALID-006 — Camera trajectory ends elsewhere",
    {
        **base_shot(
            movement="push_in",
            position=P2
        ),
        "camera": {
            **base_camera(
                "push_in",
                P2,
                T0
            ),
            "trajectory": {
                "start": P0,
                "end": P1,
                "duration_seconds": 2.0
            }
        }
    },
    base_shot(position=P0),
    True
))

tests.append((
    "INVALID-007 — Connected static camera teleport",
    base_shot(
        position={
            "x": 30.0,
            "y": 30.0,
            "z": 30.0
        }
    ),
    base_shot(position=P0),
    True
))

tests.append((
    "INVALID-008 — Excessive trajectory speed",
    moving_shot(
        "push_in",
        P0,
        {
            "x": 15.0,
            "y": 2.0,
            "z": 5.0
        },
        T0,
        duration=0.25
    ),
    base_shot(position=P0),
    True
))

tests.append((
    "INVALID-009 — Orbit target discontinuity",
    moving_shot(
        "orbit",
        P0,
        P1,
        {
            "x": 20.0,
            "y": 20.0,
            "z": 20.0
        }
    ),
    base_shot(position=P0, target=T0),
    True
))

tests.append((
    "INVALID-010 — Moving-to-moving transition without declaration",
    moving_shot(
        "pan",
        P0,
        P1,
        T0
    ),
    moving_shot(
        "tracking",
        P0,
        P1,
        T0
    ),
    True
))

tests.append((
    "INVALID-011 — Camera teleport beyond threshold",
    {
        **base_shot(
            movement="push_in",
            position={
                "x": 100.0,
                "y": 100.0,
                "z": 100.0
            }
        ),
        "camera": {
            **base_camera(
                "push_in",
                {
                    "x": 100.0,
                    "y": 100.0,
                    "z": 100.0
                },
                T0
            ),
            "trajectory": {
                "start": P0,
                "end": {
                    "x": 100.0,
                    "y": 100.0,
                    "z": 100.0
                },
                "duration_seconds": 10.0
            }
        }
    },
    base_shot(position=P0),
    True
))


passed = 0

print("=" * 60)
print("DEATHBOUND — PHASE 5G-2")
print("CAMERA CONTINUITY & TRAJECTORY ADVERSARIAL QA")
print("=" * 60)

for name, shot, previous, expected in tests:
    if run(name, shot, previous, expected):
        passed += 1

print("-" * 60)
print(f"TESTS: {len(tests)}")
print(f"PASS:  {passed}")
print(f"FAIL:  {len(tests) - passed}")
print("-" * 60)

if passed == len(tests):
    print("OVERALL: PASS")
    print("Camera continuity and trajectory contradictions were rejected.")
else:
    print("OVERALL: FAIL")
    raise SystemExit(1)

