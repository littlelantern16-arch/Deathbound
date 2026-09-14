import json
from pathlib import Path
from copy import deepcopy

ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "RIVEN_RIG_ARCHITECTURE.json"


def load():
    with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def validate(d):
    required_root = [
        "schema_version",
        "system",
        "purpose",
        "character_id",
        "canonical_source",
        "architecture",
        "rig_hierarchy",
        "body_controls",
        "facial_controls",
        "gaze_system",
        "dialogue_system",
        "emotion_system",
        "clothing_system",
        "prop_system",
        "animation_layers",
        "motion_tiers",
        "canonical_protection",
        "continuity_contract",
        "slideshow_rejection",
        "blender_contract",
        "qa_requirements",
        "provenance"
    ]

    for key in required_root:
        if key not in d:
            return False, f"Missing root field: {key}"

    if d["character_id"] != "riven":
        return False, "Character ID must be riven."

    required_modes = [
        "2d_cutout",
        "2.5d",
        "3d_hybrid"
    ]

    for mode in required_modes:
        if mode not in d["architecture"]["supported_modes"]:
            return False, f"Missing animation mode: {mode}"

    rig = d["rig_hierarchy"]

    if "root" not in rig:
        return False, "Missing rig root."

    required_body = [
        "pelvis",
        "torso",
        "spine",
        "chest",
        "shoulder.L",
        "shoulder.R"
    ]

    for component in required_body:
        if component not in rig["body"]["components"]:
            return False, f"Missing body component: {component}"

    required_faces = [
        "eye_direction",
        "eye.L",
        "eye.R",
        "brow.L",
        "brow.R",
        "mouth_open",
        "mouth_width",
        "mouth_shape",
        "expression_intensity"
    ]

    for control in required_faces:
        if control not in d["facial_controls"]["required"]:
            return False, f"Missing facial control: {control}"

    if d["gaze_system"]["enabled"] is not True:
        return False, "Gaze system must be enabled."

    if d["gaze_system"]["must_be_explicit"] is not True:
        return False, "Gaze must be explicit."

    if d["dialogue_system"]["mouth_animation_required"] is not True:
        return False, "Mouth animation requirement missing."

    if d["dialogue_system"]["lip_sync_required"] is not True:
        return False, "Lip-sync requirement missing."

    if d["emotion_system"]["expression_must_match_emotion"] is not True:
        return False, "Emotion/expression contract missing."

    if d["clothing_system"]["canonical_clothing_locked"] is not True:
        return False, "Canonical clothing must be locked."

    if "reapers_ledger" not in d["prop_system"]:
        return False, "Reaper's Ledger prop missing."

    if d["prop_system"]["reapers_ledger"]["canonical"] is not True:
        return False, "Reaper's Ledger must be canonical."

    for tier in ["hero", "standard", "atmospheric"]:
        if tier not in d["motion_tiers"]:
            return False, f"Missing motion tier: {tier}"

    protection = d["canonical_protection"]

    protection_keys = [
        "identity_immutable",
        "body_proportions_immutable",
        "face_structure_immutable",
        "default_clothing_immutable",
        "hair_identity_immutable",
        "eye_identity_immutable",
        "prop_identity_immutable",
        "temporary_animation_changes_require_state"
    ]

    for key in protection_keys:
        if protection.get(key) is not True:
            return False, f"Canonical protection failed: {key}"

    continuity = d["continuity_contract"]

    continuity_keys = [
        "character_id_must_match",
        "previous_state_required",
        "current_state_required",
        "causal_event_ids_required_for_state_changes",
        "gaze_continuity_required",
        "emotion_continuity_required",
        "dialogue_continuity_required",
        "prop_continuity_required",
        "clothing_continuity_required"
    ]

    for key in continuity_keys:
        if continuity.get(key) is not True:
            return False, f"Continuity contract failed: {key}"

    blender = d["blender_contract"]

    blender_keys = [
        "external_state_is_source_of_truth",
        "blender_scene_must_not_modify_canon",
        "scene_receives_character_state",
        "animation_exports_state_metadata",
        "render_output_is_versioned"
    ]

    for key in blender_keys:
        if blender.get(key) is not True:
            return False, f"Blender contract failed: {key}"

    for key, value in d["qa_requirements"].items():
        if value is not True:
            return False, f"QA requirement disabled: {key}"

    if d["provenance"]["invented_canon"] is not False:
        return False, "Invented canon protection failed."

    return True, "Architecture valid."


def run_tests():
    original = load()

    tests = []

    ok, _ = validate(original)
    tests.append(("BASELINE", ok))

    # 001 — Root removed
    x = deepcopy(original)
    del x["rig_hierarchy"]["root"]
    tests.append(("INVALID-001 — Missing rig root", not validate(x)[0]))

    # 002 — Body component removed
    x = deepcopy(original)
    x["rig_hierarchy"]["body"]["components"].remove("spine")
    tests.append(("INVALID-002 — Missing spine", not validate(x)[0]))

    # 003 — Facial control removed
    x = deepcopy(original)
    x["facial_controls"]["required"].remove("mouth_shape")
    tests.append(("INVALID-003 — Missing mouth control", not validate(x)[0]))

    # 004 — Gaze disabled
    x = deepcopy(original)
    x["gaze_system"]["enabled"] = False
    tests.append(("INVALID-004 — Gaze disabled", not validate(x)[0]))

    # 005 — Lip sync disabled
    x = deepcopy(original)
    x["dialogue_system"]["lip_sync_required"] = False
    tests.append(("INVALID-005 — Lip sync disabled", not validate(x)[0]))

    # 006 — Emotion matching disabled
    x = deepcopy(original)
    x["emotion_system"]["expression_must_match_emotion"] = False
    tests.append(("INVALID-006 — Emotion contract disabled", not validate(x)[0]))

    # 007 — Clothing unlocked
    x = deepcopy(original)
    x["clothing_system"]["canonical_clothing_locked"] = False
    tests.append(("INVALID-007 — Clothing unlocked", not validate(x)[0]))

    # 008 — Ledger removed
    x = deepcopy(original)
    del x["prop_system"]["reapers_ledger"]
    tests.append(("INVALID-008 — Ledger prop removed", not validate(x)[0]))

    # 009 — Invalid motion tier
    x = deepcopy(original)
    del x["motion_tiers"]["hero"]
    tests.append(("INVALID-009 — Hero tier removed", not validate(x)[0]))

    # 010 — Identity protection disabled
    x = deepcopy(original)
    x["canonical_protection"]["identity_immutable"] = False
    tests.append(("INVALID-010 — Identity protection disabled", not validate(x)[0]))

    # 011 — State protection disabled
    x = deepcopy(original)
    x["canonical_protection"]["temporary_animation_changes_require_state"] = False
    tests.append(("INVALID-011 — State protection disabled", not validate(x)[0]))

    # 012 — Previous state removed
    x = deepcopy(original)
    x["continuity_contract"]["previous_state_required"] = False
    tests.append(("INVALID-012 — Previous state disabled", not validate(x)[0]))

    # 013 — Causal events disabled
    x = deepcopy(original)
    x["continuity_contract"]["causal_event_ids_required_for_state_changes"] = False
    tests.append(("INVALID-013 — Causality disabled", not validate(x)[0]))

    # 014 — Blender can modify canon
    x = deepcopy(original)
    x["blender_contract"]["blender_scene_must_not_modify_canon"] = False
    tests.append(("INVALID-014 — Blender canon protection disabled", not validate(x)[0]))

    # 015 — Animation state metadata disabled
    x = deepcopy(original)
    x["blender_contract"]["animation_exports_state_metadata"] = False
    tests.append(("INVALID-015 — State metadata disabled", not validate(x)[0]))

    # 016 — QA requirement disabled
    x = deepcopy(original)
    first_key = next(iter(x["qa_requirements"]))
    x["qa_requirements"][first_key] = False
    tests.append(("INVALID-016 — QA gate disabled", not validate(x)[0]))

    # 017 — Invented canon enabled
    x = deepcopy(original)
    x["provenance"]["invented_canon"] = True
    tests.append(("INVALID-017 — Invented canon enabled", not validate(x)[0]))

    # 018 — 2.5D mode removed
    x = deepcopy(original)
    x["architecture"]["supported_modes"].remove("2.5d")
    tests.append(("INVALID-018 — 2.5D support removed", not validate(x)[0]))

    # 019 — Prop continuity disabled
    x = deepcopy(original)
    x["continuity_contract"]["prop_continuity_required"] = False
    tests.append(("INVALID-019 — Prop continuity disabled", not validate(x)[0]))

    # 020 — Multi-contradiction configuration
    x = deepcopy(original)

    del x["rig_hierarchy"]["root"]
    x["gaze_system"]["enabled"] = False
    x["dialogue_system"]["lip_sync_required"] = False
    x["canonical_protection"]["identity_immutable"] = False
    x["continuity_contract"]["causal_event_ids_required_for_state_changes"] = False
    x["blender_contract"]["blender_scene_must_not_modify_canon"] = False
    x["provenance"]["invented_canon"] = True

    tests.append((
        "INVALID-020 — Multi-contradiction rig configuration",
        not validate(x)[0]
    ))

    return tests


def main():
    print("=" * 60)
    print("DEATHBOUND — PHASE 5E-1")
    print("RIVEN RIG ARCHITECTURE ADVERSARIAL QA")
    print("=" * 60)

    tests = run_tests()

    passed = 0
    failed = 0

    for label, result in tests:
        if result:
            print(f"PASS  {label}")
            passed += 1
        else:
            print(f"FAIL  {label}")
            failed += 1

    print("-" * 60)
    print(f"TESTS: {len(tests)}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {failed}")
    print("-" * 60)

    if failed == 0:
        print("OVERALL: PASS")
        print("")
        print("All rig architecture contradictions were rejected.")
    else:
        print("OVERALL: FAIL")
        print("")
        print("Rig architecture requires additional hardening.")

    print("=" * 60)


if __name__ == "__main__":
    main()
