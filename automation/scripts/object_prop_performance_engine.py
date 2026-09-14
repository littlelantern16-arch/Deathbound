import json
from pathlib import Path
from math import sqrt

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "OBJECT_PROP_PERFORMANCE_SCHEMA.json"

with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
    SCHEMA = json.load(f)

ALLOWED_INTERACTIONS = set(SCHEMA["interaction_rules"]["allowed"])
ALLOWED_OWNERS = set(SCHEMA["ownership"]["owners"])


def _vec3(value):
    return (
        isinstance(value, dict)
        and all(isinstance(value.get(k), (int, float)) for k in ("x", "y", "z"))
    )


def _distance(a, b):
    return sqrt(
        (a["x"] - b["x"]) ** 2
        + (a["y"] - b["y"]) ** 2
        + (a["z"] - b["z"]) ** 2
    )


def validate_prop(prop):
    errors = []

    required = SCHEMA["prop_identity"]["required"]

    for field in required:
        if field not in prop:
            errors.append(f"Missing prop field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    if not prop.get("prop_id"):
        errors.append("prop_id cannot be empty.")

    if not prop.get("prop_type"):
        errors.append("prop_type cannot be empty.")

    if prop.get("owner") not in ALLOWED_OWNERS:
        errors.append(f"Invalid owner: {prop.get('owner')}")

    if not _vec3(prop.get("position")):
        errors.append("Invalid prop position.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_prop_transition(previous_prop, current_prop):
    errors = []

    previous_validation = validate_prop(previous_prop)
    current_validation = validate_prop(current_prop)

    errors.extend(previous_validation["errors"])
    errors.extend(current_validation["errors"])

    if errors:
        return {"valid": False, "errors": errors}

    if current_prop["prop_id"] != previous_prop["prop_id"]:
        errors.append("Prop identity changed.")

    if current_prop["prop_type"] != previous_prop["prop_type"]:
        errors.append("Prop type changed.")

    distance = _distance(
        previous_prop["position"],
        current_prop["position"]
    )

    continuity = current_prop.get("continuity", {})

    if distance > 25 and not continuity.get("intentional_position_change", False):
        errors.append("Prop teleportation detected.")

    if current_prop["owner"] != previous_prop["owner"]:
        if not continuity.get("ownership_change_event"):
            errors.append("Ownership changed without causal event.")

    if current_prop["state"] != previous_prop["state"]:
        if not continuity.get("state_change_event"):
            errors.append("Prop state changed without causal event.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_prop_interaction(prop, interaction):
    errors = []

    if not interaction:
        return {"valid": True, "errors": []}

    interaction_type = interaction.get("type")

    if interaction_type not in ALLOWED_INTERACTIONS:
        errors.append(f"Invalid prop interaction: {interaction_type}")
        return {"valid": False, "errors": errors}

    actor = interaction.get("actor")
    distance = interaction.get("distance")

    if interaction_type in ("touch", "pickup", "open", "close", "use", "activate", "deactivate"):
        if distance is None:
            errors.append("Physical prop interaction requires distance.")

        elif not isinstance(distance, (int, float)):
            errors.append("Interaction distance must be numeric.")

        elif distance > 2.5:
            errors.append("Actor is too far from prop for physical interaction.")

    if interaction_type == "pickup":
        if not prop.get("pickupable", True):
            errors.append("Prop is not pickupable.")

    if interaction_type in ("open", "close"):
        if not prop.get("openable", False):
            errors.append("Prop is not openable.")

    if interaction_type == "use":
        if not prop.get("usable", False):
            errors.append("Prop is not usable.")

    if interaction_type == "put_down":
        if not interaction.get("surface_valid", False):
            errors.append("Put-down requires a valid surface.")

    if interaction_type == "give":
        if prop.get("owner") != actor:
            if not interaction.get("authority_override", False):
                errors.append("Actor cannot give a prop they do not own.")

    if interaction_type == "receive":
        if not interaction.get("recipient_valid", False):
            errors.append("Receive interaction requires valid recipient.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_prop_action(shot, prop):
    errors = []

    action = shot.get("prop_action")

    if not action:
        return {"valid": True, "errors": []}

    action_type = action.get("type")

    if action_type not in ALLOWED_INTERACTIONS:
        errors.append(f"Invalid prop action: {action_type}")
        return {"valid": False, "errors": errors}

    if shot.get("prop_action_required", False):
        if not action.get("state_change", False):
            errors.append(
                "Required prop action must produce an actual prop state change."
            )

    if action_type == "destroy":
        if not action.get("causal_event_id"):
            errors.append("Prop destruction requires causal event.")

    if action_type == "break":
        if not action.get("causal_event_id"):
            errors.append("Prop breakage requires causal event.")

    if action_type in ("activate", "deactivate"):
        if not action.get("causal_event_id"):
            errors.append("Prop activation state change requires causal event.")

    if action.get("camera_only_substitute", False):
        errors.append("Camera motion cannot substitute for prop interaction.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_prop_shot(shot):
    errors = []

    props = shot.get("props", [])

    if not isinstance(props, list):
        return {
            "valid": False,
            "errors": ["props must be a list."]
        }

    seen = set()

    for prop in props:
        result = validate_prop(prop)

        if not result["valid"]:
            errors.extend(result["errors"])

        prop_id = prop.get("prop_id")

        if prop_id in seen:
            errors.append(f"Duplicate prop identity: {prop_id}")

        seen.add(prop_id)

    action_result = validate_prop_action(
        shot,
        props[0] if props else {}
    )

    errors.extend(action_result["errors"])

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


if __name__ == "__main__":
    print("Deathbound Object & Prop Performance Engine")
    print("Schema:", SCHEMA_PATH)
