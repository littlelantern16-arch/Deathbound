import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
sys.path.insert(0, str(ROOT / "automation" / "scripts"))

from object_prop_performance_engine import (
    validate_prop,
    validate_prop_transition,
    validate_prop_interaction,
    validate_prop_action,
    validate_prop_shot
)


def base_prop():
    return {
        "prop_id": "phone_01",
        "prop_type": "phone",
        "state": "active",
        "owner": "human",
        "position": {
            "x": 1,
            "y": 0,
            "z": 0
        },
        "continuity": {},
        "pickupable": True,
        "openable": False,
        "usable": True
    }


def run_test(name, result, should_pass):
    passed = result["valid"] == should_pass

    print(f"{'PASS' if passed else 'FAIL'} | {name}")

    if not passed:
        print("  errors:", result["errors"])

    return passed


tests = []

# VALID 001
tests.append(run_test(
    "VALID-001 valid persistent prop",
    validate_prop(base_prop()),
    True
))

# VALID 002
previous = base_prop()
current = base_prop()
current["position"] = {"x": 3, "y": 0, "z": 0}

tests.append(run_test(
    "VALID-002 valid prop movement",
    validate_prop_transition(previous, current),
    True
))

# VALID 003
prop = base_prop()
tests.append(run_test(
    "VALID-003 reachable pickup",
    validate_prop_interaction(
        prop,
        {
            "type": "pickup",
            "actor": "riven",
            "distance": 1.0
        }
    ),
    True
))

# VALID 004
prop = base_prop()
prop["openable"] = True

tests.append(run_test(
    "VALID-004 valid open interaction",
    validate_prop_interaction(
        prop,
        {
            "type": "open",
            "actor": "riven",
            "distance": 1.0
        }
    ),
    True
))

# VALID 005
prop = base_prop()
tests.append(run_test(
    "VALID-005 valid put-down",
    validate_prop_interaction(
        prop,
        {
            "type": "put_down",
            "actor": "riven",
            "surface_valid": True
        }
    ),
    True
))

# VALID 006
prop = base_prop()
prop["owner"] = "riven"

current = base_prop()
current["owner"] = "riven"
current["continuity"] = {
    "ownership_change_event": "EVT-TRANSFER-001"
}

tests.append(run_test(
    "VALID-006 causal ownership transfer",
    validate_prop_transition(prop, current),
    True
))

# VALID 007
prop = base_prop()

shot = {
    "props": [prop],
    "prop_action_required": True,
    "prop_action": {
        "type": "pickup",
        "state_change": True,
        "causal_event_id": "EVT-PICKUP-001"
    }
}

tests.append(run_test(
    "VALID-007 actual required prop action",
    validate_prop_shot(shot),
    True
))

# VALID 008
prop = base_prop()

shot = {
    "props": [prop],
    "prop_action_required": True,
    "prop_action": {
        "type": "activate",
        "state_change": True,
        "causal_event_id": "EVT-ACTIVATE-001"
    }
}

tests.append(run_test(
    "VALID-008 causal activation",
    validate_prop_shot(shot),
    True
))

# INVALID 001
prop = base_prop()
prop["prop_id"] = ""

tests.append(run_test(
    "INVALID-001 empty prop identity",
    validate_prop(prop),
    False
))

# INVALID 002
previous = base_prop()
current = base_prop()
current["position"] = {"x": 100, "y": 0, "z": 0}

tests.append(run_test(
    "INVALID-002 prop teleportation",
    validate_prop_transition(previous, current),
    False
))

# INVALID 003
previous = base_prop()
current = base_prop()
current["owner"] = "riven"

tests.append(run_test(
    "INVALID-003 silent ownership change",
    validate_prop_transition(previous, current),
    False
))

# INVALID 004
previous = base_prop()
current = base_prop()
current["state"] = "destroyed"

tests.append(run_test(
    "INVALID-004 unexplained state change",
    validate_prop_transition(previous, current),
    False
))

# INVALID 005
prop = base_prop()

tests.append(run_test(
    "INVALID-005 unreachable pickup",
    validate_prop_interaction(
        prop,
        {
            "type": "pickup",
            "actor": "riven",
            "distance": 10
        }
    ),
    False
))

# INVALID 006
prop = base_prop()

tests.append(run_test(
    "INVALID-006 invalid open",
    validate_prop_interaction(
        prop,
        {
            "type": "open",
            "actor": "riven",
            "distance": 1
        }
    ),
    False
))

# INVALID 007
prop = base_prop()

tests.append(run_test(
    "INVALID-007 invalid put-down surface",
    validate_prop_interaction(
        prop,
        {
            "type": "put_down",
            "actor": "riven",
            "surface_valid": False
        }
    ),
    False
))

# INVALID 008
prop = base_prop()

shot = {
    "props": [prop],
    "prop_action_required": True,
    "prop_action": {
        "type": "pickup",
        "state_change": False
    }
}

tests.append(run_test(
    "INVALID-008 fake required prop action",
    validate_prop_shot(shot),
    False
))

# INVALID 009
prop = base_prop()

shot = {
    "props": [prop],
    "prop_action": {
        "type": "destroy",
        "state_change": True
    }
}

tests.append(run_test(
    "INVALID-009 destruction without causal event",
    validate_prop_shot(shot),
    False
))

# INVALID 010
prop = base_prop()

shot = {
    "props": [prop],
    "prop_action": {
        "type": "pickup",
        "state_change": True,
        "camera_only_substitute": True
    }
}

tests.append(run_test(
    "INVALID-010 camera substitution for prop action",
    validate_prop_shot(shot),
    False
))

# INVALID 011
prop = base_prop()

tests.append(run_test(
    "INVALID-011 invalid prop interaction type",
    validate_prop_interaction(
        prop,
        {
            "type": "teleport",
            "actor": "riven"
        }
    ),
    False
))

# INVALID 012
prop = base_prop()
prop["owner"] = "unknown_entity"

tests.append(run_test(
    "INVALID-012 invalid owner",
    validate_prop(prop),
    False
))

passed = sum(tests)
total = len(tests)

print("")
print("==============================================")
print("DEATHBOUND — PHASE 5I")
print("OBJECT & PROP PERFORMANCE ADVERSARIAL QA")
print(f"TESTS: {total}  PASS: {passed}  FAIL: {total - passed}")
print("OVERALL:", "PASS" if passed == total else "FAIL")
print("==============================================")

if passed != total:
    raise SystemExit(1)
