"""Automated QA validation and bounded retry policy.

Validates, per generated shot (config/GENERATION_MANIFEST_SCHEMA.json ->
validation_checks):

- required_references_present   (missing required references)
- continuity_chain_intact       (broken continuity chain)
- previous_final_frame_present  (missing final frame)
- shot_transition_valid         (invalid shot transitions)
- character_state_present       (missing character state)
- provider_succeeded            (provider failures)
- manifest_fields_complete      (malformed manifests)
- final_frame_extracted

RetryPolicy implements bounded retry with exponential backoff; a shot that
still fails after max_attempts is surfaced as a hard failure — no fake
success, the executor stops and reports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

from .continuity import ContinuityError
from .paths import canonical_json
from .provider_adapter import ProviderError
from .visual_state import VisualStateError

T = TypeVar("T")

# Canonical wardrobe terms that must appear in every Riven state/prompt
# (config/DEATHBOUND_RULES.json -> rivenVisualIdentity.clothing).
REQUIRED_RIVEN_CLOTHING_TERMS = ["hooded coat", "shirt", "trousers", "boots"]

# Transition rules (ANIMATION_ARCHITECTURE.json -> shot_transition_rules,
# SHOT_SEQUENCE_INTEGRATION_SCHEMA.json -> transition_rules).
TRANSITION_RULES = {
    "character_teleport_requires_causal_event",
    "prop_teleport_requires_causal_event",
    "lighting_jump_requires_causal_event",
    "environment_jump_requires_causal_event",
    "state_jump_requires_causal_event",
    "connected_camera_change_requires_camera_transition",
}


def check(name: str, ok: bool, detail: str = "") -> Dict[str, Any]:
    return {"check": name, "status": "pass" if ok else "fail", "detail": detail}


def aggregate(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    failed = [r for r in results if r["status"] != "pass"]
    return {
        "valid": not failed,
        "checks": results,
        "failed_checks": [r["check"] for r in failed],
    }


# ----------------------------------------------------------------------
# Individual validators
# ----------------------------------------------------------------------


def validate_required_references(
    shot: Dict[str, Any], resolved_references: Dict[str, Any]
) -> Dict[str, Any]:
    """Every character in the shot must have resolved references."""
    errors: List[str] = []
    for char_id in shot.get("characters", []):
        selection = resolved_references.get(char_id)
        if not selection or not selection.get("references"):
            errors.append(f"missing references for character '{char_id}'")
    return check(
        "required_references_present",
        not errors,
        "; ".join(errors),
    )


def validate_continuity_chain(
    shot: Dict[str, Any],
    previous_shot_id: Optional[str],
    previous_final_frame: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Connected shot must receive the previous shot's final frame."""
    continuity = shot.get("continuity", {})
    inherits = bool(continuity.get("inherits_previous_shot_state", False))
    expected_previous = continuity.get("previous_shot_id")

    if not inherits or expected_previous is None:
        return check("continuity_chain_intact", True, "shot is a chain root")

    errors: List[str] = []
    if previous_shot_id != expected_previous:
        errors.append(
            f"executor previous '{previous_shot_id}' != spec previous '{expected_previous}'"
        )
    if previous_final_frame is None:
        errors.append(
            f"no final frame registered for previous shot '{expected_previous}'"
        )
    elif not previous_final_frame.get("artifact_id"):
        errors.append("previous final frame artifact has no artifact_id")
    return check("continuity_chain_intact", not errors, "; ".join(errors))


def validate_previous_final_frame(
    shot: Dict[str, Any], previous_final_frame: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    """Explicit final-frame artifact check for connected shots."""
    continuity = shot.get("continuity", {})
    if not continuity.get("inherits_previous_shot_state", False):
        return check("previous_final_frame_present", True, "not required (chain root)")
    ok = (
        previous_final_frame is not None
        and previous_final_frame.get("kind") == "frame"
        and previous_final_frame.get("artifact_id")
    )
    return check(
        "previous_final_frame_present",
        ok,
        "" if ok else "previous final frame artifact missing or malformed",
    )


def validate_shot_transition(
    previous_state: Optional[Dict[str, Any]],
    next_state: Dict[str, Any],
) -> Dict[str, Any]:
    """State jumps between connected shots require causal events.

    Inherits the SHOT_SEQUENCE_INTEGRATION_SCHEMA rules: state/character/
    spatial/prop/environment changes without a causal event are invalid.
    Camera changes at shot boundaries are allowed.
    """
    continuity = next_state.get("continuity", {})
    if not continuity.get("inherits_previous_shot_state", False):
        return check("shot_transition_valid", True, "chain root")
    if previous_state is None:
        return check(
            "shot_transition_valid", False, "inheriting shot but no previous state"
        )

    errors: List[str] = []
    causal_events = set(next_state.get("causal", {}).get("causal_event_ids", []))
    state_changes = {
        c["property"] for c in next_state.get("causal", {}).get("state_changes", [])
    }

    # Character appearance/wardrobe are immutable without cause.
    for char_id, next_char in next_state.get("characters", {}).items():
        prev_char = previous_state.get("characters", {}).get(char_id)
        if prev_char is None:
            continue
        immutable = {
            "identity": prev_char.get("identity"),
            "wardrobe": prev_char.get("wardrobe"),
            "appearance": prev_char.get("appearance"),
        }
        for field_name, before in immutable.items():
            after = next_char.get(field_name)
            if before != after:
                errors.append(
                    f"character '{char_id}' {field_name} changed without cause"
                )

    # Location identity is immutable within a connected chain
    # unless a causal event authorizes the change.
    if previous_state.get("location", {}).get("id") != next_state.get(
        "location", {}
    ).get("id") and not causal_events:
        errors.append("location changed without causal event")

    # Prop identity is immutable; prop set changes need causal events.
    prev_props = {p["id"] for p in previous_state.get("props", [])}
    next_props = {p["id"] for p in next_state.get("props", [])}
    if prev_props != next_props and not causal_events:
        errors.append("props changed without causal event")

    # Eye/supernatural state changes must be among declared causal changes.
    for char_id, next_char in next_state.get("characters", {}).items():
        prev_char = previous_state.get("characters", {}).get(char_id)
        if not prev_char:
            continue
        prev_eyes = prev_char.get("facial_state", {}).get("eyes")
        next_eyes = next_char.get("facial_state", {}).get("eyes")
        if prev_eyes != next_eyes and "eyes" not in state_changes:
            errors.append(
                f"character '{char_id}' eye state changed '{prev_eyes}' -> "
                f"'{next_eyes}' without a causal state change record"
            )

    return check("shot_transition_valid", not errors, "; ".join(errors))


def validate_character_state(
    state: Dict[str, Any], shot: Dict[str, Any]
) -> Dict[str, Any]:
    """Characters present in the shot must carry full visual state."""
    errors: List[str] = []
    for char_id in shot.get("characters", []):
        char_state = state.get("characters", {}).get(char_id)
        if not char_state:
            errors.append(f"no visual state for character '{char_id}'")
            continue
        for section in ("identity", "appearance", "wardrobe", "body_state", "facial_state"):
            if section not in char_state:
                errors.append(f"character '{char_id}' missing '{section}' state")
        identity = char_state.get("identity", {})
        if identity.get("id") != char_id:
            errors.append(f"character '{char_id}' identity id mismatch")
        # Riven canonical identity keys must never be absent.
        if char_id == "riven":
            clothing = (char_state.get("wardrobe", {}).get("canonical_clothing") or [])
            missing = [
                term
                for term in REQUIRED_RIVEN_CLOTHING_TERMS
                if not any(term in item for item in clothing)
            ]
            if missing:
                errors.append(
                    f"Riven canonical wardrobe incomplete, missing {missing}"
                )
    return check("character_state_present", not errors, "; ".join(errors))


def validate_provider_success(
    provider: str, output_artifact: Optional[Dict[str, Any]], provider_errors: List[str]
) -> Dict[str, Any]:
    ok = (
        bool(provider)
        and output_artifact is not None
        and bool(output_artifact.get("artifact_id"))
        and not provider_errors
    )
    return check(
        "provider_succeeded",
        ok,
        "" if ok else (("; ".join(provider_errors)) or "no output artifact"),
    )


def validate_manifest_integrity(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Structural manifest validation (delegates to the manifest manager rules)."""
    from .manifest import REQUIRED_FIELDS

    errors = [f"missing required field: {f}" for f in REQUIRED_FIELDS if f not in manifest]
    if not errors:
        artifacts_simulated = any(
            isinstance(a, dict) and a.get("simulated")
            for a in (manifest.get("output_artifact"), manifest.get("final_frame_artifact"))
        )
        if artifacts_simulated and not manifest.get("dry_run"):
            errors.append("simulated artifacts without dry_run flag")
        if not manifest.get("input_visual_state"):
            errors.append("input_visual_state is empty")
    return check("manifest_fields_complete", not errors, "; ".join(errors))


def validate_final_frame_extraction(
    final_frame_artifact: Optional[Dict[str, Any]], output_artifact: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    ok = (
        final_frame_artifact is not None
        and final_frame_artifact.get("kind") == "frame"
        and bool(final_frame_artifact.get("artifact_id"))
        and output_artifact is not None
        and final_frame_artifact.get("derived_from") == output_artifact.get("artifact_id")
    )
    return check(
        "final_frame_extracted",
        ok,
        "" if ok else "final frame missing or not derived from the output artifact",
    )


# ----------------------------------------------------------------------
# Retry policy
# ----------------------------------------------------------------------


@dataclass
class RetryPolicy:
    """Bounded retry with exponential backoff."""

    max_attempts: int = 3
    backoff_seconds: float = 0.0  # dry-run keeps 0; real providers set > 0
    retryable: tuple = (ProviderError, ContinuityError, VisualStateError, TimeoutError)
    _sleep: Callable[[float], None] = field(default=time.sleep, repr=False)

    def run(self, operation: Callable[[], T]) -> "RetryOutcome":
        last_error: Optional[BaseException] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                value = operation()
                return RetryOutcome(
                    value=value, attempts=attempt, retry_count=attempt - 1, error=None
                )
            except self.retryable as exc:  # type: ignore[misc]
                last_error = exc
                if attempt < self.max_attempts:
                    self._sleep(self.backoff_seconds * (2 ** (attempt - 1)))
        return RetryOutcome(
            value=None,
            attempts=self.max_attempts,
            retry_count=self.max_attempts - 1,
            error=str(last_error),
        )


@dataclass
class RetryOutcome:
    value: Optional[Any]
    attempts: int
    retry_count: int
    error: Optional[str]

    @property
    def succeeded(self) -> bool:
        return self.error is None
