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


def require_dict(obj, name, errors):
    if not isinstance(obj, dict):
        errors.append(f"{name} must be an object.")
        return False
    return True


def require_list(obj, name, errors):
    if not isinstance(obj, list):
        errors.append(f"{name} must be a list.")
        return False
    return True


def validate_registry_ids(registry, registry_name, errors):
    if not isinstance(registry, dict):
        errors.append(f"{registry_name} must be an object.")
        return

    seen = set()

    for key, value in registry.items():

        if not isinstance(value, dict):
            errors.append(
                f"{registry_name}.{key} must be an object."
            )
            continue

        item_id = value.get("id")

        if not item_id:
            errors.append(
                f"{registry_name}.{key} is missing id."
            )
            continue

        if item_id in seen:
            errors.append(
                f"Duplicate ID in {registry_name}: {item_id}"
            )

        seen.add(item_id)


def validate_world_rules(bible, errors):

    world_rules = bible.get("world_rules")

    if not require_dict(
        world_rules,
        "world_rules",
        errors
    ):
        return

    rules = world_rules.get(
        "reaper_rules"
    )

    if not require_list(
        rules,
        "world_rules.reaper_rules",
        errors
    ):
        return

    rule_ids = set()

    for rule in rules:

        if not isinstance(rule, dict):
            errors.append(
                "Every world rule must be an object."
            )
            continue

        rule_id = rule.get("rule_id")

        if not rule_id:
            errors.append(
                "World rule missing rule_id."
            )
            continue

        if rule_id in rule_ids:
            errors.append(
                f"Duplicate world rule: {rule_id}"
            )

        rule_ids.add(rule_id)

        if rule.get("status") != "canonical":
            errors.append(
                f"World rule {rule_id} must be canonical."
            )


def validate_character_registry(bible, canon, errors):

    characters = bible.get("characters")

    if not require_dict(
        characters,
        "characters",
        errors
    ):
        return

    riven = characters.get("riven")

    if riven is None:
        errors.append(
            "Riven must exist in the character registry."
        )
        return

    if not isinstance(riven, dict):
        errors.append(
            "characters.riven must be an object."
        )
        return

    if riven.get("id") != "riven":
        errors.append(
            "Riven registry ID must be riven."
        )

    if riven.get("name") != "Riven":
        errors.append(
            "Riven registry name must be Riven."
        )

    canonical_id = canon.get(
        "identity",
        {}
    ).get("id")

    if canonical_id != "riven":
        errors.append(
            "Canonical Riven ID is inconsistent."
        )

    canonical_name = canon.get(
        "identity",
        {}
    ).get("name")

    if canonical_name != "Riven":
        errors.append(
            "Canonical Riven name is inconsistent."
        )

    if riven.get("canonical_reference") != str(
        CANON_PATH
    ):
        errors.append(
            "Riven canonical_reference does not point "
            "to the canonical Riven file."
        )


def validate_locations(bible, errors):

    locations = bible.get("locations")

    if not require_dict(
        locations,
        "locations",
        errors
    ):
        return

    for key, location in locations.items():

        if not isinstance(location, dict):
            errors.append(
                f"Location {key} must be an object."
            )
            continue

        if not location.get("id"):
            errors.append(
                f"Location {key} missing id."
            )

        if not location.get("name"):
            errors.append(
                f"Location {key} missing name."
            )


def validate_props(bible, errors):

    props = bible.get("props")

    if not require_dict(
        props,
        "props",
        errors
    ):
        return

    for key, prop in props.items():

        if not isinstance(prop, dict):
            errors.append(
                f"Prop {key} must be an object."
            )
            continue

        if not prop.get("id"):
            errors.append(
                f"Prop {key} missing id."
            )

        if not prop.get("name"):
            errors.append(
                f"Prop {key} missing name."
            )


def validate_timeline(bible, errors):

    timeline = bible.get("timeline")

    if not require_list(
        timeline,
        "timeline",
        errors
    ):
        return

    previous_order = -1

    for index, event in enumerate(timeline):

        if not isinstance(event, dict):
            errors.append(
                f"Timeline entry {index} must be an object."
            )
            continue

        if not event.get("event_id"):
            errors.append(
                f"Timeline entry {index} missing event_id."
            )

        order = event.get("order")

        if order is None:
            errors.append(
                f"Timeline entry {index} missing order."
            )
        else:

            if not isinstance(order, int):
                errors.append(
                    f"Timeline entry {index} order must be integer."
                )

            elif order < previous_order:
                errors.append(
                    "Timeline order is not sequential."
                )

            else:
                previous_order = order


def validate_knowledge(bible, errors):

    knowledge = bible.get(
        "knowledge_state"
    )

    if not require_dict(
        knowledge,
        "knowledge_state",
        errors
    ):
        return

    for field in [
        "global_facts",
        "audience_known",
        "audience_unknown",
        "secrets"
    ]:

        if not isinstance(
            knowledge.get(field),
            list
        ):
            errors.append(
                f"knowledge_state.{field} must be a list."
            )

    character_knowledge = knowledge.get(
        "character_knowledge"
    )

    if not isinstance(
        character_knowledge,
        dict
    ):
        errors.append(
            "knowledge_state.character_knowledge "
            "must be an object."
        )


def validate_relationships(bible, errors):

    relationships = bible.get(
        "relationship_state"
    )

    if not require_dict(
        relationships,
        "relationship_state",
        errors
    ):
        return

    for character_id, data in relationships.items():

        if not isinstance(data, dict):
            errors.append(
                f"Relationship state for {character_id} "
                "must be an object."
            )

        elif not data.get("status"):
            errors.append(
                f"Relationship state for {character_id} "
                "must have status."
            )


def validate_open_loops(bible, errors):

    loops = bible.get(
        "open_loops"
    )

    if not require_list(
        loops,
        "open_loops",
        errors
    ):
        return

    valid_statuses = {
        "open",
        "resolved",
        "deferred",
        "unresolved"
    }

    for index, loop in enumerate(loops):

        if not isinstance(loop, dict):
            errors.append(
                f"Open loop {index} must be an object."
            )
            continue

        if not loop.get("loop_id"):
            errors.append(
                f"Open loop {index} missing loop_id."
            )

        status = loop.get("status")

        if status not in valid_statuses:
            errors.append(
                f"Open loop {index} has invalid status: "
                f"{status}"
            )


def validate_plot_state(bible, errors):

    plot = bible.get(
        "plot_state"
    )

    if not require_dict(
        plot,
        "plot_state",
        errors
    ):
        return

    ending = plot.get(
        "ending_decision"
    )

    if not isinstance(
        ending,
        dict
    ):
        errors.append(
            "plot_state.ending_decision must be an object."
        )
        return

    if ending.get("status") == "unresolved":

        if ending.get("value") is not None:
            errors.append(
                "An unresolved decision cannot have "
                "a resolved value."
            )


def validate_scene_registry(bible, errors):

    scenes = bible.get(
        "scene_registry"
    )

    if not require_list(
        scenes,
        "scene_registry",
        errors
    ):
        return

    scene_ids = set()

    for scene in scenes:

        if not isinstance(scene, dict):
            errors.append(
                "Every scene registry entry must be an object."
            )
            continue

        scene_id = scene.get("scene_id")

        if not scene_id:
            errors.append(
                "Scene missing scene_id."
            )
            continue

        if scene_id in scene_ids:
            errors.append(
                f"Duplicate scene ID: {scene_id}"
            )

        scene_ids.add(scene_id)


def validate_continuity(bible, errors):

    continuity = bible.get(
        "continuity"
    )

    if not require_dict(
        continuity,
        "continuity",
        errors
    ):
        return

    required = [
        "active_character_states",
        "active_location_states",
        "active_prop_states",
        "last_processed_event",
        "last_processed_scene",
        "last_processed_shot"
    ]

    for field in required:

        if field not in continuity:
            errors.append(
                f"continuity missing {field}."
            )


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — LIVING STORY BIBLE VALIDATOR"
    )
    print("=" * 60)

    bible = load_json(
        BIBLE_PATH
    )

    canon = load_json(
        CANON_PATH
    )

    if bible is None or canon is None:
        print("OVERALL: FAIL")
        sys.exit(1)

    errors = []

    # ------------------------------------------------------------
    # ROOT STRUCTURE
    # ------------------------------------------------------------

    if bible.get("schema_version") != "1.0.0":
        errors.append(
            "Invalid story Bible schema version."
        )

    if bible.get("bible_version") != "0.1.0":
        errors.append(
            "Unexpected story Bible version."
        )

    # ------------------------------------------------------------
    # REGISTRIES
    # ------------------------------------------------------------

    validate_registry_ids(
        bible.get("characters"),
        "characters",
        errors
    )

    validate_registry_ids(
        bible.get("locations"),
        "locations",
        errors
    )

    validate_registry_ids(
        bible.get("props"),
        "props",
        errors
    )

    # ------------------------------------------------------------
    # DOMAIN VALIDATORS
    # ------------------------------------------------------------

    validate_world_rules(
        bible,
        errors
    )

    validate_character_registry(
        bible,
        canon,
        errors
    )

    validate_locations(
        bible,
        errors
    )

    validate_props(
        bible,
        errors
    )

    validate_timeline(
        bible,
        errors
    )

    validate_knowledge(
        bible,
        errors
    )

    validate_relationships(
        bible,
        errors
    )

    validate_open_loops(
        bible,
        errors
    )

    validate_plot_state(
        bible,
        errors
    )

    validate_scene_registry(
        bible,
        errors
    )

    validate_continuity(
        bible,
        errors
    )

    # ------------------------------------------------------------
    # RESULT
    # ------------------------------------------------------------

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
        "PASS  Root schema validation"
    )

    print(
        "PASS  Character registry validation"
    )

    print(
        "PASS  Location registry validation"
    )

    print(
        "PASS  Prop registry validation"
    )

    print(
        "PASS  World-rule validation"
    )

    print(
        "PASS  Timeline validation"
    )

    print(
        "PASS  Knowledge-state validation"
    )

    print(
        "PASS  Relationship-state validation"
    )

    print(
        "PASS  Open-loop validation"
    )

    print(
        "PASS  Plot-state validation"
    )

    print(
        "PASS  Scene registry validation"
    )

    print(
        "PASS  Continuity-state validation"
    )

    print("-" * 60)

    print(
        "OVERALL: PASS"
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
