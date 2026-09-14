import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
sys.path.insert(0, str(ROOT / "automation" / "scripts"))

from lighting_effects_performance_engine import (
    validate_lighting,
    validate_lighting_transition,
    validate_effect,
    validate_effect_causality,
    validate_effect_transition,
    validate_environment_effect_alignment,
    validate_performance_effect_coupling,
    validate_effect_shot
)


def base_lighting():
    return {
        "lighting_state": "night",
        "source_type": "interior",
        "intensity": 0.5,
        "direction": {"x": 0, "y": -1, "z": 0},
        "color_temperature": 4200
    }


def base_effect(effect_type="none"):
    return {
        "effect_id": "fx_01",
        "effect_type": effect_type,
        "active": effect_type != "none"
    }


def base_shot():
    return {
        "lighting": base_lighting(),
        "environment": {
            "weather": "clear"
        },
        "effects": [
            base_effect()
        ],
        "character_performance": {
            "performance_intent": "observe",
            "emotion": "neutral"
        }
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
    "VALID-001 valid lighting state",
    validate_lighting(base_lighting()),
    True
))

# VALID 002
current = base_lighting()
current["lighting_state"] = "dramatic"
current["continuity"] = {
    "transition": True
}

tests.append(run_test(
    "VALID-002 intentional lighting transition",
    validate_lighting_transition(base_lighting(), current),
    True
))

# VALID 003
effect = base_effect("reaper_glow")
effect["causal_event_id"] = "EVT-REAPER-001"
effect["supernatural_state"] = {
    "active": True
}

tests.append(run_test(
    "VALID-003 causal reaper glow",
    validate_effect_causality(effect),
    True
))

# VALID 004
effect = base_effect("ledger_glow")
effect["causal_event_id"] = "EVT-LEDGER-001"
effect["ledger_state"] = {
    "active": True
}

tests.append(run_test(
    "VALID-004 causal Ledger glow",
    validate_effect_causality(effect),
    True
))

# VALID 005
effect = base_effect("energy_pulse")
effect["causal_event_id"] = "EVT-PULSE-001"
effect["pulse_trigger"] = "ledger_activation"

tests.append(run_test(
    "VALID-005 triggered energy pulse",
    validate_effect_causality(effect),
    True
))

# VALID 006
previous = base_effect("reaper_glow")
previous["active"] = True
previous["causal_event_id"] = "EVT-001"
previous["supernatural_state"] = {"active": True}

current = dict(previous)
current["active"] = False
current["natural_completion"] = True

tests.append(run_test(
    "VALID-006 natural effect completion",
    validate_effect_transition(previous, current),
    True
))

# VALID 007
effect = base_effect("rain")

tests.append(run_test(
    "VALID-007 rain matches weather",
    validate_environment_effect_alignment(
        {"weather": "rain"},
        effect
    ),
    True
))

# VALID 008
effects = [
    {
        **base_effect("reaper_glow"),
        "causal_event_id": "EVT-ACTIVATE",
        "supernatural_state": {"active": True}
    }
]

tests.append(run_test(
    "VALID-008 supernatural performance coupling",
    validate_performance_effect_coupling(
        {
            "performance_intent": "supernatural_activation",
            "emotion": "neutral"
        },
        effects
    ),
    True
))

# VALID 009
shot = base_shot()
shot["effects"] = [
    {
        **base_effect("reaper_glow"),
        "causal_event_id": "EVT-001",
        "supernatural_state": {"active": True}
    }
]
shot["character_performance"] = {
    "performance_intent": "supernatural_activation",
    "emotion": "neutral"
}

tests.append(run_test(
    "VALID-009 complete supernatural shot",
    validate_effect_shot(shot),
    True
))

# INVALID 001
lighting = base_lighting()
lighting["lighting_state"] = "invalid_state"

tests.append(run_test(
    "INVALID-001 invalid lighting state",
    validate_lighting(lighting),
    False
))

# INVALID 002
previous = base_lighting()
current = base_lighting()
current["lighting_state"] = "blackout"

tests.append(run_test(
    "INVALID-002 unexplained blackout",
    validate_lighting_transition(previous, current),
    False
))

# INVALID 003
effect = base_effect("reaper_glow")

tests.append(run_test(
    "INVALID-003 reaper glow without cause",
    validate_effect_causality(effect),
    False
))

# INVALID 004
effect = base_effect("reaper_glow")
effect["causal_event_id"] = "EVT-001"

tests.append(run_test(
    "INVALID-004 reaper glow without supernatural state",
    validate_effect_causality(effect),
    False
))

# INVALID 005
effect = base_effect("ledger_glow")
effect["causal_event_id"] = "EVT-002"

tests.append(run_test(
    "INVALID-005 Ledger glow without Ledger state",
    validate_effect_causality(effect),
    False
))

# INVALID 006
effect = base_effect("rain")

tests.append(run_test(
    "INVALID-006 rain contradicts clear weather",
    validate_environment_effect_alignment(
        {"weather": "clear"},
        effect
    ),
    False
))

# INVALID 007
tests.append(run_test(
    "INVALID-007 supernatural activation without effect",
    validate_performance_effect_coupling(
        {
            "performance_intent": "supernatural_activation",
            "emotion": "neutral"
        },
        [base_effect()]
    ),
    False
))

# INVALID 008
shot = base_shot()
shot["character_motion_required"] = True
shot["static_frame_with_effect_overlay"] = True

tests.append(run_test(
    "INVALID-008 effect overlay replacing character motion",
    validate_effect_shot(shot),
    False
))

# INVALID 009
shot = base_shot()
shot["action_required"] = True
shot["effect_only_motion"] = True

tests.append(run_test(
    "INVALID-009 effect-only fake action",
    validate_effect_shot(shot),
    False
))

# INVALID 010
shot = base_shot()
shot["effect_loop_without_state_change"] = True

tests.append(run_test(
    "INVALID-010 repeated effect loop without state change",
    validate_effect_shot(shot),
    False
))

# INVALID 011
effect = base_effect("energy_pulse")
effect["causal_event_id"] = "EVT-PULSE"

tests.append(run_test(
    "INVALID-011 energy pulse without trigger",
    validate_effect_causality(effect),
    False
))

# INVALID 012
previous = base_effect("shadow_distortion")
previous["active"] = False

current = base_effect("shadow_distortion")
current["active"] = True

tests.append(run_test(
    "INVALID-012 unexplained effect activation",
    validate_effect_transition(previous, current),
    False
))

# INVALID 013
shot = base_shot()
shot["effects"] = [
    base_effect("reaper_glow"),
    base_effect("reaper_glow")
]
shot["effects"][0]["causal_event_id"] = "EVT-1"
shot["effects"][0]["supernatural_state"] = {"active": True}
shot["effects"][1]["causal_event_id"] = "EVT-2"
shot["effects"][1]["supernatural_state"] = {"active": True}

tests.append(run_test(
    "INVALID-013 duplicate effect identity",
    validate_effect_shot(shot),
    False
))

passed = sum(tests)
total = len(tests)

print("")
print("==============================================")
print("DEATHBOUND — PHASE 5J")
print("LIGHTING & EFFECTS PERFORMANCE ADVERSARIAL QA")
print(f"TESTS: {total}  PASS: {passed}  FAIL: {total - passed}")
print("OVERALL:", "PASS" if passed == total else "FAIL")
print("==============================================")

if passed != total:
    raise SystemExit(1)
