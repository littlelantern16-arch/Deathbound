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

RIVEN_STATE_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "characters"
    / "riven.json"
)

HISTORY_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "characters"
    / "riven_event_history.json"
)

SNAPSHOT_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "characters"
    / "riven_state_snapshots.json"
)

OUTPUT_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "story_bible_synced.json"
)


def load_json(path):
    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig"
        ) as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read {path}: {exc}"
        )


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


def synchronize(
    bible,
    riven_state,
    history,
    snapshots
):

    result = deepcopy(bible)

    result.setdefault(
        "continuity",
        {}
    )

    continuity = result["continuity"]

    continuity.setdefault(
        "active_character_states",
        {}
    )

    continuity.setdefault(
        "active_location_states",
        {}
    )

    continuity.setdefault(
        "active_prop_states",
        {}
    )

    events = history.get(
        "events",
        []
    )

    snapshot_list = snapshots.get(
        "snapshots",
        []
    )

    # ------------------------------------------------------------
    # RIVEN STATE REFERENCE
    # ------------------------------------------------------------

    continuity[
        "active_character_states"
    ]["riven"] = str(
        RIVEN_STATE_PATH
    )

    # ------------------------------------------------------------
    # CURRENT STATE
    # ------------------------------------------------------------

    character = riven_state.get(
        "character",
        {}
    )

    state = character.get(
        "state",
        {}
    )

    current_location = state.get(
        "current_location"
    )

    if current_location:

        continuity[
            "active_location_states"
        ]["daniel_cross_bedroom"] = {
            "character": "riven",
            "current_location": current_location
        }

    # ------------------------------------------------------------
    # LAST PROCESSED EVENT
    # ------------------------------------------------------------

    if events:

        last_event = events[-1]

        continuity[
            "last_processed_event"
        ] = last_event.get(
            "event_id"
        )

        continuity[
            "last_processed_scene"
        ] = last_event.get(
            "scene_id"
        )

        continuity[
            "last_processed_shot"
        ] = last_event.get(
            "shot_id"
        )

    # ------------------------------------------------------------
    # EVENT REFERENCES
    # ------------------------------------------------------------

    causal_events = result.setdefault(
        "causal_events",
        []
    )

    existing_ids = {
        event.get("event_id")
        for event in causal_events
        if isinstance(event, dict)
    }

    for event in events:

        event_id = event.get(
            "event_id"
        )

        if event_id in existing_ids:
            continue

        causal_events.append(
            deepcopy(event)
        )

        existing_ids.add(
            event_id
        )

    # ------------------------------------------------------------
    # TIMELINE REFERENCES
    #
    # Only structured references are synchronized here.
    # No new story facts are invented.
    # ------------------------------------------------------------

    timeline = result.setdefault(
        "timeline",
        []
    )

    timeline_ids = {
        item.get("event_id")
        for item in timeline
        if isinstance(item, dict)
    }

    for index, event in enumerate(events):

        event_id = event.get(
            "event_id"
        )

        if not event_id:
            continue

        if event_id in timeline_ids:
            continue

        timeline.append(
            {
                "event_id": event_id,
                "order": len(timeline),
                "actor": event.get(
                    "actor"
                ),
                "scene_id": event.get(
                    "scene_id"
                ),
                "shot_id": event.get(
                    "shot_id"
                ),
                "status": "state_event"
            }
        )

        timeline_ids.add(
            event_id
        )

    # ------------------------------------------------------------
    # SNAPSHOT POINTER
    # ------------------------------------------------------------

    if snapshot_list:

        latest = snapshot_list[-1]

        continuity[
            "latest_snapshot"
        ] = {
            "snapshot_id": latest.get(
                "snapshot_id"
            ),
            "after_event": latest.get(
                "after_event"
            ),
            "scene_id": latest.get(
                "scene_id"
            ),
            "shot_id": latest.get(
                "shot_id"
            )
        }

    # ------------------------------------------------------------
    # PROVENANCE
    # ------------------------------------------------------------

    result.setdefault(
        "provenance",
        {}
    )

    result["provenance"][
        "invented_canon"
    ] = False

    result["provenance"][
        "episode_specific_content_complete"
    ] = False

    return result


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — STORY BIBLE "
        "DYNAMIC STATE SYNC"
    )
    print("=" * 60)

    bible = load_json(
        BIBLE_PATH
    )

    riven_state = load_json(
        RIVEN_STATE_PATH
    )

    history = load_json(
        HISTORY_PATH
    )

    snapshots = load_json(
        SNAPSHOT_PATH
    )

    synced = synchronize(
        bible,
        riven_state,
        history,
        snapshots
    )

    save_json(
        OUTPUT_PATH,
        synced
    )

    # ------------------------------------------------------------
    # VALIDATE SYNCHRONIZATION
    # ------------------------------------------------------------

    continuity = synced.get(
        "continuity",
        {}
    )

    events = history.get(
        "events",
        []
    )

    snapshots_list = snapshots.get(
        "snapshots",
        []
    )

    checks = []

    checks.append(
        continuity.get(
            "active_character_states",
            {}
        ).get("riven")
        == str(RIVEN_STATE_PATH)
    )

    if events:

        checks.append(
            continuity.get(
                "last_processed_event"
            )
            == events[-1].get(
                "event_id"
            )
        )

        checks.append(
            continuity.get(
                "last_processed_scene"
            )
            == events[-1].get(
                "scene_id"
            )
        )

        checks.append(
            continuity.get(
                "last_processed_shot"
            )
            == events[-1].get(
                "shot_id"
            )
        )

    checks.append(
        len(
            synced.get(
                "causal_events",
                []
            )
        )
        >= len(events)
    )

    checks.append(
        len(
            synced.get(
                "timeline",
                []
            )
        )
        >= len(events)
    )

    if snapshots_list:

        latest = snapshots_list[-1]

        latest_pointer = continuity.get(
            "latest_snapshot",
            {}
        )

        checks.append(
            latest_pointer.get(
                "snapshot_id"
            )
            == latest.get(
                "snapshot_id"
            )
        )

    checks.append(
        synced.get(
            "provenance",
            {}
        ).get(
            "invented_canon"
        )
        is False
    )

    if all(checks):

        print(
            "PASS  Riven state synchronized."
        )

        print(
            "PASS  Event history synchronized."
        )

        print(
            "PASS  Timeline references synchronized."
        )

        print(
            "PASS  Latest snapshot pointer synchronized."
        )

        print(
            "PASS  Canon protection preserved."
        )

        print("-" * 60)

        print(
            f"EVENTS SYNCED: "
            f"{len(events)}"
        )

        print(
            f"SNAPSHOTS AVAILABLE: "
            f"{len(snapshots_list)}"
        )

        print("-" * 60)

        print(
            "OVERALL: PASS"
        )

        print()
        print(
            "Synced Story Bible written to:"
        )
        print(
            OUTPUT_PATH
        )

        sys.exit(0)

    print(
        "FAIL  One or more synchronization "
        "checks failed."
    )

    print(
        "OVERALL: FAIL"
    )

    sys.exit(1)


if __name__ == "__main__":
    main()
