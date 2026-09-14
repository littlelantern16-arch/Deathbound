import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(r"D:\Deathbound")

SCHEMA_PATH = ROOT / "config" / "RIVEN_PERFORMANCE_SCHEMA.json"
BODY_SCHEMA_PATH = ROOT / "config" / "BODY_MOTION_SCHEMA.json"
FACIAL_SCHEMA_PATH = ROOT / "config" / "FACIAL_ANIMATION_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"

OUTPUT_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "characters"
    / "riven_performance_output.json"
)


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def make_base_performance():
    return {
        "performance_id": "PERF-001",
        "shot_id": "SHOT-001",
        "scene_id": "SCENE-001",

        "motion_tier": "standard",

        "emotion": "neutral",

        "body": {
            "posture": "standing",
            "locomotion": "stationary",
            "orientation": "front",
            "head_orientation": "forward",
            "arms": "relaxed",
            "hands": "none",
            "legs": "standing",
            "feet": "grounded",
            "weight_distribution": "balanced",
            "movement_phase": "idle",
            "physical_condition": "normal"
        },

        "facial": {
            "emotion": "neutral",
            "expression": "neutral",
            "eyes": "normal",
            "brows": "neutral",
            "mouth": "closed",
            "gaze": {
                "direction": "forward",
                "target_type": "environment",
                "attention": "normal"
            },
            "blink": {
                "active": False,
                "intensity": 0.0
            },
            "micro_expression": {
                "active": False,
                "type": None,
                "duration_ms": 0
            },
            "dialogue": {
                "active": False
            },
            "intensity": "low"
        },

        "gaze": {
            "direction": "forward",
            "target_type": "environment",
            "attention": "normal"
        },

        "dialogue": {
            "active": False,
            "dialogue_id": None,
            "voice_reference": None,
            "lip_sync_required": False
        },

        "performance_intent": "observe",

        "causal_event_ids": [],

        "continuity": {
            "identity_locked": True,
            "body_locked": True,
            "face_locked": True,
            "clothing_locked": True,
            "emotion_locked": True,
            "gaze_locked": True,
            "dialogue_locked": True,
            "causality_locked": True
        }
    }


def fail(message):
    return {
        "accepted": False,
        "errors": [message]
    }


def success():
    return {
        "accepted": True,
        "errors": []
    }


def validate_performance(performance, schema, body_schema,
                         facial_schema, canon):

    required = schema["performance_state"]["required_fields"]

    for field in required:
        if field not in performance:
            return fail(f"Missing performance field: {field}")

    if performance["performance_id"] == "":
        return fail("performance_id cannot be empty.")

    if performance["shot_id"] == "":
        return fail("shot_id cannot be empty.")

    if performance["scene_id"] == "":
        return fail("scene_id cannot be empty.")

    # ---------------------------------------------------------
    # Canonical identity
    # ---------------------------------------------------------

    canonical_id = canon.get("identity", {}).get("id")

    if canonical_id not in [None, "riven"]:
        return fail("Canonical identity mismatch.")

    runtime_id = performance.get("character_id", canonical_id)

    if runtime_id != canonical_id:
        return fail(
            "Performance character identity does not match canonical identity."
        )

    # ---------------------------------------------------------
    # Motion tier
    # ---------------------------------------------------------

    if performance["motion_tier"] not in body_schema["motion_tiers"]:
        return fail("Invalid motion tier.")

    # ---------------------------------------------------------
    # Intent
    # ---------------------------------------------------------

    intent = performance["performance_intent"]

    if intent not in schema["performance_intent"]["allowed_intents"]:
        return fail("Invalid performance intent.")

    # ---------------------------------------------------------
    # Emotion
    # ---------------------------------------------------------

    emotion = performance["emotion"]

    if emotion not in schema["emotion_alignment"]:
        return fail("Unknown unified emotion.")

    # Body and facial emotion must agree.
    if performance["facial"].get("emotion") != emotion:
        return fail("Body/facial emotion mismatch.")

    compatible_intents = schema["emotion_alignment"][emotion][
        "compatible_intents"
    ]

    if intent not in compatible_intents:
        return fail(
            f"Intent '{intent}' is incompatible with emotion '{emotion}'."
        )

    # ---------------------------------------------------------
    # Continuity
    # ---------------------------------------------------------

    for lock in schema["continuity"]["required_locks"]:
        if performance["continuity"].get(lock) is not True:
            return fail(f"Continuity lock disabled: {lock}")

    # ---------------------------------------------------------
    # Body validation
    # ---------------------------------------------------------

    body = performance["body"]

    for field in body_schema["body_state"]["required_fields"]:
        if field not in body:
            return fail(f"Missing body field: {field}")

    if body["posture"] not in body_schema["body_state"]["posture_states"]:
        return fail("Invalid body posture.")

    if body["locomotion"] not in body_schema["body_state"]["locomotion_states"]:
        return fail("Invalid body locomotion.")

    if body["orientation"] not in body_schema["body_state"]["orientation_states"]:
        return fail("Invalid body orientation.")

    if body["head_orientation"] not in body_schema["body_state"]["head_orientation_states"]:
        return fail("Invalid body head orientation.")

    if body["weight_distribution"] not in body_schema["body_state"]["weight_distribution_states"]:
        return fail("Invalid body weight distribution.")

    if body["movement_phase"] not in body_schema["body_state"]["movement_phase_states"]:
        return fail("Invalid body movement phase.")

    if body["physical_condition"] not in body_schema["body_state"]["physical_condition_states"]:
        return fail("Invalid physical condition.")

    # Basic physical consistency.
    if body["posture"] == "walking":
        if body["locomotion"] != "walking":
            return fail("Walking posture requires walking locomotion.")

    if body["posture"] == "running":
        if body["locomotion"] != "running":
            return fail("Running posture requires running locomotion.")

    if body["posture"] == "falling":
        if body["weight_distribution"] != "airborne":
            return fail("Falling requires airborne weight.")

        if body["feet"] == "grounded":
            return fail("Falling cannot have grounded feet.")

    if body["locomotion"] in ["walking", "running"]:
        if body["movement_phase"] == "idle":
            return fail("Active locomotion cannot have idle phase.")

    if body["physical_condition"] == "supernaturally_empowered":
        if not performance["causal_event_ids"]:
            return fail(
                "Supernatural body state requires causal event."
            )

    # ---------------------------------------------------------
    # Facial validation
    # ---------------------------------------------------------

    facial = performance["facial"]

    valid_emotions = facial_schema["emotion_profiles"]

    if isinstance(valid_emotions, dict):
        valid_emotions = list(valid_emotions.keys())

    if emotion not in valid_emotions:
        return fail("Emotion not present in facial schema.")

    eye_states = facial_schema.get("eye_system", {}).get("states", [])
    mouth_states = facial_schema.get("mouth_system", {}).get("states", [])

    if facial.get("eyes") not in eye_states:
        return fail("Invalid facial eye state.")

    if facial.get("mouth") not in mouth_states:
        return fail("Invalid facial mouth state.")

    if facial.get("eyes") == "glowing":
        if not performance["causal_event_ids"]:
            return fail(
                "Supernatural eye glow requires causal event."
            )

    # Dialogue / mouth.
    facial_dialogue = facial.get("dialogue", {})
    dialogue_active = performance["dialogue"].get("active") is True

    if dialogue_active:
        if facial.get("mouth") != "speaking":
            return fail(
                "Active dialogue requires speaking mouth state."
            )

        if not performance["dialogue"].get("dialogue_id"):
            return fail("Active dialogue requires dialogue ID.")

        if not performance["dialogue"].get("voice_reference"):
            return fail("Active dialogue requires voice reference.")

        if performance["dialogue"].get("lip_sync_required") is not True:
            return fail("Active dialogue requires lip-sync.")

        if facial_dialogue.get("active") is not True:
            return fail(
                "Active performance dialogue must match facial dialogue."
            )

    else:
        if facial.get("mouth") == "speaking":
            return fail(
                "Speaking mouth cannot exist without active dialogue."
            )

        if facial_dialogue.get("active") is True:
            return fail(
                "Facial dialogue cannot be active when performance dialogue is inactive."
            )

    # ---------------------------------------------------------
    # Gaze integration
    # ---------------------------------------------------------

    gaze = performance["gaze"]

    if not isinstance(gaze, dict):
        return fail("Gaze must be an object.")

    allowed_target_types = {
        "observe": ["subject", "environment"],
        "listen": ["speaker", "subject"],
        "speak": ["listener", "subject"],
        "question": ["listener", "subject"],
        "comfort": ["subject", "listener"],
        "threaten": ["subject", "listener"],
        "warn": ["subject", "environment"],
        "investigate": ["object", "environment", "subject"],
        "react": ["subject", "environment"],
        "supernatural_activation": ["subject", "environment"],
        "supernatural_intervention": ["subject", "environment"]
    }

    if intent in allowed_target_types:
        target = gaze.get("target_type")

        if target not in allowed_target_types[intent]:
            return fail(
                f"Gaze target '{target}' is incompatible with intent '{intent}'."
            )

    # Facial gaze must agree with unified gaze.
    facial_gaze = facial.get("gaze", {})

    if facial_gaze.get("direction") != gaze.get("direction"):
        return fail("Unified/facial gaze direction mismatch.")

    if facial_gaze.get("target_type") != gaze.get("target_type"):
        return fail("Unified/facial gaze target mismatch.")

    # ---------------------------------------------------------
    # Dialogue/body integration
    # ---------------------------------------------------------

    if dialogue_active:

        if (
            body["movement_phase"] == "idle"
            and body["posture"] == "standing"
        ):
            return fail(
                "Active dialogue cannot use completely idle standing performance."
            )

    # ---------------------------------------------------------
    # Intent/body compatibility
    # ---------------------------------------------------------

    if intent in ["observe", "listen", "investigate"]:
        if body["locomotion"] == "running":
            return fail(
                f"Intent '{intent}' contradicts running performance."
            )

    if intent == "comfort":
        if body["physical_condition"] == "restrained":
            return fail(
                "Restrained body state contradicts active comfort performance."
            )

    if intent == "threaten":
        if emotion not in ["angry", "determined", "afraid"]:
            return fail(
                "Threatening intent requires compatible emotional state."
            )

    if intent == "supernatural_activation":
        if not performance["causal_event_ids"]:
            return fail(
                "Supernatural activation requires causal event."
            )

        if (
            body["physical_condition"] != "supernaturally_empowered"
            and facial.get("eyes") != "glowing"
        ):
            return fail(
                "Supernatural activation requires body or facial activation."
            )

    # ---------------------------------------------------------
    # Canonical clothing/body protection
    # ---------------------------------------------------------

    if not performance["continuity"]["clothing_locked"]:
        return fail("Clothing continuity is not locked.")

    if not performance["continuity"]["body_locked"]:
        return fail("Body continuity is not locked.")

    if not performance["continuity"]["face_locked"]:
        return fail("Facial continuity is not locked.")

    return success()


def main():
    schema = load_json(SCHEMA_PATH)
    body_schema = load_json(BODY_SCHEMA_PATH)
    facial_schema = load_json(FACIAL_SCHEMA_PATH)
    canon = load_json(CANON_PATH)

    base = make_base_performance()

    print("=" * 64)
    print("DEATHBOUND — PHASE 5E-4B")
    print("RIVEN UNIFIED PERFORMANCE STATE ENGINE")
    print("=" * 64)

    tests = []

    def run(label, state, expected=True):
        result = validate_performance(
            state,
            schema,
            body_schema,
            facial_schema,
            canon
        )

        actual = result["accepted"]
        passed = actual == expected

        tests.append((label, passed, actual, expected))

        print(
            ("PASS" if passed else "FAIL"),
            label
        )

        if not passed:
            print("      errors:", result["errors"])

    # ---------------------------------------------------------
    # VALID BASELINE
    # ---------------------------------------------------------

    run(
        "VALID-001 — Unified observation state",
        base
    )

    # ---------------------------------------------------------
    # VALID DIALOGUE
    # ---------------------------------------------------------

    dialogue = deepcopy(base)

    dialogue["performance_id"] = "PERF-002"
    dialogue["performance_intent"] = "speak"
    dialogue["emotion"] = "calm" if "calm" in schema["emotion_alignment"] else "neutral"

    if dialogue["emotion"] == "neutral":
        dialogue["performance_intent"] = "explain"

    dialogue["facial"]["emotion"] = dialogue["emotion"]
    dialogue["facial"]["mouth"] = "speaking"

    dialogue["body"]["movement_phase"] = "action"
    dialogue["body"]["arms"] = "relaxed"

    dialogue["gaze"]["target_type"] = "listener"
    dialogue["facial"]["gaze"]["target_type"] = "listener"

    dialogue["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-001",
        "voice_reference": "voice/riven_001.wav",
        "lip_sync_required": True
    }

    dialogue["facial"]["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-001"
    }

    run(
        "VALID-002 — Unified dialogue state",
        dialogue
    )

    # ---------------------------------------------------------
    # VALID SUPERNATURAL
    # ---------------------------------------------------------

    supernatural = deepcopy(base)

    supernatural["performance_id"] = "PERF-003"
    supernatural["performance_intent"] = "supernatural_activation"
    supernatural["emotion"] = "determined"
    supernatural["facial"]["emotion"] = "determined"
    supernatural["facial"]["eyes"] = "glowing"

    supernatural["body"]["physical_condition"] = (
        "supernaturally_empowered"
    )
    supernatural["body"]["movement_phase"] = "action"

    supernatural["gaze"]["target_type"] = "subject"
    supernatural["facial"]["gaze"]["target_type"] = "subject"

    supernatural["causal_event_ids"] = [
        "EVENT-SUPERNATURAL-001"
    ]

    run(
        "VALID-003 — Unified supernatural activation",
        supernatural
    )

    # ---------------------------------------------------------
    # VALID REACTION
    # ---------------------------------------------------------

    reaction = deepcopy(base)

    reaction["performance_id"] = "PERF-004"
    reaction["performance_intent"] = "react"
    reaction["emotion"] = "surprised"
    reaction["facial"]["emotion"] = "surprised"
    reaction["body"]["movement_phase"] = "action"

    reaction["gaze"]["target_type"] = "subject"
    reaction["facial"]["gaze"]["target_type"] = "subject"

    run(
        "VALID-004 — Unified reaction state",
        reaction
    )

    # ---------------------------------------------------------
    # OUTPUT
    # ---------------------------------------------------------

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "schema_version": schema["schema_version"],
        "character_id": "riven",
        "system": "unified_performance",
        "smoke_tests": len(tests),
        "passed": sum(x[1] for x in tests),
        "failed": sum(not x[1] for x in tests)
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    failures = sum(not x[1] for x in tests)

    print("-" * 64)
    print(f"SMOKE TESTS: {len(tests)}")
    print(f"PASS: {len(tests) - failures}")
    print(f"FAIL: {failures}")
    print("-" * 64)

    if failures == 0:
        print("OVERALL: PASS")
        print("Unified performance gate is operational.")
    else:
        print("OVERALL: FAIL")
        print("Unified performance engine requires hardening.")

    print("=" * 64)


if __name__ == "__main__":
    main()

