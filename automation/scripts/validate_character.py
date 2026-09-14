import json
import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

CANON_PATH = ROOT / "assets" / "characters" / "Riven" / "RIVEN_CANON.json"

REQUIRED_CANON_FIELDS = [
    ("schema_version",),
    ("character_canon_version",),
    ("identity", "id"),
    ("identity", "name"),
    ("identity", "universe"),
    ("appearance", "age_appearance"),
    ("appearance", "body_type"),
    ("appearance", "skin"),
    ("appearance", "hair", "color"),
    ("appearance", "hair", "style"),
    ("appearance", "eyes", "default"),
    ("clothing", "default", "coat"),
    ("clothing", "default", "shirt"),
    ("clothing", "default", "trousers"),
    ("clothing", "default", "boots"),
    ("personality", "traits")
]

def load_json(path):
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            return json.load(f)
    except Exception as exc:
        print(f"FAIL  Could not read {path}: {exc}")
        return None

def get_path(obj, path):
    current = obj
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current

def validate_canon():
    errors = []
    warnings = []

    canon = load_json(CANON_PATH)

    if canon is None:
        return False

    for path in REQUIRED_CANON_FIELDS:
        if get_path(canon, path) is None:
            errors.append("Missing canonical field: " + ".".join(path))

    if canon.get("identity", {}).get("id") != "riven":
        errors.append("Canonical character ID must be 'riven'.")

    if canon.get("identity", {}).get("name") != "Riven":
        errors.append("Canonical character name must be 'Riven'.")

    if canon.get("appearance", {}).get("age_appearance") != "19-22":
        errors.append("Canonical age appearance must remain 19-22.")

    if canon.get("appearance", {}).get("body_type") != "slim/lean":
        errors.append("Canonical body type must remain slim/lean.")

    eyes = canon.get("appearance", {}).get("eyes", {})
    if eyes.get("default") != "dark":
        errors.append("Default eye state must remain dark.")

    weapons = canon.get("weapons", {})
    if weapons.get("giant_scythe_default") is not False:
        errors.append("Giant scythe cannot be Riven's default defining weapon.")

    if not canon.get("provenance", {}).get("invented_canon") is False:
        errors.append("Canonical provenance must explicitly state invented_canon=false.")

    if errors:
        for error in errors:
            print("FAIL  " + error)
        return False

    for warning in warnings:
        print("WARN  " + warning)

    print("PASS  Canonical Riven validation")
    return True


def validate_episode_state(path):
    errors = []

    state = load_json(path)
    if state is None:
        return False

    character = state.get("character", {})
    if character.get("id") != "riven":
        errors.append("Episode character ID must be riven.")

    policy = state.get("state_policy", {})

    if policy.get("canonical_identity_is_immutable") is not True:
        errors.append("Canonical identity immutability policy missing.")

    if policy.get("temporary_changes_require_cause") is not True:
        errors.append("Temporary-change cause policy missing.")

    if policy.get("knowledge_changes_require_events") is not True:
        errors.append("Knowledge-event policy missing.")

    if policy.get("episode_state_cannot_modify_canonical_state") is not True:
        errors.append("Episode state must not modify canonical state.")

    events = (
        character
        .get("episode_state", {})
        .get("continuity_events", [])
    )

    if not isinstance(events, list):
        errors.append("continuity_events must be a list.")

    if errors:
        for error in errors:
            print("FAIL  " + error)
        return False

    print("PASS  Episode state validation")
    return True


def validate_riven_episode(path):
    errors = []

    state = load_json(path)
    if state is None:
        return False

    character = state.get("character", {})

    if character.get("id") != "riven":
        errors.append("Character ID must be riven.")

    if not character.get("canonical_reference"):
        errors.append("Canonical reference is missing.")

    state_block = character.get("state")
    if not isinstance(state_block, dict):
        errors.append("Character state object is missing.")

    if errors:
        for error in errors:
            print("FAIL  " + error)
        return False

    print("PASS  Episode Riven state validation")
    return True


def main():
    print("=" * 60)
    print("DEATHBOUND — RIVEN CHARACTER VALIDATOR")
    print("=" * 60)

    results = []

    results.append(
        validate_canon()
    )

    episode_state = ROOT / "projects" / "EP001" / "episode_state.json"
    riven_episode = ROOT / "projects" / "EP001" / "characters" / "riven.json"

    results.append(
        validate_episode_state(episode_state)
    )

    results.append(
        validate_riven_episode(riven_episode)
    )

    print("-" * 60)

    if all(results):
        print("OVERALL: PASS")
        sys.exit(0)
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
