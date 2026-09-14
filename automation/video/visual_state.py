"""Provider-neutral visual state for the Deathbound video pipeline.

The Visual State Manager derives one consolidated, provider-neutral state
object per shot from the existing Deathbound architecture:

- ``projects/<episode>/03_shots/<episode>_production_shots.json`` (58-shot schema)
- ``projects/<episode>/story_bible.json`` (locations, props, world rules)
- ``projects/<episode>/characters/riven.json`` + ``episode_state.json``
  (episode character state and its canon-protection policy)
- ``config/DEATHBOUND_RULES.json`` / ``config/DEATHBOUND_VISUAL_STYLE_DNA.json``
  (canonical identity constraints)

It tracks, per shot: character identity, appearance, wardrobe, body state,
facial state, performance state, location, spatial position, orientation,
props, environment state, lighting state, camera state, effects, and
continuity-relevant causal changes.

This module reads canonical files but never writes them: shot generation must
consume state, it must not silently rewrite canonical state
(ANIMATION_ARCHITECTURE.json -> state_integration.rule).
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .paths import canonical_json, config_paths, episode_paths, find_project_root, load_json

# Canonical identity constraints come from the existing authoritative configs.
# Eyes may only leave "dark" via a causally justified supernatural effect.
CANONICAL_EYE_DEFAULT = "dark"
SUPERNATURAL_EFFECTS = {"supernatural_energy"}
CAUSAL_PROPERTY_BY_EFFECT = {
    # Mirrors the Ledger's causal event vocabulary (eyes: dark -> supernatural_glow
    # under EVT-001 "Riven activates Reaper sight").
    "supernatural_energy": ("eyes", CANONICAL_EYE_DEFAULT, "supernatural_glow"),
}


class VisualStateError(ValueError):
    """Raised when a shot specification cannot yield a coherent visual state."""


@dataclass
class VisualStateManager:
    """Builds provider-neutral visual state objects for an episode's shots."""

    project_root: Optional[Any] = None
    episode: str = "EP001"
    _shots_doc: Dict[str, Any] = field(default_factory=dict, repr=False)
    _bible: Dict[str, Any] = field(default_factory=dict, repr=False)
    _episode_state: Dict[str, Any] = field(default_factory=dict, repr=False)
    _rules: Dict[str, Any] = field(default_factory=dict, repr=False)
    _style_dna: Dict[str, Any] = field(default_factory=dict, repr=False)
    _shot_index: Dict[str, Dict[str, Any]] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self.project_root = find_project_root(self.project_root)
        paths = episode_paths(self.project_root, self.episode)
        self.shots_path = paths["shots"]
        self._shots_doc = load_json(self.shots_path)
        self._bible = load_json(paths["bible_synced"]) if paths["bible_synced"].exists() else load_json(paths["bible"])
        self._episode_state = load_json(paths["episode_state"])
        self._rules = load_json(config_paths(self.project_root)["rules"])
        self._style_dna = load_json(config_paths(self.project_root)["style_dna"])
        self._shots: List[Dict[str, Any]] = self._shots_doc["production_shots"]
        self._shot_index = {shot["shot_id"]: shot for shot in self._shots}

    # ------------------------------------------------------------------
    # Loading helpers
    # ------------------------------------------------------------------

    @property
    def shots(self) -> List[Dict[str, Any]]:
        """All production shots in authoritative order."""
        return self._shots

    def get_shot(self, shot_id: str) -> Dict[str, Any]:
        shot = self._shot_index.get(shot_id)
        if shot is None:
            raise VisualStateError(f"Unknown shot_id: {shot_id}")
        return shot

    def resolve_shot_order(self, shot_ids: Optional[List[str]] = None) -> List[str]:
        """Return shot IDs in execution order.

        The existing architecture already encodes the order in the production
        shot list (each shot's continuity.previous_shot_id chains backwards).
        An explicit subset request is validated against that chain: the subset
        must be a contiguous run of the authoritative sequence.
        """
        if shot_ids is None:
            return [shot["shot_id"] for shot in self._shots]

        requested = list(shot_ids)
        unknown = [s for s in requested if s not in self._shot_index]
        if unknown:
            raise VisualStateError(f"Unknown shot_ids requested: {unknown}")

        full_order = [shot["shot_id"] for shot in self._shots]
        first = full_order.index(requested[0])
        window = full_order[first : first + len(requested)]
        if window != requested:
            raise VisualStateError(
                "Requested shot order breaks the authoritative sequence: "
                f"requested {requested}, authoritative window {window}"
            )
        return requested

    # ------------------------------------------------------------------
    # State construction
    # ------------------------------------------------------------------

    def build_state(self, shot_id: str) -> Dict[str, Any]:
        """Build the full provider-neutral visual state for one shot."""
        shot = self.get_shot(shot_id)
        continuity = shot.get("continuity", {})
        previous_id = continuity.get("previous_shot_id")

        location = self._location_state(shot)
        environment = self._environment_state(shot, previous_id)
        lighting = self._lighting_state(shot, previous_id)
        camera = self._camera_state(shot)
        effects = self._effects_state(shot)
        characters = {
            char_id: self._character_state(char_id, shot, previous_id)
            for char_id in shot.get("characters", [])
        }
        props = self._props_state(shot, previous_id)

        causal = {
            "causal_event_ids": list(shot.get("causal_event_ids", [])),
            "state_changes": self._causal_state_changes(shot, previous_id),
        }

        return {
            "shot_id": shot_id,
            "scene_id": shot["scene_id"],
            "sequence_id": shot["sequence_id"],
            "episode": self._shots_doc.get("episode", self.episode),
            "characters": characters,
            "location": location,
            "spatial_position": self._spatial_position(shot, previous_id),
            "orientation": self._orientation(shot, previous_id),
            "props": props,
            "environment": environment,
            "lighting": lighting,
            "camera": camera,
            "effects": effects,
            "performance": self._performance_state(shot),
            "causal": causal,
            "continuity": {
                "inherits_previous_shot_state": bool(
                    continuity.get("inherits_previous_shot_state", False)
                ),
                "previous_shot_id": previous_id,
                "connected_to_next_shot": bool(
                    continuity.get("connected_to_next_shot", True)
                ),
            },
            "duration_seconds": shot["duration_seconds"],
        }

    # ------------------------------------------------------------------
    # Section builders (all derived from existing specs, nothing invented)
    # ------------------------------------------------------------------

    def _location_state(self, shot: Dict[str, Any]) -> Dict[str, Any]:
        location_id = shot["location"]
        locations = self._bible.get("locations", {})
        entry = None
        for value in locations.values():
            if isinstance(value, dict) and value.get("id") == location_id:
                entry = value
                break
        return {
            "id": location_id,
            "name": (entry or {}).get("name"),
            "identity_locked": bool(
                shot.get("continuity", {}).get("environment_identity_locked", True)
            ),
        }

    def _environment_state(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> Dict[str, Any]:
        environment = {
            "location_id": shot["location"],
            "environment_motion": shot.get("environment_motion", "none"),
            "time": "night",
        }
        if previous_id and shot.get("continuity", {}).get(
            "inherits_previous_shot_state", False
        ):
            previous = self.get_shot(previous_id)
            if previous.get("environment_motion") == shot.get("environment_motion"):
                environment["inherited_from"] = previous_id
        # Ledger moments get a distinct visual treatment (master spec §6);
        # the Ledger prop is present in this episode's every scene.
        if any("ledger" in prop for prop in shot.get("props", [])):
            environment["visual_treatment"] = "ledger_distinct_treatment"
        return environment

    def _lighting_state(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> Dict[str, Any]:
        lighting = {
            "continuity_required": bool(
                shot.get("lighting", {}).get("continuity_required", True)
            ),
            "changes_require_cause": bool(
                shot.get("lighting", {}).get("changes_require_cause", True)
            ),
            "profile": self._style_dna.get("rendering", {}).get("lighting"),
        }
        if previous_id:
            lighting["inherited_from"] = previous_id
        return lighting

    def _camera_state(self, shot: Dict[str, Any]) -> Dict[str, Any]:
        camera = shot.get("camera", {})
        return {
            "shot_type": camera.get("shot_type"),
            "movement": camera.get("movement"),
            "lens_behavior": "cinematic_consistency_required",
        }

    def _effects_state(self, shot: Dict[str, Any]) -> Dict[str, Any]:
        effects = list(shot.get("effects", {}).get("effects", []))
        return {
            "effects": effects,
            "require_narrative_justification": bool(
                shot.get("effects", {}).get(
                    "effects_require_narrative_justification", True
                )
            ),
        }

    def _performance_state(self, shot: Dict[str, Any]) -> Dict[str, Any]:
        performance = shot.get("character_performance", {})
        return {
            "body": list(performance.get("body", [])),
            "face": list(performance.get("face", [])),
            "speech": deepcopy(performance.get("speech", {})),
            "animation_tier": shot.get("animation_tier"),
            "purpose": shot.get("purpose"),
        }

    def _character_state(
        self, char_id: str, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> Dict[str, Any]:
        """Per-character state for one shot.

        Episode character state (riven.json / episode_state.json) supplies the
        mutable episode-level condition/emotion/knowledge tracks; canonical
        identity constraints come from DEATHBOUND_RULES.json and are never
        modified here.
        """
        episode_character = self._episode_state.get("character", {})
        if episode_character.get("id") != char_id:
            # Only Riven has episode state so far; other characters fall back
            # to shot-spec-derived performance only.
            episode_tracks: Dict[str, Any] = {}
        else:
            episode_tracks = deepcopy(episode_character.get("episode_state", {}))

        performance = shot.get("character_performance", {})
        face_values = list(performance.get("face", []))
        emotion = episode_tracks.get("emotional_state", {})
        if face_values and not emotion.get("primary_emotion"):
            emotion = dict(emotion, primary_emotion=face_values[0])

        effects = list(shot.get("effects", {}).get("effects", []))
        return {
            "id": char_id,
            "identity": self._canonical_identity(char_id),
            "appearance": deepcopy(
                self._rules.get("rivenVisualIdentity", {})
            )
            if char_id == "riven"
            else {},
            "wardrobe": self._canonical_wardrobe(char_id, episode_tracks),
            "body_state": {
                "body": list(performance.get("body", [])),
                "condition": episode_tracks.get("physical_state", {}).get(
                    "condition", "normal"
                ),
                "injuries": list(
                    episode_tracks.get("physical_state", {}).get("injuries", [])
                ),
            },
            "facial_state": {
                "face": face_values,
                "eyes": self._eye_state(shot, previous_id),
            },
            "performance_state": self._performance_state(shot),
            "emotion": emotion,
            "knowledge": deepcopy(episode_tracks.get("knowledge_state", {})),
            "inventory": list(episode_tracks.get("inventory", [])),
            "in_shot": True,
        }

    def _canonical_identity(self, char_id: str) -> Dict[str, Any]:
        characters = self._bible.get("characters", {})
        entry = None
        for value in characters.values():
            if isinstance(value, dict) and value.get("id") == char_id:
                entry = value
                break
        if entry is None:
            raise VisualStateError(
                f"Character '{char_id}' is not present in the story bible."
            )
        return {
            "id": entry.get("id", char_id),
            "name": entry.get("name"),
            "role": entry.get("role"),
            "universe": entry.get("universe"),
            "canonical_reference": entry.get("canonical_reference"),
            "status": entry.get("status"),
        }

    def _canonical_wardrobe(
        self, char_id: str, episode_tracks: Dict[str, Any]
    ) -> Dict[str, Any]:
        rules = self._rules.get("rivenVisualIdentity", {})
        clothing_state = episode_tracks.get("physical_state", {}).get(
            "clothing_state", "default"
        )
        return {
            "clothing_state": clothing_state,
            "canonical_clothing": list(rules.get("clothing", [])),
            "immutable_without_cause": True,
        }

    def _eye_state(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> str:
        """Eyes stay canonically dark unless a justified effect applies."""
        effects = list(shot.get("effects", {}).get("effects", []))
        for effect in effects:
            if effect in SUPERNATURAL_EFFECTS:
                return CAUSAL_PROPERTY_BY_EFFECT[effect][2]
        return CANONICAL_EYE_DEFAULT

    def _props_state(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> Dict[str, Any]:
        props_registry = self._bible.get("props", {})
        props = []
        for prop_id in shot.get("props", []):
            entry = None
            for value in props_registry.values():
                if isinstance(value, dict) and value.get("id") == prop_id:
                    entry = value
                    break
            props.append(
                {
                    "id": prop_id,
                    "name": (entry or {}).get("name"),
                    "identity_locked": bool(
                        shot.get("continuity", {}).get("prop_identity_locked", True)
                    ),
                }
            )
        return props

    def _spatial_position(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> Dict[str, Any]:
        return {
            "location_id": shot["location"],
            "inherited_from": previous_id
            if shot.get("continuity", {}).get("inherits_previous_shot_state", False)
            else None,
            "note": "Exact blocking is owned by the performance engines; "
            "position changes require causal events per SHOT_SEQUENCE_INTEGRATION_SCHEMA.",
        }

    def _orientation(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> Dict[str, Any]:
        camera = shot.get("camera", {})
        return {
            "shot_type": camera.get("shot_type"),
            "movement": camera.get("movement"),
            "inherited_from": previous_id
            if shot.get("continuity", {}).get("inherits_previous_shot_state", False)
            else None,
        }

    def _causal_state_changes(
        self, shot: Dict[str, Any], previous_id: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Continuity-relevant causal changes entering at this shot."""
        changes: List[Dict[str, Any]] = []
        previous_effects: List[str] = []
        if previous_id:
            previous_effects = list(
                self.get_shot(previous_id).get("effects", {}).get("effects", [])
            )
        for effect in shot.get("effects", {}).get("effects", []):
            if effect in CAUSAL_PROPERTY_BY_EFFECT and effect not in previous_effects:
                prop, old, new = CAUSAL_PROPERTY_BY_EFFECT[effect]
                changes.append(
                    {
                        "property": prop,
                        "previous": old,
                        "new": new,
                        "cause": f"effect:{effect}",
                        "causal_event_ids": list(shot.get("causal_event_ids", [])),
                    }
                )
        return changes

    # ------------------------------------------------------------------
    # State propagation
    # ------------------------------------------------------------------

    def apply_transition(
        self, previous_state: Dict[str, Any], shot_id: str
    ) -> Dict[str, Any]:
        """Propagate the previous shot's state forward into this shot's state.

        The authoritative shot spec decides inheritance
        (continuity.inherits_previous_shot_state). Causal changes recorded in
        the new state are applied on top of inherited values. This returns the
        *working* state for generation; canonical files are never touched.
        """
        next_state = self.build_state(shot_id)
        continuity = next_state.get("continuity", {})
        if not continuity.get("inherits_previous_shot_state"):
            return next_state

        # Carry unresolved causal changes forward so a later shot can detect
        # an uncaused reversal (broken chain detection).
        inherited_changes = deepcopy(previous_state.get("causal", {}).get("state_changes", []))
        merged = {c["property"]: c for c in inherited_changes}
        for change in next_state.get("causal", {}).get("state_changes", []):
            merged[change["property"]] = change
        next_state["causal"]["state_changes"] = list(merged.values())

        next_state["continuity"]["propagated_from_state"] = previous_state.get("shot_id")
        return next_state

    def fingerprint(self, state: Dict[str, Any]) -> str:
        """Deterministic fingerprint of a visual state for manifest integrity."""
        return canonical_json(state)
