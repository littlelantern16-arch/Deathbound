import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
sys.path.insert(0, str(ROOT / "automation" / "scripts"))

from shot_integration_engine import validate_shot_integration


def base_shot():
    return {
        "shot_id": "SHOT-001",
        "duration_seconds": 4,
        "animation_tier": "standard",

        "character_performance": {
            "speaker": "riven",
            "performance_intent": "observe",
            "body": {
                "locomotion": "idle"
            },
            "facial": {
                "expression_changed": False
            }
        },

        "camera": {
            "movement": "static"
        },

        "environment": {
            "location_id": "office",
            "weather": "clear"
        },

        "spatial_state": {
            "character_positions": {
                "riven": {
                    "x": 0,
                    "y": 0,
                    "z": 0
                }
            },
            "prop_positions": {
                "phone_01": {
                    "x": 1,
                    "y": 0,
                    "z": 0
                }
            }
        },

        "props": [
            {
                "prop_id": "phone_01",
                "prop_type": "phone",
                "state": "active",
                "owner": "human",
                "position": {
                    "x": 1,
                    "y": 0,
                    "z": 0
                }
            }
        ],

        "lighting": {
            "lighting_state": "night"
        },

        "effects": [],

        "audio": {},

        "dialogue": {}
    }


def run_test(name, shot, should_pass):
    result = validate_shot_integration(shot)
    passed = result["valid"] == should_pass

    print(f"{'PASS' if passed else 'FAIL'} | {name}")

    if not passed:
        print("  errors:", result["errors"])

    return passed


tests = []

# VALID 001
tests.append(run_test(
    "VALID-001 complete integrated shot",
    base_shot(),
    True
))

# VALID 002
shot = base_shot()
shot["character_performance"]["performance_intent"] = "speak"
shot["dialogue"] = {
    "dialogue_id": "D001",
    "speaker": "riven",
    "text": "You have ten minutes.",
    "start_time": 0.5,
    "end_time": 2.5
}
shot["lip_sync"] = {
    "active": True
}

tests.append(run_test(
    "VALID-002 synchronized speech integration",
    shot,
    True
))

# VALID 003
shot = base_shot()
shot["character_performance"]["performance_intent"] = "supernatural_activation"
shot["character_performance"]["supernatural_state"] = {
    "active": True
}
shot["effects"] = [
    {
        "effect_id": "fx_001",
        "effect_type": "reaper_glow",
        "active": True
    }
]

tests.append(run_test(
    "VALID-003 supernatural integration",
    shot,
    True
))

# VALID 004
shot = base_shot()
shot["character_performance"]["body"]["locomotion"] = "walking"
shot["camera"]["movement"] = "tracking"

tests.append(run_test(
    "VALID-004 locomotion camera integration",
    shot,
    True
))

# VALID 005
shot = base_shot()
shot["environment"]["weather"] = "rain"
shot["effects"] = [
    {
        "effect_id": "fx_rain",
        "effect_type": "rain",
        "active": True
    }
]

tests.append(run_test(
    "VALID-005 weather effect integration",
    shot,
    True
))

# VALID 006
shot = base_shot()
shot["environment_interaction"] = {
    "actor": "riven",
    "target": "phone_01"
}

tests.append(run_test(
    "VALID-006 spatial prop integration",
    shot,
    True
))

# VALID 007
shot = base_shot()
shot["character_performance"]["performance_intent"] = "react"
shot["character_performance"]["performance_change"] = True

tests.append(run_test(
    "VALID-007 reaction integration",
    shot,
    True
))

# VALID 008
shot = base_shot()
shot["character_performance"]["performance_intent"] = "speak"
shot["dialogue"] = {
    "dialogue_id": "D002",
    "speaker": "riven",
    "text": "Look at me.",
    "start_time": 0.2,
    "end_time": 1.2
}
shot["lip_sync"] = {
    "active": True
}
shot["audio"] = {
    "start_time": 0.2,
    "end_time": 1.2
}

tests.append(run_test(
    "VALID-008 audio timing integration",
    shot,
    True
))

# INVALID 001
shot = base_shot()
shot["character_performance"]["performance_intent"] = "speak"

tests.append(run_test(
    "INVALID-001 speech without dialogue",
    shot,
    False
))

# INVALID 002
shot = base_shot()
shot["character_performance"]["performance_intent"] = "speak"
shot["dialogue"] = {
    "speaker": "daniel",
    "text": "Hello",
    "start_time": 0,
    "end_time": 1
}
shot["lip_sync"] = {
    "active": True
}

tests.append(run_test(
    "INVALID-002 speaker contradiction",
    shot,
    False
))

# INVALID 003
shot = base_shot()
shot["character_performance"]["performance_intent"] = "supernatural_activation"
shot["character_performance"]["supernatural_state"] = {
    "active": True
}

tests.append(run_test(
    "INVALID-003 supernatural activation without effect",
    shot,
    False
))

# INVALID 004
shot = base_shot()
shot["character_performance"]["body"]["locomotion"] = "walking"
shot["camera"]["movement"] = "crane"

tests.append(run_test(
    "INVALID-004 locomotion camera contradiction",
    shot,
    False
))

# INVALID 005
shot = base_shot()
shot["environment"]["weather"] = "clear"
shot["effects"] = [
    {
        "effect_id": "fx_rain",
        "effect_type": "rain",
        "active": True
    }
]

tests.append(run_test(
    "INVALID-005 weather effect contradiction",
    shot,
    False
))

# INVALID 006
shot = base_shot()
shot["props"][0]["position"] = {
    "x": 9,
    "y": 0,
    "z": 0
}

tests.append(run_test(
    "INVALID-006 prop spatial contradiction",
    shot,
    False
))

# INVALID 007
shot = base_shot()
shot["environment_interaction"] = {
    "actor": "riven",
    "target": "missing_prop"
}

tests.append(run_test(
    "INVALID-007 undefined interaction target",
    shot,
    False
))

# INVALID 008
shot = base_shot()
shot["spatial_action_required"] = True
shot["camera_only_motion"] = True

tests.append(run_test(
    "INVALID-008 camera-only spatial substitution",
    shot,
    False
))

# INVALID 009
shot = base_shot()
shot["character_motion_required"] = True
shot["static_character_with_effect_overlay"] = True

tests.append(run_test(
    "INVALID-009 effect slideshow substitution",
    shot,
    False
))

# INVALID 010
shot = base_shot()
shot["dialogue_performance_required"] = True
shot["voiceover_over_static_character"] = True

tests.append(run_test(
    "INVALID-010 voiceover slideshow substitution",
    shot,
    False
))

# INVALID 011
shot = base_shot()
shot["prop_action_required"] = True
shot["camera_only_prop_action"] = True

tests.append(run_test(
    "INVALID-011 camera-only prop substitution",
    shot,
    False
))

# INVALID 012
shot = base_shot()
shot["duration_seconds"] = 20

tests.append(run_test(
    "INVALID-012 excessive shot duration",
    shot,
    False
))

# INVALID 013
shot = base_shot()
shot["dialogue"] = {
    "speaker": "riven",
    "text": "Too late.",
    "start_time": 3,
    "end_time": 5
}

tests.append(run_test(
    "INVALID-013 dialogue exceeds shot duration",
    shot,
    False
))

# INVALID 014
shot = base_shot()
shot["audio"] = {
    "start_time": 0,
    "end_time": 8
}

tests.append(run_test(
    "INVALID-014 audio exceeds shot duration",
    shot,
    False
))

# INVALID 015
shot = base_shot()
shot["environment"]["lighting_state"] = "night"
shot["lighting"]["lighting_state"] = "daylight"

tests.append(run_test(
    "INVALID-015 lighting contradiction",
    shot,
    False
))

# INVALID 016
shot = base_shot()
shot["character_performance"]["performance_intent"] = "react"
shot["character_performance"]["performance_change"] = False
shot["character_performance"]["facial"]["expression_changed"] = False
shot["character_performance"]["body"]["motion_changed"] = False

tests.append(run_test(
    "INVALID-016 fake reaction",
    shot,
    False
))

# INVALID 017
shot = base_shot()
del shot["props"]

tests.append(run_test(
    "INVALID-017 missing prop system",
    shot,
    False
))

# INVALID 018
shot = base_shot()
shot["camera"]["movement"] = "static"
shot["character_performance"]["camera_only_animation"] = True

tests.append(run_test(
    "INVALID-018 camera replacing performance",
    shot,
    False
))

passed = sum(tests)
total = len(tests)

print("")
print("==============================================")
print("DEATHBOUND — PHASE 5L")
print("SHOT INTEGRATION & PRE-RENDER ADVERSARIAL QA")
print(f"TESTS: {total}  PASS: {passed}  FAIL: {total - passed}")
print("OVERALL:", "PASS" if passed == total else "FAIL")
print("==============================================")

if passed != total:
    raise SystemExit(1)
