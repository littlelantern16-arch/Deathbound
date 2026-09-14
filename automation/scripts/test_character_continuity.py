import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
TEST_PATH = ROOT / "projects" / "EP001" / "characters" / "continuity_test_cases.json"
CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as exc:
        print(f"FAIL  Could not read {path}: {exc}")
        return None

def validate_test_case(test, canon):
    state = test.get("state", {})
    errors = []

    # ------------------------------------------------------------
    # IMMUTABLE IDENTITY
    # ------------------------------------------------------------
    if "id" in state and state["id"] != "riven":
        errors.append("canonical identity mutation")

    if "name" in state and state["name"] != "Riven":
        errors.append("canonical name mutation")

    # ------------------------------------------------------------
    # IMMUTABLE PHYSICAL IDENTITY
    # ------------------------------------------------------------
    if (
        "age_appearance" in state
        and state["age_appearance"] != canon["appearance"]["age_appearance"]
    ):
        errors.append("age appearance mutation")

    if (
        "body_type" in state
        and state["body_type"] != canon["appearance"]["body_type"]
    ):
        errors.append("body type mutation")

    # ------------------------------------------------------------
    # CLOTHING CONTINUITY
    # ------------------------------------------------------------
    default_clothing = canon["clothing"]["default"]

    if state.get("clothing") == "default":
        pass
    elif "clothing" in state:
        if not state.get("clothing_change_cause"):
            errors.append("unexplained clothing change")

    # ------------------------------------------------------------
    # EYE STATE CONTINUITY
    # ------------------------------------------------------------
    eye_state = state.get("eye_state")

    if eye_state == "dark":
        pass

    elif eye_state == "supernatural_glow":
        if not state.get("eye_change_cause"):
            errors.append("unexplained supernatural eye activation")

    elif eye_state is not None:
        errors.append("unknown eye state")

    # ------------------------------------------------------------
    # KNOWLEDGE CONTINUITY
    # ------------------------------------------------------------
    if state.get("knowledge"):
        if state.get("knowledge_event") is not True:
            errors.append("knowledge mutation without event")

    # ------------------------------------------------------------
    # WEAPON CONTINUITY
    # ------------------------------------------------------------
    if state.get("default_weapon") == "giant scythe":
        errors.append("giant scythe incorrectly introduced as default weapon")

    expected = test.get("expected")

    passed = len(errors) == 0

    # Test expectation logic:
    # expected PASS -> validator must pass
    # expected FAIL -> validator must reject
    if expected == "PASS" and not passed:
        return False, errors

    if expected == "FAIL" and passed:
        return False, ["validator failed to detect expected violation"]

    return True, errors


def main():
    print("=" * 60)
    print("DEATHBOUND — RIVEN CONTINUITY TEST HARNESS")
    print("=" * 60)

    tests = load_json(TEST_PATH)
    canon = load_json(CANON_PATH)

    if tests is None or canon is None:
        print("OVERALL: FAIL")
        sys.exit(1)

    cases = tests.get("tests", [])

    if not cases:
        print("FAIL  No test cases found.")
        print("OVERALL: FAIL")
        sys.exit(1)

    passed = 0
    failed = 0

    for test in cases:
        test_id = test.get("id", "UNKNOWN")
        name = test.get("name", "Unnamed test")

        ok, errors = validate_test_case(test, canon)

        if ok:
            print(f"PASS  {test_id} — {name}")
            passed += 1
        else:
            print(f"FAIL  {test_id} — {name}")
            for error in errors:
                print(f"      {error}")
            failed += 1

    print("-" * 60)
    print(f"TESTS: {len(cases)}")
    print(f"PASS:  {passed}")
    print(f"FAIL:  {failed}")
    print("-" * 60)

    if failed == 0:
        print("OVERALL: PASS")
        sys.exit(0)
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
