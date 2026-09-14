import json
from pathlib import Path


BASE = Path(r"D:\Deathbound")
SCHEMA_PATH = BASE / "config" / "CAMERA_BEHAVIOR_SCHEMA.json"


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def success():
    return {
        "accepted": True,
        "errors": []
    }


def fail(message):
    return {
        "accepted": False,
        "errors": [message]
    }


def normalize_movement(movement):
    aliases = {
        "slow_push_in": "push_in",
        "slow_pull_out": "pull_out"
    }
    return aliases.get(movement, movement)


def validate_camera_behavior(
    shot,
    previous_shot=None,
    sequence=None,
    schema=None
):
    if schema is None:
        schema = load_schema()

    errors = []

    camera = shot.get("camera", {})
    movement = normalize_movement(camera.get("movement"))
    shot_type = camera.get("shot_type")
    role = shot.get("role") or shot.get("purpose")

    valid_movements = set(schema["movement_types"])
    valid_shot_types = set(schema["shot_types"])

    if movement not in valid_movements:
        errors.append(
            f"Invalid camera movement: {camera.get('movement')}"
        )

    if shot_type not in valid_shot_types:
        errors.append(
            f"Invalid camera shot type: {shot_type}"
        )

    duration = shot.get("duration_seconds")

    if not isinstance(duration, (int, float)):
        errors.append("Camera duration must be numeric.")
    elif duration < schema["duration_rules"]["minimum_duration_seconds"]:
        errors.append("Camera duration is below minimum.")

    if isinstance(duration, (int, float)):
        if duration > schema["duration_rules"]["maximum_single_shot_seconds"]:
            errors.append("Single camera shot exceeds maximum duration.")

    if isinstance(duration, (int, float)):
        movement_minimums = {
            "tracking": schema["duration_rules"].get("tracking_minimum_seconds"),
            "orbit": schema["duration_rules"].get("orbit_minimum_seconds"),
            "crane": schema["duration_rules"].get("crane_minimum_seconds")
        }

        movement_minimum = movement_minimums.get(movement)

        if (
            movement_minimum is not None
            and duration < movement_minimum
        ):
            errors.append(
                f"Camera movement '{movement}' requires at least {movement_minimum} seconds."
            )

    if role in schema["role_rules"]:
        rules = schema["role_rules"][role]

        if movement not in rules["preferred_movements"]:
            errors.append(
                f"Camera movement '{movement}' is not appropriate for role '{role}'."
            )

        if shot_type not in rules["preferred_shot_types"]:
            errors.append(
                f"Shot type '{shot_type}' is not appropriate for role '{role}'."
            )

    profile = schema["movement_profiles"].get(movement)

    if profile:
        if profile["requires_motion_subject"]:
            performance = shot.get("character_performance", {})

            if not performance:
                errors.append(
                    f"{movement} requires an active character performance."
                )

            motion_required = shot.get(
                "character_motion_required",
                True
            )

            if motion_required is False:
                errors.append(
                    f"{movement} requires a moving subject."
                )

    # Camera-only slideshow defense.
    camera_only = shot.get("camera_only_animation", False)

    if camera_only:
        performance = shot.get("character_performance", {})
        environment_motion = shot.get("environment_motion")

        if not performance and environment_motion in (
            None,
            "none",
            "subtle"
        ):
            errors.append(
                "Camera-only animation detected."
            )

        if isinstance(duration, (int, float)):
            if duration > schema["slideshow_defense"]["maximum_camera_only_seconds"]:
                errors.append(
                    "Camera-only movement exceeds allowed duration."
                )

    # Dialogue must have actual performance, not just camera movement.
    dialogue = shot.get("dialogue", {})

    if isinstance(dialogue, dict) and dialogue.get("active"):
        performance = shot.get("character_performance", {})

        if not performance:
            errors.append(
                "Active dialogue cannot rely on camera movement alone."
            )

        if movement != "static" and shot.get(
            "camera_replaces_performance",
            False
        ):
            errors.append(
                "Camera movement cannot replace dialogue performance."
            )

    # Tracking requires locomotion or explicit tracking performance.
    if movement == "tracking":
        performance = shot.get("character_performance", {})

        locomotion = performance.get("locomotion")

        if (
            locomotion not in (
                "walking",
                "running",
                "following",
                "moving"
            )
            and shot.get("tracking_subject")
            in (None, "")
        ):
            errors.append(
                "Tracking shot has no valid moving subject."
            )

    # Transition continuity.
    if previous_shot is not None:
        previous_camera = previous_shot.get("camera", {})
        previous_movement = normalize_movement(
            previous_camera.get("movement")
        )

        if (
            movement != "static"
            and previous_movement == movement
            and shot.get("duration_seconds", 0) > 5
            and previous_shot.get("duration_seconds", 0) > 5
        ):
            if not shot.get("intentional_continuation", False):
                errors.append(
                    "Extended identical camera movement requires intentional continuation."
                )

    if errors:
        return {
            "accepted": False,
            "errors": errors
        }

    return success()
