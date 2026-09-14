import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(r"D:\Deathbound")

SCHEMA_PATH = ROOT / "config" / "CHARACTER_PERFORMANCE_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"
OUTPUT_PATH = ROOT / "projects" / "EP001" / "characters" / "riven_motion_engine_output.json"


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def fail(message):
    return {
        "accepted": False,
        "reason": message
    }


def accept(state):
    return {
        "accepted": True,
        "state": state
    }


def validate_state(state, schema, canon):
    required = schema["performance_state"]["required_fields"]

    for field in required:
        if field not in state:
            return fail(f"Missing required field: {field}")

    if state["character_id"] != "riven":
        return fail("Character identity mismatch.")

    body = state["body"]
    face = state["face"]
    gaze = state["gaze"]
    dialogue = state["dialogue"]
    continuity = state["continuity"]

    if body["posture"] not in schema["body_state"]["posture"]:
        return fail("Invalid body posture.")

    if body["movement"] not in schema["body_state"]["movement"]:
        return fail("Invalid body movement.")

    if body["movement_intensity"] not in schema["body_state"]["movement_intensity"]:
        return fail("Invalid movement intensity.")

    if face["expression"] not in schema["facial_state"]["expression"]:
        return fail("Invalid facial expression.")

    if face["eyes"] not in schema["facial_state"]["eyes"]:
        return fail("Invalid eye state.")

    if face["brows"] not in schema["facial_state"]["brows"]:
        return fail("Invalid eyebrow state.")

    if face["mouth"] not in schema["facial_state"]["mouth"]:
        return fail("Invalid mouth state.")

    if gaze["target_type"] not in schema["gaze_state"]["target_type"]:
        return fail("Invalid gaze target type.")

    if gaze["direction"] not in schema["gaze_state"]["direction"]:
        return fail("Invalid gaze direction.")

    if gaze["attention"] not in schema["gaze_state"]["attention"]:
        return fail("Invalid gaze attention.")

    if state["emotion"] not in schema["facial_state"]["expression"]:
        return fail("Invalid emotional state.")

    if state["intensity"] not in schema["body_state"]["movement_intensity"]:
        return fail("Invalid performance intensity.")

    # ---------------------------------------------------------
    # DIALOGUE / MOUTH CONSISTENCY
    # ---------------------------------------------------------

    dialogue_active = dialogue.get("active", False)
    mouth_speaking = face["mouth"] == "speaking"

    if mouth_speaking and not dialogue_active:
        return fail(
            "Mouth is speaking but no dialogue is active."
        )

    if dialogue_active:
        required = [
            "dialogue_id",
            "voice_reference"
        ]

        for field in required:
            if not dialogue.get(field):
                return fail(
                    f"Active dialogue missing required field: {field}"
                )

        if not dialogue.get("lip_sync_required", False):
            return fail(
                "Active dialogue must require lip sync."
            )

        if not mouth_speaking:
            return fail(
                "Active dialogue requires speaking mouth state."
            )

    # ---------------------------------------------------------
    # CONTINUITY LOCK PROTECTION
    # ---------------------------------------------------------

    if continuity.get("identity_locked") is not True:
        return fail(
            "Identity continuity lock cannot be disabled."
        )

    if continuity.get("clothing_locked") is not True:
        return fail(
            "Clothing continuity lock cannot be disabled."
        )

    if continuity.get("environment_locked") is not True:
        return fail(
            "Environment continuity lock cannot be disabled."
        )

    # ---------------------------------------------------------
    # PHYSICAL CONDITION PROTECTION
    # ---------------------------------------------------------

    allowed_conditions = [
        "normal",
        "injured",
        "severely_injured",
        "exhausted",
        "unconscious",
        "dead",
        "custom"
    ]

    if state["physical_condition"] not in allowed_conditions:
        return fail(
            "Invalid physical condition."
        )

    # Physical conditions other than normal must be causally grounded.
    # This protects against an injured/exhausted/unconscious state
    # appearing without a recorded story event.
    if state["physical_condition"] != "normal":
        if not state.get("causal_event_ids"):
            return fail(
                "Non-normal physical condition requires at least one "
                "causal event reference."
            )

    return accept(state)


def transition(previous, current, event=None):
    event = event or {}

    changes = []

    fields = [
        ("body.posture", previous["body"]["posture"], current["body"]["posture"]),
        ("body.movement", previous["body"]["movement"], current["body"]["movement"]),
        (
            "body.movement_intensity",
            previous["body"]["movement_intensity"],
            current["body"]["movement_intensity"]
        ),
        (
            "face.expression",
            previous["face"]["expression"],
            current["face"]["expression"]
        ),
        (
            "face.eyes",
            previous["face"]["eyes"],
            current["face"]["eyes"]
        ),
        (
            "gaze.target_type",
            previous["gaze"]["target_type"],
            current["gaze"]["target_type"]
        ),
        (
            "gaze.direction",
            previous["gaze"]["direction"],
            current["gaze"]["direction"]
        ),
        (
            "emotion",
            previous["emotion"],
            current["emotion"]
        ),
        (
            "physical_condition",
            previous["physical_condition"],
            current["physical_condition"]
        )
    ]

    for name, old, new in fields:
        if old != new:
            changes.append({
                "property": name,
                "previous": old,
                "new": new
            })

    if not changes:
        return accept(current)

    event_type = event.get("type")
    cause = event.get("cause")

    # ---------------------------------------------------------
    # PHYSICAL / POSTURE TRANSITIONS
    # ---------------------------------------------------------

    for change in changes:
        prop = change["property"]
        old = change["previous"]
        new = change["new"]

        if prop == "body.posture":

            valid_pairs = {
                ("standing", "walking"),
                ("walking", "standing"),
                ("sitting", "standing"),
                ("standing", "sitting"),
                ("walking", "running"),
                ("running", "walking"),
                ("standing", "crouching"),
                ("crouching", "standing")
            }

            if (old, new) not in valid_pairs:
                if not event_type:
                    return fail(
                        f"Unsupported posture transition without event: "
                        f"{old} -> {new}"
                    )

            # Crouching requires a deliberate transition.
            if new == "crouching" and event_type not in [
                "movement_transition",
                "crouch_transition",
                "action"
            ]:
                return fail(
                    "Entering crouching posture requires an explicit "
                    "movement/action transition."
                )

        # -----------------------------------------------------
        # SUPERNATURAL VISUAL STATE
        # -----------------------------------------------------

        if prop == "face.eyes" and new == "glowing":
            if event_type != "supernatural_activation":
                return fail(
                    "Eye glow requires supernatural_activation event."
                )

        # -----------------------------------------------------
        # EMOTIONAL TRANSITIONS
        # -----------------------------------------------------

        if prop == "emotion":
            major_emotions = [
                "afraid",
                "angry"
            ]

            if (
                old in ["calm", "neutral"]
                and new in major_emotions
                and not event_type
            ):
                return fail(
                    f"Major emotional transition requires causal event: "
                    f"{old} -> {new}"
                )

        # -----------------------------------------------------
        # GAZE CONTINUITY
        # -----------------------------------------------------

        if prop == "gaze.direction":
            if not event_type:
                return fail(
                    f"Gaze direction changed without explicit transition: "
                    f"{old} -> {new}"
                )

        # -----------------------------------------------------
        # PHYSICAL CONDITION
        # -----------------------------------------------------

        if prop == "physical_condition":
            if not event_type:
                return fail(
                    "Physical condition changed without causal event: "
                    f"{old} -> {new}"
                )

    # ---------------------------------------------------------
    # CURRENT STATE MUST ITSELF BE INTERNALLY VALID
    # ---------------------------------------------------------

    return accept(current)


def make_base_state():
    return {
        "character_id": "riven",
        "timestamp": 0.0,
        "shot_id": "SHOT-000",

        "body": {
            "posture": "standing",
            "movement": "idle",
            "movement_intensity": "none"
        },

        "face": {
            "expression": "calm",
            "eyes": "normal",
            "brows": "relaxed",
            "mouth": "closed"
        },

        "gaze": {
            "target_type": "character",
            "direction": "forward",
            "attention": "focused"
        },

        "dialogue": {
            "active": False,
            "dialogue_id": None,
            "voice_reference": None,
            "lip_sync_required": False
        },

        "emotion": "calm",
        "intensity": "none",
        "physical_condition": "normal",

        "continuity": {
            "clothing_locked": True,
            "identity_locked": True,
            "environment_locked": True
        },

        "causal_event_ids": []
    }


def run_tests(schema, canon):
    base = make_base_state()

    tests = []

    tests.append({
        "id": "VALID-001",
        "expected": True,
        "result": validate_state(base, schema, canon)["accepted"]
    })

    walking = deepcopy(base)
    walking["shot_id"] = "SHOT-001"
    walking["body"]["posture"] = "walking"
    walking["body"]["movement"] = "walk"
    walking["body"]["movement_intensity"] = "low"

    tests.append({
        "id": "VALID-002",
        "expected": True,
        "result": transition(base, walking)["accepted"]
    })

    supernatural = deepcopy(base)
    supernatural["shot_id"] = "SHOT-002"
    supernatural["face"]["eyes"] = "glowing"

    tests.append({
        "id": "VALID-003",
        "expected": True,
        "result": transition(
            base,
            supernatural,
            {
                "type": "supernatural_activation",
                "cause": "Reaper power activates."
            }
        )["accepted"]
    })

    invalid_glow = deepcopy(base)
    invalid_glow["face"]["eyes"] = "glowing"

    tests.append({
        "id": "INVALID-001",
        "expected": False,
        "result": transition(base, invalid_glow)["accepted"]
    })

    invalid_gaze = deepcopy(base)
    invalid_gaze["gaze"]["direction"] = "left"

    tests.append({
        "id": "INVALID-002",
        "expected": False,
        "result": transition(base, invalid_gaze)["accepted"]
    })

    invalid_emotion = deepcopy(base)
    invalid_emotion["emotion"] = "afraid"
    invalid_emotion["face"]["expression"] = "afraid"

    tests.append({
        "id": "INVALID-003",
        "expected": False,
        "result": transition(base, invalid_emotion)["accepted"]
    })

    invalid_body = deepcopy(base)
    invalid_body["body"]["posture"] = "lying"

    tests.append({
        "id": "INVALID-004",
        "expected": False,
        "result": transition(base, invalid_body)["accepted"]
    })

    invalid_identity = deepcopy(base)
    invalid_identity["character_id"] = "someone_else"

    tests.append({
        "id": "INVALID-005",
        "expected": False,
        "result": validate_state(
            invalid_identity,
            schema,
            canon
        )["accepted"]
    })

    return tests


def main():
    print("=" * 60)
    print("DEATHBOUND — PHASE 5D-1")
    print("CHARACTER PERFORMANCE / MOTION STATE ENGINE")
    print("=" * 60)

    schema = load_json(SCHEMA_PATH)
    canon = load_json(CANON_PATH)

    print("PASS  Performance schema loaded.")
    print("PASS  Riven canon loaded.")

    tests = run_tests(schema, canon)

    passed = 0

    print("-" * 60)

    for test in tests:
        status = test["result"] == test["expected"]

        if status:
            passed += 1
            print(f"PASS  {test['id']}")
        else:
            print(f"FAIL  {test['id']}")

    output = {
        "schema_version": "1.1.0",
        "character": "riven",
        "tests": tests,
        "summary": {
            "tests": len(tests),
            "passed": passed,
            "failed": len(tests) - passed,
            "overall": "PASS" if passed == len(tests) else "FAIL"
        },
        "base_performance_state": make_base_state()
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    print("-" * 60)
    print(f"TESTS: {len(tests)}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {len(tests) - passed}")
    print("-" * 60)

    if passed == len(tests):
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")

    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

