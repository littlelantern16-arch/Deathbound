import json
import copy
import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
CONFIG = ROOT / "config"
PROJECT = ROOT / "projects" / "EP001"
SCRIPT = ROOT / "automation" / "scripts" / "riven_performance_engine.py"

SCHEMA = CONFIG / "RIVEN_PERFORMANCE_SCHEMA.json"
BODY_SCHEMA = CONFIG / "BODY_MOTION_SCHEMA.json"
FACIAL_SCHEMA = CONFIG / "FACIAL_ANIMATION_SCHEMA.json"
CANON = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"

def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

PERFORMANCE_SCHEMA = load_json(SCHEMA)
BODY_SCHEMA_DATA = load_json(BODY_SCHEMA)
FACIAL_SCHEMA_DATA = load_json(FACIAL_SCHEMA)
CANON_DATA = load_json(CANON)

print("=" * 64)
print("DEATHBOUND — PHASE 5E-4C")
print("RIVEN UNIFIED PERFORMANCE ADVERSARIAL QA")
print("=" * 64)

# ------------------------------------------------------------------
# Load engine module
# ------------------------------------------------------------------

sys.path.insert(0, str(SCRIPT.parent))

try:
    import riven_performance_engine as engine
except Exception as e:
    print(f"FAIL — Could not import performance engine: {e}")
    sys.exit(1)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def deep_find_callable(module, candidates):
    for name in candidates:
        fn = getattr(module, name, None)
        if callable(fn):
            return fn
    return None

validate_fn = deep_find_callable(
    engine,
    [
        "validate_performance_state",
        "validate_performance",
        "validate_state",
        "validate"
    ]
)

if validate_fn is None:
    print("FAIL — Could not locate performance validation function.")
    print("Available callables:")
    for name in dir(engine):
        if not name.startswith("_") and callable(getattr(engine, name)):
            print("  ", name)
    sys.exit(1)

# ------------------------------------------------------------------
# Baseline state
# ------------------------------------------------------------------

def make_baseline():
    """
    Construct a baseline state using the engine's own smoke-test
    factory when available. Otherwise use a conservative explicit
    state matching the locked architecture.
    """

    factories = [
        "build_valid_state",
        "make_valid_state",
        "create_valid_state",
        "build_state",
        "make_state"
    ]

    for name in factories:
        fn = getattr(engine, name, None)
        if callable(fn):
            try:
                state = fn()
                if isinstance(state, dict):
                    return state
            except TypeError:
                pass

    return {
        "performance_id": "QA-BASELINE",
        "shot_id": "QA-SHOT-001",
        "scene_id": "QA-SCENE-001",
        "character_id": "riven",
        "motion_tier": "standard",
        "performance_intent": "observe",
        "emotion": "neutral",

        "body": {
            "posture": "standing",
            "locomotion": "stationary",
            "orientation": "front",
            "head_orientation": "forward",
            "arms": "relaxed",
            "hands": "relaxed",
            "legs": "neutral",
            "feet": "grounded",
            "weight_distribution": "balanced",
            "movement_phase": "idle",
            "physical_condition": "normal"
        },

        "facial": {
            "emotion": "neutral",
            "eyes": "normal",
            "brows": "neutral",
            "mouth": "closed",
            "gaze_target": "scene",
            "gaze": {
                "direction": "forward",
                "target_type": "environment"
            },
            "blink": False,
            "blink_intensity": 0.0,
            "micro_expression": None,
            "performance_intensity": 0.3,
            "dialogue": {
                "active": False,
                "text": "",
                "lip_sync_required": False
            }
        },

        "gaze": {
            "direction": "forward",
            "target_type": "environment"
        },

        "gaze_target": "scene",

        "dialogue": {
            "active": False,
            "text": "",
            "lip_sync_required": False
        },

        "supernatural": {
            "active": False,
            "eye_glow": False,
            "body_effect": False,
            "causal_event_id": None
        },

        "continuity": {
            "identity_locked": True,
            "appearance_locked": True,
            "clothing_locked": True,
            "emotion_locked": True,
            "dialogue_locked": True,
            "causality_locked": True,
            "body_locked": True,
            "face_locked": True,
            "gaze_locked": True,
            "props_locked": True
        },

        "continuity_locks": {
            "identity": True,
            "appearance": True,
            "clothing": True,
            "emotion": True,
            "body": True,
            "facial": True,
            "gaze": True,
            "props": True
        },

        "causal_event_ids": []
    }


BASELINE = make_baseline()

# ------------------------------------------------------------------
# Validation adapter
# ------------------------------------------------------------------

def validate_state(state):
    """Call the production validator with its complete contract."""
    try:
        result = validate_fn(
            state,
            PERFORMANCE_SCHEMA,
            BODY_SCHEMA_DATA,
            FACIAL_SCHEMA_DATA,
            CANON_DATA
        )

        if isinstance(result, tuple):
            ok = bool(result[0])
            errors = result[1] if len(result) > 1 else []
            return (
                ok,
                list(errors)
                if isinstance(errors, (list, tuple))
                else [str(errors)]
            )

        if isinstance(result, dict):
            if "accepted" in result:
                errors = result.get("errors", [])
                return (
                    bool(result["accepted"]),
                    list(errors)
                    if isinstance(errors, list)
                    else [str(errors)]
                )

        if isinstance(result, bool):
            return result, []

        return bool(result), []

    except Exception as e:
        return False, [f"ENGINE EXCEPTION: {e}"]

# ------------------------------------------------------------------
# Test mutations
# ------------------------------------------------------------------

def mutate(name, mutation):
    state = copy.deepcopy(BASELINE)
    mutation(state)
    return name, state


TESTS = [

    mutate(
        "VALID-001 Baseline unified performance",
        lambda s: None
    ),

    mutate(
        "INVALID-001 Body/facial emotion mismatch",
        lambda s: (
            s["body"].update({"posture": "defensive"}),
            s["facial"].update({"emotion": "afraid"}),
            s.update({"emotion": "curious"})
        )
    ),

    mutate(
        "INVALID-002 Unified/facial emotion mismatch",
        lambda s: (
            s.update({"emotion": "curious"}),
            s["facial"].update({"emotion": "sad"})
        )
    ),

    mutate(
        "INVALID-003 Invalid performance intent",
        lambda s: s.update({"performance_intent": "teleport"})
    ),

    mutate(
        "INVALID-004 Invalid motion tier",
        lambda s: s.update({"motion_tier": "cinematic_ultra"})
    ),

    mutate(
        "INVALID-005 Unknown unified emotion",
        lambda s: s.update({"emotion": "joyful"})
    ),

    mutate(
        "INVALID-006 Gaze target mismatch",
        lambda s: (
            s["gaze"].update({
                "direction": "forward",
                "target_type": "subject"
            }),
            s["facial"]["gaze"].update({
                "direction": "forward",
                "target_type": "environment"
            })
        )
    ),

    mutate(
        "INVALID-007 Dialogue active with closed mouth",
        lambda s: (
            s["dialogue"].update({
                "active": True,
                "text": "Daniel, listen to me.",
                "lip_sync_required": True
            }),
            s["facial"]["dialogue"].update({
                "active": True,
                "text": "Daniel, listen to me.",
                "lip_sync_required": True
            }),
            s["facial"].update({"mouth": "closed"})
        )
    ),

    mutate(
        "INVALID-008 Mouth speaking without dialogue",
        lambda s: s["facial"].update({"mouth": "speaking"})
    ),

    mutate(
        "INVALID-009 Dialogue without lip sync",
        lambda s: (
            s["dialogue"].update({
                "active": True,
                "text": "Hello.",
                "lip_sync_required": False
            }),
            s["facial"]["dialogue"].update({
                "active": True,
                "text": "Hello.",
                "lip_sync_required": False
            }),
            s["facial"].update({"mouth": "speaking"})
        )
    ),

    mutate(
        "INVALID-010 Supernatural eyes without causal event",
        lambda s: (
            s["supernatural"].update({
                "active": True,
                "eye_glow": True,
                "causal_event_id": None
            }),
            s["facial"].update({"eyes": "glowing"})
        )
    ),

    mutate(
        "INVALID-011 Supernatural body effect without causal event",
        lambda s: s.update({
            "body": {**s["body"], "physical_condition": "supernaturally_empowered"},
            "causal_event_ids": []
        })
    ),

    mutate(
        "INVALID-012 Observe intent with running locomotion",
        lambda s: (
            s["body"].update({"locomotion": "running"}),
            s.update({"performance_intent": "observe"})
        )
    ),

    mutate(
        "INVALID-013 Speak intent with completely idle performance",
        lambda s: (
            s.update({"performance_intent": "speak"}),
            s["dialogue"].update({
                "active": True,
                "text": "We need to talk.",
                "lip_sync_required": True
            }),
            s["facial"]["dialogue"].update({
                "active": True,
                "text": "We need to talk.",
                "lip_sync_required": True
            }),
            s["facial"].update({"mouth": "speaking"}),
            s["body"].update({
                "posture": "standing",
                "locomotion": "stationary",
                "movement_phase": "idle"
            })
        )
    ),

    mutate(
        "INVALID-014 Broken identity continuity lock",
        lambda s: s["continuity"].update({"identity_locked": False})
    ),

    mutate(
        "INVALID-015 Broken clothing continuity lock",
        lambda s: s["continuity"].update({"clothing_locked": False})
    ),

    mutate(
        "INVALID-016 Broken facial continuity lock",
        lambda s: s["continuity"].update({"face_locked": False})
    ),

    mutate(
        "INVALID-017 Canonical identity mutation",
        lambda s: s.update({"character_id": "riven_clone"})
    ),

    mutate(
        "INVALID-018 Invalid physical condition",
        lambda s: s["body"].update({"physical_condition": "teleported"})
    ),

    mutate(
        "INVALID-019 Falling while grounded",
        lambda s: s["body"].update({
            "posture": "falling",
            "locomotion": "falling",
            "weight_distribution": "airborne",
            "feet": "grounded"
        })
    ),

    mutate(
        "INVALID-020 Unknown body posture",
        lambda s: s["body"].update({"posture": "floating_sideways"})
    ),

    mutate(
        "INVALID-021 Unknown facial eye state",
        lambda s: s["facial"].update({"eyes": "laser_eyes"})
    ),

    mutate(
        "INVALID-022 Unknown mouth state",
        lambda s: s["facial"].update({"mouth": "talking_magically"})
    ),

    mutate(
        "INVALID-023 Missing required performance intent",
        lambda s: s.pop("performance_intent", None)
    ),

    mutate(
        "INVALID-024 Missing unified emotion",
        lambda s: s.pop("emotion", None)
    ),

    mutate(
        "INVALID-025 Missing body state",
        lambda s: s.pop("body", None)
    ),

    mutate(
        "INVALID-026 Missing facial state",
        lambda s: s.pop("facial", None)
    ),

    mutate(
        "INVALID-027 Missing continuity locks",
        lambda s: s.pop("continuity", None)
    ),

    mutate(
        "INVALID-028 Supernatural activation without active flag",
        lambda s: s.update({
            "performance_intent": "supernatural_activation",
            "causal_event_ids": []
        })
    ),

    mutate(
        "INVALID-029 Dialogue text exists while dialogue inactive",
        lambda s: (
            s["dialogue"].update({
                "active": False,
                "text": "This should not exist.",
                "lip_sync_required": False
            }),
            s["facial"]["dialogue"].update({
                "active": True,
                "text": "This should not exist.",
                "lip_sync_required": False
            })
        )
    ),

    mutate(
        "INVALID-030 Multi-system contradiction",
        lambda s: (
            s.update({
                "character_id": "wrong_character",
                "performance_intent": "speak",
                "emotion": "joyful",
                "motion_tier": "invalid_tier",
                "gaze_target": "unknown_target"
            }),
            s["body"].update({
                "posture": "falling",
                "locomotion": "running",
                "feet": "grounded",
                "physical_condition": "teleported"
            }),
            s["facial"].update({
                "emotion": "afraid",
                "eyes": "laser_eyes",
                "mouth": "talking_magically",
                "gaze_target": "scene"
            }),
            s["supernatural"].update({
                "active": True,
                "eye_glow": True,
                "body_effect": True,
                "causal_event_id": None
            }),
            s["continuity_locks"].update({
                "identity": False,
                "clothing": False,
                "facial": False
            })
        )
    )
]

# ------------------------------------------------------------------
# Execute tests
# ------------------------------------------------------------------

passed = 0
failed = 0
unexpected = []

for name, state in TESTS:
    ok, errors = validate_state(state)

    is_valid_test = name.startswith("VALID-")
    expected_accept = is_valid_test

    if ok == expected_accept:
        passed += 1
        print(f"PASS {name}")
    else:
        failed += 1
        unexpected.append((name, ok, errors))
        print(f"FAIL {name}")
        print(f"      expected {'ACCEPT' if expected_accept else 'REJECT'}")
        print(f"      actual   {'ACCEPT' if ok else 'REJECT'}")
        if errors:
            print(f"      errors: {errors}")

# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------

print("-" * 64)
print(f"TESTS:      {len(TESTS)}")
print(f"PASS:       {passed}")
print(f"FAIL:       {failed}")
print(f"UNEXPECTED: {len(unexpected)}")
print("-" * 64)

if unexpected:
    print("UNEXPECTED RESULTS:")
    for name, ok, errors in unexpected:
        print(f"- {name}")
        print(f"  result: {'ACCEPT' if ok else 'REJECT'}")
        if errors:
            for error in errors:
                print(f"  error: {error}")

print("-" * 64)

if failed == 0:
    print("OVERALL: PASS")
    print("All unified-performance adversarial contradictions were rejected.")
else:
    print("OVERALL: FAIL")
    print("Unified performance integration requires hardening.")

print("=" * 64)

sys.exit(0 if failed == 0 else 1)
