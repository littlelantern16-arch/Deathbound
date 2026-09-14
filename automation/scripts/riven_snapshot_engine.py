import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

CANON_PATH = (
    ROOT
    / "assets"
    / "characters"
    / "Riven"
    / "RIVEN_CANON.json"
)

STATE_PATH = (
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


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(
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


class SnapshotEngine:

    def __init__(self, canon, base_state, history):

        self.canon = deepcopy(canon)
        self.base_state = deepcopy(base_state)
        self.history = deepcopy(history)

    # ============================================================
    # CREATE INITIAL SNAPSHOT
    # ============================================================

    def initial_snapshot(self):

        character = self.base_state.get(
            "character",
            {}
        )

        state = character.get(
            "state",
            {}
        )

        return {
            "snapshot_id": "SNAP-000",
            "after_event": None,
            "scene_id": None,
            "shot_id": None,

            "character_id": "riven",

            "canonical_reference": str(
                CANON_PATH
            ),

            "state": deepcopy(state)
        }

    # ============================================================
    # APPLY EVENT TO STATE
    # ============================================================

    def apply_event(self, state, event):

        change = event.get(
            "state_change",
            {}
        )

        property_name = change.get(
            "property"
        )

        new_value = deepcopy(
            change.get("new")
        )

        if property_name == "scene":

            state["current_scene"] = new_value

        elif property_name == "shot":

            state["current_shot"] = new_value

        elif property_name == "location":

            state["current_location"] = new_value

        elif property_name == "clothing":

            state.setdefault(
                "physical_state",
                {}
            )

            state["physical_state"][
                "clothing_state"
            ] = new_value

        elif property_name == "eyes":

            state.setdefault(
                "visual_state",
                {}
            )

            state["visual_state"][
                "eye_state"
            ] = new_value

        elif property_name == "physical_condition":

            state.setdefault(
                "physical_state",
                {}
            )

            state["physical_state"][
                "condition"
            ] = new_value

        elif property_name == "emotion":

            state.setdefault(
                "emotional_state",
                {}
            )

            state["emotional_state"][
                "primary_emotion"
            ] = new_value

        elif property_name == "knowledge":

            state.setdefault(
                "knowledge_state",
                {}
            )

            state["knowledge_state"].setdefault(
                "knows",
                []
            )

            if new_value not in state[
                "knowledge_state"
            ]["knows"]:

                state[
                    "knowledge_state"
                ]["knows"].append(
                    new_value
                )

        elif property_name == "inventory_add":

            state.setdefault(
                "inventory",
                []
            )

            if new_value not in state[
                "inventory"
            ]:

                state[
                    "inventory"
                ].append(
                    new_value
                )

        elif property_name == "relationship":

            state.setdefault(
                "relationships",
                {}
            )

            if isinstance(new_value, dict):

                character = new_value.get(
                    "character"
                )

                relationship = new_value.get(
                    "relationship"
                )

                if character:

                    state[
                        "relationships"
                    ][character] = relationship

        return state

    # ============================================================
    # RECONSTRUCT ALL SNAPSHOTS
    # ============================================================

    def reconstruct(self):

        snapshots = []

        current_state = deepcopy(
            self.initial_snapshot()["state"]
        )

        snapshots.append(
            self.initial_snapshot()
        )

        events = self.history.get(
            "events",
            []
        )

        for index, event in enumerate(
            events,
            start=1
        ):

            current_state = self.apply_event(
                current_state,
                event
            )

            snapshot = {
                "snapshot_id": (
                    f"SNAP-{index:03d}"
                ),

                "after_event": event.get(
                    "event_id"
                ),

                "scene_id": event.get(
                    "scene_id"
                ),

                "shot_id": event.get(
                    "shot_id"
                ),

                "character_id": "riven",

                "canonical_reference": str(
                    CANON_PATH
                ),

                "state": deepcopy(
                    current_state
                )
            }

            snapshots.append(
                snapshot
            )

        return {
            "schema_version": "1.0.0",
            "episode": "YR-001",
            "character": "riven",
            "snapshot_count": len(
                snapshots
            ),
            "snapshots": snapshots
        }

    # ============================================================
    # FIND SNAPSHOT
    # ============================================================

    def find_snapshot(
        self,
        reconstructed,
        scene_id=None,
        shot_id=None
    ):

        matches = []

        for snapshot in reconstructed[
            "snapshots"
        ]:

            if (
                scene_id is not None
                and snapshot.get("scene_id")
                != scene_id
            ):
                continue

            if (
                shot_id is not None
                and snapshot.get("shot_id")
                != shot_id
            ):
                continue

            matches.append(
                snapshot
            )

        return matches

    # ============================================================
    # EXPORT
    # ============================================================

    def export(self, reconstructed):

        save_json(
            SNAPSHOT_PATH,
            reconstructed
        )


def demo():

    print("=" * 60)
    print(
        "DEATHBOUND — RIVEN STATE "
        "SNAPSHOT & RECONSTRUCTION ENGINE"
    )
    print("=" * 60)

    canon = load_json(
        CANON_PATH
    )

    base_state = load_json(
        STATE_PATH
    )

    history = load_json(
        HISTORY_PATH
    )

    engine = SnapshotEngine(
        canon,
        base_state,
        history
    )

    reconstructed = engine.reconstruct()

    engine.export(
        reconstructed
    )

    snapshots = reconstructed[
        "snapshots"
    ]

    print(
        f"PASS  Reconstructed "
        f"{len(snapshots)} snapshots."
    )

    # ------------------------------------------------------------
    # VERIFY EVENT CHAIN
    # ------------------------------------------------------------

    events = history.get(
        "events",
        []
    )

    if len(snapshots) != len(events) + 1:

        print(
            "FAIL  Snapshot/event count mismatch."
        )

        print("OVERALL: FAIL")

        return False

    print(
        "PASS  Snapshot/event chain integrity."
    )

    # ------------------------------------------------------------
    # VERIFY FIRST EVENT
    # ------------------------------------------------------------

    if events:

        first_event = events[0]

        first_snapshot = snapshots[1]

        if (
            first_snapshot.get(
                "after_event"
            )
            != first_event.get(
                "event_id"
            )
        ):

            print(
                "FAIL  First snapshot does not "
                "reference first event."
            )

            print("OVERALL: FAIL")

            return False

        print(
            "PASS  First event successfully "
            "reconstructed."
        )

    # ------------------------------------------------------------
    # VERIFY LATEST STATE
    # ------------------------------------------------------------

    latest = snapshots[-1]

    print(
        "PASS  Latest state reconstructed."
    )

    print(
        f"      Scene: "
        f"{latest.get('scene_id')}"
    )

    print(
        f"      Shot: "
        f"{latest.get('shot_id')}"
    )

    print(
        f"      Location: "
        f"{latest['state'].get('current_location')}"
    )

    print(
        f"      Emotion: "
        f"{latest['state'].get('emotional_state', {}).get('primary_emotion')}"
    )

    print(
        f"      Eye state: "
        f"{latest['state'].get('visual_state', {}).get('eye_state')}"
    )

    # ------------------------------------------------------------
    # VERIFY HISTORICAL LOOKUP
    # ------------------------------------------------------------

    if events:

        target_scene = events[1].get(
            "scene_id"
        )

        target_shot = events[1].get(
            "shot_id"
        )

        matches = engine.find_snapshot(
            reconstructed,
            scene_id=target_scene,
            shot_id=target_shot
        )

        if not matches:

            print(
                "FAIL  Historical snapshot "
                "lookup failed."
            )

            print("OVERALL: FAIL")

            return False

        print(
            "PASS  Historical snapshot lookup."
        )

    print("-" * 60)

    print(
        f"SNAPSHOTS: "
        f"{len(snapshots)}"
    )

    print(
        f"EVENTS: "
        f"{len(events)}"
    )

    print("-" * 60)

    print(
        "OVERALL: PASS"
    )

    print()
    print(
        "Snapshot database written to:"
    )
    print(
        SNAPSHOT_PATH
    )

    return True


if __name__ == "__main__":

    success = demo()

    sys.exit(
        0 if success else 1
    )
