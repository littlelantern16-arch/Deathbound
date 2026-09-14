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

OUTPUT_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "characters"
    / "riven_state_engine_output.json"
)


def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(f"Could not read {path}: {exc}")


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat()


def get_nested(obj, *keys, default=None):
    current = obj

    for key in keys:
        if not isinstance(current, dict):
            return default

        if key not in current:
            return default

        current = current[key]

    return current


def ensure_state_shape(state):
    """
    Makes sure the episode state has the structures required
    by the transition engine without modifying canonical data.
    """

    if "character" not in state:
        state["character"] = {}

    character = state["character"]

    character.setdefault("id", "riven")
    character.setdefault("canonical_reference", str(CANON_PATH))

    episode_state = character.setdefault("state", {})

    episode_state.setdefault("current_scene", None)
    episode_state.setdefault("current_shot", None)
    episode_state.setdefault("current_location", None)

    episode_state.setdefault(
        "physical_state",
        {
            "condition": "normal",
            "injuries": [],
            "clothing_state": "default",
            "environmental_effects": []
        }
    )

    episode_state.setdefault(
        "emotional_state",
        {
            "primary_emotion": None,
            "secondary_emotion": None,
            "intensity": None,
            "trigger": None,
            "objective": None,
            "internal_conflict": None,
            "external_behavior": None
        }
    )

    episode_state.setdefault(
        "knowledge_state",
        {
            "knows": [],
            "does_not_know": [],
            "suspects": [],
            "believes": [],
            "confirmed": [],
            "misunderstands": []
        }
    )

    episode_state.setdefault("inventory", [])
    episode_state.setdefault("relationships", {})
    episode_state.setdefault("continuity_events", [])

    return state


class RivenStateEngine:

    def __init__(self, canon, state):
        self.canon = canon
        self.state = ensure_state_shape(deepcopy(state))

        self.episode_state = self.state["character"]["state"]

    # ------------------------------------------------------------
    # CANONICAL PROTECTION
    # ------------------------------------------------------------

    def canonical_value(self, *path):
        return get_nested(self.canon, *path)

    def immutable_check(self, transition):
        """
        Prevents episode transitions from changing canonical identity.
        """

        forbidden = {
            "id",
            "name",
            "age_appearance",
            "body_type",
            "skin",
            "hair",
            "default_eyes",
            "canonical_clothing"
        }

        if transition["type"] in forbidden:
            return False, (
                f"Attempted mutation of immutable canonical property: "
                f"{transition['type']}"
            )

        return True, None

    # ------------------------------------------------------------
    # TRANSITION VALIDATION
    # ------------------------------------------------------------

    def validate_transition(self, transition):

        required = [
            "type",
            "new_value",
            "cause"
        ]

        for field in required:
            if field not in transition:
                return False, f"Missing required transition field: {field}"

        if not transition["cause"]:
            return False, "Every state transition requires a narrative cause."

        immutable_ok, immutable_error = self.immutable_check(transition)

        if not immutable_ok:
            return False, immutable_error

        transition_type = transition["type"]
        new_value = transition["new_value"]

        # --------------------------------------------------------
        # CLOTHING
        # --------------------------------------------------------

        if transition_type == "clothing":

            if new_value == "default":
                return True, None

            if not transition.get("cause"):
                return False, (
                    "Clothing changes require a narrative cause."
                )

        # --------------------------------------------------------
        # EYES
        # --------------------------------------------------------

        if transition_type == "eyes":

            allowed = [
                "dark",
                "supernatural_glow"
            ]

            if new_value not in allowed:
                return False, f"Unknown eye state: {new_value}"

            if new_value == "supernatural_glow":
                cause = transition.get("cause", "").lower()

                supernatural_keywords = [
                    "power",
                    "ability",
                    "supernatural",
                    "ledger",
                    "reaper",
                    "magic",
                    "activation"
                ]

                if not any(
                    keyword in cause
                    for keyword in supernatural_keywords
                ):
                    return False, (
                        "Supernatural eye activation requires "
                        "a supernatural narrative cause."
                    )

        # --------------------------------------------------------
        # KNOWLEDGE
        # --------------------------------------------------------

        if transition_type == "knowledge":

            if not transition.get("event_id"):
                return False, (
                    "Knowledge changes require a causal event_id."
                )

        # --------------------------------------------------------
        # EMOTION
        # --------------------------------------------------------

        if transition_type == "emotion":

            if not isinstance(new_value, dict):
                return False, (
                    "Emotion transition must provide an object."
                )

            if not new_value.get("primary_emotion"):
                return False, (
                    "Emotion transition requires primary_emotion."
                )

            if new_value.get("intensity") is None:
                return False, (
                    "Emotion transition requires intensity."
                )

        # --------------------------------------------------------
        # SCENE
        # --------------------------------------------------------

        if transition_type == "scene":

            if not isinstance(new_value, str) or not new_value.strip():
                return False, "Scene must be a non-empty string."

        # --------------------------------------------------------
        # SHOT
        # --------------------------------------------------------

        if transition_type == "shot":

            if not isinstance(new_value, str) or not new_value.strip():
                return False, "Shot must be a non-empty string."

        # --------------------------------------------------------
        # LOCATION
        # --------------------------------------------------------

        if transition_type == "location":

            if not isinstance(new_value, str) or not new_value.strip():
                return False, "Location must be a non-empty string."

        # --------------------------------------------------------
        # PHYSICAL CONDITION
        # --------------------------------------------------------

        if transition_type == "physical_condition":

            if not isinstance(new_value, str) or not new_value.strip():
                return False, (
                    "Physical condition must be a non-empty string."
                )

        # --------------------------------------------------------
        # INVENTORY
        # --------------------------------------------------------

        if transition_type == "inventory_add":

            if not isinstance(new_value, str) or not new_value.strip():
                return False, "Inventory item must be a non-empty string."

        # --------------------------------------------------------
        # RELATIONSHIP
        # --------------------------------------------------------

        if transition_type == "relationship":

            if not isinstance(new_value, dict):
                return False, (
                    "Relationship transition must provide an object."
                )

            if not new_value.get("character"):
                return False, (
                    "Relationship transition requires character."
                )

            if not new_value.get("relationship"):
                return False, (
                    "Relationship transition requires relationship."
                )

        return True, None

    # ------------------------------------------------------------
    # APPLY TRANSITION
    # ------------------------------------------------------------

    def apply_transition(self, transition):

        valid, error = self.validate_transition(transition)

        if not valid:
            return {
                "status": "REJECTED",
                "reason": error,
                "transition": transition
            }

        transition_type = transition["type"]
        new_value = deepcopy(transition["new_value"])

        event = {
            "event_id": transition.get(
                "event_id",
                "EVT-" + uuid4().hex[:10]
            ),
            "timestamp": utc_timestamp(),
            "scene": self.episode_state.get("current_scene"),
            "shot": self.episode_state.get("current_shot"),
            "type": transition_type,
            "previous_state": None,
            "new_state": deepcopy(new_value),
            "cause": transition["cause"]
        }

        # --------------------------------------------------------
        # SCENE
        # --------------------------------------------------------

        if transition_type == "scene":
            event["previous_state"] = (
                self.episode_state.get("current_scene")
            )

            self.episode_state["current_scene"] = new_value

        # --------------------------------------------------------
        # SHOT
        # --------------------------------------------------------

        elif transition_type == "shot":
            event["previous_state"] = (
                self.episode_state.get("current_shot")
            )

            self.episode_state["current_shot"] = new_value

        # --------------------------------------------------------
        # LOCATION
        # --------------------------------------------------------

        elif transition_type == "location":
            event["previous_state"] = (
                self.episode_state.get("current_location")
            )

            self.episode_state["current_location"] = new_value

        # --------------------------------------------------------
        # CLOTHING
        # --------------------------------------------------------

        elif transition_type == "clothing":
            event["previous_state"] = (
                self.episode_state
                .get("physical_state", {})
                .get("clothing_state")
            )

            self.episode_state["physical_state"][
                "clothing_state"
            ] = new_value

        # --------------------------------------------------------
        # EYES
        # --------------------------------------------------------

        elif transition_type == "eyes":
            event["previous_state"] = (
                self.episode_state
                .get("visual_state", {})
                .get("eye_state", "dark")
            )

            self.episode_state.setdefault(
                "visual_state",
                {}
            )

            self.episode_state["visual_state"][
                "eye_state"
            ] = new_value

        # --------------------------------------------------------
        # PHYSICAL CONDITION
        # --------------------------------------------------------

        elif transition_type == "physical_condition":
            event["previous_state"] = (
                self.episode_state
                .get("physical_state", {})
                .get("condition")
            )

            self.episode_state["physical_state"][
                "condition"
            ] = new_value

        # --------------------------------------------------------
        # EMOTION
        # --------------------------------------------------------

        elif transition_type == "emotion":
            event["previous_state"] = deepcopy(
                self.episode_state.get(
                    "emotional_state",
                    {}
                )
            )

            self.episode_state["emotional_state"] = new_value

        # --------------------------------------------------------
        # KNOWLEDGE
        # --------------------------------------------------------

        elif transition_type == "knowledge":
            event["previous_state"] = deepcopy(
                self.episode_state
                .get("knowledge_state", {})
            )

            knowledge = self.episode_state.setdefault(
                "knowledge_state",
                {
                    "knows": [],
                    "does_not_know": [],
                    "suspects": [],
                    "believes": [],
                    "confirmed": [],
                    "misunderstands": []
                }
            )

            knowledge.setdefault("knows", [])

            if new_value not in knowledge["knows"]:
                knowledge["knows"].append(new_value)

        # --------------------------------------------------------
        # INVENTORY
        # --------------------------------------------------------

        elif transition_type == "inventory_add":
            event["previous_state"] = deepcopy(
                self.episode_state.get("inventory", [])
            )

            inventory = self.episode_state.setdefault(
                "inventory",
                []
            )

            if new_value not in inventory:
                inventory.append(new_value)

        # --------------------------------------------------------
        # RELATIONSHIP
        # --------------------------------------------------------

        elif transition_type == "relationship":
            event["previous_state"] = deepcopy(
                self.episode_state
                .get("relationships", {})
            )

            relationships = self.episode_state.setdefault(
                "relationships",
                {}
            )

            relationships[
                new_value["character"]
            ] = new_value["relationship"]

        else:
            return {
                "status": "REJECTED",
                "reason": (
                    f"Unsupported transition type: "
                    f"{transition_type}"
                ),
                "transition": transition
            }

        self.episode_state["continuity_events"].append(event)

        return {
            "status": "ACCEPTED",
            "event": event
        }

    # ------------------------------------------------------------
    # EXPORT
    # ------------------------------------------------------------

    def export(self):
        save_json(OUTPUT_PATH, self.state)


def run_demo():

    print("=" * 60)
    print("DEATHBOUND — RIVEN STATE TRANSITION ENGINE")
    print("=" * 60)

    canon = load_json(CANON_PATH)
    state = load_json(STATE_PATH)

    engine = RivenStateEngine(canon, state)

    tests = [

        {
            "name": "Scene transition",
            "transition": {
                "type": "scene",
                "new_value": "SCENE-001",
                "cause": "Episode begins."
            }
        },

        {
            "name": "Location transition",
            "transition": {
                "type": "location",
                "new_value": "Daniel Cross Bedroom",
                "cause": "Riven enters Daniel Cross's bedroom."
            }
        },

        {
            "name": "Emotion transition",
            "transition": {
                "type": "emotion",
                "new_value": {
                    "primary_emotion": "curiosity",
                    "secondary_emotion": "concern",
                    "intensity": 65,
                    "trigger": "Riven observes Daniel's final minutes.",
                    "objective": "Understand Daniel's true priority.",
                    "internal_conflict": "Riven questions whether death should be absolute.",
                    "external_behavior": "Quiet observation."
                },
                "cause": "Riven notices Daniel is more afraid of losing his daughter than losing his fortune."
            }
        },

        {
            "name": "Supernatural eye activation",
            "transition": {
                "type": "eyes",
                "new_value": "supernatural_glow",
                "cause": "Riven activates his Reaper ability to inspect the Ledger.",
                "event_id": "EVT-EYE-001"
            }
        },

        {
            "name": "Knowledge transition",
            "transition": {
                "type": "knowledge",
                "new_value": "Daniel has only minutes remaining.",
                "cause": "The Ledger reveals Daniel's appointed death.",
                "event_id": "EVT-KNOW-001"
            }
        },

        {
            "name": "Inventory transition",
            "transition": {
                "type": "inventory_add",
                "new_value": "Reaper's Ledger",
                "cause": "Riven carries the Ledger into the human world."
            }
        },

        {
            "name": "Invalid age mutation",
            "transition": {
                "type": "age_appearance",
                "new_value": "30",
                "cause": "No narrative cause."
            }
        },

        {
            "name": "Invalid unexplained clothing change",
            "transition": {
                "type": "clothing",
                "new_value": "red suit",
                "cause": ""
            }
        },

        {
            "name": "Invalid unexplained eye activation",
            "transition": {
                "type": "eyes",
                "new_value": "supernatural_glow",
                "cause": "He looks at Daniel."
            }
        }
    ]

    accepted = 0
    rejected = 0
    unexpected = 0

    for test in tests:

        result = engine.apply_transition(
            test["transition"]
        )

        status = result["status"]

        if status == "ACCEPTED":
            accepted += 1
            print(
                f"PASS  {test['name']} "
                f"→ ACCEPTED"
            )

        elif status == "REJECTED":
            rejected += 1
            print(
                f"PASS  {test['name']} "
                f"→ REJECTED"
            )
            print(
                f"      Reason: "
                f"{result['reason']}"
            )

        else:
            unexpected += 1
            print(
                f"FAIL  {test['name']} "
                f"→ UNKNOWN RESULT"
            )

    engine.export()

    print("-" * 60)
    print(f"ACCEPTED: {accepted}")
    print(f"REJECTED: {rejected}")
    print(f"UNEXPECTED: {unexpected}")
    print("-" * 60)

    if unexpected == 0:
        print("OVERALL: PASS")
        print()
        print(
            "State transition output written to:"
        )
        print(OUTPUT_PATH)

        return True

    print("OVERALL: FAIL")
    return False


if __name__ == "__main__":
    success = run_demo()
    sys.exit(0 if success else 1)
