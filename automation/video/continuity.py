"""Final-frame extraction and shot-to-shot continuity registration.

Implements the OpenX Flow chaining principle on top of the existing Deathbound
shot architecture:

    previous shot -> generated clip -> extract final frame
        -> register final frame as continuity state
        -> construct next-shot conditioning -> generate next shot

Final frames are explicit artifacts registered in
``production/generation/state/continuity_chain.json`` and referenced by every
generation manifest. In dry-run the extractor produces deterministic simulated
frames (never real media) so the chain is still fully machine-checkable.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .paths import find_project_root, generation_paths, load_json, write_json


class ContinuityError(ValueError):
    """Raised when the continuity chain is broken or inconsistent."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TemporalContinuityManager:
    """Tracks the connected chain of shots and their final-frame artifacts."""

    def __init__(
        self,
        project_root: Optional[Any] = None,
        output_root: Optional[Any] = None,
        episode: str = "EP001",
        run_id: Optional[str] = None,
    ) -> None:
        self.project_root = find_project_root(project_root)
        paths = generation_paths(self.project_root, output_root)
        self.state_dir = paths["state"]
        self.chain_path = self.state_dir / "continuity_chain.json"
        self.chain: Dict[str, Any] = self._load_chain()
        if run_id:
            self.chain.setdefault("run_id", run_id)
        self.chain.setdefault("episode", episode)
        self.chain.setdefault("links", {})
        self.chain.setdefault("simulated", True)

    # ------------------------------------------------------------------
    # Chain persistence
    # ------------------------------------------------------------------

    def _load_chain(self) -> Dict[str, Any]:
        if self.chain_path.exists():
            return load_json(self.chain_path)
        return {}

    def save(self) -> None:
        write_json(self.chain_path, self.chain)

    def reset(self, run_id: Optional[str] = None) -> None:
        """Clear the chain (used when starting a fresh run)."""
        self.chain = {
            "schema_version": "1.0",
            "kind": "DEATHBOUND_CONTINUITY_CHAIN",
            "episode": self.chain.get("episode", "EP001"),
            "run_id": run_id,
            "simulated": self.chain.get("simulated", True),
            "links": {},
            "updated_utc": utc_now(),
        }
        self.save()

    # ------------------------------------------------------------------
    # Final-frame extraction
    # ------------------------------------------------------------------

    def extract_final_frame(
        self,
        shot_id: str,
        output_artifact: Dict[str, Any],
        *,
        simulated: bool,
    ) -> Dict[str, Any]:
        """Extract the final frame of a generated clip as an explicit artifact.

        ``output_artifact`` is the manifest artifact reference produced by the
        provider adapter. In dry-run (simulated=True) the frame is a
        deterministic placeholder derived from the clip artifact id, clearly
        marked simulated; it is never presented as real media.
        """
        if output_artifact is None:
            raise ContinuityError(
                f"Cannot extract final frame for {shot_id}: no output artifact."
            )
        clip_id = output_artifact.get("artifact_id", "")
        frame_id = f"finalframe-{shot_id}"
        digest = hashlib.sha256(clip_id.encode("utf-8")).hexdigest()[:16]
        frame = {
            "artifact_id": frame_id,
            "kind": "frame",
            "path": f"artifacts/{shot_id}/final_frame.json"
            if simulated
            else f"artifacts/{shot_id}/final_frame.png",
            "simulated": bool(simulated),
            "derived_from": output_artifact.get("artifact_id"),
            "digest": digest,
            "extracted_utc": utc_now(),
        }
        return frame

    def register_final_frame(
        self,
        shot_id: str,
        frame: Dict[str, Any],
        end_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register the final frame as continuity state for the next shot."""
        if frame is None or not frame.get("artifact_id"):
            raise ContinuityError(f"Invalid final frame for {shot_id}.")
        links = self.chain.setdefault("links", {})
        links[shot_id] = {
            "shot_id": shot_id,
            "final_frame": deepcopy(frame),
            "end_state_fingerprint": (end_state or {}).get("state_fingerprint"),
            "registered_utc": utc_now(),
        }
        self.chain["updated_utc"] = utc_now()
        self.save()

    # ------------------------------------------------------------------
    # Conditioning lookup
    # ------------------------------------------------------------------

    def get_final_frame(self, shot_id: str) -> Optional[Dict[str, Any]]:
        link = self.chain.get("links", {}).get(shot_id)
        if link is None:
            return None
        return deepcopy(link.get("final_frame"))

    def get_conditioning_for(
        self, shot_id: str, previous_shot_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Return the previous final frame to condition this shot on."""
        if previous_shot_id is None:
            return None
        frame = self.get_final_frame(previous_shot_id)
        if frame is None:
            raise ContinuityError(
                f"Broken continuity chain: shot {shot_id} inherits from "
                f"{previous_shot_id} but no final frame is registered for it."
            )
        return frame

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_chain(self, ordered_shot_ids: List[str]) -> Dict[str, Any]:
        """Verify every connected consecutive pair has a registered final frame."""
        errors: List[str] = []
        for index in range(1, len(ordered_shot_ids)):
            previous_id = ordered_shot_ids[index - 1]
            current_id = ordered_shot_ids[index]
            frame = self.get_final_frame(previous_id)
            if frame is None:
                errors.append(
                    f"Broken chain between {previous_id} and {current_id}: "
                    "previous final frame not registered."
                )
        return {
            "valid": not errors,
            "errors": errors,
            "checked_links": max(0, len(ordered_shot_ids) - 1),
        }
