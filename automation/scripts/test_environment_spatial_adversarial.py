import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
sys.path.insert(0, str(ROOT / "automation" / "scripts"))

from environment_spatial_performance_engine import validate_environment

def base_shot():
    return {
        "environment": {
            "location_id": "office",
            "spatial_layout": "office_layout_v1",
            "time_of_day": "night",
            "weather": "clear",
            "lighting": "overhead_dim",
            "environment_motion": "static",
            "interactive_objects": ["desk"]
        },
        "spatial_state": {
            "character_positions": {
                "riven": {"x": 0, "y": 0, "z": 0}
            },
            "prop_positions": {
                "desk": {"x": 1, "y": 0, "z": 0}
            },
            "walkable_regions": ["main_floor"],
            "obstacles": [],
            "exits": ["door"],
            "camera_safe_regions": ["center"]
        },
        "continuity": {},
        "character_performance": {
            "body": {
                "locomotion": "idle"
            }
        }
    }

def run_test(name, shot, should_pass):
    result = validate_environment(shot)
    passed = result["valid"] == should_pass

    print(
        f"{'PASS' if passed else 'FAIL'} | {name}"
    )

    if not passed:
        print("  errors:", result["errors"])

    return passed

tests = []

# VALID 001
tests.append(run_test(
    "VALID-001 stable environment",
    base_shot(),
    True
))

# VALID 002
shot = base_shot()
shot["environment"]["environment_motion"] = "wind"
shot["environment"]["motion_cause"] = "open_window"
tests.append(run_test(
    "VALID-002 causal environment motion",
    shot,
    True
))

# VALID 003
shot = base_shot()
shot["environment_interaction_required"] = True
shot["environment_interaction"] = {
    "actor": "riven",
    "target": "desk",
    "type": "touch"
}
tests.append(run_test(
    "VALID-003 valid spatial interaction",
    shot,
    True
))

# VALID 004
shot = base_shot()
shot["continuity"] = {
    "previous_location_id": "office"
}
tests.append(run_test(
    "VALID-004 location continuity",
    shot,
    True
))

# VALID 005
shot = base_shot()
shot["character_performance"]["body"]["locomotion"] = "walking"
tests.append(run_test(
    "VALID-005 walking with walkable region",
    shot,
    True
))

# VALID 006
shot = base_shot()
shot["continuity"] = {
    "previous_weather": "clear",
    "weather_transition": True
}
shot["environment"]["weather"] = "rain"
shot["environment"]["environment_motion"] = "rain"
shot["environment"]["motion_cause"] = "storm_front"
tests.append(run_test(
    "VALID-006 weather transition",
    shot,
    True
))

# INVALID 001
shot = base_shot()
shot["environment"]["location_id"] = "street"
shot["continuity"] = {
    "previous_location_id": "office"
}
tests.append(run_test(
    "INVALID-001 unexplained location change",
    shot,
    False
))

# INVALID 002
shot = base_shot()
shot["spatial_state"]["character_positions"]["riven"] = {
    "x": 100,
    "y": 0,
    "z": 0
}
shot["continuity"] = {
    "previous_character_positions": {
        "riven": {"x": 0, "y": 0, "z": 0}
    }
}
tests.append(run_test(
    "INVALID-002 character teleportation",
    shot,
    False
))

# INVALID 003
shot = base_shot()
shot["spatial_state"]["prop_positions"]["desk"] = {
    "x": 100,
    "y": 0,
    "z": 0
}
shot["continuity"] = {
    "previous_prop_positions": {
        "desk": {"x": 0, "y": 0, "z": 0}
    }
}
tests.append(run_test(
    "INVALID-003 prop teleportation",
    shot,
    False
))

# INVALID 004
shot = base_shot()
shot["environment"]["environment_motion"] = "wind"
tests.append(run_test(
    "INVALID-004 environment motion without cause",
    shot,
    False
))

# INVALID 005
shot = base_shot()
shot["environment"]["weather"] = "rain"
shot["continuity"] = {
    "previous_weather": "clear"
}
tests.append(run_test(
    "INVALID-005 weather discontinuity",
    shot,
    False
))

# INVALID 006
shot = base_shot()
shot["environment"]["time_of_day"] = "morning"
shot["continuity"] = {
    "previous_time_of_day": "night"
}
tests.append(run_test(
    "INVALID-006 time discontinuity",
    shot,
    False
))

# INVALID 007
shot = base_shot()
shot["environment"]["lighting"] = "sunset"
shot["continuity"] = {
    "previous_lighting": "overhead_dim"
}
tests.append(run_test(
    "INVALID-007 lighting discontinuity",
    shot,
    False
))

# INVALID 008
shot = base_shot()
shot["environment_interaction_required"] = True
tests.append(run_test(
    "INVALID-008 missing required interaction",
    shot,
    False
))

# INVALID 009
shot = base_shot()
shot["environment_interaction"] = {
    "actor": "riven",
    "target": "desk",
    "type": "pickup"
}
shot["spatial_state"]["character_positions"]["riven"] = {
    "x": 0,
    "y": 0,
    "z": 0
}
shot["spatial_state"]["prop_positions"]["desk"] = {
    "x": 10,
    "y": 0,
    "z": 0
}
tests.append(run_test(
    "INVALID-009 unreachable pickup",
    shot,
    False
))

# INVALID 010
shot = base_shot()
shot["spatial_action_required"] = True
shot["camera"] = {
    "movement": "static"
}
tests.append(run_test(
    "INVALID-010 camera-only spatial action",
    shot,
    False
))

passed = sum(tests)
total = len(tests)

print("")
print("==============================================")
print("DEATHBOUND — PHASE 5H")
print("ENVIRONMENT & SPATIAL PERFORMANCE ADVERSARIAL QA")
print(f"TESTS: {total}  PASS: {passed}  FAIL: {total - passed}")
print("OVERALL:", "PASS" if passed == total else "FAIL")
print("==============================================")

if passed != total:
    raise SystemExit(1)
