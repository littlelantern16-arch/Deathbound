import json
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "AUDIO_DIALOGUE_PERFORMANCE_SCHEMA.json"

with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
    SCHEMA = json.load(f)

ALLOWED_INTENTS = set(SCHEMA["performance"]["speech_intents"])
ALLOWED_PAUSES = set(SCHEMA["performance"]["pause_types"])


def validate_dialogue(dialogue):
    errors = []

    for field in SCHEMA["dialogue"]["required"]:
        if field not in dialogue:
            errors.append(f"Missing dialogue field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    if not dialogue.get("dialogue_id"):
        errors.append("dialogue_id cannot be empty.")

    if not dialogue.get("speaker"):
        errors.append("Dialogue speaker is required.")

    if not isinstance(dialogue.get("text"), str) or not dialogue["text"].strip():
        errors.append("Dialogue text is required.")

    start = dialogue.get("start_time")
    end = dialogue.get("end_time")

    if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
        errors.append("Dialogue timing must be numeric.")
    elif start >= end:
        errors.append("Dialogue start_time must be less than end_time.")
    elif end - start < SCHEMA["dialogue"]["minimum_duration_seconds"]:
        errors.append("Dialogue duration is below minimum.")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_voice(voice):
    errors = []

    for field in SCHEMA["voice"]["required"]:
        if field not in voice:
            errors.append(f"Missing voice field: {field}")

    if errors:
        return {"valid": False, "errors": errors}

    if not isinstance(voice.get("voice_id"), str) or not voice["voice_id"]:
        errors.append("voice_id cannot be empty.")

    if voice.get("language") != SCHEMA["voice"]["language"]:
        errors.append("Voice language must be en-US.")

    rate = voice.get("speaking_rate")

    if not isinstance(rate, (int, float)):
        errors.append("Speaking rate must be numeric.")
    elif not (
        SCHEMA["voice"]["speaking_rate_min"]
        <= rate
        <= SCHEMA["voice"]["speaking_rate_max"]
    ):
        errors.append("Speaking rate is outside allowed range.")

    pitch = voice.get("pitch")

    if not isinstance(pitch, (int, float)):
        errors.append("Pitch must be numeric.")
    elif not (
        SCHEMA["voice"]["pitch_min"]
        <= pitch
        <= SCHEMA["voice"]["pitch_max"]
    ):
        errors.append("Pitch is outside allowed range.")

    if not isinstance(voice.get("emotion"), str) or not voice["emotion"]:
        errors.append("Voice emotion is required.")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_lip_sync(dialogue, lip_sync):
    errors = []

    dialogue_result = validate_dialogue(dialogue)
    errors.extend(dialogue_result["errors"])

    if not isinstance(lip_sync, dict):
        errors.append("Lip-sync data is required.")
        return {"valid": False, "errors": errors}

    if not lip_sync.get("active"):
        errors.append("Active dialogue requires active lip-sync.")

    if not lip_sync.get("phoneme_timing"):
        errors.append("Phoneme timing is required.")

    if not lip_sync.get("mouth_performance"):
        errors.append("Mouth performance is required.")

    overlap_start = lip_sync.get("start_time")
    overlap_end = lip_sync.get("end_time")

    if not isinstance(overlap_start, (int, float)) or not isinstance(overlap_end, (int, float)):
        errors.append("Lip-sync timing must be numeric.")
    else:
        if overlap_end <= dialogue["start_time"] or overlap_start >= dialogue["end_time"]:
            errors.append("Lip-sync timing does not overlap dialogue.")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_performance(performance):
    errors = []

    if not isinstance(performance, dict):
        return {
            "valid": False,
            "errors": ["Character performance is required."]
        }

    intent = performance.get("performance_intent")

    if intent not in ALLOWED_INTENTS:
        errors.append(f"Invalid speech performance intent: {intent}")

    if not performance.get("active"):
        errors.append("Speech requires active character performance.")

    if performance.get("mouth_performance") is False:
        errors.append("Speech performance cannot disable mouth performance.")

    pauses = performance.get("pauses", [])

    if not isinstance(pauses, list):
        errors.append("Pauses must be a list.")
    else:
        for pause in pauses:
            if pause.get("type") not in ALLOWED_PAUSES:
                errors.append(
                    f"Invalid pause type: {pause.get('type')}"
                )

            if not isinstance(pause.get("duration"), (int, float)):
                errors.append("Pause duration must be numeric.")
            elif pause["duration"] <= 0:
                errors.append("Pause duration must be positive.")

    emphasis = performance.get("emphasis")

    if emphasis is not None:
        if not isinstance(emphasis, dict):
            errors.append("Emphasis must be an object.")
        elif not emphasis.get("text"):
            errors.append("Emphasis requires a word or phrase.")

    return {"valid": len(errors) == 0, "errors": errors}


def validate_audio_continuity(previous, current):
    errors = []

    multi_speaker_overlap = current.get(
        "multi_speaker_overlap",
        False
    )

    if previous.get("speaker") != current.get("speaker"):
        if not current.get("scene_boundary", False) and not multi_speaker_overlap:
            errors.append(
                "Speaker changed without valid dialogue boundary."
            )

    if previous.get("voice_id") != current.get("voice_id"):
        if not current.get("voice_change_event") and not multi_speaker_overlap:
            errors.append(
                "Voice identity changed without causal event."
            )

    previous_end = previous.get("end_time")
    current_start = current.get("start_time")

    if (
        isinstance(previous_end, (int, float))
        and isinstance(current_start, (int, float))
    ):
        if current_start < previous_end:
            if not multi_speaker_overlap:
                errors.append(
                    "Dialogue overlap requires multi-speaker justification."
                )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def validate_dialogue_shot(shot):
    errors = []

    dialogue = shot.get("dialogue")

    if not isinstance(dialogue, dict):
        errors.append("Dialogue data is required.")
        return {"valid": False, "errors": errors}

    result = validate_dialogue(dialogue)
    errors.extend(result["errors"])

    voice = shot.get("voice")

    if not isinstance(voice, dict):
        errors.append("Voice data is required.")
    else:
        result = validate_voice(voice)
        errors.extend(result["errors"])

    lip_sync = shot.get("lip_sync")

    result = validate_lip_sync(dialogue, lip_sync)
    errors.extend(result["errors"])

    performance = shot.get("character_performance")

    result = validate_performance(performance)
    errors.extend(result["errors"])

    if shot.get("speech_performance_required", False):
        if shot.get("static_character_voiceover", False):
            errors.append(
                "Voiceover over static character cannot replace speech performance."
            )

    if shot.get("audio_only_action", False):
        errors.append(
            "Audio-only action cannot replace required visual performance."
        )

    if shot.get("generic_repeated_voice_track", False):
        errors.append(
            "Repeated generic voice track rejected."
        )

    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


if __name__ == "__main__":
    print("Deathbound Audio & Dialogue Performance Engine")
    print("Schema:", SCHEMA_PATH)
