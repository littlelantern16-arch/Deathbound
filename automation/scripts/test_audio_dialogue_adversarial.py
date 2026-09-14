import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
sys.path.insert(0, str(ROOT / "automation" / "scripts"))

from audio_dialogue_performance_engine import (
    validate_dialogue,
    validate_voice,
    validate_lip_sync,
    validate_performance,
    validate_audio_continuity,
    validate_dialogue_shot
)


def base_dialogue():
    return {
        "dialogue_id": "D001",
        "speaker": "riven",
        "text": "You have ten minutes.",
        "start_time": 0.0,
        "end_time": 2.5
    }


def base_voice():
    return {
        "voice_id": "riven_voice_v1",
        "language": "en-US",
        "speaking_rate": 1.0,
        "pitch": 0,
        "emotion": "calm"
    }


def base_lips():
    return {
        "active": True,
        "phoneme_timing": [
            {"phoneme": "Y", "start": 0.0, "end": 0.1}
        ],
        "mouth_performance": True,
        "start_time": 0.0,
        "end_time": 2.5
    }


def base_performance():
    return {
        "active": True,
        "performance_intent": "warn",
        "mouth_performance": True,
        "pauses": [
            {
                "type": "dramatic",
                "duration": 0.25
            }
        ],
        "emphasis": {
            "text": "ten minutes"
        }
    }


def base_shot():
    return {
        "dialogue": base_dialogue(),
        "voice": base_voice(),
        "lip_sync": base_lips(),
        "character_performance": base_performance()
    }


def run_test(name, result, should_pass):
    passed = result["valid"] == should_pass
    print(f"{'PASS' if passed else 'FAIL'} | {name}")

    if not passed:
        print("  errors:", result["errors"])

    return passed


tests = []

# VALID 001
tests.append(run_test(
    "VALID-001 valid dialogue",
    validate_dialogue(base_dialogue()),
    True
))

# VALID 002
tests.append(run_test(
    "VALID-002 valid voice",
    validate_voice(base_voice()),
    True
))

# VALID 003
tests.append(run_test(
    "VALID-003 valid lip-sync",
    validate_lip_sync(base_dialogue(), base_lips()),
    True
))

# VALID 004
tests.append(run_test(
    "VALID-004 valid speech performance",
    validate_performance(base_performance()),
    True
))

# VALID 005
previous = {
    "speaker": "riven",
    "voice_id": "riven_voice_v1",
    "start_time": 0,
    "end_time": 2
}

current = {
    "speaker": "riven",
    "voice_id": "riven_voice_v1",
    "start_time": 2.1,
    "end_time": 4
}

tests.append(run_test(
    "VALID-005 continuous same-speaker audio",
    validate_audio_continuity(previous, current),
    True
))

# VALID 006
previous = {
    "speaker": "riven",
    "voice_id": "riven_voice_v1",
    "start_time": 0,
    "end_time": 2
}

current = {
    "speaker": "daniel",
    "voice_id": "daniel_voice_v1",
    "start_time": 1,
    "end_time": 3,
    "multi_speaker_overlap": True
}

tests.append(run_test(
    "VALID-006 justified multi-speaker overlap",
    validate_audio_continuity(previous, current),
    True
))

# VALID 007
shot = base_shot()

tests.append(run_test(
    "VALID-007 complete dialogue shot",
    validate_dialogue_shot(shot),
    True
))

# VALID 008
performance = base_performance()
performance["pauses"].append({
    "type": "hesitation",
    "duration": 0.4
})

tests.append(run_test(
    "VALID-008 natural hesitation performance",
    validate_performance(performance),
    True
))

# VALID 009
previous = {
    "speaker": "riven",
    "voice_id": "riven_voice_v1",
    "start_time": 0,
    "end_time": 2
}

current = {
    "speaker": "riven",
    "voice_id": "riven_voice_v2",
    "start_time": 2.1,
    "end_time": 4,
    "voice_change_event": "EVT-VOICE-001"
}

tests.append(run_test(
    "VALID-009 causal voice change",
    validate_audio_continuity(previous, current),
    True
))

# VALID 010
shot = base_shot()
shot["speech_performance_required"] = False
shot["character_performance"]["performance_intent"] = "speak"

tests.append(run_test(
    "VALID-010 valid speak intent",
    validate_dialogue_shot(shot),
    True
))

# INVALID 001
dialogue = base_dialogue()
dialogue["start_time"] = 3
dialogue["end_time"] = 2

tests.append(run_test(
    "INVALID-001 reversed dialogue timing",
    validate_dialogue(dialogue),
    False
))

# INVALID 002
dialogue = base_dialogue()
dialogue["text"] = ""

tests.append(run_test(
    "INVALID-002 empty dialogue",
    validate_dialogue(dialogue),
    False
))

# INVALID 003
voice = base_voice()
voice["language"] = "hi-IN"

tests.append(run_test(
    "INVALID-003 wrong voice language",
    validate_voice(voice),
    False
))

# INVALID 004
voice = base_voice()
voice["speaking_rate"] = 3.0

tests.append(run_test(
    "INVALID-004 invalid speaking rate",
    validate_voice(voice),
    False
))

# INVALID 005
lips = base_lips()
lips["active"] = False

tests.append(run_test(
    "INVALID-005 inactive lip-sync",
    validate_lip_sync(base_dialogue(), lips),
    False
))

# INVALID 006
lips = base_lips()
lips["phoneme_timing"] = None

tests.append(run_test(
    "INVALID-006 missing phoneme timing",
    validate_lip_sync(base_dialogue(), lips),
    False
))

# INVALID 007
lips = base_lips()
lips["mouth_performance"] = False

tests.append(run_test(
    "INVALID-007 missing mouth performance",
    validate_lip_sync(base_dialogue(), lips),
    False
))

# INVALID 008
performance = base_performance()
performance["active"] = False

tests.append(run_test(
    "INVALID-008 inactive speech performance",
    validate_performance(performance),
    False
))

# INVALID 009
performance = base_performance()
performance["performance_intent"] = "walk"

tests.append(run_test(
    "INVALID-009 invalid speech intent",
    validate_performance(performance),
    False
))

# INVALID 010
previous = {
    "speaker": "riven",
    "voice_id": "riven_voice_v1",
    "start_time": 0,
    "end_time": 2
}

current = {
    "speaker": "daniel",
    "voice_id": "daniel_voice_v1",
    "start_time": 1,
    "end_time": 3
}

tests.append(run_test(
    "INVALID-010 unjustified dialogue overlap",
    validate_audio_continuity(previous, current),
    False
))

# INVALID 011
previous = {
    "speaker": "riven",
    "voice_id": "riven_voice_v1",
    "start_time": 0,
    "end_time": 2
}

current = {
    "speaker": "riven",
    "voice_id": "riven_voice_v2",
    "start_time": 2.1,
    "end_time": 4
}

tests.append(run_test(
    "INVALID-011 silent voice identity change",
    validate_audio_continuity(previous, current),
    False
))

# INVALID 012
shot = base_shot()
shot["speech_performance_required"] = True
shot["static_character_voiceover"] = True

tests.append(run_test(
    "INVALID-012 static voiceover substitution",
    validate_dialogue_shot(shot),
    False
))

# INVALID 013
shot = base_shot()
shot["audio_only_action"] = True

tests.append(run_test(
    "INVALID-013 audio-only action",
    validate_dialogue_shot(shot),
    False
))

# INVALID 014
shot = base_shot()
shot["generic_repeated_voice_track"] = True

tests.append(run_test(
    "INVALID-014 repeated generic voice track",
    validate_dialogue_shot(shot),
    False
))

# INVALID 015
shot = base_shot()
shot["lip_sync"]["start_time"] = 5
shot["lip_sync"]["end_time"] = 6

tests.append(run_test(
    "INVALID-015 lip-sync timing outside dialogue",
    validate_dialogue_shot(shot),
    False
))

# INVALID 016
performance = base_performance()
performance["pauses"] = [
    {
        "type": "random",
        "duration": 0.2
    }
]

tests.append(run_test(
    "INVALID-016 invalid pause type",
    validate_performance(performance),
    False
))

# INVALID 017
performance = base_performance()
performance["emphasis"] = {}

tests.append(run_test(
    "INVALID-017 empty emphasis",
    validate_performance(performance),
    False
))

# INVALID 018
shot = base_shot()
shot["character_performance"]["mouth_performance"] = False

tests.append(run_test(
    "INVALID-018 speech disables mouth performance",
    validate_dialogue_shot(shot),
    False
))

passed = sum(tests)
total = len(tests)

print("")
print("==============================================")
print("DEATHBOUND — PHASE 5K")
print("AUDIO & DIALOGUE PERFORMANCE ADVERSARIAL QA")
print(f"TESTS: {total}  PASS: {passed}  FAIL: {total - passed}")
print("OVERALL:", "PASS" if passed == total else "FAIL")
print("==============================================")

if passed != total:
    raise SystemExit(1)
