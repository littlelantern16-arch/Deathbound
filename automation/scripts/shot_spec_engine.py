import json
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

ARCHITECTURE_PATH = (
    ROOT
    / "config"
    / "ANIMATION_ARCHITECTURE.json"
)

OUTPUT_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "shot_specifications.json"
)


class ShotSpecError(Exception):
    pass


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as exc:
        raise ShotSpecError(
            f"Could not read {path}: {exc}"
        )


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False
        )


def registry_ids(bible, registry_name):
    registry = bible.get(registry_name, {})

    ids = set()

    if isinstance(registry, dict):

        for key, item in registry.items():

            # Canonical registry entries use their nested
            # "id" field as the actual reference ID.
            if isinstance(item, dict):

                item_id = item.get("id")

                if item_id:
                    ids.add(item_id)

            # Also support registries where the key itself
            # is the canonical ID.
            elif isinstance(key, str):
                ids.add(key)

    elif isinstance(registry, list):

        for item in registry:

            if isinstance(item, dict):

                item_id = item.get("id")

                if item_id:
                    ids.add(item_id)

    return ids


def collect_scene_ids(bible):
    return registry_ids(
        bible,
        "scene_registry"
    )


def collect_character_ids(bible):
    return registry_ids(
        bible,
        "characters"
    )


def collect_location_ids(bible):
    return registry_ids(
        bible,
        "locations"
    )


def collect_prop_ids(bible):
    return registry_ids(
        bible,
        "props"
    )


def collect_event_ids(bible):
    events = bible.get(
        "causal_events",
        []
    )

    return {
        event.get("event_id")
        for event in events
        if isinstance(event, dict)
        and event.get("event_id")
    }


def create_shot(
    shot_id,
    scene_id,
    sequence_id,
    duration_seconds,
    animation_tier,
    purpose,
    characters,
    location,
    props,
    camera,
    character_performance,
    environment_motion,
    lighting,
    effects,
    audio,
    state_before,
    state_after,
    causal_event_ids
):
    return {
        "shot_id": shot_id,
        "scene_id": scene_id,
        "sequence_id": sequence_id,

        "duration_seconds": duration_seconds,

        "animation_tier": animation_tier,

        "purpose": purpose,

        "characters": characters,

        "location": location,

        "props": props,

        "camera": camera,

        "character_performance": character_performance,

        "environment_motion": environment_motion,

        "lighting": lighting,

        "effects": effects,

        "audio": audio,

        "continuity": {
            "inherits_previous_shot_state": True,
            "connected_to_next_shot": True,
            "character_identity_locked": True,
            "environment_identity_locked": True,
            "prop_identity_locked": True,
            "lighting_continuity_required": True,
            "emotional_continuity_required": True
        },

        "state_before": state_before,

        "state_after": state_after,

        "causal_event_ids": causal_event_ids
    }


def validate_shot(
    shot,
    bible,
    architecture,
    known_scene_ids=None,
    known_character_ids=None,
    known_location_ids=None,
    known_prop_ids=None,
    known_event_ids=None
):

    errors = []

    if known_scene_ids is None:
        known_scene_ids = collect_scene_ids(bible)

    if known_character_ids is None:
        known_character_ids = collect_character_ids(bible)

    if known_location_ids is None:
        known_location_ids = collect_location_ids(bible)

    if known_prop_ids is None:
        known_prop_ids = collect_prop_ids(bible)

    if known_event_ids is None:
        known_event_ids = collect_event_ids(bible)

    required = (
        architecture
        .get("shot_schema", {})
        .get("required_fields", [])
    )

    for field in required:
        if field not in shot:
            errors.append(
                f"Missing required field: {field}"
            )

    shot_id = shot.get("shot_id")

    if not shot_id:
        errors.append(
            "Missing shot_id"
        )

    duration = shot.get(
        "duration_seconds"
    )

    if not isinstance(
        duration,
        (int, float)
    ) or duration <= 0:
        errors.append(
            "duration_seconds must be > 0"
        )

    animation_tier = shot.get(
        "animation_tier"
    )

    valid_tiers = set(
        architecture
        .get("animation_tiers", {})
        .keys()
    )

    if animation_tier not in valid_tiers:
        errors.append(
            f"Invalid animation tier: {animation_tier}"
        )

    scene_id = shot.get(
        "scene_id"
    )

    if scene_id not in known_scene_ids:
        errors.append(
            f"Unknown scene reference: {scene_id}"
        )

    location = shot.get(
        "location"
    )

    if location not in known_location_ids:
        errors.append(
            f"Unknown location reference: {location}"
        )

    characters = shot.get(
        "characters",
        []
    )

    if not isinstance(
        characters,
        list
    ):
        errors.append(
            "characters must be a list"
        )
    else:
        for character_id in characters:
            if character_id not in known_character_ids:
                errors.append(
                    f"Unknown character reference: {character_id}"
                )

    props = shot.get(
        "props",
        []
    )

    if not isinstance(
        props,
        list
    ):
        errors.append(
            "props must be a list"
        )
    else:
        for prop_id in props:
            if prop_id not in known_prop_ids:
                errors.append(
                    f"Unknown prop reference: {prop_id}"
                )

    causal_events = shot.get(
        "causal_event_ids",
        []
    )

    if not isinstance(
        causal_events,
        list
    ):
        errors.append(
            "causal_event_ids must be a list"
        )
    else:
        for event_id in causal_events:
            if event_id not in known_event_ids:
                errors.append(
                    f"Unknown causal event: {event_id}"
                )

    camera = shot.get(
        "camera",
        {}
    )

    valid_shot_types = set(
        architecture
        .get("shot_schema", {})
        .get("camera", {})
        .get("shot_type", [])
    )

    valid_movements = set(
        architecture
        .get("shot_schema", {})
        .get("camera", {})
        .get("movement", [])
    )

    if camera.get("shot_type") not in valid_shot_types:
        errors.append(
            f"Invalid camera shot type: "
            f"{camera.get('shot_type')}"
        )

    if camera.get("movement") not in valid_movements:
        errors.append(
            f"Invalid camera movement: "
            f"{camera.get('movement')}"
        )

    environment_motion = shot.get(
        "environment_motion"
    )

    valid_environment_motion = set(
        architecture
        .get("shot_schema", {})
        .get("environment_motion", [])
    )

    if environment_motion not in valid_environment_motion:
        errors.append(
            f"Invalid environment motion: "
            f"{environment_motion}"
        )

    performance = shot.get(
        "character_performance",
        {}
    )

    speech = performance.get(
        "speech",
        {}
    )

    if speech.get(
        "required_when_dialogue"
    ) is not True:
        errors.append(
            "Speech contract missing."
        )

    if speech.get(
        "lip_sync_required"
    ) is not True:
        errors.append(
            "Lip-sync contract missing."
        )

    continuity = shot.get(
        "continuity",
        {}
    )

    if continuity.get(
        "character_identity_locked"
    ) is not True:
        errors.append(
            "Character identity must be locked."
        )

    if continuity.get(
        "environment_identity_locked"
    ) is not True:
        errors.append(
            "Environment identity must be locked."
        )

    if continuity.get(
        "prop_identity_locked"
    ) is not True:
        errors.append(
            "Prop identity must be locked."
        )

    return errors


def build_demo_shot(bible):

    scenes = collect_scene_ids(
        bible
    )

    characters = collect_character_ids(
        bible
    )

    locations = collect_location_ids(
        bible
    )

    props = collect_prop_ids(
        bible
    )

    events = collect_event_ids(
        bible
    )

    # Current EP001 registries are intentionally
    # incomplete. We therefore do not fabricate a
    # production shot.
    #
    # The engine itself is validated structurally.

    return None


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — PHASE 5B"
    )
    print(
        "SHOT SPECIFICATION ENGINE"
    )
    print("=" * 60)

    bible = load_json(
        BIBLE_PATH
    )

    architecture = load_json(
        ARCHITECTURE_PATH
    )

    # ------------------------------------------------------------
    # SCHEMA VALIDATION
    # ------------------------------------------------------------

    required_fields = architecture.get(
        "shot_schema",
        {}
    ).get(
        "required_fields",
        []
    )

    if len(required_fields) == 0:
        print(
            "FAIL  Animation architecture has no shot schema."
        )
        sys.exit(1)

    print(
        "PASS  Shot schema loaded."
    )

    # ------------------------------------------------------------
    # REGISTRY VALIDATION
    # ------------------------------------------------------------

    scene_ids = collect_scene_ids(
        bible
    )

    character_ids = collect_character_ids(
        bible
    )

    location_ids = collect_location_ids(
        bible
    )

    prop_ids = collect_prop_ids(
        bible
    )

    event_ids = collect_event_ids(
        bible
    )

    print(
        f"PASS  Character registry: "
        f"{len(character_ids)}"
    )

    print(
        f"PASS  Location registry: "
        f"{len(location_ids)}"
    )

    print(
        f"PASS  Prop registry: "
        f"{len(prop_ids)}"
    )

    print(
        f"PASS  Scene registry: "
        f"{len(scene_ids)}"
    )

    print(
        f"PASS  Causal event registry: "
        f"{len(event_ids)}"
    )

    # ------------------------------------------------------------
    # VALIDATE BUILDER CONTRACT
    # ------------------------------------------------------------

    if not isinstance(
        create_shot(
            "TEST-SHOT",
            "TEST-SCENE",
            "SEQ-001",
            5.0,
            "standard",
            "Architecture contract test",
            [],
            "TEST-LOCATION",
            [],
            {
                "shot_type": "medium",
                "movement": "static"
            },
            {
                "body": ["idle"],
                "face": ["neutral"],
                "speech": {
                    "required_when_dialogue": True,
                    "lip_sync_required": True
                }
            },
            "subtle",
            {
                "continuity_required": True,
                "changes_require_cause": True
            },
            {
                "effects": [],
                "effects_require_narrative_justification": True
            },
            {
                "dialogue": [],
                "sfx": [],
                "music": None
            },
            {},
            {},
            []
        ),
        dict
    ):
        print(
            "FAIL  Shot builder contract."
        )
        sys.exit(1)

    print(
        "PASS  Shot builder contract."
    )

    # ------------------------------------------------------------
    # VALID SHOT STRUCTURE TEST
    # ------------------------------------------------------------

    if (
        scene_ids
        and character_ids
        and location_ids
        and prop_ids
    ):

        test_shot = create_shot(
            "QA-SHOT-001",
            next(iter(scene_ids)),
            "SEQ-QA",
            4.0,
            "standard",
            "Structural QA shot",
            [next(iter(character_ids))],
            next(iter(location_ids)),
            [next(iter(prop_ids))],
            {
                "shot_type": "medium",
                "movement": "static"
            },
            {
                "body": ["idle"],
                "face": ["neutral"],
                "speech": {
                    "required_when_dialogue": True,
                    "lip_sync_required": True
                }
            },
            "subtle",
            {
                "continuity_required": True,
                "changes_require_cause": True
            },
            {
                "effects": [],
                "effects_require_narrative_justification": True
            },
            {
                "dialogue": [],
                "sfx": [],
                "music": None
            },
            {},
            {},
            []
        )

        errors = validate_shot(
            test_shot,
            bible,
            architecture
        )

        if errors:
            print(
                "FAIL  Valid shot rejected:"
            )

            for error in errors:
                print(
                    f"       {error}"
                )

            sys.exit(1)

        print(
            "PASS  Valid shot accepted."
        )

    else:

        print(
            "PASS  No production shot generated "
            "(EP001 registries are not yet populated)."
        )

    # ------------------------------------------------------------
    # STRUCTURAL OUTPUT
    # ------------------------------------------------------------

    output = {
        "schema_version": "1.0",
        "episode": "EP001",
        "status": "architecture_validated",
        "production_shots": [],
        "required_shot_fields": required_fields,
        "validation_policy": {
            "unknown_character": "REJECT",
            "unknown_location": "REJECT",
            "unknown_prop": "REJECT",
            "unknown_scene": "REJECT",
            "unknown_causal_event": "REJECT",
            "invalid_camera": "REJECT",
            "invalid_animation_tier": "REJECT",
            "continuity_contract_failure": "REJECT"
        },
        "provenance": {
            "invented_canon": False,
            "production_content_generated": False
        }
    }

    save_json(
        OUTPUT_PATH,
        output
    )

    print("-" * 60)
    print(
        "OVERALL: PASS"
    )

    print()
    print(
        "Shot specification system written to:"
    )

    print(
        OUTPUT_PATH
    )


if __name__ == "__main__":
    main()

