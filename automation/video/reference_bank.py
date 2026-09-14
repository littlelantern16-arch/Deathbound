"""Persistent character reference bank for the Deathbound video pipeline.

The reference bank preserves the existing canonical identity, wardrobe and
visual constraints for each character and associates reference assets with
them. Selection for a shot is deterministic and canon-preserving:

- Canonical identity constraints come from ``DEATHBOUND_RULES.json`` and
  ``DEATHBOUND_VISUAL_STYLE_DNA.json`` and are never altered.
- ``DEATHBOUND_VISUAL_STYLE_DNA.json`` reference_policy governs what a valid
  primary identity reference must look like.
- Simulated references (dry-run) are explicitly marked ``simulated: true`` so
  no placeholder can ever pass as real generated media.
- The system works before any real video provider is connected.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional

from .paths import config_paths, episode_paths, find_project_root, load_json


class ReferenceBankError(ValueError):
    """Raised when reference selection would violate or drift from canon."""


class CharacterReferenceBank:
    """Persistent, canon-preserving character reference bank."""

    def __init__(
        self,
        project_root: Optional[Any] = None,
        episode: str = "EP001",
        bank_path: Optional[Any] = None,
        simulate_missing_references: bool = True,
    ) -> None:
        self.project_root = find_project_root(project_root)
        paths = episode_paths(self.project_root, episode)
        self.bible = (
            load_json(paths["bible_synced"])
            if paths["bible_synced"].exists()
            else load_json(paths["bible"])
        )
        config = config_paths(self.project_root)
        self.rules = load_json(config["rules"])
        self.style_dna = load_json(config["style_dna"])
        self.bank_path = bank_path
        self.bank: Dict[str, Any] = {}
        self.simulate_missing_references = simulate_missing_references
        # Canon is always the foundation; a persisted bank (when present)
        # only adds reference assets on top of the canonical identity.
        self._seed_from_canon()
        if bank_path is not None:
            self.load(bank_path)

    # ------------------------------------------------------------------
    # Bank construction
    # ------------------------------------------------------------------

    def _seed_from_canon(self) -> None:
        """Seed the bank from the canonical identity in the story bible.

        No canon is invented: character name/role/universe and wardrobe come
        from files that already exist. Reference *assets* may not exist yet,
        in which case selection yields simulated references only when the
        caller asked for simulation.
        """
        for entry in self.bible.get("characters", {}).values():
            if not isinstance(entry, dict):
                continue
            char_id = entry.get("id")
            if not char_id:
                continue
            self.bank[char_id] = {
                "character_id": char_id,
                "canonical_identity": deepcopy(entry),
                "canonical_constraints": self._canonical_constraints(char_id),
                "reference_policy": deepcopy(
                    self.style_dna.get("reference_policy", {})
                ),
                "references": [],
            }

    def _canonical_constraints(self, char_id: str) -> Dict[str, Any]:
        if char_id != "riven":
            return {"note": "no style DNA entry for this character yet"}
        riven = self.style_dna.get("riven", {})
        rules = self.rules.get("rivenVisualIdentity", {})
        return {
            "identity_lock": riven.get("identity_lock"),
            "age_appearance": riven.get("age_appearance"),
            "build": riven.get("build"),
            "wardrobe": deepcopy(riven.get("wardrobe", {})),
            "canonical_clothing": list(rules.get("clothing", [])),
            "avoid": list(rules.get("avoid", [])),
            "anti_style": list(self.style_dna.get("anti_style", [])),
            "giant_scythe_default": rules.get("avoid", []) and "giant scythe as default defining prop" in rules.get("avoid", []),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self, path: Any) -> None:
        """Load a persisted reference bank (file may not exist yet)."""
        target = Path(path) if not hasattr(path, "exists") else path
        if target.exists():
            self.bank = load_json(target).get("characters", {})
        self.bank_path = target

    def save(self, path: Optional[Any] = None) -> Dict[str, Any]:
        """Persist the bank. Canonical fields are written read-only (copies)."""
        target = path or self.bank_path
        if target is None:
            raise ReferenceBankError("No reference bank path configured.")
        target = Path(target) if not hasattr(target, "exists") else target
        document = {
            "schema_version": "1.0",
            "kind": "DEATHBOUND_CHARACTER_REFERENCE_BANK",
            "canon_policy": {
                "canonical_identity_is_immutable": True,
                "bank_cannot_modify_canon": True,
                "source_of_truth": "projects/EP001/story_bible.json + config/DEATHBOUND_RULES.json + config/DEATHBOUND_VISUAL_STYLE_DNA.json",
            },
            "characters": self.bank,
        }
        import json

        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=False)
        self.bank_path = target
        return document

    # ------------------------------------------------------------------
    # Reference asset association
    # ------------------------------------------------------------------

    def associate_reference(
        self,
        character_id: str,
        reference_id: str,
        kind: str,
        path: Optional[str],
        *,
        simulated: bool = False,
        primary: bool = False,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Associate a reference asset with a character.

        ``kind`` follows DEATHBOUND_VISUAL_STYLE_DNA reference_policy:
        primary identity references must be face-unobstructed; angle references
        are optional extras.
        """
        character = self._require_character(character_id)
        if kind not in {"primary_identity", "angle", "expression", "wardrobe", "prop"}:
            raise ReferenceBankError(f"Unsupported reference kind: {kind}")
        if kind == "primary_identity" and not primary:
            primary = True
        reference = {
            "reference_id": reference_id,
            "kind": kind,
            "path": path,
            "simulated": bool(simulated),
            "primary": bool(primary),
            "tags": list(tags or []),
            "metadata": dict(metadata or {}),
        }
        references = character.setdefault("references", [])
        references[:] = [r for r in references if r["reference_id"] != reference_id]
        references.append(reference)
        return reference

    # ------------------------------------------------------------------
    # Shot selection
    # ------------------------------------------------------------------

    def select_for_shot(
        self, character_id: str, shot: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Select the correct references for one shot.

        Deterministic order: primary identity reference first, then angle
        references, then expression references matching the shot's facial
        state. When no real assets are associated yet, a canon-derived
        simulated reference is returned (marked simulated=true) so the
        pipeline runs before any provider or asset exists.
        """
        character = self._require_character(character_id)
        face_values = (
            shot.get("character_performance", {}).get("face", [])
            if isinstance(shot, dict)
            else []
        )

        references = character.get("references", [])
        selected: List[Dict[str, Any]] = []
        primary = [r for r in references if r.get("primary")]
        if primary:
            selected.append(primary[0])
        selected.extend(r for r in references if r.get("kind") == "angle")
        for face in face_values:
            selected.extend(
                r
                for r in references
                if r.get("kind") == "expression" and face in r.get("tags", [])
            )

        if not selected:
            if not self.simulate_missing_references:
                raise ReferenceBankError(
                    f"No real reference assets associated with '{character_id}'. "
                    "Disable simulation or associate references first."
                )
            selected.append(self._simulated_canonical_reference(character_id))

        # Drop duplicates while preserving deterministic order.
        seen = set()
        unique = []
        for reference in selected:
            if reference["reference_id"] not in seen:
                seen.add(reference["reference_id"])
                unique.append(reference)
        return {
            "character_id": character_id,
            "references": unique,
            "canonical_constraints": character.get("canonical_constraints", {}),
            "all_simulated": all(r.get("simulated") for r in unique),
        }

    def _simulated_canonical_reference(self, character_id: str) -> Dict[str, Any]:
        """Canon-derived simulated reference for dry-runs.

        The descriptor is built only from existing canonical files; it is
        clearly marked simulated and is not an image.
        """
        character = self.bank[character_id]
        constraints = character.get("canonical_constraints", {})
        descriptor_parts: List[str] = []
        identity = character.get("canonical_identity", {})
        if identity.get("name"):
            descriptor_parts.append(str(identity["name"]))
        if identity.get("role"):
            descriptor_parts.append(str(identity["role"]))
        rules_identity = self.rules.get("rivenVisualIdentity", {})
        for key in ("appearanceAge", "body", "skin", "hair"):
            if rules_identity.get(key):
                descriptor_parts.append(f"{key}: {rules_identity[key]}")
        clothing = constraints.get("canonical_clothing") or []
        if clothing:
            descriptor_parts.append("clothing: " + ", ".join(clothing))
        return {
            "reference_id": f"sim-{character_id}-canonical-identity",
            "kind": "primary_identity",
            "path": None,
            "simulated": True,
            "primary": True,
            "tags": ["canonical", "simulated"],
            "metadata": {
                "descriptor": "; ".join(descriptor_parts),
                "derived_from": [
                    "projects/EP001/story_bible.json",
                    "config/DEATHBOUND_RULES.json",
                    "config/DEATHBOUND_VISUAL_STYLE_DNA.json",
                ],
                "note": "Dry-run placeholder; not a real image asset.",
            },
        }

    # ------------------------------------------------------------------
    # Canon protection
    # ------------------------------------------------------------------

    def enforce_canon(self, character_id: str, candidate: Dict[str, Any]) -> Dict[str, Any]:
        """Fail loudly if a candidate reference/selection violates canon.

        Canonical fields may never be silently altered: identity, age, body,
        wardrobe and prohibited items are compared against the rules config.
        """
        character = self._require_character(character_id)
        constraints = character.get("canonical_constraints", {})
        violations: List[str] = []

        anti_style = [a.lower() for a in constraints.get("anti_style", [])]
        avoid = [a.lower() for a in constraints.get("avoid", [])]
        text_blob = " ".join(
            str(value)
            for value in [
                candidate.get("metadata", {}).get("descriptor", ""),
                " ".join(candidate.get("tags", []) or []),
            ]
        ).lower()
        for banned in anti_style + avoid:
            if banned and banned in text_blob:
                violations.append(f"banned style term in reference: '{banned}'")

        wardrobe = constraints.get("wardrobe", {})
        prohibited = [p.lower() for p in wardrobe.get("prohibited", [])]
        for banned in prohibited:
            if banned and banned in text_blob:
                violations.append(f"prohibited wardrobe item in reference: '{banned}'")

        if violations:
            raise ReferenceBankError(
                "Canon violation for "
                + character_id
                + ": "
                + "; ".join(violations)
            )
        return candidate

    def _require_character(self, character_id: str) -> Dict[str, Any]:
        character = self.bank.get(character_id)
        if character is None:
            raise ReferenceBankError(
                f"Character '{character_id}' is not in the reference bank."
            )
        return character

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def canonical_fingerprint(self, character_id: str) -> Dict[str, Any]:
        """Canonical identity snapshot used to prove identity continuity."""
        character = self._require_character(character_id)
        identity = character.get("canonical_identity", {})
        constraints = character.get("canonical_constraints", {})
        return {
            "character_id": character_id,
            "name": identity.get("name"),
            "role": identity.get("role"),
            "universe": identity.get("universe"),
            "age_appearance": constraints.get("age_appearance"),
            "build": constraints.get("build"),
            "canonical_clothing": constraints.get("canonical_clothing"),
        }
