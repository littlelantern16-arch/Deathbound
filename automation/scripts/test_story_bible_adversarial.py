import json
import shutil
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

BIBLE_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "story_bible.json"
)

CANON_PATH = (
    ROOT
    / "assets"
    / "characters"
    / "Riven"
    / "RIVEN_CANON.json"
)

VALIDATOR_PATH = (
    ROOT
    / "automation"
    / "scripts"
    / "validate_story_bible_crossrefs.py"
)

TEST_DIR = (
    ROOT
    / "cache"
    / "story_bible_adversarial_tests"
)


def load_json(path):

    with open(
        path,
        "r",
        encoding="utf-8-sig"
    ) as f:

        return json.load(f)


def save_json(path, data):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def run_validator(test_file):

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR_PATH),
            str(test_file)
        ],
        capture_output=True,
        text=True
    )

    return result.returncode, (
        result.stdout
        + result.stderr
    )


def run_custom_validator(test_file):

    """
    The production validator currently reads the canonical
    story_bible.json path directly.

    For adversarial testing we therefore create an isolated
    validator copy whose BIBLE_PATH points at the temporary
    corrupted Bible.
    """

    validator_text = VALIDATOR_PATH.read_text(
        encoding="utf-8"
    )

    replacement = (
        'BIBLE_PATH = Path(r"'
        + str(test_file)
        + '")'
    )

    import re

    modified = re.sub(
        r'BIBLE_PATH\s*=\s*\(\s*ROOT.*?\n\)',
        lambda match: replacement,
        validator_text,
        count=1,
        flags=re.DOTALL
    )

    temp_validator = (
        TEST_DIR
        / "temp_validator.py"
    )

    temp_validator.write_text(
        modified,
        encoding="utf-8"
    )

    result = subprocess.run(
        [
            sys.executable,
            str(temp_validator)
        ],
        capture_output=True,
        text=True
    )

    return result.returncode, (
        result.stdout
        + result.stderr
    )


def make_tests():

    original = load_json(
        BIBLE_PATH
    )

    tests = []

    # ============================================================
    # TEST 1 — UNKNOWN CHARACTER
    # ============================================================

    data = deepcopy(original)

    data["scene_registry"] = [
        {
            "scene_id": "SCENE-TEST-001",
            "character_ids": [
                "unknown_character"
            ],
            "location_ids": [],
            "prop_ids": []
        }
    ]

    tests.append(
        (
            "INVALID-001",
            "Unknown character reference",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 2 — UNKNOWN LOCATION
    # ============================================================

    data = deepcopy(original)

    data["scene_registry"] = [
        {
            "scene_id": "SCENE-TEST-002",
            "character_ids": [
                "riven"
            ],
            "location_ids": [
                "loc-does-not-exist"
            ],
            "prop_ids": []
        }
    ]

    tests.append(
        (
            "INVALID-002",
            "Unknown location reference",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 3 — UNKNOWN PROP
    # ============================================================

    data = deepcopy(original)

    data["scene_registry"] = [
        {
            "scene_id": "SCENE-TEST-003",
            "character_ids": [
                "riven"
            ],
            "location_ids": [
                "loc-daniel-bedroom"
            ],
            "prop_ids": [
                "prop-does-not-exist"
            ]
        }
    ]

    tests.append(
        (
            "INVALID-003",
            "Unknown prop reference",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 4 — UNKNOWN SCENE FROM SHOT
    # ============================================================

    data = deepcopy(original)

    data["shot_registry"] = [
        {
            "shot_id": "SHOT-TEST-001",
            "scene_id": "SCENE-DOES-NOT-EXIST",
            "character_ids": [
                "riven"
            ]
        }
    ]

    tests.append(
        (
            "INVALID-004",
            "Shot references unknown scene",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 5 — UNKNOWN CHARACTER IN SHOT
    # ============================================================

    data = deepcopy(original)

    data["shot_registry"] = [
        {
            "shot_id": "SHOT-TEST-002",
            "scene_id": "SCENE-TEST-001",
            "character_ids": [
                "character-does-not-exist"
            ]
        }
    ]

    tests.append(
        (
            "INVALID-005",
            "Shot references unknown character",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 6 — UNKNOWN RELATIONSHIP SOURCE
    # ============================================================

    data = deepcopy(original)

    data["relationship_state"] = {
        "ghost_character": {
            "status": "established_character",
            "relationships": []
        }
    }

    tests.append(
        (
            "INVALID-006",
            "Unknown relationship source",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 7 — UNKNOWN KNOWLEDGE OWNER
    # ============================================================

    data = deepcopy(original)

    data["knowledge_state"][
        "character_knowledge"
    ] = {
        "unknown_character": {
            "knows": []
        }
    }

    tests.append(
        (
            "INVALID-007",
            "Unknown knowledge owner",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 8 — DUPLICATE SCENE ID
    # ============================================================

    data = deepcopy(original)

    data["scene_registry"] = [
        {
            "scene_id": "SCENE-DUPLICATE",
            "character_ids": [],
            "location_ids": [],
            "prop_ids": []
        },
        {
            "scene_id": "SCENE-DUPLICATE",
            "character_ids": [],
            "location_ids": [],
            "prop_ids": []
        }
    ]

    tests.append(
        (
            "INVALID-008",
            "Duplicate scene ID",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 9 — MISSING WORLD RULE
    # ============================================================

    data = deepcopy(original)

    data["world_rules"]["reaper_rules"] = [
        rule
        for rule in data["world_rules"]["reaper_rules"]
        if rule.get("rule_id") != "RULE-001"
    ]

    tests.append(
        (
            "INVALID-009",
            "Missing canonical world rule",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 10 — CANONICAL REFERENCE MUTATION
    # ============================================================

    data = deepcopy(original)

    data["characters"]["riven"][
        "canonical_reference"
    ] = "D:\\Fake\\Riven.json"

    tests.append(
        (
            "INVALID-010",
            "Riven canonical reference mutation",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 11 — UNRESOLVED DECISION HAS VALUE
    # ============================================================

    data = deepcopy(original)

    data["plot_state"][
        "ending_decision"
    ]["value"] = True

    tests.append(
        (
            "INVALID-011",
            "Unresolved ending has resolved value",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 12 — TIMELINE UNKNOWN ACTOR
    # ============================================================

    data = deepcopy(original)

    data["timeline"] = [
        {
            "event_id": "TL-TEST-001",
            "order": 0,
            "actor": "unknown_character",
            "location_id": "loc-daniel-bedroom",
            "prop_id": "prop-reapers-ledger"
        }
    ]

    tests.append(
        (
            "INVALID-012",
            "Timeline references unknown actor",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 13 — TIMELINE UNKNOWN LOCATION
    # ============================================================

    data = deepcopy(original)

    data["timeline"] = [
        {
            "event_id": "TL-TEST-002",
            "order": 0,
            "actor": "riven",
            "location_id": "unknown-location",
            "prop_id": "prop-reapers-ledger"
        }
    ]

    tests.append(
        (
            "INVALID-013",
            "Timeline references unknown location",
            data,
            "FAIL"
        )
    )

    # ============================================================
    # TEST 14 — TIMELINE UNKNOWN PROP
    # ============================================================

    data = deepcopy(original)

    data["timeline"] = [
        {
            "event_id": "TL-TEST-003",
            "order": 0,
            "actor": "riven",
            "location_id": "loc-daniel-bedroom",
            "prop_id": "unknown-prop"
        }
    ]

    tests.append(
        (
            "INVALID-014",
            "Timeline references unknown prop",
            data,
            "FAIL"
        )
    )

    return tests


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — STORY BIBLE "
        "ADVERSARIAL QA"
    )
    print("=" * 60)

    TEST_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    tests = make_tests()

    passed = 0
    failed = 0

    for test_id, name, data, expected in tests:

        test_file = (
            TEST_DIR
            / f"{test_id}.json"
        )

        save_json(
            test_file,
            data
        )

        return_code, output = (
            run_custom_validator(
                test_file
            )
        )

        rejected = return_code != 0

        if expected == "FAIL" and rejected:

            print(
                f"PASS  {test_id} — {name}"
            )

            passed += 1

        else:

            print(
                f"FAIL  {test_id} — {name}"
            )

            print(
                f"      Expected validator rejection."
            )

            if output.strip():

                last_lines = (
                    output.strip()
                    .splitlines()[-3:]
                )

                for line in last_lines:
                    print(
                        f"      {line}"
                    )

            failed += 1

    print("-" * 60)

    print(
        f"TESTS: {len(tests)}"
    )

    print(
        f"PASS:  {passed}"
    )

    print(
        f"FAIL:  {failed}"
    )

    print("-" * 60)

    if failed == 0:

        print(
            "OVERALL: PASS"
        )

        print()
        print(
            "All adversarial contradictions "
            "were rejected."
        )

        return 0

    print(
        "OVERALL: FAIL"
    )

    return 1


if __name__ == "__main__":

    sys.exit(
        main()
    )

