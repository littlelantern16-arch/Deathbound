import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "BODY_MOTION_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"
OUTPUT_PATH = ROOT / "projects" / "EP001" / "characters" / "riven_body_motion_output.json"


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def make_base_state():
    return {
        "character_id": "riven",
        "motion_tier": "standard",
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
            "physical_condition": "normal",
        },
        "gesture": {"active": False, "type": "none"},
        "environment_interaction": {
            "ground_contact": True,
            "surface_aware": True,
            "prop_interaction": False,
            "collision_aware": True,
            "spatially_valid": True,
        },
        "clothing": {"locked": True, "canonical": True, "damage": False},
        "continuity": {
            "identity_locked": True,
            "body_structure_locked": True,
            "proportion_locked": True,
            "clothing_locked": True,
            "position_continuity_locked": True,
            "orientation_continuity_locked": True,
            "physical_condition_locked": True,
        },
        "dialogue": {"active": False},
        "emotion": "neutral",
        "position": {"x": 0.0, "y": 0.0, "z": 0.0},
        "causal_event_ids": [],
    }


def error(message):
    return {"accepted": False, "errors": [message]}


def success():
    return {"accepted": True, "errors": []}


def _schema_list(schema, key):
    value = schema.get(key, [])
    return list(value.keys()) if isinstance(value, dict) else list(value)


def validate_state(state, schema, canon):
    required_top = [
        "character_id", "motion_tier", "body", "gesture",
        "environment_interaction", "clothing", "continuity",
        "dialogue", "emotion", "position", "causal_event_ids"
    ]
    for field in required_top:
        if field not in state:
            return error(f"Missing required field: {field}")

    if state["character_id"] != "riven":
        return error("Character identity mismatch.")

    if state["motion_tier"] not in schema["motion_tiers"]:
        return error("Invalid motion tier.")

    body = state["body"]
    body_schema = schema["body_state"]
    for field in body_schema["required_fields"]:
        if field not in body:
            return error(f"Missing body field: {field}")

    checks = [
        ("posture", "posture_states", "Invalid posture."),
        ("locomotion", "locomotion_states", "Invalid locomotion."),
        ("orientation", "orientation_states", "Invalid orientation."),
        ("head_orientation", "head_orientation_states", "Invalid head orientation."),
        ("weight_distribution", "weight_distribution_states", "Invalid weight distribution."),
        ("movement_phase", "movement_phase_states", "Invalid movement phase."),
        ("physical_condition", "physical_condition_states", "Invalid physical condition."),
    ]
    for field, schema_key, message in checks:
        if body[field] not in body_schema[schema_key]:
            return error(message)

    gesture = state["gesture"]
    if gesture["type"] not in schema["gesture_system"]["gesture_states"]:
        return error("Invalid gesture.")
    if not isinstance(gesture["active"], bool):
        return error("Gesture active must be boolean.")

    if not isinstance(state["causal_event_ids"], list):
        return error("causal_event_ids must be a list.")

    for lock in schema["continuity_contract"]["required_locks"]:
        if state["continuity"].get(lock) is not True:
            return error(f"Continuity lock disabled: {lock}")

    if state["clothing"].get("canonical") is not True:
        return error("Canonical clothing protection violated.")
    if state["clothing"].get("locked") is not True:
        return error("Clothing lock disabled.")
    if state["clothing"].get("damage") is True and not state["causal_event_ids"]:
        return error("Clothing damage requires causal event.")

    position = state["position"]
    if not all(isinstance(position.get(axis), (int, float)) and not isinstance(position.get(axis), bool)
               for axis in ["x", "y", "z"]):
        return error("Position coordinates must be numeric.")

    environment = state["environment_interaction"]
    for field in ["ground_contact", "surface_aware", "prop_interaction", "collision_aware", "spatially_valid"]:
        if not isinstance(environment.get(field), bool):
            return error(f"Environment field must be boolean: {field}")
    if not environment["spatially_valid"]:
        return error("Spatial validity failed.")
    if not environment["collision_aware"]:
        return error("Collision awareness disabled.")

    posture = body["posture"]
    locomotion = body["locomotion"]
    phase = body["movement_phase"]
    feet = body["feet"]
    weight = body["weight_distribution"]

    if posture == "standing" and locomotion == "stationary" and feet != "grounded":
        return error("Standing stationary state requires grounded feet.")
    if locomotion in ["walking", "running"]:
        if posture not in ["walking", "running"]:
            return error("Locomotion/posture contradiction.")
        if phase == "idle":
            return error("Walking/running cannot remain in idle phase.")
        if weight == "airborne":
            return error("Walking/running cannot have airborne weight state.")
    if posture == "walking" and locomotion != "walking":
        return error("Walking posture requires walking locomotion.")
    if posture == "running" and locomotion != "running":
        return error("Running posture requires running locomotion.")
    if posture == "falling":
        if weight != "airborne":
            return error("Falling requires airborne weight state.")
        if feet == "grounded":
            return error("Falling cannot have grounded feet.")
    if posture == "lying" and locomotion != "stationary":
        return error("Lying state requires stationary locomotion.")
    if body["physical_condition"] == "supernaturally_empowered" and not state["causal_event_ids"]:
        return error("Supernatural physical state requires causal event.")

    if gesture["active"] is False and gesture["type"] != "none":
        return error("Inactive gesture cannot have active gesture type.")
    if gesture["active"] is True and gesture["type"] == "none":
        return error("Active gesture requires gesture type.")
    if gesture["type"] == "hands_in_pockets" and body["hands"] not in ["hands_in_pockets", "none"]:
        return error("Hands contradict hands-in-pockets gesture.")
    if gesture["type"] == "closed_fist" and body["hands"] not in ["closed_fist", "none"]:
        return error("Hands contradict closed-fist gesture.")

    if state["dialogue"]["active"] is True:
        if schema["dialogue_integration"]["active_dialogue_requires_body_performance"]:
            if phase == "idle" and gesture["active"] is False and posture == "standing":
                return error("Active dialogue has no intentional body performance.")

    emotion = state["emotion"]
    if emotion not in schema["emotional_motion"]:
        return error("Unknown emotional motion profile.")
    if emotion == "afraid" and posture == "running" and weight == "forward":
        return error("Fear profile contradicts unsafe forward weight state.")
    if emotion == "sad" and body["head_orientation"] == "up":
        return error("Sad profile contradicts upward head orientation.")
    if emotion == "determined" and weight == "backward":
        return error("Determined profile contradicts backward weight.")
    if emotion == "compassionate" and gesture["type"] == "closed_fist":
        return error("Compassionate profile contradicts closed fist.")

    return success()


def _changed(previous, next_state):
    return (
        previous["body"] != next_state["body"]
        or previous["position"] != next_state["position"]
        or previous["gesture"] != next_state["gesture"]
        or previous["environment_interaction"] != next_state["environment_interaction"]
        or previous["clothing"] != next_state["clothing"]
        or previous["emotion"] != next_state["emotion"]
    )


def _validate_lock_integrity(previous, next_state):
    for state_name, state in [("Previous", previous), ("Next", next_state)]:
        for lock in [
            "identity_locked", "body_structure_locked", "proportion_locked",
            "clothing_locked", "position_continuity_locked",
            "orientation_continuity_locked", "physical_condition_locked"
        ]:
            if state["continuity"].get(lock) is not True:
                return error(f"{state_name} continuity lock disabled: {lock}")
    return success()


def transition(previous, next_state, transition_type, duration_seconds, causal_event_ids=None):
    causal_event_ids = [] if causal_event_ids is None else causal_event_ids

    if transition_type not in {
        "idle", "walk", "run", "turn", "stop", "start", "sit",
        "stand", "crouch", "kneel", "fall", "recover",
        "gesture", "supernatural"
    }:
        return error("Unknown transition type.")

    if not isinstance(duration_seconds, (int, float)) or isinstance(duration_seconds, bool):
        return error("Transition duration must be numeric.")

    if duration_seconds < 0:
        return error("Transition duration cannot be negative.")

    # Contract: zero-duration is forbidden except explicitly instantaneous supernatural motion.
    if duration_seconds == 0 and transition_type != "supernatural":
        return error("Physical transition duration must be positive.")

    if not isinstance(causal_event_ids, list):
        return error("Transition causal_event_ids must be a list.")

    if previous.get("character_id") != next_state.get("character_id"):
        return error("Character identity changed during transition.")
    if previous.get("character_id") != "riven":
        return error("Transition character identity mismatch.")

    lock_result = _validate_lock_integrity(previous, next_state)
    if not lock_result["accepted"]:
        return lock_result

    # Canonical clothing/identity/body structure may not silently mutate across a transition.
    if previous["clothing"] != next_state["clothing"]:
        return error("Clothing continuity break: canonical clothing state changed.")
    if previous["continuity"].get("body_structure_locked") is not True:
        return error("Previous body structure lock is not protected.")
    if next_state["continuity"].get("body_structure_locked") is not True:
        return error("Next body structure lock is not protected.")

    prev_body = previous["body"]
    next_body = next_state["body"]
    p_posture, n_posture = prev_body["posture"], next_body["posture"]
    p_loco, n_loco = prev_body["locomotion"], next_body["locomotion"]

    legal_pairs = {
        "walk": [("standing", "walking"), ("walking", "walking")],
        "run": [("walking", "running"), ("running", "running")],
        "stop": [
            ("walking", "standing"), ("running", "standing"),
            ("walking", "walking"), ("running", "walking")
        ],
        "start": [("standing", "walking"), ("walking", "running")],
        "turn": [(p_posture, p_posture)],
        "sit": [("standing", "sitting"), ("walking", "sitting")],
        "stand": [("sitting", "standing"), ("kneeling", "standing"), ("lying", "standing")],
        "crouch": [("standing", "crouching"), ("walking", "crouching")],
        "kneel": [("standing", "kneeling"), ("crouching", "kneeling")],
        "fall": [
            ("standing", "falling"), ("walking", "falling"),
            ("running", "falling"), ("crouching", "falling")
        ],
        "recover": [
            ("falling", "standing"), ("falling", "kneeling"), ("falling", "sitting")
        ],
        "gesture": [(p_posture, n_posture)],
        "idle": [(p_posture, n_posture)],
        "supernatural": [(p_posture, n_posture)],
    }

    if transition_type not in ["gesture", "idle", "turn", "supernatural"]:
        if (p_posture, n_posture) not in legal_pairs[transition_type]:
            return error(f"Illegal {transition_type} transition: {p_posture} -> {n_posture}")

    if transition_type == "turn":
        if previous["position"] != next_state["position"]:
            return error("Turn cannot teleport position.")
        if prev_body["orientation"] == next_body["orientation"]:
            return error("Turn transition requires an orientation change.")

    changed = _changed(previous, next_state)

    # A transition record must actually describe the requested state change.
    if not changed and transition_type not in ["idle"]:
        return error("Non-idle transition contains no state change.")

    significant = (
        p_posture != n_posture
        or p_loco != n_loco
        or previous["position"] != next_state["position"]
        or previous["environment_interaction"] != next_state["environment_interaction"]
    )

    if significant and not causal_event_ids and transition_type != "idle":
        return error("Significant body transition requires causal event.")

    if prev_body["physical_condition"] != next_body["physical_condition"]:
        if not causal_event_ids:
            return error("Physical condition change requires causal event.")

    if previous["position"] != next_state["position"]:
        if transition_type not in ["walk", "run", "start", "stop", "fall", "recover", "supernatural"]:
            return error("Position changed without locomotion or supernatural transition.")

    if prev_body["orientation"] != next_body["orientation"]:
        if transition_type not in ["turn", "walk", "run", "supernatural"]:
            return error("Orientation changed without valid transition.")

    # Slideshow/teleport defense: locomotion must agree with the transition.
    if transition_type == "walk":
        if n_loco != "walking":
            return error("Walk transition requires walking locomotion.")
        if next_body["movement_phase"] == "idle":
            return error("Walking transition cannot end in idle movement phase.")
    if transition_type == "run":
        if n_loco != "running":
            return error("Run transition requires running locomotion.")
        if next_body["movement_phase"] == "idle":
            return error("Running transition cannot end in idle movement phase.")

    if n_posture == "falling":
        if not causal_event_ids:
            return error("Falling requires causal event.")
        if next_body["weight_distribution"] != "airborne":
            return error("Falling requires airborne weight.")
        if next_body["feet"] == "grounded":
            return error("Falling cannot have grounded feet.")
    if next_body["locomotion"] in ["walking", "running"]:
        if next_body["weight_distribution"] == "airborne":
            return error("Walking/running cannot have airborne weight state.")
    if transition_type == "supernatural":
        if not causal_event_ids:
            return error("Supernatural transition requires causal event.")

    # Environment continuity: a state may not silently disable collision/spatial validity.
    if next_state["environment_interaction"]["collision_aware"] is not True:
        return error("Environment interaction cannot disable collision awareness.")
    if next_state["environment_interaction"]["spatially_valid"] is not True:
        return error("Environment interaction cannot disable spatial validity.")

    return success()


def main():
    schema = load_json(SCHEMA_PATH)
    canon = load_json(CANON_PATH)
    base = make_base_state()

    tests = []

    def run(label, result, expected):
        accepted = result["accepted"]
        passed = accepted == expected
        tests.append((label, passed))

    run("VALID-001 baseline standing", validate_state(base, schema, canon), True)

    walking = deepcopy(base)
    walking["body"]["posture"] = "walking"
    walking["body"]["locomotion"] = "walking"
    walking["body"]["movement_phase"] = "action"

    run("VALID-002 walking state", validate_state(walking, schema, canon), True)
    run("VALID-003 standing to walking",
        transition(base, walking, "walk", 0.8, ["EVENT-WALK-001"]), True)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump({"schema": schema.get("schema_version"), "character": "riven",
                   "tests": ["baseline", "walking", "standing_to_walking"]}, f, indent=2)

    print("=" * 60)
    print("DEATHBOUND â€” PHASE 5F")
    print("RIVEN MOTION TRANSITION ENGINE")
    print("=" * 60)
    for label, passed in tests:
        print(("PASS" if passed else "FAIL") + " " + label)
    failures = sum(not p for _, p in tests)
    print("-" * 60)
    print(f"SMOKE TESTS: {len(tests)}")
    print(f"PASS: {len(tests) - failures}")
    print(f"FAIL: {failures}")
    print("-" * 60)
    print("OVERALL:", "PASS" if failures == 0 else "FAIL")
    print("=" * 60)


if __name__ == "__main__":
    main()

