import sys
from copy import deepcopy

sys.path.insert(0, r"D:\Deathbound\automation\scripts")
import riven_body_motion_engine as e


def base():
    return e.make_base_state()


def valid_walking():
    s = base()
    s["body"]["posture"] = "walking"
    s["body"]["locomotion"] = "walking"
    s["body"]["movement_phase"] = "action"
    return s


def valid_running():
    s = valid_walking()
    s["body"]["posture"] = "running"
    s["body"]["locomotion"] = "running"
    return s


def valid_falling():
    s = base()
    s["body"]["posture"] = "falling"
    s["body"]["locomotion"] = "stationary"
    s["body"]["weight_distribution"] = "airborne"
    s["body"]["feet"] = "airborne"
    s["body"]["movement_phase"] = "action"
    return s


def run(label, previous, next_state, transition_type, duration, events, expected=False):
    result = e.transition(previous, next_state, transition_type, duration, events)
    passed = result["accepted"] == expected
    print(("PASS" if passed else "FAIL"), label)
    if not passed:
        print("  result:", result)
    return passed


def main():
    tests = []

    # Valid transition coverage.
    tests.append(run("VALID-001 standing -> walking", base(), valid_walking(),
                     "walk", 0.8, ["E1"], True))

    tests.append(run("VALID-002 walking -> running", valid_walking(), valid_running(),
                     "run", 0.6, ["E2"], True))

    # Contract violations.
    tests.append(run("INVALID-001 zero-duration physical", base(), valid_walking(),
                     "walk", 0, ["E3"], False))

    tests.append(run("INVALID-002 negative duration", base(), valid_walking(),
                     "walk", -0.1, ["E4"], False))

    tests.append(run("INVALID-003 unknown transition type", base(), valid_walking(),
                     "fly", 0.5, ["E5"], False))

    bad = valid_running()
    tests.append(run("INVALID-004 impossible stand -> running via walk", base(), bad,
                     "walk", 0.5, ["E6"], False))

    no_event = valid_walking()
    tests.append(run("INVALID-005 significant transition without causal event",
                     base(), no_event, "walk", 0.5, [], False))

    teleport = valid_walking()
    teleport["position"]["x"] = 999
    tests.append(run("INVALID-006 position teleport under turn",
                     base(), teleport, "turn", 0.5, ["E7"], False))

    orient = deepcopy(base())
    orient["body"]["orientation"] = "profile_left"
    tests.append(run("VALID-003 orientation change under turn",
                     base(), orient, "turn", 0.5, ["E8"], True))

    same_orient = deepcopy(base())
    tests.append(run("INVALID-007 turn without orientation change",
                     base(), same_orient, "turn", 0.5, ["E9"], False))

    idle_walk = valid_walking()
    idle_walk["body"]["movement_phase"] = "idle"
    tests.append(run("INVALID-008 walking with idle phase",
                     base(), idle_walk, "walk", 0.5, ["E10"], False))

    fall = valid_falling()
    tests.append(run("INVALID-009 falling without cause",
                     base(), fall, "fall", 0.5, [], False))

    fall_grounded = valid_falling()
    fall_grounded["body"]["feet"] = "grounded"
    tests.append(run("INVALID-010 falling while grounded",
                     base(), fall_grounded, "fall", 0.5, ["E11"], False))

    clothing = valid_walking()
    clothing["clothing"]["damage"] = True
    tests.append(run("INVALID-011 clothing continuity break",
                     base(), clothing, "walk", 0.5, ["E12"], False))

    identity = valid_walking()
    identity["character_id"] = "other"
    tests.append(run("INVALID-012 character identity mutation",
                     base(), identity, "walk", 0.5, ["E13"], False))

    bodylock = valid_walking()
    bodylock["continuity"]["body_structure_locked"] = False
    tests.append(run("INVALID-013 body structure lock broken",
                     base(), bodylock, "walk", 0.5, ["E14"], False))

    pos_only = deepcopy(base())
    pos_only["position"]["x"] = 2
    tests.append(run("INVALID-014 position change without locomotion transition",
                     base(), pos_only, "gesture", 0.5, ["E15"], False))

    env = valid_walking()
    env["environment_interaction"]["collision_aware"] = False
    tests.append(run("INVALID-015 collision awareness disabled",
                     base(), env, "walk", 0.5, ["E16"], False))

    env2 = valid_walking()
    env2["environment_interaction"]["spatially_valid"] = False
    tests.append(run("INVALID-016 spatial validity disabled",
                     base(), env2, "walk", 0.5, ["E17"], False))

    physical = valid_walking()
    physical["body"]["physical_condition"] = "supernaturally_empowered"
    tests.append(run("INVALID-017 supernatural physical change without cause",
                     base(), physical, "walk", 0.5, [], False))

    supernatural = deepcopy(base())
    supernatural["body"]["physical_condition"] = "supernaturally_empowered"
    supernatural["causal_event_ids"] = ["E18"]
    tests.append(run("VALID-004 instantaneous supernatural transition",
                     base(), supernatural, "supernatural", 0, ["E18"], True))

    supernatural_no_event = deepcopy(base())
    supernatural_no_event["body"]["physical_condition"] = "supernaturally_empowered"
    tests.append(run("INVALID-018 supernatural transition without cause",
                     base(), supernatural_no_event, "supernatural", 0, [], False))

    negative_event_type = valid_walking()
    tests.append(run("INVALID-019 causal_event_ids not a list",
                     base(), negative_event_type, "walk", 0.5, "E19", False))

    noop = deepcopy(base())
    tests.append(run("INVALID-020 non-idle transition with no state change",
                     base(), noop, "walk", 0.5, ["E20"], False))

    # State mutation that creates a physically impossible next state.
    bad_state = valid_walking()
    bad_state["body"]["feet"] = "grounded"
    bad_state["body"]["weight_distribution"] = "airborne"
    tests.append(run("INVALID-021 walking state with contradictory airborne weight",
                     base(), bad_state, "walk", 0.5, ["E21"], False))

    print("=" * 60)
    print("DEATHBOUND — PHASE 5F")
    print("RIVEN MOTION TRANSITION ADVERSARIAL QA")
    print("=" * 60)
    passed = sum(tests)
    failed = len(tests) - passed
    print(f"TESTS: {len(tests)}")
    print(f"PASS: {passed}")
    print(f"FAIL: {failed}")
    print(f"OVERALL: {'PASS' if failed == 0 else 'FAIL'}")
    print("=" * 60)
    raise SystemExit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
