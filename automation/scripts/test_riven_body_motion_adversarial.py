import json
from pathlib import Path
from copy import deepcopy
import importlib.util

ROOT = Path(r"D:\Deathbound")

ENGINE_PATH = ROOT / "automation" / "scripts" / "riven_body_motion_engine.py"
SCHEMA_PATH = ROOT / "config" / "BODY_MOTION_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "riven_body_motion_engine",
        ENGINE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    engine = load_engine()
    schema = load_json(SCHEMA_PATH)
    canon = load_json(CANON_PATH)

    base = engine.make_base_state()
    tests = []

    def check(label, result, expected):
        actual = result["accepted"]
        passed = actual == expected
        tests.append((label, passed, actual, expected))

    def invalid_state(label, mutate):
        state = deepcopy(base)
        mutate(state)
        check(
            label,
            engine.validate_state(state, schema, canon),
            False
        )

    def invalid_transition(label, mutate_previous, mutate_next,
                           transition_type, duration=1.0, events=None):
        previous = deepcopy(base)
        next_state = deepcopy(base)

        if mutate_previous:
            mutate_previous(previous)

        if mutate_next:
            mutate_next(next_state)

        check(
            label,
            engine.transition(
                previous,
                next_state,
                transition_type,
                duration,
                events or []
            ),
            False
        )

    # =========================================================
    # VALID BASELINES
    # =========================================================

    check(
        "VALID-001 — Baseline standing",
        engine.validate_state(base, schema, canon),
        True
    )

    walking = deepcopy(base)
    walking["body"]["posture"] = "walking"
    walking["body"]["locomotion"] = "walking"
    walking["body"]["movement_phase"] = "action"

    check(
        "VALID-002 — Walking state",
        engine.validate_state(walking, schema, canon),
        True
    )

    running = deepcopy(walking)
    running["body"]["posture"] = "running"
    running["body"]["locomotion"] = "running"

    check(
        "VALID-003 — Running state",
        engine.validate_state(running, schema, canon),
        True
    )

    # =========================================================
    # STATE CONTRADICTIONS
    # =========================================================

    invalid_state(
        "INVALID-001 — Walking posture with stationary locomotion",
        lambda s: (
            s["body"].update({
                "posture": "walking",
                "locomotion": "stationary",
                "movement_phase": "action"
            })
        )
    )

    invalid_state(
        "INVALID-002 — Running posture with walking locomotion",
        lambda s: (
            s["body"].update({
                "posture": "running",
                "locomotion": "walking",
                "movement_phase": "action"
            })
        )
    )

    invalid_state(
        "INVALID-003 — Running while idle",
        lambda s: (
            s["body"].update({
                "posture": "running",
                "locomotion": "running",
                "movement_phase": "idle"
            })
        )
    )

    invalid_state(
        "INVALID-004 — Falling while grounded",
        lambda s: (
            s["body"].update({
                "posture": "falling",
                "weight_distribution": "airborne",
                "feet": "grounded"
            })
        )
    )

    invalid_state(
        "INVALID-005 — Falling without airborne weight",
        lambda s: (
            s["body"].update({
                "posture": "falling",
                "weight_distribution": "balanced",
                "feet": "grounded"
            })
        )
    )

    invalid_state(
        "INVALID-006 — Lying while walking",
        lambda s: (
            s["body"].update({
                "posture": "lying",
                "locomotion": "walking"
            })
        )
    )

    invalid_state(
        "INVALID-007 — Invalid posture",
        lambda s: s["body"].update({"posture": "teleporting"})
    )

    invalid_state(
        "INVALID-008 — Invalid locomotion",
        lambda s: s["body"].update({"locomotion": "teleporting"})
    )

    invalid_state(
        "INVALID-009 — Invalid orientation",
        lambda s: s["body"].update({"orientation": "diagonal"})
    )

    invalid_state(
        "INVALID-010 — Invalid weight distribution",
        lambda s: s["body"].update({"weight_distribution": "floating"})
    )

    invalid_state(
        "INVALID-011 — Invalid movement phase",
        lambda s: s["body"].update({"movement_phase": "teleport"})
    )

    invalid_state(
        "INVALID-012 — Invalid physical condition",
        lambda s: s["body"].update({
            "physical_condition": "invincible"
        })
    )

    # =========================================================
    # GESTURE CONTRADICTIONS
    # =========================================================

    invalid_state(
        "INVALID-013 — Active gesture with none type",
        lambda s: s["gesture"].update({
            "active": True,
            "type": "none"
        })
    )

    invalid_state(
        "INVALID-014 — Inactive gesture with active type",
        lambda s: s["gesture"].update({
            "active": False,
            "type": "point"
        })
    )

    invalid_state(
        "INVALID-015 — Hands contradiction",
        lambda s: (
            s["gesture"].update({
                "active": True,
                "type": "hands_in_pockets"
            }),
            s["body"].update({
                "hands": "closed_fist"
            })
        )
    )

    invalid_state(
        "INVALID-016 — Invalid gesture",
        lambda s: s["gesture"].update({
            "active": True,
            "type": "teleport_gesture"
        })
    )

    # =========================================================
    # ENVIRONMENT ATTACKS
    # =========================================================

    invalid_state(
        "INVALID-017 — Spatial validity disabled",
        lambda s: s["environment_interaction"].update({
            "spatially_valid": False
        })
    )

    invalid_state(
        "INVALID-018 — Collision awareness disabled",
        lambda s: s["environment_interaction"].update({
            "collision_aware": False
        })
    )

    invalid_state(
        "INVALID-019 — Invalid environment boolean",
        lambda s: s["environment_interaction"].update({
            "surface_aware": "yes"
        })
    )

    # =========================================================
    # CONTINUITY ATTACKS
    # =========================================================

    invalid_state(
        "INVALID-020 — Identity lock disabled",
        lambda s: s["continuity"].update({
            "identity_locked": False
        })
    )

    invalid_state(
        "INVALID-021 — Body structure lock disabled",
        lambda s: s["continuity"].update({
            "body_structure_locked": False
        })
    )

    invalid_state(
        "INVALID-022 — Proportion lock disabled",
        lambda s: s["continuity"].update({
            "proportion_locked": False
        })
    )

    invalid_state(
        "INVALID-023 — Clothing lock disabled",
        lambda s: s["continuity"].update({
            "clothing_locked": False
        })
    )

    invalid_state(
        "INVALID-024 — Position continuity lock disabled",
        lambda s: s["continuity"].update({
            "position_continuity_locked": False
        })
    )

    invalid_state(
        "INVALID-025 — Orientation continuity lock disabled",
        lambda s: s["continuity"].update({
            "orientation_continuity_locked": False
        })
    )

    invalid_state(
        "INVALID-026 — Physical condition lock disabled",
        lambda s: s["continuity"].update({
            "physical_condition_locked": False
        })
    )

    # =========================================================
    # CLOTHING ATTACKS
    # =========================================================

    invalid_state(
        "INVALID-027 — Clothing no longer canonical",
        lambda s: s["clothing"].update({
            "canonical": False
        })
    )

    invalid_state(
        "INVALID-028 — Clothing unlocked",
        lambda s: s["clothing"].update({
            "locked": False
        })
    )

    invalid_state(
        "INVALID-029 — Damaged clothing without event",
        lambda s: s["clothing"].update({
            "damage": True
        })
    )

    # =========================================================
    # SUPERNATURAL ATTACKS
    # =========================================================

    invalid_state(
        "INVALID-030 — Supernatural condition without event",
        lambda s: s["body"].update({
            "physical_condition": "supernaturally_empowered"
        })
    )

    # =========================================================
    # EMOTIONAL CONTRADICTIONS
    # =========================================================

    invalid_state(
        "INVALID-031 — Sad emotion with upward head",
        lambda s: (
            s.update({"emotion": "sad"}),
            s["body"].update({
                "head_orientation": "up"
            })
        )
    )

    invalid_state(
        "INVALID-032 — Determined emotion with backward weight",
        lambda s: (
            s.update({"emotion": "determined"}),
            s["body"].update({
                "weight_distribution": "backward"
            })
        )
    )

    invalid_state(
        "INVALID-033 — Compassionate emotion with closed fist",
        lambda s: (
            s.update({"emotion": "compassionate"}),
            s["gesture"].update({
                "active": True,
                "type": "closed_fist"
            }),
            s["body"].update({
                "hands": "closed_fist"
            })
        )
    )

    # =========================================================
    # DIALOGUE ATTACK
    # =========================================================

    invalid_state(
        "INVALID-034 — Dialogue with completely idle performance",
        lambda s: s.update({
            "dialogue": {"active": True}
        })
    )

    # =========================================================
    # TRANSITION ATTACKS
    # =========================================================

    invalid_transition(
        "INVALID-035 — Standing to running directly",
        None,
        lambda s: s["body"].update({
            "posture": "running",
            "locomotion": "running",
            "movement_phase": "action"
        }),
        "run",
        events=["EVENT-RUN-001"]
    )

    invalid_transition(
        "INVALID-036 — Sitting to running",
        None,
        lambda s: s["body"].update({
            "posture": "running",
            "locomotion": "running",
            "movement_phase": "action"
        }),
        "run",
        events=["EVENT-RUN-002"]
    )

    invalid_transition(
        "INVALID-037 — Walking to sitting via walk",
        lambda s: s["body"].update({
            "posture": "walking",
            "locomotion": "walking",
            "movement_phase": "action"
        }),
        lambda s: s["body"].update({
            "posture": "sitting",
            "locomotion": "stationary"
        }),
        "walk",
        events=["EVENT-SIT-001"]
    )

    invalid_transition(
        "INVALID-038 — Position teleport",
        None,
        lambda s: s["position"].update({
            "x": 500.0,
            "y": 500.0,
            "z": 500.0
        }),
        "gesture",
        events=["EVENT-TELEPORT-001"]
    )

    invalid_transition(
        "INVALID-039 — Position change during idle",
        None,
        lambda s: s["position"].update({
            "x": 10.0
        }),
        "idle",
        events=[]
    )

    invalid_transition(
        "INVALID-040 — Fall without causal event",
        None,
        lambda s: s["body"].update({
            "posture": "falling",
            "locomotion": "falling",
            "weight_distribution": "airborne",
            "feet": "airborne",
            "movement_phase": "action"
        }),
        "fall",
        events=[]
    )

    invalid_transition(
        "INVALID-041 — Physical injury without event",
        None,
        lambda s: s["body"].update({
            "physical_condition": "injured"
        }),
        "idle",
        events=[]
    )

    invalid_transition(
        "INVALID-042 — Orientation change without turn",
        None,
        lambda s: s["body"].update({
            "orientation": "profile_left"
        }),
        "gesture",
        events=["EVENT-ORIENTATION-001"]
    )

    invalid_transition(
        "INVALID-043 — Supernatural transition without event",
        None,
        lambda s: s["body"].update({
            "physical_condition": "supernaturally_empowered"
        }),
        "supernatural",
        events=[]
    )

    invalid_transition(
        "INVALID-044 — Zero-duration physical transition",
        None,
        lambda s: s["body"].update({
            "posture": "walking",
            "locomotion": "walking",
            "movement_phase": "action"
        }),
        "walk",
        duration=0,
        events=["EVENT-WALK-003"]
    )

    invalid_transition(
        "INVALID-045 — Negative-duration transition",
        None,
        lambda s: s["body"].update({
            "posture": "walking",
            "locomotion": "walking",
            "movement_phase": "action"
        }),
        "walk",
        duration=-1,
        events=["EVENT-WALK-004"]
    )

    # =========================================================
    # MULTI-CONTRADICTION
    # =========================================================

    def corrupt_multi(s):
        s["character_id"] = "other"
        s["body"].update({
            "posture": "running",
            "locomotion": "stationary",
            "movement_phase": "idle",
            "weight_distribution": "airborne",
            "physical_condition": "supernaturally_empowered"
        })
        s["gesture"].update({
            "active": True,
            "type": "none"
        })
        s["environment_interaction"].update({
            "spatially_valid": False,
            "collision_aware": False
        })
        s["clothing"].update({
            "canonical": False,
            "locked": False
        })
        s["continuity"].update({
            "identity_locked": False,
            "body_structure_locked": False,
            "proportion_locked": False
        })
        s["emotion"] = "unknown"
        s["position"].update({
            "x": "teleport"
        })

    invalid_state(
        "INVALID-046 — Multi-contradiction body state",
        corrupt_multi
    )

    # =========================================================
    # RESULTS
    # =========================================================

    print("=" * 64)
    print("DEATHBOUND — PHASE 5E-3C")
    print("RIVEN BODY MOTION ADVERSARIAL QA")
    print("=" * 64)

    passed = 0
    failed = 0

    for label, correct, actual, expected in tests:
        if correct:
            print(f"PASS  {label}")
            passed += 1
        else:
            print(
                f"FAIL  {label} "
                f"(actual={actual}, expected={expected})"
            )
            failed += 1

    print("-" * 64)
    print(f"TESTS: {len(tests)}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {failed}")
    print("-" * 64)

    if failed == 0:
        print("OVERALL: PASS")
        print("All hostile body-motion contradictions were rejected.")
    else:
        print("OVERALL: FAIL")
        print("Body-motion engine requires hardening.")

    print("=" * 64)


if __name__ == "__main__":
    main()
