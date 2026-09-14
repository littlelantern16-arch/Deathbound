"""Test suite for the Deathbound Visual State + Temporal Continuity Engine.

Covers (per the production brief): visual state construction, Riven reference
resolution, state transition, previous-frame propagation, broken chain
detection, manifest integrity, retry behavior, resume behavior, and the
3-shot vertical slice — plus canon protection and dry-run honesty.

Run:
    python3 -m automation.video.tests.test_video_pipeline
    (from the repository root; DEATHBOUND_ROOT is auto-detected)
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from automation.video import (  # noqa: E402
    CharacterReferenceBank,
    GenerationManifestManager,
    TemporalContinuityManager,
    VisualStateManager,
    get_provider,
    register_provider,
)
from automation.video.continuity import ContinuityError  # noqa: E402
from automation.video.executor import EpisodeExecutor  # noqa: E402
from automation.video.manifest import ManifestError  # required for integrity tests  # noqa: E402
from automation.video.paths import canonical_json, find_project_root, generation_paths, load_json  # noqa: E402
from automation.video.provider_adapter import (  # noqa: E402
    DryRunProvider,
    GenerationRequest,
    ProviderError,
    VideoProvider,
)
from automation.video.qa import (  # noqa: E402
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
from automation.video.reference_bank import ReferenceBankError  # noqa: E402
from automation.video.visual_state import VisualStateError  # noqa: E402


# ----------------------------------------------------------------------
# Fakes / helpers
# ----------------------------------------------------------------------


class FlakyProvider(VideoProvider):
    """Fails N times per shot then succeeds; exercises bounded retry."""

    provider_id = "test-flaky"
    capabilities = {**DryRunProvider.capabilities, "polling": False}

    def __init__(self, fail_times: int = 1) -> None:
        self.fail_times = fail_times
        self.attempts: dict = {}

    def generate(self, request: GenerationRequest):
        shot = request.shot_id
        self.attempts[shot] = self.attempts.get(shot, 0) + 1
        if self.attempts[shot] <= self.fail_times:
            raise ProviderError(f"simulated provider failure #{self.attempts[shot]}")
        artifact = {
            "artifact_id": f"{shot}-clip",
            "kind": "video_clip",
            "path": f"artifacts/{shot}/clip.json",
            "simulated": True,
        }
        from automation.video.provider_adapter import GenerationResult

        return GenerationResult(
            shot_id=shot,
            output_artifact=artifact,
            poll_count=0,
            generation_parameters={"provider": self.provider_id, "simulated": True},
        )


register_provider(FlakyProvider)


def make_state(vsm: VisualStateManager, shot_id: str = "S01-SHOT-001"):
    return vsm.build_state(shot_id)


def make_selection(bank: CharacterReferenceBank, shot: dict):
    return {
        char_id: bank.select_for_shot(char_id, shot)
        for char_id in shot.get("characters", [])
    }


# ----------------------------------------------------------------------
# Tests
# ----------------------------------------------------------------------


class VisualStateConstructionTest(unittest.TestCase):
    """Requirement: visual state construction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.vsm = VisualStateManager()

    def test_all_58_shots_build_state(self) -> None:
        self.assertEqual(len(self.vsm.shots), 58)
        for shot_id in self.vsm.resolve_shot_order():
            state = self.vsm.build_state(shot_id)
            self.assertEqual(state["shot_id"], shot_id)

    def test_state_tracks_required_dimensions(self) -> None:
        state = make_state(self.vsm)
        for key in (
            "characters",
            "location",
            "spatial_position",
            "orientation",
            "props",
            "environment",
            "lighting",
            "camera",
            "effects",
            "performance",
            "causal",
            "continuity",
        ):
            self.assertIn(key, state)

    def test_character_state_sections_present(self) -> None:
        state = make_state(self.vsm)
        riven = state["characters"]["riven"]
        for section in (
            "identity",
            "appearance",
            "wardrobe",
            "body_state",
            "facial_state",
            "performance_state",
        ):
            self.assertIn(section, riven)

    def test_riven_identity_from_canon(self) -> None:
        riven = make_state(self.vsm)["characters"]["riven"]
        self.assertEqual(riven["identity"]["id"], "riven")
        self.assertEqual(riven["identity"]["name"], "Riven")
        self.assertEqual(riven["identity"]["role"], "Young Reaper")
        self.assertEqual(riven["identity"]["universe"], "The Reaper's Ledger")

    def test_wardrobe_matches_canonical_clothing(self) -> None:
        wardrobe = make_state(self.vsm)["characters"]["riven"]["wardrobe"]
        self.assertEqual(
            wardrobe["canonical_clothing"],
            [
                "long charcoal-black hooded coat",
                "dark fitted shirt",
                "black trousers",
                "dark boots",
                "subtle silver details",
            ],
        )
        self.assertTrue(wardrobe["immutable_without_cause"])

    def test_chain_root_has_no_previous(self) -> None:
        state = make_state(self.vsm, "S01-SHOT-001")
        self.assertFalse(state["continuity"]["inherits_previous_shot_state"])
        self.assertIsNone(state["continuity"]["previous_shot_id"])

    def test_connected_shot_inherits_spec_previous(self) -> None:
        state = make_state(self.vsm, "S01-SHOT-002")
        self.assertTrue(state["continuity"]["inherits_previous_shot_state"])
        self.assertEqual(state["continuity"]["previous_shot_id"], "S01-SHOT-001")

    def test_supernatural_effect_drives_eye_state(self) -> None:
        state = make_state(self.vsm, "S01-SHOT-003")  # has supernatural_energy
        riven = state["characters"]["riven"]
        self.assertEqual(riven["facial_state"]["eyes"], "supernatural_glow")
        changes = {
            c["property"]: c for c in state["causal"]["state_changes"]
        }
        self.assertIn("eyes", changes)
        self.assertEqual(changes["eyes"]["previous"], "dark")
        self.assertEqual(changes["eyes"]["new"], "supernatural_glow")

    def test_unknown_shot_rejected(self) -> None:
        with self.assertRaises(VisualStateError):
            self.vsm.get_shot("S99-SHOT-999")

    def test_resolve_shot_order_full_and_subset(self) -> None:
        full = self.vsm.resolve_shot_order()
        self.assertEqual(full[0], "S01-SHOT-001")
        self.assertEqual(full[2], "S01-SHOT-003")
        self.assertEqual(
            self.vsm.resolve_shot_order(["S01-SHOT-002", "S01-SHOT-003"]),
            ["S01-SHOT-002", "S01-SHOT-003"],
        )
        with self.assertRaises(VisualStateError):
            self.vsm.resolve_shot_order(["S01-SHOT-002", "S01-SHOT-001"])

    def test_fingerprint_is_deterministic(self) -> None:
        state = make_state(self.vsm)
        self.assertEqual(
            self.vsm.fingerprint(state), self.vsm.fingerprint(self.vsm.build_state("S01-SHOT-001"))
        )


class RivenReferenceResolutionTest(unittest.TestCase):
    """Requirement: Riven reference resolution (persistent reference bank)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.bank = CharacterReferenceBank()

    def test_riven_canon_preserved_in_bank(self) -> None:
        fingerprint = self.bank.canonical_fingerprint("riven")
        self.assertEqual(fingerprint["name"], "Riven")
        self.assertEqual(fingerprint["role"], "Young Reaper")
        self.assertEqual(fingerprint["age_appearance"], "young adult, approximately 19-22")
        self.assertIn("subtle silver details", fingerprint["canonical_clothing"] or [])

    def test_canonical_clothing_listed(self) -> None:
        constraints = self.bank.bank["riven"]["canonical_constraints"]
        self.assertEqual(
            constraints["canonical_clothing"],
            [
                "long charcoal-black hooded coat",
                "dark fitted shirt",
                "black trousers",
                "dark boots",
                "subtle silver details",
            ],
        )

    def test_select_for_shot_without_assets_yields_simulated(self) -> None:
        shot = {"characters": ["riven"], "character_performance": {"face": ["neutral"]}}
        selection = self.bank.select_for_shot("riven", shot)
        self.assertEqual(len(selection["references"]), 1)
        reference = selection["references"][0]
        self.assertTrue(reference["simulated"])
        self.assertTrue(selection["all_simulated"])
        self.assertIsNone(reference["path"])

    def test_real_assets_selected_over_simulated(self) -> None:
        bank = CharacterReferenceBank()
        bank.associate_reference(
            "riven",
            "riven-front-portrait",
            "primary_identity",
            "assets/characters/Riven/riven_front.png",
        )
        bank.associate_reference(
            "riven",
            "riven-side-angle",
            "angle",
            "assets/characters/Riven/riven_side.png",
        )
        shot = {"characters": ["riven"], "character_performance": {"face": ["conflicted"]}}
        selection = bank.select_for_shot("riven", shot)
        ids = [r["reference_id"] for r in selection["references"]]
        self.assertEqual(ids[0], "riven-front-portrait")
        self.assertIn("riven-side-angle", ids)
        self.assertFalse(selection["all_simulated"])

    def test_no_simulation_mode_requires_assets(self) -> None:
        bank = CharacterReferenceBank(simulate_missing_references=False)
        shot = {"characters": ["riven"], "character_performance": {"face": ["neutral"]}}
        with self.assertRaises(ReferenceBankError):
            bank.select_for_shot("riven", shot)

    def test_canon_violation_rejected(self) -> None:
        candidate = {
            "reference_id": "bad",
            "tags": ["anime", "giant scythe"],
            "metadata": {"descriptor": ""},
        }
        with self.assertRaises(ReferenceBankError):
            self.bank.enforce_canon("riven", candidate)

    def test_bank_persistence_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reference_bank.json"
            bank = CharacterReferenceBank(bank_path=path)
            bank.associate_reference(
                "riven", "ref-x", "primary_identity", "assets/x.png"
            )
            bank.save()
            reloaded = CharacterReferenceBank(bank_path=path)
            self.assertIn("ref-x", [r["reference_id"] for r in reloaded.bank["riven"]["references"]])
            # Canonical identity survives reload untouched.
            self.assertEqual(
                reloaded.bank["riven"]["canonical_identity"]["name"], "Riven"
            )


class StateTransitionTest(unittest.TestCase):
    """Requirement: state transition (propagation between connected shots)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.vsm = VisualStateManager()

    def test_apply_transition_marks_propagation(self) -> None:
        previous = self.vsm.build_state("S01-SHOT-001")
        nxt = self.vsm.apply_transition(previous, "S01-SHOT-002")
        self.assertEqual(
            nxt["continuity"]["propagated_from_state"], "S01-SHOT-001"
        )

    def test_causal_changes_carry_forward(self) -> None:
        previous = self.vsm.build_state("S01-SHOT-001")
        nxt = self.vsm.apply_transition(previous, "S01-SHOT-003")
        properties = [c["property"] for c in nxt["causal"]["state_changes"]]
        self.assertIn("eyes", properties)

    def test_uncaused_identity_change_is_invalid_transition(self) -> None:
        previous = make_state(self.vsm)
        nxt = self.vsm.apply_transition(previous, "S01-SHOT-002")
        # Simulate an uncaused wardrobe change.
        nxt["characters"]["riven"]["wardrobe"]["canonical_clothing"] = ["spacesuit"]
        result = validate_shot_transition(previous, nxt)
        self.assertEqual(result["status"], "fail")
        self.assertIn("wardrobe changed without cause", result["detail"])

    def test_uncaused_eye_change_is_invalid(self) -> None:
        previous = make_state(self.vsm)
        nxt = self.vsm.apply_transition(previous, "S01-SHOT-002")
        nxt["characters"]["riven"]["facial_state"]["eyes"] = "supernatural_glow"
        result = validate_shot_transition(previous, nxt)
        self.assertEqual(result["status"], "fail")
        self.assertIn("eye state changed", result["detail"])

    def test_valid_chain_transition_passes(self) -> None:
        previous = make_state(self.vsm)
        nxt = self.vsm.apply_transition(previous, "S01-SHOT-002")
        result = validate_shot_transition(previous, nxt)
        self.assertEqual(result["status"], "pass", result["detail"])


class PreviousFramePropagationTest(unittest.TestCase):
    """Requirement: previous-frame propagation through the chain."""

    def test_extract_and_register_then_condition_next(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = TemporalContinuityManager(output_root=Path(tmp))
            artifact = {
                "artifact_id": "S01-SHOT-001-clip",
                "kind": "video_clip",
                "path": "artifacts/S01-SHOT-001/clip.json",
                "simulated": True,
            }
            frame = manager.extract_final_frame(
                "S01-SHOT-001", artifact, simulated=True
            )
            self.assertEqual(frame["kind"], "frame")
            self.assertTrue(frame["simulated"])
            self.assertEqual(frame["derived_from"], "S01-SHOT-001-clip")

            manager.register_final_frame("S01-SHOT-001", frame, {"state_fingerprint": "abc"})
            conditioning = manager.get_conditioning_for(
                "S01-SHOT-002", "S01-SHOT-001"
            )
            self.assertIsNotNone(conditioning)
            self.assertEqual(conditioning["artifact_id"], "finalframe-S01-SHOT-001")

    def test_missing_previous_frame_raises_broken_chain(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = TemporalContinuityManager(output_root=Path(tmp))
            with self.assertRaises(ContinuityError):
                manager.get_conditioning_for("S01-SHOT-002", "S01-SHOT-001")

    def test_extraction_requires_output_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = TemporalContinuityManager(output_root=Path(tmp))
            with self.assertRaises(ContinuityError):
                manager.extract_final_frame("S01-SHOT-001", None, simulated=True)


class BrokenChainDetectionTest(unittest.TestCase):
    """Requirement: broken chain detection."""

    def test_validate_chain_detects_missing_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = TemporalContinuityManager(output_root=Path(tmp))
            result = manager.validate_chain(["A", "B", "C"])
            self.assertFalse(result["valid"])
            self.assertEqual(len(result["errors"]), 2)

    def test_validate_chain_passes_when_all_registered(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = TemporalContinuityManager(output_root=Path(tmp))
            for shot_id in ["A", "B", "C"]:
                artifact = {"artifact_id": f"{shot_id}-clip", "kind": "video_clip", "simulated": True}
                frame = manager.extract_final_frame(shot_id, artifact, simulated=True)
                manager.register_final_frame(shot_id, frame)
            result = manager.validate_chain(["A", "B", "C"])
            self.assertTrue(result["valid"], result["errors"])


class ManifestIntegrityTest(unittest.TestCase):
    """Requirement: manifest integrity."""

    def _valid_manifest(self) -> dict:
        from automation.video.manifest import utc_now

        return {
            "manifest_version": "1.0",
            "episode": "EP001",
            "scene_id": "S01",
            "shot_id": "S01-SHOT-001",
            "run_id": "test-run",
            "input_visual_state": {"shot_id": "S01-SHOT-001", "characters": {"riven": {}}},
            "previous_shot": None,
            "previous_final_frame": None,
            "character_references": {"riven": {"references": [{"reference_id": "sim-riven"}]}},
            "prompt": "Riven stands in a bedroom.",
            "provider": "dryrun",
            "model": None,
            "generation_parameters": {"simulated": True},
            "output_artifact": {
                "artifact_id": "S01-SHOT-001-clip",
                "kind": "video_clip",
                "path": "artifacts/x.json",
                "simulated": True,
            },
            "final_frame_artifact": {
                "artifact_id": "finalframe-S01-SHOT-001",
                "kind": "frame",
                "path": "artifacts/x.frame.json",
                "simulated": True,
                "derived_from": "S01-SHOT-001-clip",
            },
            "validation_result": {"valid": True, "checks": []},
            "retry_count": 0,
            "dry_run": True,
            "timestamps": {
                "created_utc": utc_now(),
                "generation_started_utc": utc_now(),
                "generation_finished_utc": utc_now(),
            },
            "errors": [],
        }

    def test_valid_manifest_passes(self) -> None:
        manifest = self._valid_manifest()
        result = validate_manifest_integrity(manifest)
        self.assertTrue(result["status"] == "pass", result["detail"])

    def test_missing_field_fails(self) -> None:
        manifest = self._valid_manifest()
        del manifest["retry_count"]
        result = validate_manifest_integrity(manifest)
        self.assertEqual(result["status"], "fail")
        self.assertIn("retry_count", result["detail"])

    def test_simulated_artifacts_require_dry_run_flag(self) -> None:
        manifest = self._valid_manifest()
        manifest.pop("dry_run", None)
        manager = GenerationManifestManager()
        errors = manager.validate(manifest)
        self.assertFalse(errors["valid"])
        self.assertTrue(
            any("dry_run flag missing" in e for e in errors["errors"])
        )

    def test_errors_and_valid_coherence(self) -> None:
        manifest = self._valid_manifest()
        manifest["errors"] = ["something went wrong"]
        manager = GenerationManifestManager()
        errors = manager.validate(manifest)
        self.assertFalse(errors["valid"])

    def test_save_refuses_invalid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = GenerationManifestManager(output_root=Path(tmp))
            manifest = self._valid_manifest()
            del manifest["prompt"]
            with self.assertRaises(ManifestError):
                manager.save(manifest)

    def test_save_load_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = GenerationManifestManager(output_root=Path(tmp))
            manifest = self._valid_manifest()
            manager.build  # build exists
            saved = manager.save(manifest)
            loaded = manager.load(manifest["shot_id"])
            self.assertEqual(loaded["shot_id"], manifest["shot_id"])
            self.assertTrue(Path(saved).exists())


class RetryBehaviorTest(unittest.TestCase):
    """Requirement: retry behavior (bounded, with backoff hook)."""

    def test_flaky_provider_recovers_within_bounded_retries(self) -> None:
        provider = FlakyProvider(fail_times=1)
        request = GenerationRequest(
            shot_id="RETRY-001",
            prompt="test",
            duration_seconds=1.0,
            fps=24,
            resolution="1280x720",
        )
        policy = RetryPolicy(max_attempts=3, backoff_seconds=0.0)
        outcome = policy.run(lambda: provider.generate(request))
        self.assertTrue(outcome.succeeded)
        self.assertEqual(outcome.attempts, 2)
        self.assertEqual(outcome.retry_count, 1)
        self.assertEqual(provider.attempts["RETRY-001"], 2)

    def test_retry_gives_up_after_max_attempts(self) -> None:
        provider = FlakyProvider(fail_times=10)
        request = GenerationRequest(
            shot_id="RETRY-002",
            prompt="test",
            duration_seconds=1.0,
            fps=24,
            resolution="1280x720",
        )
        policy = RetryPolicy(max_attempts=3, backoff_seconds=0.0)
        outcome = policy.run(lambda: provider.generate(request))
        self.assertFalse(outcome.succeeded)
        self.assertEqual(outcome.attempts, 3)
        self.assertEqual(provider.attempts["RETRY-002"], 3)

    def test_executor_records_retry_count_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            original = get_provider
            import automation.video.executor as executor_module

            executor_module.get_provider = lambda provider_id: FlakyProvider(fail_times=1)
            try:
                executor = EpisodeExecutor(
                    shot_ids=["S01-SHOT-001"], output_root=Path(tmp)
                )
                report = executor.execute()
                self.assertTrue(report["overall_pass"])
            finally:
                executor_module.get_provider = original

            manifest = load_json(Path(tmp) / "manifests" / "S01-SHOT-001.manifest.json")
            self.assertEqual(manifest["retry_count"], 1)
            self.assertEqual(manifest["provider"], "test-flaky")


class ResumeBehaviorTest(unittest.TestCase):
    """Requirement: resume after failure."""

    def test_resume_skips_completed_shots(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            import automation.video.executor as executor_module

            original = executor_module.get_provider

            class FailingThenFlaky:
                pass

            # First run: provider fails on shot 2 -> run halts at shot 2.
            executor_module.get_provider = lambda provider_id: FlakyProvider(fail_times=0)
            try:
                # A provider that succeeds for shot 1 but fails for shot 2.
                class Shot2Fails(VideoProvider):
                    provider_id = "test-shot2-fails"

                    def __init__(self) -> None:
                        self.attempts = {}

                    def generate(self, request):
                        self.attempts[request.shot_id] = self.attempts.get(request.shot_id, 0) + 1
                        if request.shot_id == "S01-SHOT-002":
                            raise ProviderError("shot 2 always fails")
                        artifact = {
                            "artifact_id": f"{request.shot_id}-clip",
                            "kind": "video_clip",
                            "path": f"artifacts/{request.shot_id}/clip.json",
                            "simulated": True,
                        }
                        from automation.video.provider_adapter import GenerationResult

                        return GenerationResult(
                            shot_id=request.shot_id,
                            output_artifact=artifact,
                            poll_count=0,
                            generation_parameters={"simulated": True},
                        )

                provider = Shot2Fails()
                executor_module.get_provider = lambda provider_id: provider
                first = EpisodeExecutor(
                    shot_ids=["S01-SHOT-001", "S01-SHOT-002", "S01-SHOT-003"],
                    output_root=Path(tmp),
                ).execute()
                self.assertFalse(first["overall_pass"])
                self.assertEqual(first["halted"]["shot_id"], "S01-SHOT-002")
            finally:
                executor_module.get_provider = original

            # Second run with resume=True and a working provider.
            executor_module.get_provider = lambda provider_id: FlakyProvider(fail_times=0)
            try:
                second = EpisodeExecutor(
                    shot_ids=["S01-SHOT-001", "S01-SHOT-002", "S01-SHOT-003"],
                    output_root=Path(tmp),
                    resume=True,
                ).execute()
                self.assertTrue(second["overall_pass"])
            finally:
                executor_module.get_provider = original

            resumed_entry = next(
                s for s in second["shots"] if s["shot_id"] == "S01-SHOT-001"
            )
            self.assertTrue(resumed_entry["resumed"])
            # The chain from shot 1 is preserved: shot 2's manifest must still
            # reference the ORIGINAL shot 1 final frame.
            manifest2 = load_json(Path(tmp) / "manifests" / "S01-SHOT-002.manifest.json")
            self.assertEqual(manifest2["previous_shot"], "S01-SHOT-001")
            self.assertEqual(
                manifest2["previous_final_frame"]["artifact_id"],
                "finalframe-S01-SHOT-001",
            )

    def test_resume_requires_run_state_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = EpisodeExecutor(
                shot_ids=["S01-SHOT-001"], output_root=Path(tmp), resume=True
            )
            state = executor._load_run_state()
            self.assertEqual(state["run_id"], executor.run_id)
            self.assertEqual(state["shots"], {})


class ThreeShotVerticalSliceTest(unittest.TestCase):
    """Requirement: 3-shot vertical slice dry-run (the success condition)."""

    def test_three_shot_chained_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            executor = EpisodeExecutor(
                shot_ids=["S01-SHOT-001", "S01-SHOT-002", "S01-SHOT-003"],
                output_root=Path(tmp),
            )
            report = executor.execute()

            # Correct shot ordering
            self.assertEqual(report["executed_shot_order"], [
                "S01-SHOT-001", "S01-SHOT-002", "S01-SHOT-003",
            ])
            self.assertTrue(report["correct_shot_ordering"])

            # Visual-state propagation
            self.assertTrue(report["visual_state_propagation"]["verified"],
                            report["visual_state_propagation"]["details"])

            # Riven identity continuity
            self.assertTrue(report["riven_identity_continuity"]["verified"])

            # Previous final-frame propagation
            self.assertTrue(report["previous_final_frame_propagation"]["verified"])

            # Valid manifests + no broken links
            self.assertTrue(report["validation"]["all_manifests_valid"])
            self.assertTrue(report["validation"]["no_broken_links"])

            # No credentials required; everything simulated
            self.assertFalse(report["credentials_required"])
            self.assertTrue(report["dry_run"])
            self.assertTrue(report["overall_pass"])

            shot2 = next(s for s in report["shots"] if s["shot_id"] == "S01-SHOT-002")
            shot3 = next(s for s in report["shots"] if s["shot_id"] == "S01-SHOT-003")
            self.assertEqual(shot2["previous_shot"], "S01-SHOT-001")
            self.assertEqual(shot3["previous_shot"], "S01-SHOT-002")
            self.assertEqual(
                shot2["previous_final_frame"]["artifact_id"], "finalframe-S01-SHOT-001"
            )
            self.assertEqual(
                shot3["previous_final_frame"]["artifact_id"], "finalframe-S01-SHOT-002"
            )
            self.assertTrue(all(s["simulated"] for s in report["shots"]))

    def test_vertical_slice_entry_point(self) -> None:
        from automation.video.executor import run_three_shot_vertical_slice

        with tempfile.TemporaryDirectory() as tmp:
            report = run_three_shot_vertical_slice(output_root=Path(tmp))
            self.assertTrue(report["overall_pass"])
            self.assertEqual(len(report["shots"]), 3)


class DryRunHonestyTest(unittest.TestCase):
    """Requirement: no fake success — simulated artifacts clearly marked."""

    def test_artifacts_marked_simulated(self) -> None:
        provider = get_provider("dryrun")
        request = GenerationRequest(
            shot_id="HONESTY-001",
            prompt="test",
            duration_seconds=1.0,
            fps=24,
            resolution="1280x720",
        )
        result = provider.generate(request)
        self.assertTrue(result.output_artifact["simulated"])
        stub_path = find_project_root() / "production" / "generation" / "artifacts" / "HONESTY-001" / "clip.json"
        try:
            stub = load_json(stub_path)
            self.assertTrue(stub["simulated"])
            self.assertIn("NOT real generated media", stub["note"])
        finally:
            shutil.rmtree(
                find_project_root() / "production" / "generation" / "artifacts" / "HONESTY-001",
                ignore_errors=True,
            )

    def test_reports_flag_mode_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = EpisodeExecutor(
                shot_ids=["S01-SHOT-001"], output_root=Path(tmp)
            ).execute()
            self.assertEqual(report["mode"], "dry_run")
            self.assertTrue(report["dry_run"])

    def test_manifest_flags_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            EpisodeExecutor(shot_ids=["S01-SHOT-001"], output_root=Path(tmp)).execute()
            manifest = load_json(Path(tmp) / "manifests" / "S01-SHOT-001.manifest.json")
            self.assertTrue(manifest["dry_run"])
            self.assertTrue(manifest["output_artifact"]["simulated"])
            self.assertTrue(manifest["final_frame_artifact"]["simulated"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
