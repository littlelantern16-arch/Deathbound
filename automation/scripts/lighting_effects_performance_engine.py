import json
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "LIGHTING_EFFECTS_PERFORMANCE_SCHEMA.json"

with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
    SCHEMA = json.load(f)

ALLOWED_EFFECTS = set(SCHEMA["effects"]["allowed"])
ALLOWED_LIGHTING = set(SCHEMA["lighting"]["allowed_states"])


def validate_lighting(lighting):
    errors = []

    required = SCHEMA["lighting"]["required"]

    for field in required:
        if field not in lighting:
            errors.append(f"Missing lighting field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    if lighting.get("lighting_state") not in ALLOWED_LIGHTING:
        errors.append(
            f"Invalid lighting state: {lighting.get('lighting_state')}"
        )

    if not isinstance(lighting.get("intensity"), (int, float)):
        errors.append("Lighting intensity must be numeric.")
    elif not 0 <= lighting["intensity"] <= 1:
        errors.append("Lighting intensity must be between 0 and 1.")

    if not isinstance(lighting.get("direction"), dict):
        errors.append("Lighting direction must be an object.")

    if not isinstance(lighting.get("color_temperature"), (int, float)):
        errors.append("Color temperature must be numeric.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_lighting_transition(previous, current):
    errors = []

    previous_result = validate_lighting(previous)
    current_result = validate_lighting(current)

    errors.extend(previous_result["errors"])
    errors.extend(current_result["errors"])

    if errors:
        return {"valid": False, "errors": errors}

    if previous["lighting_state"] != current["lighting_state"]:
        continuity = current.get("continuity", {})

        if not continuity.get("transition", False):
            if not continuity.get("causal_event_id"):
                errors.append(
                    "Major lighting change requires transition or causal event."
                )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_effect(effect):
    errors = []

    required = [
        "effect_id",
        "effect_type",
        "active"
    ]

    for field in required:
        if field not in effect:
            errors.append(f"Missing effect field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    if not effect.get("effect_id"):
        errors.append("Effect identity cannot be empty.")

    if effect.get("effect_type") not in ALLOWED_EFFECTS:
        errors.append(
            f"Invalid effect type: {effect.get('effect_type')}"
        )

    if not isinstance(effect.get("active"), bool):
        errors.append("Effect active state must be boolean.")

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_effect_causality(effect, performance=None):
    errors = []

    result = validate_effect(effect)
    errors.extend(result["errors"])

    if errors:
        return {"valid": False, "errors": errors}

    effect_type = effect["effect_type"]
    active = effect["active"]
    cause = effect.get("causal_event_id")

    if active and effect_type not in ("none", "fog", "smoke", "rain", "snow", "dust"):
        if not cause:
            errors.append(
                f"Effect '{effect_type}' requires causal event."
            )

    if effect_type == "reaper_glow":
        supernatural = effect.get("supernatural_state", {})
        if not supernatural.get("active", False):
            errors.append(
                "Reaper glow requires active supernatural state."
            )

    if effect_type == "ledger_glow":
        ledger = effect.get("ledger_state", {})
        if not ledger.get("active", False):
            errors.append(
                "Ledger glow requires active Ledger state."
            )

    if effect_type == "energy_pulse" and active:
        if not effect.get("pulse_trigger"):
            errors.append(
                "Energy pulse requires explicit pulse trigger."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_effect_transition(previous, current):
    errors = []

    previous_result = validate_effect(previous)
    current_result = validate_effect(current)

    errors.extend(previous_result["errors"])
    errors.extend(current_result["errors"])

    if errors:
        return {"valid": False, "errors": errors}

    if previous["effect_id"] != current["effect_id"]:
        errors.append("Effect identity changed.")

    if previous["effect_type"] != current["effect_type"]:
        errors.append("Effect type changed.")

    if previous["active"] != current["active"]:
        if not current.get("causal_event_id") and not current.get("natural_completion"):
            errors.append(
                "Effect activation/deactivation requires causal event or natural completion."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_environment_effect_alignment(environment, effect):
    errors = []

    weather = environment.get("weather")
    effect_type = effect.get("effect_type")

    if effect_type == "rain" and weather != "rain":
        errors.append("Rain effect contradicts environment weather state.")

    if effect_type == "snow" and weather != "snow":
        errors.append("Snow effect contradicts environment weather state.")

    if effect_type in ("fog", "smoke"):
        if not environment.get("atmospheric_cause"):
            errors.append(
                f"{effect_type} requires atmospheric cause."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_performance_effect_coupling(performance, effects):
    errors = []

    intent = performance.get("performance_intent")
    emotion = performance.get("emotion")

    active_effects = {
        effect.get("effect_type")
        for effect in effects
        if effect.get("active")
    }

    if intent == "supernatural_activation":
        preferred = {
            "reaper_glow",
            "energy_pulse",
            "shadow_distortion",
            "environmental_light_flicker"
        }

        if not active_effects.intersection(preferred):
            errors.append(
                "Supernatural activation requires compatible visual effect."
            )

    if intent == "supernatural_intervention":
        preferred = {
            "reaper_glow",
            "energy_pulse",
            "shadow_distortion"
        }

        if not active_effects.intersection(preferred):
            errors.append(
                "Supernatural intervention requires compatible visual effect."
            )

    if emotion == "fear":
        if "reaper_glow" in active_effects and intent not in (
            "supernatural_activation",
            "supernatural_intervention",
            "threaten"
        ):
            errors.append(
                "Reaper glow is not justified by ordinary fear alone."
            )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_effect_shot(shot):
    errors = []

    lighting = shot.get("lighting")

    if not isinstance(lighting, dict):
        errors.append("Shot requires lighting state.")
    else:
        result = validate_lighting(lighting)
        errors.extend(result["errors"])

    effects = shot.get("effects", [])

    if not isinstance(effects, list):
        errors.append("effects must be a list.")
        return {"valid": False, "errors": errors}

    seen = set()

    for effect in effects:
        result = validate_effect(effect)
        errors.extend(result["errors"])

        effect_id = effect.get("effect_id")

        if effect_id in seen:
            errors.append(
                f"Duplicate effect identity: {effect_id}"
            )

        seen.add(effect_id)

        causal_result = validate_effect_causality(
            effect,
            shot.get("character_performance", {})
        )

        errors.extend(causal_result["errors"])

    environment = shot.get("environment", {})

    for effect in effects:
        result = validate_environment_effect_alignment(
            environment,
            effect
        )
        errors.extend(result["errors"])

    performance = shot.get("character_performance", {})

    coupling_result = validate_performance_effect_coupling(
        performance,
        effects
    )

    errors.extend(coupling_result["errors"])

    # Slideshow defense
    if shot.get("character_motion_required", False):
        if shot.get("static_frame_with_effect_overlay", False):
            errors.append(
                "Effect overlay cannot replace required character motion."
            )

    if shot.get("action_required", False):
        if shot.get("effect_only_motion", False):
            errors.append(
                "Effect-only motion cannot fake required action."
            )

    if shot.get("effect_loop_without_state_change", False):
        errors.append(
            "Repeated effect loop without state change rejected."
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


if __name__ == "__main__":
    print("Deathbound Lighting & Effects Performance Engine")
    print("Schema:", SCHEMA_PATH)

