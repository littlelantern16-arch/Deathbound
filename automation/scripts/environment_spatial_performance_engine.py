import json
from pathlib import Path
from math import sqrt

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "ENVIRONMENT_SPATIAL_PERFORMANCE_SCHEMA.json"

with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
    SCHEMA = json.load(f)

def _vec3(value):
    if not isinstance(value, dict):
        return False
    return all(isinstance(value.get(k), (int, float)) for k in ("x", "y", "z"))

def _distance(a, b):
    return sqrt(
        (a["x"] - b["x"]) ** 2 +
        (a["y"] - b["y"]) ** 2 +
        (a["z"] - b["z"]) ** 2
    )

def validate_environment(shot):
    errors = []

    env = shot.get("environment", {})
    spatial = shot.get("spatial_state", {})
    continuity = shot.get("continuity", {})
    interaction = shot.get("environment_interaction", {})

    required_env = SCHEMA["environment_state"]["required"]

    for field in required_env:
        if field not in env:
            errors.append(f"Missing environment field: {field}")

    for field in SCHEMA["spatial_layout"]["required"]:
        if field not in spatial:
            errors.append(f"Missing spatial field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    if not env.get("location_id"):
        errors.append("Environment location_id cannot be empty.")

    if not isinstance(env.get("spatial_layout"), (dict, str)):
        errors.append("Invalid environment spatial_layout.")

    # Location continuity
    previous_location = continuity.get("previous_location_id")
    current_location = env.get("location_id")

    if previous_location and current_location != previous_location:
        if not continuity.get("intentional_scene_change", False):
            errors.append("Location identity changed without intentional scene change.")

    # Character positions
    characters = spatial.get("character_positions", {})
    if not isinstance(characters, dict):
        errors.append("character_positions must be an object.")
    else:
        for cid, pos in characters.items():
            if not _vec3(pos):
                errors.append(f"Invalid character position: {cid}")

    # Prop positions
    props = spatial.get("prop_positions", {})
    if not isinstance(props, dict):
        errors.append("prop_positions must be an object.")
    else:
        for pid, pos in props.items():
            if not _vec3(pos):
                errors.append(f"Invalid prop position: {pid}")

    # Character teleport defense
    previous_positions = continuity.get("previous_character_positions", {})
    for cid, current in characters.items():
        previous = previous_positions.get(cid)
        if previous and _vec3(previous):
            distance = _distance(previous, current)
            if distance > 25 and not continuity.get("intentional_position_change", False):
                errors.append(f"Character teleportation detected: {cid}")

    # Prop teleport defense
    previous_props = continuity.get("previous_prop_positions", {})
    for pid, current in props.items():
        previous = previous_props.get(pid)
        if previous and _vec3(previous):
            distance = _distance(previous, current)
            if distance > 25 and not continuity.get("intentional_prop_change", False):
                errors.append(f"Prop teleportation detected: {pid}")

    # Interaction validation
    if interaction:
        actor = interaction.get("actor")
        target = interaction.get("target")
        interaction_type = interaction.get("type")

        if interaction_type in ("touch", "pickup", "lean", "sit"):

            if actor not in characters:
                errors.append(f"Interaction actor missing from spatial state: {actor}")

            if target not in props:
                errors.append(f"Interaction target missing from spatial state: {target}")

            if actor in characters and target in props:
                distance = _distance(characters[actor], props[target])

                if interaction_type in ("touch", "pickup") and distance > 2.0:
                    errors.append("Interaction requires spatial overlap/reachability.")

                if interaction_type in ("lean", "sit") and distance > 2.5:
                    errors.append("Support interaction is spatially invalid.")

    # Walking validation
    performance = shot.get("character_performance", {})
    body = performance.get("body", {}) if isinstance(performance, dict) else {}
    locomotion = body.get("locomotion")

    if locomotion in ("walking", "running"):
        walkable = spatial.get("walkable_regions", [])
        if not walkable:
            errors.append("Walking/running requires a valid walkable region.")

    # Environment motion
    motion = env.get("environment_motion")
    allowed_motion = SCHEMA["environment_motion_rules"]["allowed"]

    if motion not in allowed_motion:
        errors.append(f"Invalid environment motion: {motion}")

    if motion != "static":
        if not env.get("motion_cause"):
            errors.append("Meaningful environment motion requires environmental cause.")

    # Weather continuity
    previous_weather = continuity.get("previous_weather")
    current_weather = env.get("weather")

    if previous_weather and current_weather != previous_weather:
        if not continuity.get("weather_transition", False):
            errors.append("Weather changed without transition.")

    # Time continuity
    previous_time = continuity.get("previous_time_of_day")
    current_time = env.get("time_of_day")

    if previous_time and current_time != previous_time:
        if not continuity.get("time_transition", False):
            errors.append("Time of day changed without transition.")

    # Lighting continuity
    previous_lighting = continuity.get("previous_lighting")
    current_lighting = env.get("lighting")

    if previous_lighting and current_lighting != previous_lighting:
        if not continuity.get("lighting_transition", False):
            errors.append("Lighting changed without cause or transition.")

    # Slideshow defense
    if shot.get("spatial_action_required", False):
        camera = shot.get("camera", {})
        if camera.get("movement") not in ("tracking", "orbit", "crane", "pan", "tilt"):
            if env.get("environment_motion") == "static":
                errors.append(
                    "Spatial action cannot be replaced by static environment plus camera-only motion."
                )

    if shot.get("environment_interaction_required", False):
        if not interaction:
            errors.append("Required environment interaction is missing.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


if __name__ == "__main__":
    print("Deathbound Environment & Spatial Performance Engine")
    print("Schema:", SCHEMA_PATH)
