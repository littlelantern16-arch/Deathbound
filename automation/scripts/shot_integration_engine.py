import json
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "SHOT_INTEGRATION_SCHEMA.json"

with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
    SCHEMA = json.load(f)


def _result(errors):
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_shot_integration(shot):
    errors = []

    for field in SCHEMA["render_contract"]["required"]:
        if field not in shot:
            errors.append(f"Missing required shot system: {field}")

    if errors:
        return _result(errors)

    duration = shot.get("duration_seconds")

    if not isinstance(duration, (int, float)):
        errors.append("duration_seconds must be numeric.")
    elif duration < SCHEMA["render_contract"]["minimum_duration_seconds"]:
        errors.append("Shot duration is below minimum.")
    elif duration > SCHEMA["render_contract"]["maximum_duration_seconds"]:
        errors.append("Shot duration exceeds maximum.")

    # ---------------------------------------------------------
    # CHARACTER / PERFORMANCE
    # ---------------------------------------------------------

    performance = shot.get("character_performance", {})
    body = performance.get("body", {})
    facial = performance.get("facial", {})

    intent = performance.get("performance_intent")
    locomotion = body.get("locomotion")

    if intent == "speak":
        dialogue = shot.get("dialogue", {})
        lips = shot.get("lip_sync", {})

        if not dialogue.get("text"):
            errors.append("Speaking performance requires dialogue.")

        if not lips.get("active"):
            errors.append("Speaking performance requires active lip-sync.")

    if intent in (
        "supernatural_activation",
        "supernatural_intervention"
    ):
        supernatural = performance.get("supernatural_state", {})

        if not supernatural.get("active"):
            errors.append(
                "Supernatural performance intent requires active supernatural state."
            )

        effects = shot.get("effects", [])

        compatible = {
            "reaper_glow",
            "ledger_glow",
            "energy_pulse",
            "shadow_distortion",
            "environmental_light_flicker"
        }

        active_effects = {
            e.get("effect_type")
            for e in effects
            if e.get("active")
        }

        if not active_effects.intersection(compatible):
            errors.append(
                "Supernatural performance lacks compatible active effect."
            )

    if intent == "react":
        if (
            performance.get("performance_change") is False
            and facial.get("expression_changed") is False
            and body.get("motion_changed") is False
        ):
            errors.append(
                "Reaction performance requires visible performance change."
            )

    # ---------------------------------------------------------
    # CAMERA / PERFORMANCE
    # ---------------------------------------------------------

    camera = shot.get("camera", {})
    movement = camera.get("movement")

    if locomotion in ("walking", "running"):
        if movement not in (
            "tracking",
            "pan",
            "handheld",
            "static"
        ):
            errors.append(
                "Locomotion is incompatible with camera behavior."
            )

    if performance.get("camera_only_animation", False):
        errors.append(
            "Camera-only animation cannot replace character performance."
        )

    if performance.get("camera_replaces_performance", False):
        errors.append(
            "Camera cannot replace required character performance."
        )

    # ---------------------------------------------------------
    # SPATIAL / PROP
    # ---------------------------------------------------------

    spatial = shot.get("spatial_state", {})
    props = shot.get("props", [])

    if not isinstance(spatial.get("character_positions"), dict):
        errors.append("Spatial character positions are required.")

    if not isinstance(spatial.get("prop_positions"), dict):
        errors.append("Spatial prop positions are required.")

    interaction = shot.get("environment_interaction")

    if interaction:
        actor = interaction.get("actor")
        target = interaction.get("target")

        if actor not in spatial.get("character_positions", {}):
            errors.append(
                "Prop/environment interaction actor is spatially undefined."
            )

        if target not in spatial.get("prop_positions", {}):
            errors.append(
                "Prop/environment interaction target is spatially undefined."
            )

    for prop in props:
        prop_id = prop.get("prop_id")

        if prop_id not in spatial.get("prop_positions", {}):
            errors.append(
                f"Prop {prop_id} has no matching spatial position."
            )

        if (
            prop.get("position")
            != spatial.get("prop_positions", {}).get(prop_id)
        ):
            errors.append(
                f"Prop {prop_id} position contradicts spatial state."
            )

    # ---------------------------------------------------------
    # ENVIRONMENT / LIGHTING
    # ---------------------------------------------------------

    environment = shot.get("environment", {})
    lighting = shot.get("lighting", {})

    weather = environment.get("weather")

    effects = shot.get("effects", [])

    for effect in effects:
        effect_type = effect.get("effect_type")

        if effect_type == "rain" and weather != "rain":
            errors.append(
                "Rain effect contradicts environment weather."
            )

        if effect_type == "snow" and weather != "snow":
            errors.append(
                "Snow effect contradicts environment weather."
            )

    if (
        environment.get("lighting_state")
        and lighting.get("lighting_state")
        and environment.get("lighting_state")
        != lighting.get("lighting_state")
    ):
        errors.append(
            "Environment lighting state contradicts shot lighting state."
        )

    # ---------------------------------------------------------
    # AUDIO / DIALOGUE / TIMING
    # ---------------------------------------------------------

    dialogue = shot.get("dialogue", {})
    audio = shot.get("audio", {})

    if dialogue:
        speaker = dialogue.get("speaker")

        if speaker != performance.get("speaker"):
            errors.append(
                "Dialogue speaker contradicts performance speaker."
            )

        start = dialogue.get("start_time")
        end = dialogue.get("end_time")

        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            if start < 0 or end > duration:
                errors.append(
                    "Dialogue timing exceeds shot duration."
                )

    if audio:
        audio_start = audio.get("start_time")
        audio_end = audio.get("end_time")

        if isinstance(audio_start, (int, float)) and isinstance(audio_end, (int, float)):
            if audio_start < 0 or audio_end > duration:
                errors.append(
                    "Audio timing exceeds shot duration."
                )

    # ---------------------------------------------------------
    # SLIDESHOW DEFENSE
    # ---------------------------------------------------------

    if shot.get("spatial_action_required") and shot.get("camera_only_motion"):
        errors.append(
            "Camera-only motion cannot replace required spatial action."
        )

    if shot.get("character_motion_required"):
        if shot.get("static_character_with_effect_overlay"):
            errors.append(
                "Static character plus effects cannot replace required motion."
            )

    if shot.get("dialogue_performance_required"):
        if shot.get("voiceover_over_static_character"):
            errors.append(
                "Voiceover cannot replace required dialogue performance."
            )

    if shot.get("prop_action_required"):
        if shot.get("camera_only_prop_action"):
            errors.append(
                "Camera motion cannot replace required prop action."
            )

    return _result(errors)


if __name__ == "__main__":
    print("Deathbound Shot Integration Engine")
    print("Schema:", SCHEMA_PATH)
