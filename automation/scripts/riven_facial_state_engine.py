import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(r"D:\Deathbound")

SCHEMA_PATH = ROOT / "config" / "FACIAL_ANIMATION_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"
OUTPUT_PATH = ROOT / "projects" / "EP001" / "characters" / "riven_facial_state_output.json"


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


def make_base_state():
    return {
        "character_id": "riven",
        "shot_id": "SHOT-000",
        "timestamp": 0.0,

        "emotion": "calm",
        "expression": "calm",

        "eyes": "focused",

        "brows": "relaxed",

        "mouth": "closed",

        "gaze": {
            "target_type": "character",
            "direction": "forward",
            "attention": "focused"
        },

        "blink": {
            "active": False,
            "intensity": 0.0
        },

        "dialogue": {
            "active": False,
            "dialogue_id": None,
            "voice_reference": None,
            "lip_sync_required": False,
            "lip_sync_complete": False
        },

        "intensity": "subtle",

        "micro_expression": {
            "active": False,
            "type": None,
            "duration_ms": 0
        },

        "causal_event_ids": [],

        "continuity": {
            "identity_locked": True,
            "face_structure_locked": True,
            "eye_identity_locked": True,
            "hair_identity_locked": True
        }
    }


def validate_state(state, schema, canon):
    required = schema["facial_state"]["required_fields"]

    for field in required:
        if field not in state:
            return fail(f"Missing required facial field: {field}")

    if state["character_id"] != "riven":
        return fail("Character identity mismatch.")

    # ---------------------------------------------------------
    # EMOTION / EXPRESSION
    # ---------------------------------------------------------

    emotion = state["emotion"]

    if emotion not in schema["emotion_profiles"]:
        return fail(f"Invalid emotion: {emotion}")

    profile = schema["emotion_profiles"][emotion]

    if state["expression"] != profile["expression"]:
        return fail(
            f"Expression does not match emotion: "
            f"{emotion} -> {state['expression']}"
        )

    # ---------------------------------------------------------
    # EYES
    # ---------------------------------------------------------

    if state["eyes"] not in schema["eye_system"]["states"]:
        return fail("Invalid eye state.")

    # ---------------------------------------------------------
    # BROWS
    # ---------------------------------------------------------

    if state["brows"] not in schema["brow_system"]["states"]:
        return fail("Invalid brow state.")

    # ---------------------------------------------------------
    # MOUTH
    # ---------------------------------------------------------

    if state["mouth"] not in schema["mouth_system"]["states"]:
        return fail("Invalid mouth state.")

    # ---------------------------------------------------------
    # GAZE
    # ---------------------------------------------------------

    gaze = state["gaze"]

    if gaze["target_type"] not in schema["gaze_system"]["targets"]:
        return fail("Invalid gaze target.")

    if gaze["attention"] not in [
        "passive",
        "focused",
        "alert",
        "distracted",
        "searching",
        "locked"
    ]:
        return fail("Invalid gaze attention.")

    # ---------------------------------------------------------
    # BLINK
    # ---------------------------------------------------------

    blink = state["blink"]

    if not isinstance(blink.get("active"), bool):
        return fail("Blink active state must be boolean.")

    if not isinstance(blink.get("intensity"), (int, float)):
        return fail("Blink intensity must be numeric.")

    if blink["intensity"] < 0.0 or blink["intensity"] > 1.0:
        return fail("Blink intensity must be between 0 and 1.")

    # ---------------------------------------------------------
    # DIALOGUE / MOUTH
    # ---------------------------------------------------------

    dialogue = state["dialogue"]

    if dialogue["active"]:

        if not dialogue.get("dialogue_id"):
            return fail("Active dialogue requires dialogue_id.")

        if not dialogue.get("voice_reference"):
            return fail("Active dialogue requires voice reference.")

        if dialogue.get("lip_sync_required") is not True:
            return fail(
                "Active dialogue requires lip_sync_required=true."
            )

        if state["mouth"] != "speaking":
            return fail(
                "Active dialogue requires speaking mouth state."
            )

    else:

        if state["mouth"] == "speaking":
            return fail(
                "Speaking mouth is forbidden without active dialogue."
            )

        if dialogue.get("lip_sync_complete") is True:
            return fail(
                "Lip-sync cannot be complete when dialogue is inactive."
            )

    # ---------------------------------------------------------
    # SUPERNATURAL EYES
    # ---------------------------------------------------------

    if state["eyes"] == "glowing":

        if not state["causal_event_ids"]:
            return fail(
                "Glowing eyes require causal event reference."
            )

    # ---------------------------------------------------------
    # MICRO-EXPRESSION
    # ---------------------------------------------------------

    micro = state["micro_expression"]

    if not isinstance(micro.get("active"), bool):
        return fail("Micro-expression active state must be boolean.")

    allowed_micro = schema["micro_expressions"]["allowed"]

    if micro["active"]:

        if micro.get("type") not in allowed_micro:
            return fail("Invalid micro-expression type.")

        if micro.get("duration_ms", 0) <= 0:
            return fail(
                "Active micro-expression requires positive duration."
            )

    else:

        if micro.get("type") is not None:
            return fail(
                "Inactive micro-expression cannot have a type."
            )

        if micro.get("duration_ms", 0) != 0:
            return fail(
                "Inactive micro-expression must have zero duration."
            )

    # ---------------------------------------------------------
    # CONTINUITY LOCKS
    # ---------------------------------------------------------

    continuity = state["continuity"]

    required_locks = [
        "identity_locked",
        "face_structure_locked",
        "eye_identity_locked",
        "hair_identity_locked"
    ]

    for lock in required_locks:
        if continuity.get(lock) is not True:
            return fail(
                f"Facial continuity lock disabled: {lock}"
            )

    # ---------------------------------------------------------
    # INTENSITY
    # ---------------------------------------------------------

    if state["intensity"] not in [
        "subtle",
        "low",
        "medium",
        "high",
        "extreme"
    ]:
        return fail("Invalid facial performance intensity.")

    return accept(state)


def transition(previous, current, event=None):
    event = event or {}

    changes = []

    fields = [
        ("emotion", previous["emotion"], current["emotion"]),
        ("expression", previous["expression"], current["expression"]),
        ("eyes", previous["eyes"], current["eyes"]),
        ("brows", previous["brows"], current["brows"]),
        ("mouth", previous["mouth"], current["mouth"]),
        (
            "gaze.direction",
            previous["gaze"]["direction"],
            current["gaze"]["direction"]
        ),
        (
            "gaze.target_type",
            previous["gaze"]["target_type"],
            current["gaze"]["target_type"]
        )
    ]

    for name, old, new in fields:
        if old != new:
            changes.append({
                "property": name,
                "previous": old,
                "new": new
            })

    event_type = event.get("type")

    for change in changes:

        prop = change["property"]
        old = change["previous"]
        new = change["new"]

        # -----------------------------------------------------
        # EMOTION TRANSITION
        # -----------------------------------------------------

        if prop == "emotion":

            major = [
                "afraid",
                "angry",
                "sad",
                "determined",
                "conflicted"
            ]

            if old in ["neutral", "calm"] and new in major:

                if not event_type:
                    return fail(
                        f"Major emotional transition requires event: "
                        f"{old} -> {new}"
                    )

        # -----------------------------------------------------
        # EYE GLOW
        # -----------------------------------------------------

        if prop == "eyes" and new == "glowing":

            if event_type != "supernatural_activation":
                return fail(
                    "Eye glow requires supernatural_activation."
                )

        # -----------------------------------------------------
        # GAZE
        # -----------------------------------------------------

        if prop.startswith("gaze."):

            if not event_type:
                return fail(
                    f"Gaze transition requires explicit event: "
                    f"{old} -> {new}"
                )

    return accept(current)


def run_tests(schema, canon):

    base = make_base_state()

    tests = []

    # ---------------------------------------------------------
    # VALID
    # ---------------------------------------------------------

    tests.append({
        "id": "VALID-001",
        "expected": True,
        "result": validate_state(
            base,
            schema,
            canon
        )["accepted"]
    })

    dialogue = deepcopy(base)

    dialogue["shot_id"] = "SHOT-001"
    dialogue["mouth"] = "speaking"

    dialogue["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-001",
        "voice_reference": "voice/riven_001.wav",
        "lip_sync_required": True,
        "lip_sync_complete": False
    }

    tests.append({
        "id": "VALID-002",
        "expected": True,
        "result": validate_state(
            dialogue,
            schema,
            canon
        )["accepted"]
    })

    glow = deepcopy(base)

    glow["eyes"] = "glowing"
    glow["causal_event_ids"] = ["EVENT-SUPERNATURAL-001"]

    tests.append({
        "id": "VALID-003",
        "expected": True,
        "result": validate_state(
            glow,
            schema,
            canon
        )["accepted"]
    })

    # ---------------------------------------------------------
    # INVALID
    # ---------------------------------------------------------

    x = deepcopy(base)
    x["emotion"] = "angry"
    x["expression"] = "calm"

    tests.append({
        "id": "INVALID-001",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["eyes"] = "invalid_eye"

    tests.append({
        "id": "INVALID-002",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["brows"] = "invalid_brow"

    tests.append({
        "id": "INVALID-003",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["mouth"] = "speaking"

    tests.append({
        "id": "INVALID-004",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-002",
        "voice_reference": "voice/riven.wav",
        "lip_sync_required": True,
        "lip_sync_complete": False
    }

    tests.append({
        "id": "INVALID-005",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["eyes"] = "glowing"

    tests.append({
        "id": "INVALID-006",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["gaze"]["direction"] = "left"

    tests.append({
        "id": "INVALID-007",
        "expected": False,
        "result": transition(base, x)["accepted"]
    })

    x = deepcopy(base)
    x["blink"]["intensity"] = 2.0

    tests.append({
        "id": "INVALID-008",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["micro_expression"] = {
        "active": True,
        "type": "not_real",
        "duration_ms": 100
    }

    tests.append({
        "id": "INVALID-009",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["continuity"]["identity_locked"] = False

    tests.append({
        "id": "INVALID-010",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["intensity"] = "MAXIMUM"

    tests.append({
        "id": "INVALID-011",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["micro_expression"] = {
        "active": False,
        "type": "brief_eye_widen",
        "duration_ms": 0
    }

    tests.append({
        "id": "INVALID-012",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    x = deepcopy(base)
    x["emotion"] = "afraid"
    x["expression"] = "afraid"

    tests.append({
        "id": "INVALID-013",
        "expected": False,
        "result": transition(base, x)["accepted"]
    })

    # ---------------------------------------------------------
    # MULTI-CONTRADICTION
    # ---------------------------------------------------------

    x = deepcopy(base)

    x["character_id"] = "someone_else"
    x["emotion"] = "angry"
    x["expression"] = "calm"
    x["eyes"] = "glowing"
    x["mouth"] = "speaking"
    x["gaze"]["direction"] = "left"
    x["continuity"]["identity_locked"] = False

    tests.append({
        "id": "INVALID-014",
        "expected": False,
        "result": validate_state(x, schema, canon)["accepted"]
    })

    return tests


def main():

    print("=" * 60)
    print("DEATHBOUND — PHASE 5E-2B")
    print("RIVEN FACIAL STATE ENGINE")
    print("=" * 60)

    schema = load_json(SCHEMA_PATH)
    canon = load_json(CANON_PATH)

    print("PASS  Facial schema loaded.")
    print("PASS  Riven canon loaded.")

    tests = run_tests(schema, canon)

    passed = 0
    failed = 0

    print("-" * 60)

    for test in tests:

        if test["result"] == test["expected"]:
            print(f"PASS  {test['id']}")
            passed += 1

        else:
            print(f"FAIL  {test['id']}")
            failed += 1

    output = {
        "schema_version": "1.0.0",
        "character": "riven",
        "tests": tests,
        "summary": {
            "tests": len(tests),
            "passed": passed,
            "failed": failed,
            "overall": "PASS" if failed == 0 else "FAIL"
        },
        "base_facial_state": make_base_state()
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            indent=2
        )

    print("-" * 60)
    print(f"TESTS: {len(tests)}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {failed}")
    print("-" * 60)

    print(
        "OVERALL: PASS"
        if failed == 0
        else "OVERALL: FAIL"
    )

    print(f"Output: {OUTPUT_PATH}")
    print("=" * 60)


if __name__ == "__main__":
    main()
