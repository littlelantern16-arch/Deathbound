import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

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


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def generate_event_id():
    return "EVT-" + uuid4().hex[:12].upper()


class CausalityEngine:

    def __init__(self, canon, state):

        self.canon = canon
        self.state = deepcopy(state)

        self.history = {
            "schema_version": "1.0.0",
            "episode": "YR-001",
            "character": "riven",
            "events": []
        }

    # ============================================================
    # REQUIRED EVENT STRUCTURE
    # ============================================================

    REQUIRED_FIELDS = [
        "event_id",
        "scene_id",
        "shot_id",
        "actor",
        "action",
        "cause",
        "state_change",
        "consequences"
    ]

    # ============================================================
    # STORY CAUSE VALIDATION
    # ============================================================

    def validate_cause(self, cause):

        if not isinstance(cause, str):
            return False, "Cause must be a string."

        cause = cause.strip()

        if not cause:
            return False, "Cause cannot be empty."

        forbidden = [
            "ai decided",
            "ai generated",
            "for visual variety",
            "because the scene needed it",
            "for visual reasons",
            "randomly",
            "just because",
            "make him look different",
            "prompt required it"
        ]

        lowered = cause.lower()

        for phrase in forbidden:
            if phrase in lowered:
                return False, (
                    "Cause describes a production decision "
                    "rather than a narrative cause."
                )

        if len(cause) < 12:
            return False, (
                "Cause is too vague. "
                "Provide a meaningful narrative cause."
            )

        return True, None

    # ============================================================
    # STATE CHANGE VALIDATION
    # ============================================================

    def validate_state_change(self, change):

        if not isinstance(change, dict):
            return False, "state_change must be an object."

        required = [
            "property",
            "previous",
            "new"
        ]

        for field in required:
            if field not in change:
                return False, (
                    f"state_change missing: {field}"
                )

        property_name = change["property"]

        immutable = [
            "identity.id",
            "identity.name",
            "appearance.age_appearance",
            "appearance.body_type",
            "appearance.skin",
            "appearance.hair",
            "appearance.default_eyes",
            "canonical_clothing"
        ]

        if property_name in immutable:
            return False, (
                f"Immutable canonical property cannot change: "
                f"{property_name}"
            )

        if property_name == "eyes":

            allowed = [
                "dark",
                "supernatural_glow"
            ]

            if change["new"] not in allowed:
                return False, (
                    f"Invalid eye state: "
                    f"{change['new']}"
                )

        return True, None

    # ============================================================
    # EVENT VALIDATION
    # ============================================================

    def validate_event(self, event):

        if not isinstance(event, dict):
            return False, "Event must be an object."

        for field in self.REQUIRED_FIELDS:

            if field not in event:
                return False, (
                    f"Missing required event field: "
                    f"{field}"
                )

        if event["actor"] != "riven":
            return False, (
                "This event engine currently targets Riven."
            )

        if not isinstance(event["scene_id"], str):
            return False, "scene_id must be a string."

        if not isinstance(event["shot_id"], str):
            return False, "shot_id must be a string."

        if not isinstance(event["action"], str):
            return False, "action must be a string."

        if not event["action"].strip():
            return False, "action cannot be empty."

        cause_ok, cause_error = self.validate_cause(
            event["cause"]
        )

        if not cause_ok:
            return False, cause_error

        change_ok, change_error = self.validate_state_change(
            event["state_change"]
        )

        if not change_ok:
            return False, change_error

        if not isinstance(
            event["consequences"],
            list
        ):
            return False, (
                "consequences must be a list."
            )

        if len(event["consequences"]) == 0:
            return False, (
                "Every state-changing event must "
                "declare at least one consequence."
            )

        return True, None

    # ============================================================
    # RECORD EVENT
    # ============================================================

    def record_event(self, event):

        valid, error = self.validate_event(event)

        if not valid:

            return {
                "status": "REJECTED",
                "reason": error,
                "event": event
            }

        event = deepcopy(event)

        if not event.get("event_id"):
            event["event_id"] = generate_event_id()

        event["timestamp"] = timestamp()

        self.history["events"].append(event)

        return {
            "status": "ACCEPTED",
            "event": event
        }

    # ============================================================
    # EXPORT
    # ============================================================

    def export_history(self):

        save_json(
            HISTORY_PATH,
            self.history
        )


def demo():

    print("=" * 60)
    print("DEATHBOUND — STRUCTURED CAUSALITY ENGINE")
    print("=" * 60)

    canon = load_json(CANON_PATH)
    state = load_json(STATE_PATH)

    engine = CausalityEngine(
        canon,
        state
    )

    tests = [

        # --------------------------------------------------------
        # VALID EVENT
        # --------------------------------------------------------

        {
            "name": "Riven activates Reaper sight",
            "event": {
                "event_id": "EVT-001",
                "scene_id": "SCENE-001",
                "shot_id": "SHOT-003",
                "actor": "riven",
                "action": "Riven activates Reaper sight.",
                "cause": (
                    "Riven needs to inspect Daniel's "
                    "Ledger entry."
                ),
                "state_change": {
                    "property": "eyes",
                    "previous": "dark",
                    "new": "supernatural_glow"
                },
                "consequences": [
                    "Riven can perceive the hidden "
                    "death entry.",
                    "The supernatural eye glow becomes "
                    "visible to the audience."
                ]
            }
        },

        # --------------------------------------------------------
        # VALID EVENT
        # --------------------------------------------------------

        {
            "name": "Riven enters Daniel's bedroom",
            "event": {
                "event_id": "EVT-002",
                "scene_id": "SCENE-001",
                "shot_id": "SHOT-004",
                "actor": "riven",
                "action": (
                    "Riven enters Daniel Cross's bedroom."
                ),
                "cause": (
                    "The Ledger directs Riven to "
                    "Daniel's appointed death location."
                ),
                "state_change": {
                    "property": "location",
                    "previous": "unknown",
                    "new": "Daniel Cross Bedroom"
                },
                "consequences": [
                    "Riven is now present in the "
                    "human environment.",
                    "The bedroom becomes Riven's "
                    "current location."
                ]
            }
        },

        # --------------------------------------------------------
        # VALID EMOTIONAL EVENT
        # --------------------------------------------------------

        {
            "name": "Riven becomes conflicted",
            "event": {
                "event_id": "EVT-003",
                "scene_id": "SCENE-002",
                "shot_id": "SHOT-011",
                "actor": "riven",
                "action": (
                    "Riven becomes emotionally conflicted."
                ),
                "cause": (
                    "Daniel chooses to call his estranged "
                    "daughter instead of protecting his fortune."
                ),
                "state_change": {
                    "property": "emotion",
                    "previous": "detached",
                    "new": "conflicted"
                },
                "consequences": [
                    "Riven begins questioning "
                    "Daniel's appointed death.",
                    "Riven's behavior becomes less detached."
                ]
            }
        },

        # --------------------------------------------------------
        # INVALID: PRODUCTION-ONLY CAUSE
        # --------------------------------------------------------

        {
            "name": "Invalid production reason",
            "event": {
                "event_id": "EVT-INVALID-001",
                "scene_id": "SCENE-002",
                "shot_id": "SHOT-012",
                "actor": "riven",
                "action": (
                    "Riven changes his clothing."
                ),
                "cause": (
                    "For visual variety."
                ),
                "state_change": {
                    "property": "clothing",
                    "previous": "default",
                    "new": "red suit"
                },
                "consequences": [
                    "Riven looks different."
                ]
            }
        },

        # --------------------------------------------------------
        # INVALID: CANONICAL MUTATION
        # --------------------------------------------------------

        {
            "name": "Invalid canonical age mutation",
            "event": {
                "event_id": "EVT-INVALID-002",
                "scene_id": "SCENE-003",
                "shot_id": "SHOT-001",
                "actor": "riven",
                "action": (
                    "Riven appears older."
                ),
                "cause": (
                    "A supernatural event changes his appearance."
                ),
                "state_change": {
                    "property": (
                        "appearance.age_appearance"
                    ),
                    "previous": "19-22",
                    "new": "35"
                },
                "consequences": [
                    "Riven appears significantly older."
                ]
            }
        },

        # --------------------------------------------------------
        # INVALID: VAGUE CAUSE
        # --------------------------------------------------------

        {
            "name": "Invalid vague cause",
            "event": {
                "event_id": "EVT-INVALID-003",
                "scene_id": "SCENE-003",
                "shot_id": "SHOT-002",
                "actor": "riven",
                "action": (
                    "Riven's eyes glow."
                ),
                "cause": "Magic.",
                "state_change": {
                    "property": "eyes",
                    "previous": "dark",
                    "new": "supernatural_glow"
                },
                "consequences": [
                    "The audience sees the glow."
                ]
            }
        }
    ]

    accepted = 0
    rejected = 0
    unexpected = 0

    for test in tests:

        result = engine.record_event(
            test["event"]
        )

        if result["status"] == "ACCEPTED":

            accepted += 1

            print(
                f"PASS  {test['name']} → ACCEPTED"
            )

        elif result["status"] == "REJECTED":

            rejected += 1

            print(
                f"PASS  {test['name']} → REJECTED"
            )

            print(
                f"      Reason: "
                f"{result['reason']}"
            )

        else:

            unexpected += 1

            print(
                f"FAIL  {test['name']} → UNKNOWN"
            )

    engine.export_history()

    print("-" * 60)

    print(f"ACCEPTED:   {accepted}")
    print(f"REJECTED:   {rejected}")
    print(f"UNEXPECTED: {unexpected}")

    print("-" * 60)

    if unexpected == 0:

        print("OVERALL: PASS")
        print()
        print(
            "Event history written to:"
        )
        print(HISTORY_PATH)

        return True

    print("OVERALL: FAIL")

    return False


if __name__ == "__main__":

    success = demo()

    sys.exit(
        0 if success else 1
    )
