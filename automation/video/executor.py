"""Episode executor for the Deathbound temporal continuity pipeline.

Executes a connected sequence of shots end to end:

    load EP001 -> resolve shot order -> build visual state
        -> resolve references -> generate -> validate
        -> extract final frame -> update continuity state
        -> continue to next shot -> write manifests

Supports dry-run mode (mandatory: no paid API, no video model, no
credentials) and resume after failure (completed shots are skipped; the
continuity chain persists in production/generation/state/).

The executor never regenerates shots independently: every connected shot is
conditioned on the previous shot's registered final-frame artifact.
"""

from __future__ import annotations

import hashlib
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .capabilities import PRODUCTION_COST_POLICY, PolicyViolation, ProviderPolicy
from .continuity import ContinuityError, TemporalContinuityManager, utc_now
from .manifest import GenerationManifestManager, ManifestError
from .media import MediaError, MediaToolkit
from .paths import canonical_json, episode_paths, find_project_root, generation_paths, load_json, write_json
from .provider_adapter import (
    GenerationRequest,
    VideoProvider,
    get_provider,
)
from .qa import (
    RetryOutcome,
    RetryPolicy,
    aggregate,
    validate_character_state,
    validate_continuity_chain,
    validate_final_frame_extraction,
    validate_manifest_integrity,
    validate_previous_final_frame,
    validate_provider_success,
    validate_required_references,
    validate_shot_transition,
)
from .reference_bank import CharacterReferenceBank, ReferenceBankError
from .visual_state import VisualStateManager, VisualStateError


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class EpisodeExecutorError(RuntimeError):
    """Raised when episode execution cannot proceed."""


class EpisodeExecutor:
    """Runs a connected shot sequence for one episode."""

    def __init__(
        self,
        episode: str = "EP001",
        provider: str = "dryrun",
        project_root: Optional[Any] = None,
        output_root: Optional[Any] = None,
        run_id: Optional[str] = None,
        shot_ids: Optional[List[str]] = None,
        max_attempts: int = 3,
        resume: bool = True,
    ) -> None:
        self.project_root = find_project_root(project_root)
        self.episode = episode
        self.output_root = output_root
        self.provider_id = provider
        self.requested_shot_ids = list(shot_ids) if shot_ids else None
        self.resume = resume

        self.vsm = VisualStateManager(self.project_root, episode)
        self.shot_order = self.vsm.resolve_shot_order(self.requested_shot_ids)

        paths = generation_paths(self.project_root, output_root)
        if run_id:
            self.run_id = run_id
        else:
            # Deterministic per (episode, provider, shot list) so a resumed
            # execution of the same scope lands on the same run state.
            self.run_id = (
                f"{self.episode}-"
                + hashlib.sha1(
                    (self.provider_id + "|" + "|".join(self.shot_order)).encode()
                ).hexdigest()[:10]
            )
        self.continuity = TemporalContinuityManager(
            self.project_root, output_root, episode, run_id=self.run_id
        )
        self.bank = CharacterReferenceBank(self.project_root, episode)
        self.manifests = GenerationManifestManager(self.project_root, output_root, episode)
        self.retry_policy = RetryPolicy(max_attempts=max_attempts, backoff_seconds=0.0)
        self.toolkit = MediaToolkit(self.project_root)
        self.policy = ProviderPolicy()
        self.run_state_path = paths["state"] / "run_state.json"
        self.reports_dir = paths["reports"]

        self._provider: Optional[VideoProvider] = None

    # ------------------------------------------------------------------
    # Provider access (never hard-coded; resolved through the registry)
    # ------------------------------------------------------------------

    @property
    def provider(self) -> VideoProvider:
        if self._provider is None:
            try:  # register bundled local providers (ltx-local, ...)
                from . import providers as _providers  # noqa: F401
            except Exception:
                pass
            self._provider = get_provider(self.provider_id)
            # Providers that write artifacts locally must honor this run's
            # output root, so test/temp runs never leak into the default
            # production location.
            artifacts_dir = generation_paths(
                self.project_root, self.output_root
            )["artifacts"]
            if hasattr(self._provider, "artifacts_dir"):
                self._provider.artifacts_dir = artifacts_dir
        return self._provider

    # ------------------------------------------------------------------
    # Run state (resume support)
    # ------------------------------------------------------------------

    def _load_run_state(self) -> Dict[str, Any]:
        if self.resume and self.run_state_path.exists():
            state = load_json(self.run_state_path)
            if state.get("run_id") == self.run_id:
                return state
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "episode": self.episode,
            "provider": self.provider_id,
            "shots": {},
            "updated_utc": _now(),
        }

    def _save_run_state(self, state: Dict[str, Any]) -> None:
        state["updated_utc"] = _now()
        write_json(self.run_state_path, state)

    # ------------------------------------------------------------------
    # Prompt assembly (provider-neutral text from canonical state)
    # ------------------------------------------------------------------

    def build_prompt(self, state: Dict[str, Any]) -> Dict[str, str]:
        """Deterministic positive/negative prompt built only from state."""
        lines: List[str] = []
        for char_id, char in state.get("characters", {}).items():
            identity = char.get("identity", {})
            appearance = char.get("appearance", {})
            wardrobe = char.get("wardrobe", {}).get("canonical_clothing") or []
            facial = char.get("facial_state", {})
            lines.append(
                f"{identity.get('name', char_id)} ({identity.get('role', '')}), "
                f"age {appearance.get('appearanceAge', '')}, {appearance.get('body', '')}, "
                f"skin {appearance.get('skin', '')}, hair {appearance.get('hair', '')}, "
                f"eyes {facial.get('eyes', 'dark')}"
            )
            if wardrobe:
                lines.append("wearing " + ", ".join(wardrobe))
        location = state.get("location", {})
        lines.append(f"location: {location.get('name') or location.get('id')}")
        camera = state.get("camera", {})
        lines.append(f"camera: {camera.get('shot_type')} shot, {camera.get('movement')} movement")
        performance = state.get("performance", {})
        lines.append(
            f"performance: body {'/'.join(performance.get('body', [])) or 'idle'}, "
            f"face {'/'.join(performance.get('face', [])) or 'neutral'}, "
            f"tier {performance.get('animation_tier')}"
        )
        effects = state.get("effects", {}).get("effects") or []
        lines.append(f"effects: {', '.join(effects) if effects else 'none'}")
        env = state.get("environment", {})
        if env.get("visual_treatment"):
            lines.append(f"treatment: {env['visual_treatment']}")
        if state.get("continuity", {}).get("inherits_previous_shot_state"):
            lines.append("continues directly from the previous shot's final frame")
        prompt = ". ".join(part for part in lines if part and part != ".")

        anti_style = self.vsm._style_dna.get("anti_style", [])
        avoid = self.vsm._rules.get("rivenVisualIdentity", {}).get("avoid", [])
        negative = ", ".join(sorted({*anti_style, *avoid}))
        return {"positive": prompt, "negative": negative}

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute(self) -> Dict[str, Any]:
        """Run the connected shot sequence and return a machine-readable report."""
        # ₹0 gate: refuse providers that violate ZERO_RUPEE_ONLY before any
        # work happens. There is no silent paid fallback.
        try:
            self.policy_report = self.policy.ensure_allowed(self.provider)
        except PolicyViolation as exc:
            raise EpisodeExecutorError(
                f"production-cost policy gate ({PRODUCTION_COST_POLICY}): {exc}"
            ) from exc

        run_state = self._load_run_state()
        run_state.setdefault("shots", {})
        self.continuity.chain.setdefault("links", {})

        report_shots: List[Dict[str, Any]] = []
        previous_state: Optional[Dict[str, Any]] = None
        previous_shot_id: Optional[str] = None
        halted: Optional[Dict[str, Any]] = None

        for shot_id in self.shot_order:
            shot_record = run_state["shots"].get(shot_id)
            spec = self.vsm.get_shot(shot_id)

            if self.resume and shot_record and shot_record.get("status") == "completed":
                # Resume: reuse the completed shot and its registered chain link.
                final_frame = self.continuity.get_final_frame(shot_id)
                manifest = self.manifests.load(shot_id)
                state_fingerprint = shot_record.get("state_fingerprint")
                report_shots.append(
                    {
                        "shot_id": shot_id,
                        "scene_id": spec.get("scene_id"),
                        "resumed": True,
                        "status": "completed",
                        "previous_shot": manifest.get("previous_shot") if manifest else None,
                        "previous_final_frame": manifest.get("previous_final_frame") if manifest else None,
                        "output_artifact": manifest.get("output_artifact") if manifest else None,
                        "final_frame_artifact": final_frame,
                        "retry_count": manifest.get("retry_count", 0) if manifest else 0,
                        "validation_valid": (manifest or {}).get("validation_result", {}).get("valid", False),
                        "state_fingerprint": state_fingerprint,
                        "simulated": (manifest or {}).get("dry_run", False),
                    }
                )
                previous_shot_id = shot_id
                previous_state = shot_record.get("end_state")
                continue

            outcome = self._execute_shot(
                shot_id, spec, previous_state, previous_shot_id, run_state
            )
            if not outcome["success"]:
                halted = {
                    "shot_id": shot_id,
                    "error": outcome["error"],
                    "retry_count": outcome["retry_count"],
                }
                report_shots.append(outcome["report"])
                break

            report_shots.append(outcome["report"])
            previous_shot_id = shot_id
            previous_state = outcome["end_state"]

        chain_validation = self.continuity.validate_chain(self.shot_order)
        report = self._build_report(report_shots, chain_validation, halted, run_state)
        self._save_run_state(run_state)
        report_path = self.reports_dir / f"{self.run_id}.report.json"
        write_json(report_path, report)
        report["report_path"] = str(report_path)
        return report

    # ------------------------------------------------------------------
    # One shot
    # ------------------------------------------------------------------

    def _execute_shot(
        self,
        shot_id: str,
        spec: Dict[str, Any],
        previous_state: Optional[Dict[str, Any]],
        previous_shot_id: Optional[str],
        run_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        timestamps = {"created_utc": _now()}
        accumulated_errors: List[str] = []

        # 1. Visual state: propagate from previous working state.
        state = (
            self.vsm.apply_transition(deepcopy(previous_state), shot_id)
            if previous_state is not None
            else self.vsm.build_state(shot_id)
        )
        state_fingerprint = hashlib.sha256(
            canonical_json(state).encode("utf-8")
        ).hexdigest()

        # 2. Previous final-frame conditioning (explicit artifact).
        inherits = bool(state.get("continuity", {}).get("inherits_previous_shot_state"))
        previous_final_frame: Optional[Dict[str, Any]] = None
        if inherits:
            try:
                previous_final_frame = self.continuity.get_conditioning_for(
                    shot_id, state["continuity"]["previous_shot_id"]
                )
            except ContinuityError as exc:
                return self._failure_report(
                    shot_id, spec, str(exc), timestamps, state
                )

        # 3. References (canon-preserving selection).
        try:
            resolved_references = {}
            for char_id in spec.get("characters", []):
                selection = self.bank.select_for_shot(char_id, spec)
                for reference in selection["references"]:
                    self.bank.enforce_canon(char_id, reference)
                resolved_references[char_id] = selection
        except (ReferenceBankError, VisualStateError) as exc:
            return self._failure_report(
                shot_id, spec, str(exc), timestamps, state
            )

        prompt_bundle = self.build_prompt(state)
        request = GenerationRequest(
            shot_id=shot_id,
            prompt=prompt_bundle["positive"],
            duration_seconds=float(spec["duration_seconds"]),
            fps=24,
            resolution="1280x720",
            reference_images=[
                r
                for sel in resolved_references.values()
                for r in sel.get("references", [])
            ],
            previous_final_frame=previous_final_frame,
            negative_prompt=prompt_bundle["negative"],
        )

        # 4. Generate -> validate -> extract -> register (bounded retry).
        def attempt() -> Dict[str, Any]:
            timestamps["generation_started_utc"] = _now()
            result = self.provider.generate(request)
            final_frame = self._finalize_artifact(shot_id, spec, result)
            timestamps["generation_finished_utc"] = _now()
            return {"result": result, "final_frame": final_frame}

        retry_outcome = self.retry_policy.run(attempt)
        if not retry_outcome.succeeded:
            accumulated_errors.append(retry_outcome.error or "unknown provider error")
            return self._failure_report(
                shot_id,
                spec,
                retry_outcome.error or "provider failed after bounded retries",
                timestamps,
                state,
                retry_count=retry_outcome.retry_count,
                errors=accumulated_errors,
            )

        generation = retry_outcome.value
        result = generation["result"]
        final_frame = generation["final_frame"]

        # 5. Full QA validation for this shot.
        validation = aggregate(
            [
                validate_required_references(spec, resolved_references),
                validate_continuity_chain(spec, previous_shot_id, previous_final_frame),
                validate_previous_final_frame(spec, previous_final_frame),
                validate_shot_transition(previous_state, state),
                validate_character_state(state, spec),
                validate_provider_success(
                    self.provider_id, result.output_artifact, result.errors
                ),
                validate_final_frame_extraction(final_frame, result.output_artifact),
            ]
        )

        # 6. Register final frame as continuity state, then build the manifest.
        end_state = deepcopy(state)
        end_state["state_fingerprint"] = state_fingerprint
        self.continuity.register_final_frame(shot_id, final_frame, end_state)

        manifest = self.manifests.build(
            scene_id=spec["scene_id"],
            shot_id=shot_id,
            run_id=self.run_id,
            input_visual_state=state,
            previous_shot=state["continuity"]["previous_shot_id"],
            previous_final_frame=previous_final_frame,
            character_references=resolved_references,
            prompt=prompt_bundle["positive"],
            provider=getattr(self.provider, "provider_id", self.provider_id),
            model=getattr(self.provider, "model_id", None),
            generation_parameters=result.generation_parameters,
            output_artifact=result.output_artifact,
            final_frame_artifact=final_frame,
            validation_result=validation,
            retry_count=retry_outcome.retry_count,
            errors=accumulated_errors
            + [e for e in result.errors]
            + validation["failed_checks"],
            created_utc=timestamps["created_utc"],
            generation_started_utc=timestamps.get("generation_started_utc"),
            generation_finished_utc=timestamps.get("generation_finished_utc"),
        )

        # Manifest integrity is itself a QA gate.
        integrity = validate_manifest_integrity(manifest)
        if not integrity["status"] == "pass":
            validation["valid"] = False
            validation["failed_checks"].append("manifest_fields_complete")
            validation["checks"].append(integrity)

        try:
            self.manifests.save(manifest)
        except ManifestError as exc:
            return self._failure_report(
                shot_id, spec, str(exc), timestamps, state,
                retry_count=retry_outcome.retry_count,
                errors=accumulated_errors + [str(exc)],
            )

        # 7. Update continuity/run state and continue.
        run_state["shots"][shot_id] = {
            "status": "completed",
            "retry_count": retry_outcome.retry_count,
            "state_fingerprint": state_fingerprint,
            "end_state": end_state,
            "manifest_path": str(self.manifests.manifest_path(shot_id)),
        }

        report_entry = {
            "shot_id": shot_id,
            "scene_id": spec["scene_id"],
            "resumed": False,
            "status": "completed",
            "previous_shot": manifest["previous_shot"],
            "previous_final_frame": manifest["previous_final_frame"],
            "output_artifact": manifest["output_artifact"],
            "final_frame_artifact": final_frame,
            "retry_count": retry_outcome.retry_count,
            "validation_valid": validation["valid"],
            "failed_checks": validation["failed_checks"],
            "state_fingerprint": state_fingerprint,
            "simulated": manifest["dry_run"],
            "manifest_path": str(self.manifests.manifest_path(shot_id)),
        }
        return {
            "success": validation["valid"],
            "report": report_entry,
            "end_state": end_state,
            "error": None if validation["valid"] else "; ".join(validation["failed_checks"]),
            "retry_count": retry_outcome.retry_count,
        }

    def _finalize_artifact(
        self,
        shot_id: str,
        spec: Dict[str, Any],
        result: Any,
    ) -> Dict[str, Any]:
        """Validate + extract the final frame from a real clip, or simulate.

        Real path (simulated=false): validate the MP4 with ffprobe, then
        extract the actual last frame to PNG and register it. Simulated
        behavior remains exclusive to the dry-run providers/tests.
        """
        output_artifact = result.output_artifact
        simulated = bool(output_artifact.get("simulated"))
        if simulated:
            return self.continuity.extract_final_frame(
                shot_id, output_artifact, simulated=True
            )

        # ---- Real media path -------------------------------------------
        artifact_path = output_artifact.get("path")
        if not artifact_path or not str(artifact_path).lower().endswith((".mp4", ".mov", ".webm", ".mkv")):
            raise MediaError(
                f"real provider returned no usable video path for {shot_id}: {artifact_path!r}"
            )
        gen_root = generation_paths(self.project_root, self.output_root)["root"]
        clip_path = gen_root / artifact_path
        self.toolkit.validate_media(
            clip_path,
            expect_duration=float(spec["duration_seconds"]),
            expect_fps=24,
            expect_resolution="1280x720",
            tolerance=1.0,
        )
        frame_path = gen_root / "artifacts" / shot_id / "final_frame.png"
        info = self.toolkit.extract_last_frame(clip_path, frame_path)
        return {
            "artifact_id": f"finalframe-{shot_id}",
            "kind": "frame",
            "path": f"artifacts/{shot_id}/final_frame.png",
            "simulated": False,
            "derived_from": output_artifact.get("artifact_id"),
            "sha256": info["sha256"],
            "digest": info["sha256"][:16],
            "size_bytes": info["size_bytes"],
            "source_video": info["source_video"],
            "extracted_utc": utc_now(),
        }

    def _failure_report(
        self,
        shot_id: str,
        spec: Dict[str, Any],
        error: str,
        timestamps: Dict[str, Any],
        state: Dict[str, Any],
        retry_count: int = 0,
        errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "success": False,
            "error": error,
            "retry_count": retry_count,
            "end_state": None,
            "report": {
                "shot_id": shot_id,
                "scene_id": spec.get("scene_id"),
                "status": "failed",
                "error": error,
                "retry_count": retry_count,
                "errors": list(errors or [error]),
                "timestamps": timestamps,
            },
        }

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _build_report(
        self,
        report_shots: List[Dict[str, Any]],
        chain_validation: Dict[str, Any],
        halted: Optional[Dict[str, Any]],
        run_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        executed = [s for s in report_shots if s.get("status") == "completed"]
        all_valid = all(s.get("validation_valid") for s in executed) and len(executed) == len(
            self.shot_order
        )
        no_broken_links = bool(chain_validation["valid"]) and len(executed) == len(
            self.shot_order
        )

        # Riven identity continuity: canonical fingerprint must be identical
        # in every shot state that includes Riven.
        riven_fingerprints = []
        for shot_id in self.shot_order:
            manifest = self.manifests.load(shot_id)
            if not manifest:
                continue
            riven = manifest["input_visual_state"]["characters"].get("riven")
            if riven:
                riven_fingerprints.append(
                    {
                        "shot_id": shot_id,
                        "identity": riven["identity"],
                        "wardrobe": riven["wardrobe"],
                    }
                )
        identity_continuity = bool(riven_fingerprints) and all(
            canonical_json(r["identity"]) == canonical_json(riven_fingerprints[0]["identity"])
            and canonical_json(r["wardrobe"]) == canonical_json(riven_fingerprints[0]["wardrobe"])
            for r in riven_fingerprints
        )

        # Visual-state propagation: each connected shot inherited the
        # previous working state (propagated_from_state marker set).
        propagation_verified = True
        propagation_details = []
        for shot_id in self.shot_order:
            manifest = self.manifests.load(shot_id)
            if not manifest:
                propagation_verified = False
                propagation_details.append(f"{shot_id}: no manifest")
                continue
            state = manifest["input_visual_state"]
            inherits = state["continuity"]["inherits_previous_shot_state"]
            if inherits:
                marker = state["continuity"].get("propagated_from_state")
                if marker != manifest["previous_shot"]:
                    propagation_verified = False
                    propagation_details.append(
                        f"{shot_id}: expected propagation from {manifest['previous_shot']}, got {marker}"
                    )

        return {
            "schema_version": "1.0",
            "kind": "DEATHBOUND_GENERATION_RUN_REPORT",
            "production_cost_policy": PRODUCTION_COST_POLICY,
            "policy_gate": "passed",
            "episode": self.episode,
            "run_id": self.run_id,
            "mode": "dry_run" if all(
                s.get("simulated") for s in executed
            ) and executed else "unknown",
            "provider": self.provider_id,
            "requested_shot_order": self.shot_order,
            "executed_shot_order": [s["shot_id"] for s in report_shots],
            "correct_shot_ordering": [s["shot_id"] for s in report_shots] == self.shot_order[: len(report_shots)],
            "shots": report_shots,
            "visual_state_propagation": {
                "verified": propagation_verified,
                "details": propagation_details,
            },
            "riven_identity_continuity": {
                "verified": identity_continuity,
                "shots_compared": [r["shot_id"] for r in riven_fingerprints],
                "canonical_identity": (
                    riven_fingerprints[0]["identity"] if riven_fingerprints else None
                ),
            },
            "previous_final_frame_propagation": {
                "verified": chain_validation["valid"]
                and all(
                    s.get("previous_final_frame") is not None
                    for s in executed
                    if s.get("previous_shot")
                ),
                "chain_checked_links": chain_validation["checked_links"],
            },
            "continuity_chain": {
                "links": sorted(self.continuity.chain.get("links", {}).keys()),
                "valid": chain_validation["valid"],
                "errors": chain_validation["errors"],
            },
            "validation": {
                "all_manifests_valid": all(
                    (self.manifests.load(s["shot_id"]) or {}).get("validation_result", {}).get("valid")
                    for s in executed
                )
                if executed
                else False,
                "no_broken_links": no_broken_links,
            },
            "credentials_required": False,
            "dry_run": all(s.get("simulated") for s in executed) if executed else False,
            "halted": halted,
            "overall_pass": bool(
                all_valid
                and propagation_verified
                and identity_continuity
                and chain_validation["valid"]
                and not halted
            ),
            "generated_utc": utc_now(),
        }


def run_three_shot_vertical_slice(
    project_root: Optional[Any] = None,
    output_root: Optional[Any] = None,
    resume: bool = False,
) -> Dict[str, Any]:
    """Success-condition entry point: S01-SHOT-001 -> 002 -> 003 chained dry run."""
    executor = EpisodeExecutor(
        episode="EP001",
        provider="dryrun",
        project_root=project_root,
        output_root=output_root,
        shot_ids=["S01-SHOT-001", "S01-SHOT-002", "S01-SHOT-003"],
        resume=resume,
    )
    return executor.execute()
