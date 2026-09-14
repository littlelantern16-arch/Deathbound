import json
import math
from pathlib import Path


BASE = Path(r"D:\Deathbound")
SCHEMA_PATH = BASE / "config" / "CAMERA_CONTINUITY_SCHEMA.json"


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


def distance(a, b):
    return math.sqrt(
        (a["x"] - b["x"]) ** 2 +
        (a["y"] - b["y"]) ** 2 +
        (a["z"] - b["z"]) ** 2
    )


def valid_vector(value):
    if not isinstance(value, dict):
        return False

    return all(
        isinstance(value.get(axis), (int, float))
        and not isinstance(value.get(axis), bool)
        and math.isfinite(value.get(axis))
        for axis in ("x", "y", "z")
    )


def normalize_movement(value):
    return {
        "slow_push_in": "push_in",
        "slow_pull_out": "pull_out"
    }.get(value, value)


def validate_camera_state(camera, schema):
    errors = []

    if not isinstance(camera, dict):
        return fail("Camera state must be an object.")

    for field in schema["camera_state"]["required_fields"]:
        if field not in camera:
            errors.append(
                f"Missing camera state field: {field}"
            )

    position = camera.get("position")
    target = camera.get("target")

    if not valid_vector(position):
        errors.append(
            "Camera position must contain finite x, y, z values."
        )

    if not valid_vector(target):
        errors.append(
            "Camera target must contain finite x, y, z values."
        )

    movement = normalize_movement(
        camera.get("movement")
    )

    if movement not in schema["movement_types"]:
        errors.append(
            f"Invalid camera movement: {camera.get('movement')}"
        )

    return {
        "accepted": not errors,
        "errors": errors
    }


def validate_trajectory(camera, schema):
    errors = []

    movement = normalize_movement(
        camera.get("movement")
    )

    if movement == "static":
        return success()

    trajectory = camera.get("trajectory")

    if not isinstance(trajectory, dict):
        return fail(
            f"Non-static camera movement '{movement}' requires a trajectory."
        )

    duration = trajectory.get("duration_seconds")

    if not isinstance(duration, (int, float)) or isinstance(duration, bool):
        errors.append(
            "Camera trajectory duration must be numeric."
        )
    elif duration < schema["trajectory_rules"]["minimum_duration_seconds"]:
        errors.append(
            "Camera trajectory duration is below minimum."
        )

    start = trajectory.get("start")
    end = trajectory.get("end")

    if not valid_vector(start):
        errors.append(
            "Camera trajectory start must contain finite x, y, z values."
        )

    if not valid_vector(end):
        errors.append(
            "Camera trajectory end must contain finite x, y, z values."
        )

    if valid_vector(start) and valid_vector(end):
        delta = distance(start, end)

        if (
            delta == 0
            and schema["trajectory_rules"]["zero_length_movement_forbidden"]
        ):
            errors.append(
                f"Movement '{movement}' has zero-length trajectory."
            )

        if delta > schema["trajectory_rules"]["teleport_threshold"]:
            errors.append(
                "Camera trajectory exceeds teleport threshold."
            )

        if isinstance(duration, (int, float)) and duration > 0:
            speed = delta / duration

            if speed > schema["trajectory_rules"]["maximum_position_delta_per_second"]:
                errors.append(
                    "Camera trajectory exceeds maximum movement speed."
                )

    return {
        "accepted": not errors,
        "errors": errors
    }


def validate_camera_continuity(
    current_shot,
    previous_shot=None,
    schema=None
):
    if schema is None:
        schema = load_schema()

    errors = []

    current_camera = current_shot.get("camera", {})

    state_result = validate_camera_state(
        current_camera,
        schema
    )

    errors.extend(state_result["errors"])

    trajectory_result = validate_trajectory(
        current_camera,
        schema
    )

    errors.extend(trajectory_result["errors"])

    if previous_shot is None:
        return {
            "accepted": not errors,
            "errors": errors
        }

    previous_camera = previous_shot.get("camera", {})

    previous_state = validate_camera_state(
        previous_camera,
        schema
    )

    errors.extend(previous_state["errors"])

    if errors:
        return {
            "accepted": False,
            "errors": errors
        }

    current_movement = normalize_movement(
        current_camera.get("movement")
    )

    previous_movement = normalize_movement(
        previous_camera.get("movement")
    )

    intentional_cut = bool(
        current_shot.get("intentional_cut", False)
    )

    previous_position = previous_camera["position"]
    current_position = current_camera["position"]

    previous_target = previous_camera["target"]
    current_target = current_camera["target"]

    position_delta = distance(
        previous_position,
        current_position
    )

    target_delta = distance(
        previous_target,
        current_target
    )

    # Static continuity.
    if (
        previous_movement == "static"
        and current_movement == "static"
        and not intentional_cut
        and position_delta > 0
    ):
        errors.append(
            "Connected static shots cannot change camera position."
        )

    # Connected shots cannot silently teleport.
    if (
        not intentional_cut
        and position_delta
        > schema["trajectory_rules"]["teleport_threshold"]
    ):
        errors.append(
            "Connected camera shots contain a teleportation jump."
        )

    # Static camera followed by a moving camera must have a valid
    # trajectory beginning from the previous camera state.
    if (
        not intentional_cut
        and current_movement != "static"
    ):
        trajectory = current_camera.get("trajectory", {})

        start = trajectory.get("start")

        if valid_vector(start):
            start_delta = distance(
                previous_position,
                start
            )

            if start_delta > 0.01:
                errors.append(
                    "Camera trajectory does not begin at previous camera position."
                )

    # Moving camera trajectory must end at the current camera position.
    if current_movement != "static":
        trajectory = current_camera.get("trajectory", {})

        end = trajectory.get("end")

        if valid_vector(end):
            end_delta = distance(
                end,
                current_position
            )

            if end_delta > 0.01:
                errors.append(
                    "Camera trajectory does not end at current camera position."
                )

    # Orbit must retain its target unless intentionally cut.
    if (
        current_movement == "orbit"
        and not intentional_cut
        and target_delta > 1.5
    ):
        errors.append(
            "Orbit camera target changed excessively across connected shots."
        )

    # Push/pull should not suddenly become an unrelated lateral jump.
    if (
        current_movement in ("push_in", "pull_out")
        and not intentional_cut
        and position_delta > 10.0
    ):
        errors.append(
            f"{current_movement} contains excessive connected-shot displacement."
        )

    # Movement transition must be explicit for connected moving shots.
    if (
        not intentional_cut
        and previous_movement != current_movement
        and previous_movement != "static"
        and current_movement != "static"
    ):
        if not current_shot.get("camera_transition"):
            errors.append(
                "Connected camera movement change requires explicit camera_transition."
            )

    return {
        "accepted": not errors,
        "errors": errors
    }
