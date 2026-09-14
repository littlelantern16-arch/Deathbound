import json
from pathlib import Path


BASE = Path(r"D:\Deathbound")
SCHEMA_PATH = BASE / "config" / "CAMERA_INTENT_SCHEMA.json"


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


def normalize(value):
    aliases = {
        "medium-close": "medium_close",
        "extreme-wide": "extreme_wide",
        "extreme-close": "extreme_close"
    }
    return aliases.get(value, value)


def validate_camera_intent(
    shot,
    sequence=None,
    schema=None
):
    if schema is None:
        schema = load_schema()

    errors = []

    camera = shot.get("camera", {})
    composition = shot.get("composition", {})

    shot_type = normalize(
        camera.get("shot_type")
    )

    role = shot.get("role") or shot.get("purpose")

    valid_shot_types = set(
        schema["shot_type_behavior"].keys()
    )

    if shot_type not in valid_shot_types:
        errors.append(
            f"Invalid shot type for intent validation: {shot_type}"
        )

    for field in schema["composition_fields"]:
        if field not in composition:
            errors.append(
                f"Missing composition field: {field}"
            )

    subject_priority = composition.get(
        "subject_priority"
    )

    framing_intent = composition.get(
        "framing_intent"
    )

    visual_focus = composition.get(
        "visual_focus"
    )

    depth_strategy = composition.get(
        "depth_strategy"
    )

    if (
        subject_priority is not None
        and subject_priority not in schema["subject_priority"]
    ):
        errors.append(
            f"Invalid subject priority: {subject_priority}"
        )

    if (
        framing_intent is not None
        and framing_intent not in schema["framing_intents"]
    ):
        errors.append(
            f"Invalid framing intent: {framing_intent}"
        )

    if (
        visual_focus is not None
        and visual_focus not in schema["visual_focus"]
    ):
        errors.append(
            f"Invalid visual focus: {visual_focus}"
        )

    if (
        depth_strategy is not None
        and depth_strategy not in schema["depth_strategies"]
    ):
        errors.append(
            f"Invalid depth strategy: {depth_strategy}"
        )

    # Role alignment.
    role_rule = schema["role_rules"].get(role)

    if role_rule:
        if (
            framing_intent is not None
            and framing_intent
            not in role_rule["framing_intents"]
        ):
            errors.append(
                f"Framing intent '{framing_intent}' conflicts with role '{role}'."
            )

        if (
            visual_focus is not None
            and visual_focus
            not in role_rule["focus"]
        ):
            errors.append(
                f"Visual focus '{visual_focus}' conflicts with role '{role}'."
            )

    # Shot type / focus alignment.
    shot_rule = schema["shot_type_behavior"].get(
        shot_type
    )

    if shot_rule:
        preferred_focus = shot_rule.get(
            "preferred_focus",
            []
        )

        if (
            visual_focus is not None
            and visual_focus not in preferred_focus
        ):
            errors.append(
                f"Visual focus '{visual_focus}' is unsuitable for shot type '{shot_type}'."
            )

    # Narrative requirements.
    narrative = schema["narrative_requirements"].get(
        role,
        {}
    )

    if narrative.get("requires_subject_priority"):
        if not subject_priority:
            errors.append(
                f"Role '{role}' requires subject priority."
            )

    if narrative.get("requires_visual_focus"):
        if not visual_focus:
            errors.append(
                f"Role '{role}' requires visual focus."
            )

    if narrative.get("character_must_be_visible"):
        if subject_priority not in (
            "primary_character",
            "secondary_character",
            "relationship"
        ):
            errors.append(
                "Dialogue composition must prioritize a visible character or relationship."
            )

    if narrative.get("requires_face_or_character_focus"):
        if visual_focus not in (
            "face",
            "eyes",
            "character"
        ):
            errors.append(
                "Reaction composition must focus on face, eyes, or character."
            )

    if narrative.get("requires_action_subject"):
        if subject_priority not in (
            "primary_character",
            "secondary_character",
            "relationship"
        ):
            errors.append(
                "Action composition must prioritize an action subject."
            )

    if narrative.get("requires_reveal_or_effect_focus"):
        if visual_focus not in (
            "supernatural_effect",
            "face",
            "eyes",
            "environment"
        ):
            errors.append(
                "Supernatural payoff must focus on the reveal or its reaction."
            )

    if narrative.get("requires_environment_or_scale_focus"):
        if visual_focus not in (
            "environment",
            "silhouette",
            "negative_space"
        ):
            errors.append(
                "Establishing composition must communicate environment or scale."
            )

    if narrative.get("requires_emotional_subject_focus"):
        if visual_focus not in (
            "face",
            "eyes",
            "character",
            "negative_space"
        ):
            errors.append(
                "Emotional resolution must prioritize the emotional subject."
            )

    # Negative space must have a declared reason.
    if (
        subject_priority == "negative_space"
        or visual_focus == "negative_space"
    ):
        allowed = schema["negative_space"]["allowed_purposes"]

        if framing_intent not in allowed:
            errors.append(
                "Negative space requires an appropriate narrative framing intent."
            )

    # Composition purpose must be explicit.
    if not shot.get("purpose"):
        errors.append(
            "Camera composition requires an explicit shot purpose."
        )

    if errors:
        return {
            "accepted": False,
            "errors": errors
        }

    return success()
