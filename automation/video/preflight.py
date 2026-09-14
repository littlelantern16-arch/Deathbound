"""Preflight readiness report for the Deathbound video pipeline.

Reports readiness WITHOUT generating anything: selected provider, registered
capabilities, ₹0 policy compatibility, credentials/payment requirements,
FFmpeg availability, reference-bank status, previous-frame availability,
output writability, required shot inputs, blocking errors and warnings.

Runnable via ``python3 -m automation.video.run preflight ...``.
"""

from __future__ import annotations

import os
import tempfile
from typing import Any, Dict, List, Optional

from .capabilities import capability_report
from .continuity import TemporalContinuityManager
from .media import MediaToolkit
from .paths import episode_paths, find_project_root, generation_paths, load_json
from .reference_bank import CharacterReferenceBank
from .visual_state import VisualStateManager


class Preflight:
    """Assembles the machine-readable readiness report for a shot scope."""

    def __init__(
        self,
        provider_id: str = "dryrun",
        episode: str = "EP001",
        shot_ids: Optional[List[str]] = None,
        project_root: Optional[Any] = None,
        output_root: Optional[Any] = None,
    ) -> None:
        self.project_root = find_project_root(project_root)
        self.provider_id = provider_id
        self.episode = episode
        self.shot_ids = shot_ids  # None = full episode

        self.vsm = VisualStateManager(self.project_root, episode)
        self.shot_order = self.vsm.resolve_shot_order(shot_ids)
        self.toolkit = MediaToolkit(self.project_root)
        self.bank = CharacterReferenceBank(self.project_root, episode)
        self.continuity = TemporalContinuityManager(
            self.project_root, output_root, episode
        )

    def run(self) -> Dict[str, Any]:
        errors: List[str] = []
        warnings: List[str] = []

        # --- Provider & policy --------------------------------------
        provider_report: Dict[str, Any]
        try:
            from .provider_adapter import get_provider

            provider = get_provider(self.provider_id)
            provider_report = capability_report(provider)
            if provider_report.get("capability_errors"):
                errors.extend(provider_report["capability_errors"])
            if not provider_report.get("policy_compatible"):
                errors.append(provider_report.get("policy_error", "policy violation"))
            if provider_report["capabilities"].get("requires_credentials"):
                errors.append("provider requires credentials; none may be committed")
        except Exception as exc:  # unknown provider id etc.
            provider_report = {"provider_id": self.provider_id, "error": str(exc)}
            errors.append(f"provider unavailable: {exc}")

        # --- FFmpeg ---------------------------------------------------
        ffmpeg = self.toolkit.resolve_ffmpeg()
        ffprobe = self.toolkit.resolve_ffprobe()
        ffmpeg_status = {
            "ffmpeg_path": ffmpeg,
            "ffprobe_path": ffprobe,
            "available": bool(ffmpeg and ffprobe),
            "discovery": "env/PATH/config/paths.json fallback chain",
        }
        if not ffmpeg_status["available"]:
            warnings.append(
                "FFmpeg/ffprobe not found; real media validation and real "
                "final-frame extraction will be unavailable (dry-run unaffected)."
            )

        # --- Reference bank ------------------------------------------
        reference_status: Dict[str, Any] = {}
        for shot_id in self.shot_order:
            shot = self.vsm.get_shot(shot_id)
            for char_id in shot.get("characters", []):
                if char_id in reference_status:
                    continue
                try:
                    selection = self.bank.select_for_shot(char_id, shot)
                    references = selection["references"]
                    reference_status[char_id] = {
                        "references": [
                            {
                                "reference_id": r["reference_id"],
                                "simulated": r["simulated"],
                                "path": r.get("path"),
                            }
                            for r in references
                        ],
                        "all_simulated": selection["all_simulated"],
                    }
                    if selection["all_simulated"]:
                        warnings.append(
                            f"character '{char_id}' has no real reference assets "
                            "yet (simulated canon-derived reference in use)"
                        )
                except Exception as exc:
                    errors.append(f"reference bank failure for {char_id}: {exc}")

        # --- Previous-frame availability / shot inputs ----------------
        shots: List[Dict[str, Any]] = []
        for shot_id in self.shot_order:
            state = self.vsm.build_state(shot_id)
            inherits = state["continuity"]["inherits_previous_shot_state"]
            previous_id = state["continuity"]["previous_shot_id"]
            frame = self.continuity.get_final_frame(previous_id) if inherits else None
            shots.append(
                {
                    "shot_id": shot_id,
                    "duration_seconds": state["duration_seconds"],
                    "requires_previous_frame": inherits,
                    "previous_shot_id": previous_id,
                    "previous_frame_registered": frame is not None,
                    "previous_frame_simulated": (frame or {}).get("simulated"),
                }
            )
            if inherits and frame is None:
                warnings.append(
                    f"{shot_id}: no registered final frame yet for {previous_id} "
                    "(expected for a fresh run; the executor will chain it)"
                )

        # --- Output writability ---------------------------------------
        output_dir = generation_paths(self.project_root, None)["root"]
        try:
            with tempfile.TemporaryDirectory(dir=str(output_dir.parent)):
                writable = True
        except OSError:
            writable = False
        if not writable:
            errors.append(f"output directory not writable: {output_dir}")

        # --- Dry-run honesty ------------------------------------------
        mode = "dry_run" if self.provider_id.startswith("dryrun") else "real_provider"
        if mode == "real_provider":
            warnings.append(
                "real provider selected: readiness here does NOT mean media "
                "exists; artifacts must come from an actual generation run"
            )

        return {
            "schema_version": "1.0",
            "kind": "DEATHBOUND_VIDEO_PREFLIGHT_REPORT",
            "episode": self.episode,
            "mode": mode,
            "provider": provider_report,
            "production_cost_policy": "ZERO_RUPEE_ONLY",
            "ffmpeg": ffmpeg_status,
            "reference_bank": reference_status,
            "required_shot_inputs": shots,
            "output_directory": {"path": str(output_dir), "writable": writable},
            "ready_for_dry_run": not errors and writable,
            "ready_for_real_generation": (
                not errors
                and writable
                and ffmpeg_status["available"]
                and mode == "real_provider"
                and not provider_report.get("capability_errors")
            ),
            "blocking_errors": errors,
            "warnings": warnings,
        }
