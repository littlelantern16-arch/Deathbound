import json
from pathlib import Path
from copy import deepcopy
import importlib.util

ROOT = Path(r"D:\Deathbound")

ENGINE_PATH = ROOT / "automation" / "scripts" / "riven_facial_state_engine.py"
SCHEMA_PATH = ROOT / "config" / "FACIAL_ANIMATION_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "riven_facial_state_engine",
        ENGINE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    print("=" * 60)
    print("DEATHBOUND — PHASE 5E-2C")
    print("RIVEN FACIAL ADVERSARIAL QA")
    print("=" * 60)

    engine = load_engine()
    schema = load_json(SCHEMA_PATH)
    canon = load_json(CANON_PATH)

    base = engine.make_base_state()

    tests = []

    def reject(label, state, transition=False, event=None):
        if transition:
            result = engine.transition(base, state, event)
        else:
            result = engine.validate_state(state, schema, canon)

        tests.append((label, result["accepted"], False))

    def accept(label, state, transition=False, event=None):
        if transition:
            result = engine.transition(base, state, event)
        else:
            result = engine.validate_state(state, schema, canon)

        tests.append((label, result["accepted"], True))

    # =========================================================
    # VALID BASELINES
    # =========================================================

    accept(
        "VALID-001 — Baseline calm face",
        deepcopy(base)
    )

    dialogue = deepcopy(base)
    dialogue["mouth"] = "speaking"
    dialogue["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-001",
        "voice_reference": "voice/riven_001.wav",
        "lip_sync_required": True,
        "lip_sync_complete": False
    }

    accept(
        "VALID-002 — Dialogue facial state",
        dialogue
    )

    supernatural = deepcopy(base)
    supernatural["eyes"] = "glowing"
    supernatural["causal_event_ids"] = [
        "EVENT-SUPERNATURAL-001"
    ]

    accept(
        "VALID-003 — Causally justified eye glow",
        supernatural
    )

    # =========================================================
    # EMOTION / EXPRESSION ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["emotion"] = "angry"
    x["expression"] = "calm"

    reject(
        "INVALID-001 — Emotion/expression mismatch",
        x
    )

    x = deepcopy(base)
    x["emotion"] = "sad"
    x["expression"] = "amused"

    reject(
        "INVALID-002 — Contradictory emotional expression",
        x
    )

    x = deepcopy(base)
    x["emotion"] = "determined"
    x["expression"] = "confused"

    reject(
        "INVALID-003 — Determined/confused contradiction",
        x
    )

    # =========================================================
    # EYE ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["eyes"] = "glowing"

    reject(
        "INVALID-004 — Eye glow without causal event",
        x
    )

    x = deepcopy(base)
    x["eyes"] = "invalid_eye"

    reject(
        "INVALID-005 — Invalid eye state",
        x
    )

    x = deepcopy(base)
    x["eyes"] = "glowing"
    x["causal_event_ids"] = []

    reject(
        "INVALID-006 — Empty causal reference for glow",
        x
    )

    # =========================================================
    # BROW ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["brows"] = "teleporting"

    reject(
        "INVALID-007 — Invalid brow state",
        x
    )

    # =========================================================
    # MOUTH / DIALOGUE ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["mouth"] = "speaking"

    reject(
        "INVALID-008 — Speaking without dialogue",
        x
    )

    x = deepcopy(base)
    x["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-002",
        "voice_reference": "voice/riven.wav",
        "lip_sync_required": True,
        "lip_sync_complete": False
    }

    reject(
        "INVALID-009 — Dialogue with closed mouth",
        x
    )

    x = deepcopy(base)
    x["mouth"] = "speaking"
    x["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-003",
        "voice_reference": "voice/riven.wav",
        "lip_sync_required": False,
        "lip_sync_complete": False
    }

    reject(
        "INVALID-010 — Dialogue with lip-sync disabled",
        x
    )

    x = deepcopy(base)
    x["dialogue"] = {
        "active": True,
        "dialogue_id": None,
        "voice_reference": "voice/riven.wav",
        "lip_sync_required": True,
        "lip_sync_complete": False
    }
    x["mouth"] = "speaking"

    reject(
        "INVALID-011 — Dialogue without dialogue ID",
        x
    )

    x = deepcopy(base)
    x["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-004",
        "voice_reference": None,
        "lip_sync_required": True,
        "lip_sync_complete": False
    }
    x["mouth"] = "speaking"

    reject(
        "INVALID-012 — Dialogue without voice reference",
        x
    )

    x = deepcopy(base)
    x["dialogue"] = {
        "active": False,
        "dialogue_id": None,
        "voice_reference": None,
        "lip_sync_required": False,
        "lip_sync_complete": True
    }

    reject(
        "INVALID-013 — Lip-sync complete without active dialogue",
        x
    )

    # =========================================================
    # GAZE ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["gaze"]["target_type"] = "unknown"

    reject(
        "INVALID-014 — Invalid gaze target",
        x
    )

    x = deepcopy(base)
    x["gaze"]["attention"] = "telepathic"

    reject(
        "INVALID-015 — Invalid gaze attention",
        x
    )

    x = deepcopy(base)
    x["gaze"]["direction"] = "left"

    reject(
        "INVALID-016 — Gaze change without event",
        x,
        transition=True
    )

    # =========================================================
    # BLINK ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["blink"]["active"] = "yes"

    reject(
        "INVALID-017 — Non-boolean blink state",
        x
    )

    x = deepcopy(base)
    x["blink"]["intensity"] = -0.1

    reject(
        "INVALID-018 — Negative blink intensity",
        x
    )

    x = deepcopy(base)
    x["blink"]["intensity"] = 1.1

    reject(
        "INVALID-019 — Blink intensity above maximum",
        x
    )

    # =========================================================
    # MICRO-EXPRESSION ATTACKS
    # =========================================================

    x = deepcopy(base)
    x["micro_expression"] = {
        "active": True,
        "type": "fake_expression",
        "duration_ms": 100
    }

    reject(
        "INVALID-020 — Invalid micro-expression",
        x
    )

    x = deepcopy(base)
    x["micro_expression"] = {
        "active": True,
        "type": "brief_eye_widen",
        "duration_ms": 0
    }

    reject(
        "INVALID-021 — Zero-duration micro-expression",
        x
    )

    x = deepcopy(base)
    x["micro_expression"] = {
        "active": False,
        "type": "brief_eye_widen",
        "duration_ms": 0
    }

    reject(
        "INVALID-022 — Inactive micro-expression with type",
        x
    )

    # =========================================================
    # CONTINUITY LOCK ATTACKS
    # =========================================================

    for index, lock in enumerate([
        "identity_locked",
        "face_structure_locked",
        "eye_identity_locked",
        "hair_identity_locked"
    ], start=23):

        x = deepcopy(base)
        x["continuity"][lock] = False

        reject(
            f"INVALID-{index:03d} — {lock} disabled",
            x
        )

    # =========================================================
    # INTENSITY ATTACK
    # =========================================================

    x = deepcopy(base)
    x["intensity"] = "MAXIMUM"

    reject(
        "INVALID-027 — Invalid facial intensity",
        x
    )

    # =========================================================
    # MULTI-CONTRADICTION
    # =========================================================

    x = deepcopy(base)

    x["character_id"] = "unknown_character"
    x["emotion"] = "angry"
    x["expression"] = "calm"
    x["eyes"] = "glowing"
    x["mouth"] = "speaking"
    x["gaze"]["direction"] = "left"

    x["dialogue"] = {
        "active": True,
        "dialogue_id": None,
        "voice_reference": None,
        "lip_sync_required": False,
        "lip_sync_complete": False
    }

    x["blink"]["intensity"] = 2.0

    x["micro_expression"] = {
        "active": True,
        "type": "fake_expression",
        "duration_ms": -100
    }

    x["continuity"]["identity_locked"] = False

    reject(
        "INVALID-028 — Multi-contradiction facial state",
        x
    )

    # =========================================================
    # RESULTS
    # =========================================================

    passed = 0
    failed = 0

    print("-" * 60)

    for label, actual, expected in tests:

        correct = actual == expected

        if correct:
            passed += 1
            print(f"PASS  {label}")
        else:
            failed += 1
            print(f"FAIL  {label}")

    print("-" * 60)
    print(f"TESTS: {len(tests)}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {failed}")
    print("-" * 60)

    if failed == 0:
        print("OVERALL: PASS")
        print("")
        print("All adversarial facial contradictions were rejected.")
    else:
        print("OVERALL: FAIL")
        print("")
        print("Facial state engine requires additional hardening.")

    print("=" * 60)


if __name__ == "__main__":
    main()
