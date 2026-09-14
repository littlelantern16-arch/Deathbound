import json
from pathlib import Path


BASE = Path(r"D:\Deathbound")
SCHEMA_PATH = BASE / "config" / "CAMERA_PERFORMANCE_SCHEMA.json"


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def success():
    return {
        "accepted": True,
        "errors": []
    }


def validate_camera_performance(
    shot,
    schema=None
):
    if schema is None:
        schema = load_schema()

    errors = []

    camera = shot.get("camera", {})
    movement = camera.get("movement")

    if movement == "slow_push_in":
        movement = "push_in"

    if movement == "slow_pull_out":
        movement = "pull_out"

    if movement not in schema["camera_movements"]:
        errors.append(
            f"Invalid camera movement: {movement}"
        )

    performance = shot.get(
        "character_performance",
        {}
    )

    intent = performance.get(
        "performance_intent"
    )

    # Some existing shot structures store intent at shot level.
    if intent is None:
        intent = shot.get(
            "performance_intent"
        )

    if intent not in schema["performance_intents"]:
        errors.append(
            f"Invalid performance intent: {intent}"
        )

    # Motion state.
    locomotion = performance.get(
        "locomotion"
    )

    emotion = performance.get(
        "emotion"
    )

    movement_rule = schema[
        "coupling_rules"
    ].get(movement, {})

    required_performance = movement_rule.get(
        "required_performance",
        []
    )

    if required_performance:
        if locomotion not in required_performance:
            errors.append(
                f"Camera movement '{movement}' requires compatible locomotion."
            )

    compatible_intents = movement_rule.get(
        "compatible_intents"
    )

    if (
        compatible_intents
        and intent not in compatible_intents
    ):
        errors.append(
            f"Camera movement '{movement}' conflicts with performance intent '{intent}'."
        )

    # Emotion coupling.
    emotion_camera = schema[
        "emotion_camera_coupling"
    ].get(emotion)

    if (
        emotion_camera
        and movement not in emotion_camera
    ):
        errors.append(
            f"Camera movement '{movement}' conflicts with emotion '{emotion}'."
        )

    # Performance-state coupling.
    state_rule = schema[
        "performance_state_requirements"
    ].get(locomotion)

    if state_rule:
        compatible = state_rule.get(
            "compatible_camera",
            []
        )

        if movement not in compatible:
            errors.append(
                f"Camera movement '{movement}' is incompatible with locomotion state '{locomotion}'."
            )

    # React requires actual change.
    if intent == "react":
        change = performance.get(
            "performance_change"
        )

        if change is False:
            errors.append(
                "Reaction performance requires a facial or body change."
            )

    # Speak requires active dialogue.
    if intent == "speak":
        dialogue = shot.get(
            "dialogue",
            {}
        )

        if not isinstance(dialogue, dict):
            errors.append(
                "Speaking performance requires dialogue object."
            )
        elif not dialogue.get("active"):
            errors.append(
                "Speaking performance requires active dialogue."
            )

    # Supernatural performance.
    if intent in (
        "supernatural_activation",
        "supernatural_intervention"
    ):
        supernatural = shot.get(
            "supernatural",
            {}
        )

        if not isinstance(supernatural, dict):
            errors.append(
                "Supernatural performance requires supernatural state."
            )
        elif not supernatural.get("active"):
            errors.append(
                "Supernatural camera/performance coupling requires active supernatural state."
            )

        preferred = schema[
            "performance_state_requirements"
        ].get(intent, {}).get(
            "preferred_camera",
            []
        )

        if preferred and movement not in preferred:
            errors.append(
                f"Supernatural performance prefers camera movement from {preferred}."
            )

    # Camera-only performance defense.
    if shot.get("camera_replaces_performance", False):
        errors.append(
            "Camera movement cannot replace character performance."
        )

    if shot.get("camera_only_animation", False):
        errors.append(
            "Camera-only animation cannot satisfy performance coupling."
        )

    return {
        "accepted": not errors,
        "errors": errors
    }
