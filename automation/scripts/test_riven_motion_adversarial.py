import json
from pathlib import Path
from copy import deepcopy
import importlib.util

ROOT = Path(r"D:\Deathbound")

ENGINE_PATH = ROOT / "automation" / "scripts" / "riven_motion_engine.py"
SCHEMA_PATH = ROOT / "config" / "CHARACTER_PERFORMANCE_SCHEMA.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"


def load_json(path):
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def load_engine():
    spec = importlib.util.spec_from_file_location(
        "riven_motion_engine",
        ENGINE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_reject(label, result):
    if result.get("accepted") is False:
        print(f"PASS  {label}")
        return True

    print(f"FAIL  {label}")
    return False


def expect_accept(label, result):
    if result.get("accepted") is True:
        print(f"PASS  {label}")
        return True

    print(f"FAIL  {label}")
    return False


def main():
    print("=" * 60)
    print("DEATHBOUND — PHASE 5D-2")
    print("RIVEN MOTION / PERFORMANCE ADVERSARIAL QA")
    print("=" * 60)

    engine = load_engine()
    schema = load_json(SCHEMA_PATH)
    canon = load_json(CANON_PATH)

    base = engine.make_base_state()

    passed = 0
    failed = 0
    total = 0

    def test(label, result, expected=True):
        nonlocal passed, failed, total
        total += 1

        ok = (
            result.get("accepted") is expected
        )

        if ok:
            passed += 1
            print(f"PASS  {label}")
        else:
            failed += 1
            print(f"FAIL  {label}")
            print(f"      Result: {result}")

    # ---------------------------------------------------------
    # VALID BASELINE
    # ---------------------------------------------------------

    test(
        "Baseline valid performance state",
        engine.validate_state(base, schema, canon),
        True
    )

    # ---------------------------------------------------------
    # VALID TRANSITIONS
    # ---------------------------------------------------------

    walking = deepcopy(base)
    walking["shot_id"] = "SHOT-001"
    walking["body"]["posture"] = "walking"
    walking["body"]["movement"] = "walk"
    walking["body"]["movement_intensity"] = "low"

    test(
        "VALID-001 — Standing to walking",
        engine.transition(base, walking),
        True
    )

    standing = deepcopy(base)
    standing["shot_id"] = "SHOT-002"
    standing["body"]["posture"] = "sitting"

    test(
        "VALID-002 — Standing to sitting",
        engine.transition(base, standing),
        True
    )

    glowing = deepcopy(base)
    glowing["shot_id"] = "SHOT-003"
    glowing["face"]["eyes"] = "glowing"

    test(
        "VALID-003 — Supernatural eye activation",
        engine.transition(
            base,
            glowing,
            {
                "type": "supernatural_activation",
                "cause": "Riven activates Reaper power."
            }
        ),
        True
    )

    # ---------------------------------------------------------
    # ADVERSARIAL BODY MOTION
    # ---------------------------------------------------------

    teleport_lying = deepcopy(base)
    teleport_lying["body"]["posture"] = "lying"

    test(
        "INVALID-001 — Standing to lying without transition",
        engine.transition(base, teleport_lying),
        False
    )

    teleport_kneeling = deepcopy(base)
    teleport_kneeling["body"]["posture"] = "kneeling"

    test(
        "INVALID-002 — Standing to kneeling without transition",
        engine.transition(base, teleport_kneeling),
        False
    )

    unexplained_run = deepcopy(base)
    unexplained_run["body"]["posture"] = "running"
    unexplained_run["body"]["movement"] = "run"
    unexplained_run["body"]["movement_intensity"] = "high"

    test(
        "INVALID-003 — Sudden running state",
        engine.transition(base, unexplained_run),
        False
    )

    unexplained_crouch = deepcopy(base)
    unexplained_crouch["body"]["posture"] = "crouching"

    test(
        "INVALID-004 — Sudden crouch state",
        engine.transition(base, unexplained_crouch),
        False
    )

    # ---------------------------------------------------------
    # FACIAL / EMOTIONAL ATTACKS
    # ---------------------------------------------------------

    fear = deepcopy(base)
    fear["emotion"] = "afraid"
    fear["face"]["expression"] = "afraid"

    test(
        "INVALID-005 — Calm to fear without event",
        engine.transition(base, fear),
        False
    )

    anger = deepcopy(base)
    anger["emotion"] = "angry"
    anger["face"]["expression"] = "angry"

    test(
        "INVALID-006 — Calm to anger without event",
        engine.transition(base, anger),
        False
    )

    # ---------------------------------------------------------
    # SUPERNATURAL ATTACKS
    # ---------------------------------------------------------

    unexplained_glow = deepcopy(base)
    unexplained_glow["face"]["eyes"] = "glowing"

    test(
        "INVALID-007 — Eye glow without supernatural event",
        engine.transition(base, unexplained_glow),
        False
    )

    # ---------------------------------------------------------
    # GAZE CONTINUITY
    # ---------------------------------------------------------

    gaze_left = deepcopy(base)
    gaze_left["gaze"]["direction"] = "left"

    test(
        "INVALID-008 — Gaze teleport",
        engine.transition(base, gaze_left),
        False
    )

    gaze_up = deepcopy(base)
    gaze_up["gaze"]["direction"] = "up"

    test(
        "INVALID-009 — Forward to upward gaze without event",
        engine.transition(base, gaze_up),
        False
    )

    # ---------------------------------------------------------
    # DIALOGUE / MOUTH CONTRADICTIONS
    # ---------------------------------------------------------

    talking_without_dialogue = deepcopy(base)
    talking_without_dialogue["face"]["mouth"] = "speaking"

    test(
        "INVALID-010 — Speaking mouth without dialogue",
        engine.validate_state(
            talking_without_dialogue,
            schema,
            canon
        ),
        False
    )

    silent_with_dialogue = deepcopy(base)
    silent_with_dialogue["dialogue"] = {
        "active": True,
        "dialogue_id": "DIALOGUE-001",
        "voice_reference": "voice/riven_001.wav",
        "lip_sync_required": True
    }

    test(
        "INVALID-011 — Active dialogue with closed mouth",
        engine.validate_state(
            silent_with_dialogue,
            schema,
            canon
        ),
        False
    )

    # ---------------------------------------------------------
    # IDENTITY ATTACK
    # ---------------------------------------------------------

    identity_attack = deepcopy(base)
    identity_attack["character_id"] = "daniel"

    test(
        "INVALID-012 — Character identity mutation",
        engine.validate_state(
            identity_attack,
            schema,
            canon
        ),
        False
    )

    # ---------------------------------------------------------
    # PHYSICAL CONDITION ATTACK
    # ---------------------------------------------------------

    injured = deepcopy(base)
    injured["physical_condition"] = "severely_injured"

    test(
        "INVALID-013 — Unexplained physical condition",
        engine.validate_state(
            injured,
            schema,
            canon
        ),
        False
    )

    # ---------------------------------------------------------
    # INVALID ENUM ATTACKS
    # ---------------------------------------------------------

    bad_posture = deepcopy(base)
    bad_posture["body"]["posture"] = "teleporting"

    test(
        "INVALID-014 — Invalid posture value",
        engine.validate_state(
            bad_posture,
            schema,
            canon
        ),
        False
    )

    bad_expression = deepcopy(base)
    bad_expression["face"]["expression"] = "hysterical_laughter"

    test(
        "INVALID-015 — Invalid facial expression",
        engine.validate_state(
            bad_expression,
            schema,
            canon
        ),
        False
    )

    bad_gaze = deepcopy(base)
    bad_gaze["gaze"]["direction"] = "backwards"

    test(
        "INVALID-016 — Invalid gaze direction",
        engine.validate_state(
            bad_gaze,
            schema,
            canon
        ),
        False
    )

    bad_intensity = deepcopy(base)
    bad_intensity["intensity"] = "MAXIMUM"

    test(
        "INVALID-017 — Invalid performance intensity",
        engine.validate_state(
            bad_intensity,
            schema,
            canon
        ),
        False
    )

    # ---------------------------------------------------------
    # CONTINUITY ATTACK
    # ---------------------------------------------------------

    clothing_unlock = deepcopy(base)
    clothing_unlock["continuity"]["clothing_locked"] = False

    test(
        "INVALID-018 — Clothing continuity unlocked",
        engine.validate_state(
            clothing_unlock,
            schema,
            canon
        ),
        False
    )

    identity_unlock = deepcopy(base)
    identity_unlock["continuity"]["identity_locked"] = False

    test(
        "INVALID-019 — Identity continuity unlocked",
        engine.validate_state(
            identity_unlock,
            schema,
            canon
        ),
        False
    )

    # ---------------------------------------------------------
    # MULTI-CONTRADICTION ATTACK
    # ---------------------------------------------------------

    chaos = deepcopy(base)

    chaos["character_id"] = "unknown_character"

    chaos["body"]["posture"] = "teleporting"

    chaos["face"]["eyes"] = "glowing"

    chaos["face"]["expression"] = "afraid"

    chaos["emotion"] = "afraid"

    chaos["gaze"]["direction"] = "left"

    chaos["face"]["mouth"] = "speaking"

    chaos["physical_condition"] = "severely_injured"

    test(
        "INVALID-020 — Multi-contradiction performance state",
        engine.validate_state(
            chaos,
            schema,
            canon
        ),
        False
    )

    print("-" * 60)
    print(f"TESTS: {total}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {failed}")
    print("-" * 60)

    if failed == 0:
        print("OVERALL: PASS")
        print("")
        print("All adversarial motion/performance contradictions were rejected.")
    else:
        print("OVERALL: FAIL")
        print("")
        print("Motion/performance engine requires additional hardening.")

    print("=" * 60)


if __name__ == "__main__":
    main()
