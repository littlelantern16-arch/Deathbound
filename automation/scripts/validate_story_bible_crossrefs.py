import json
import sys
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


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as exc:
        print(f"FAIL  Could not read {path}: {exc}")
        return None


def validate_unique_ids(items, id_field, name, errors):
    seen = set()

    for index, item in enumerate(items):

        if not isinstance(item, dict):
            errors.append(
                f"{name}[{index}] must be an object."
            )
            continue

        item_id = item.get(id_field)

        if not item_id:
            errors.append(
                f"{name}[{index}] missing {id_field}."
            )
            continue

        if item_id in seen:
            errors.append(
                f"Duplicate {id_field}: {item_id}"
            )

        seen.add(item_id)

    return seen


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — STORY BIBLE "
        "CROSS-REFERENCE VALIDATOR"
    )
    print("=" * 60)

    bible = load_json(BIBLE_PATH)
    canon = load_json(CANON_PATH)

    if bible is None or canon is None:
        print("OVERALL: FAIL")
        sys.exit(1)

    errors = []

    # ============================================================
    # REGISTRY ID MAPS
    # ============================================================

    characters = bible.get(
        "characters",
        {}
    )

    locations = bible.get(
        "locations",
        {}
    )

    props = bible.get(
        "props",
        {}
    )

    character_ids = {
        value.get("id")
        for value in characters.values()
        if isinstance(value, dict)
        and value.get("id")
    }

    location_ids = {
        value.get("id")
        for value in locations.values()
        if isinstance(value, dict)
        and value.get("id")
    }

    prop_ids = {
        value.get("id")
        for value in props.values()
        if isinstance(value, dict)
        and value.get("id")
    }

    # ============================================================
    # CHARACTER REFERENCES
    # ============================================================

    if "riven" not in characters:
        errors.append(
            "Riven missing from character registry."
        )

    else:

        riven = characters["riven"]

        if riven.get("id") not in character_ids:
            errors.append(
                "Riven registry ID is inconsistent."
            )

        if riven.get("canonical_reference") != str(
            CANON_PATH
        ):
            errors.append(
                "Riven canonical reference mismatch."
            )

    # ============================================================
    # RELATIONSHIP REFERENCES
    # ============================================================

    relationships = bible.get(
        "relationship_state",
        {}
    )

    for source_character, data in relationships.items():

        if source_character not in character_ids:
            errors.append(
                "Relationship source references unknown "
                f"character: {source_character}"
            )

        if not isinstance(data, dict):
            continue

        relationship_list = data.get(
            "relationships",
            []
        )

        if not isinstance(
            relationship_list,
            list
        ):
            errors.append(
                f"Relationships for {source_character} "
                "must be a list."
            )

            continue

        for relationship in relationship_list:

            if not isinstance(
                relationship,
                dict
            ):
                errors.append(
                    "Relationship entry must be an object."
                )
                continue

            target = relationship.get(
                "character_id"
            )

            if target and target not in character_ids:
                errors.append(
                    "Relationship references unknown "
                    f"character: {target}"
                )

    # ============================================================
    # CHARACTER KNOWLEDGE REFERENCES
    # ============================================================

    knowledge = bible.get(
        "knowledge_state",
        {}
    )

    character_knowledge = knowledge.get(
        "character_knowledge",
        {}
    )

    if isinstance(
        character_knowledge,
        dict
    ):

        for character_id in character_knowledge:

            if character_id not in character_ids:

                errors.append(
                    "Knowledge state references unknown "
                    f"character: {character_id}"
                )

    # ============================================================
    # TIMELINE REFERENCES
    # ============================================================

    timeline = bible.get(
        "timeline",
        []
    )

    timeline_event_ids = validate_unique_ids(
        timeline,
        "event_id",
        "timeline",
        errors
    )

    for event in timeline:

        if not isinstance(event, dict):
            continue

        actor = event.get(
            "actor"
        )

        if actor and actor not in character_ids:
            errors.append(
                "Timeline event references unknown "
                f"actor: {actor}"
            )

        location = event.get(
            "location_id"
        )

        if location and location not in location_ids:
            errors.append(
                "Timeline event references unknown "
                f"location: {location}"
            )

        prop = event.get(
            "prop_id"
        )

        if prop and prop not in prop_ids:
            errors.append(
                "Timeline event references unknown "
                f"prop: {prop}"
            )

    # ============================================================
    # SCENE REFERENCES
    # ============================================================

    scenes = bible.get(
        "scene_registry",
        []
    )

    scene_ids = validate_unique_ids(
        scenes,
        "scene_id",
        "scene_registry",
        errors
    )

    for scene in scenes:

        if not isinstance(scene, dict):
            continue

        scene_characters = scene.get(
            "character_ids",
            []
        )

        if not isinstance(
            scene_characters,
            list
        ):
            errors.append(
                "scene.character_ids must be a list."
            )

        else:

            for character_id in scene_characters:

                if character_id not in character_ids:
                    errors.append(
                        "Scene references unknown "
                        f"character: {character_id}"
                    )

        scene_locations = scene.get(
            "location_ids",
            []
        )

        if not isinstance(
            scene_locations,
            list
        ):
            errors.append(
                "scene.location_ids must be a list."
            )

        else:

            for location_id in scene_locations:

                if location_id not in location_ids:
                    errors.append(
                        "Scene references unknown "
                        f"location: {location_id}"
                    )

        scene_props = scene.get(
            "prop_ids",
            []
        )

        if not isinstance(
            scene_props,
            list
        ):
            errors.append(
                "scene.prop_ids must be a list."
            )

        else:

            for prop_id in scene_props:

                if prop_id not in prop_ids:
                    errors.append(
                        "Scene references unknown "
                        f"prop: {prop_id}"
                    )

    # ============================================================
    # SHOT REFERENCES
    # ============================================================

    shots = bible.get(
        "shot_registry",
        []
    )

    shot_ids = validate_unique_ids(
        shots,
        "shot_id",
        "shot_registry",
        errors
    )

    for shot in shots:

        if not isinstance(shot, dict):
            continue

        scene_id = shot.get(
            "scene_id"
        )

        if scene_id and scene_id not in scene_ids:
            errors.append(
                "Shot references unknown "
                f"scene: {scene_id}"
            )

        character_ids_in_shot = shot.get(
            "character_ids",
            []
        )

        if not isinstance(
            character_ids_in_shot,
            list
        ):
            errors.append(
                "shot.character_ids must be a list."
            )

        else:

            for character_id in character_ids_in_shot:

                if character_id not in character_ids:
                    errors.append(
                        "Shot references unknown "
                        f"character: {character_id}"
                    )

    # ============================================================
    # OPEN LOOP REFERENCES
    # ============================================================

    open_loops = bible.get(
        "open_loops",
        []
    )

    loop_ids = validate_unique_ids(
        open_loops,
        "loop_id",
        "open_loops",
        errors
    )

    # ============================================================
    # PLOT / UNRESOLVED DECISION PROTECTION
    # ============================================================

    plot_state = bible.get(
        "plot_state",
        {}
    )

    ending = plot_state.get(
        "ending_decision",
        {}
    )

    if ending.get("status") == "unresolved":

        if ending.get("value") is not None:
            errors.append(
                "Ending is marked unresolved but has "
                "a resolved value."
            )

    # ============================================================
    # CANON PROTECTION
    # ============================================================

    provenance = bible.get(
        "provenance",
        {}
    )

    if provenance.get(
        "invented_canon"
    ) is not False:

        errors.append(
            "Story Bible invented_canon must remain false."
        )

    canonical_riven_id = canon.get(
        "identity",
        {}
    ).get("id")

    canonical_riven_name = canon.get(
        "identity",
        {}
    ).get("name")

    bible_riven = characters.get(
        "riven",
        {}
    )

    if canonical_riven_id != "riven":
        errors.append(
            "Canonical Riven ID has changed."
        )

    if canonical_riven_name != "Riven":
        errors.append(
            "Canonical Riven name has changed."
        )

    if bible_riven.get("id") != canonical_riven_id:
        errors.append(
            "Bible Riven ID conflicts with canonical Riven."
        )

    if bible_riven.get("name") != canonical_riven_name:
        errors.append(
            "Bible Riven name conflicts with canonical Riven."
        )

    # ============================================================
    # WORLD RULE PROTECTION
    # ============================================================

    world_rules = bible.get(
        "world_rules",
        {}
    )

    rules = world_rules.get(
        "reaper_rules",
        []
    )

    required_rule_ids = {
        "RULE-001",
        "RULE-002",
        "RULE-003",
        "RULE-004",
        "RULE-005",
        "RULE-006",
        "RULE-007",
        "RULE-008",
        "RULE-009",
        "RULE-010"
    }

    actual_rule_ids = {
        rule.get("rule_id")
        for rule in rules
        if isinstance(rule, dict)
    }

    missing_rules = (
        required_rule_ids
        - actual_rule_ids
    )

    for rule_id in sorted(
        missing_rules
    ):

        errors.append(
            f"Canonical world rule missing: {rule_id}"
        )

    # ============================================================
    # RESULT
    # ============================================================

    if errors:

        for error in errors:
            print(
                "FAIL  " + error
            )

        print("-" * 60)
        print(
            f"ERRORS: {len(errors)}"
        )
        print(
            "OVERALL: FAIL"
        )

        sys.exit(1)

    print(
        "PASS  Character cross-references"
    )

    print(
        "PASS  Relationship cross-references"
    )

    print(
        "PASS  Knowledge cross-references"
    )

    print(
        "PASS  Timeline cross-references"
    )

    print(
        "PASS  Scene cross-references"
    )

    print(
        "PASS  Shot cross-references"
    )

    print(
        "PASS  Open-loop references"
    )

    print(
        "PASS  Unresolved-decision protection"
    )

    print(
        "PASS  Canon protection"
    )

    print(
        "PASS  World-rule protection"
    )

    print("-" * 60)

    print(
        "OVERALL: PASS"
    )

    sys.exit(0)


if __name__ == "__main__":
    main()
