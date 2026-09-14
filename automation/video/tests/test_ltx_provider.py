"""LTX provider tests (no GPU/weights required to run).

These validate the parts of the LTX provider that are machine-independent:
capability honesty, ₹0 policy compliance, registry integration, generation
geometry clamping, canonical Riven prompt locking, lazy-import robustness
(in environments without torch), and honest unavailability reporting.
GPU/weight-dependent behavior is covered by LTX_SETUP.md on the target
machine and by the provider acceptance suite.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from automation.video.capabilities import (  # noqa: E402
    PRODUCTION_COST_POLICY,
    PolicyViolation,
    ProviderPolicy,
    capability_report,
    validate_capabilities,
)
from automation.video.ltx_provider import (  # noqa: E402
    DEFAULT_FPS,
    DEFAULT_HEIGHT,
    DEFAULT_NUM_FRAMES,
    DEFAULT_STEPS,
    DEFAULT_WIDTH,
    RIVEN_NEGATIVE_BASE,
    RIVEN_POSITIVE_BASE,
    LTX_CHECKPOINT_FILE,
    LTX_MODEL_ID,
    LTX_SINGLE_FILE_URL,
    LTXLocalProvider,
    resolve_ltx_checkpoint_source,
)
from automation.video.provider_adapter import (  # noqa: E402
    GenerationRequest,
    get_provider,
    registered_providers,
)

PROVIDER_ID = "ltx-local"


class LTXCapabilityHonestyTest(unittest.TestCase):
    """Task requirement: declare capabilities honestly."""

    def setUp(self) -> None:
        self.provider = get_provider(PROVIDER_ID)

    def test_registered(self) -> None:
        self.assertIn(PROVIDER_ID, registered_providers())

    def test_cost_and_execution_honesty(self) -> None:
        caps = self.provider.capabilities
        self.assertIs(caps["local_execution"], True)
        self.assertIs(caps["requires_payment"], False)
        self.assertIs(caps["requires_credentials"], False)
        self.assertIs(caps["remote_execution"], False)

    def test_policy_gate_passes(self) -> None:
        report = capability_report(self.provider)
        self.assertEqual(report["provider_id"], PROVIDER_ID)
        self.assertEqual(report["capability_errors"], [])
        self.assertTrue(report["policy_compatible"], report.get("policy_error"))
        self.assertEqual(report["policy"]["policy"], PRODUCTION_COST_POLICY)

    def test_all_capability_keys_declared(self) -> None:
        errors = validate_capabilities(self.provider.capabilities)
        self.assertEqual(errors, [])

    def test_unsupported_capabilities_declared_false(self) -> None:
        """Never pretend: unsupported features must be explicitly False."""
        caps = self.provider.capabilities
        self.assertIs(caps["last_frame_conditioning"], False)
        self.assertIs(caps["video_extension"], False)

    def test_supported_conditioning_declared_true(self) -> None:
        caps = self.provider.capabilities
        self.assertIs(caps["text_to_video"], True)
        self.assertIs(caps["image_to_video"], True)
        self.assertIs(caps["first_frame_conditioning"], True)
        self.assertIs(caps["reference_images"], True)


class LTXGeometryTest(unittest.TestCase):
    """4 GB VRAM conservative defaults and LTX's 8n+1 frame constraint."""

    def test_default_resolution_is_conservative(self) -> None:
        self.assertEqual((DEFAULT_WIDTH, DEFAULT_HEIGHT), (512, 320))

    def test_resolution_clamped_and_divisible_by_32(self) -> None:
        request = GenerationRequest(
            shot_id="X", prompt="p", duration_seconds=2.0,
            fps=24, resolution="1920x1080",
        )
        width, height = LTXLocalProvider._target_resolution(request)
        self.assertEqual((width, height), (768, 512))
        self.assertEqual(width % 32, 0)
        self.assertEqual(height % 32, 0)

    def test_tiny_resolution_floor(self) -> None:
        request = GenerationRequest(
            shot_id="X", prompt="p", duration_seconds=2.0,
            fps=24, resolution="64x64",
        )
        width, height = LTXLocalProvider._target_resolution(request)
        self.assertEqual((width, height), (256, 256))

    def test_frames_constrained_to_8n_plus_1(self) -> None:
        for duration in (0.5, 1.0, 2.0, 4.0, 10.0, 14.5):
            request = GenerationRequest(
                shot_id="X", prompt="p", duration_seconds=duration,
                fps=DEFAULT_FPS, resolution="512x320",
            )
            frames = LTXLocalProvider._target_frames(request)
            self.assertEqual((frames - 1) % 8, 0, f"{duration}s -> {frames} frames")
            self.assertLessEqual(frames, 97)
            self.assertGreaterEqual(frames, 9)

    def test_long_shot_clamped_for_4gb(self) -> None:
        request = GenerationRequest(
            shot_id="X", prompt="p", duration_seconds=14.5,
            fps=24, resolution="512x320",
        )
        self.assertEqual(LTXLocalProvider._target_frames(request), 97)


class LTXCanonLockTest(unittest.TestCase):
    """Riven prompts get canonical identity terms; canon files untouched."""

    def setUp(self) -> None:
        self.provider = get_provider(PROVIDER_ID)
        self.request = GenerationRequest(
            shot_id="X", prompt="Riven standing in a dim bedroom",
            duration_seconds=2.0, fps=24, resolution="512x320",
        )

    def test_riven_prompt_gets_canonical_lock(self) -> None:
        prompt = self.provider.build_prompt(self.request)
        self.assertIn("charcoal-black hooded coat", prompt)
        self.assertIn("RIVEN", prompt.upper() or prompt)  # base mention survives
        self.assertIn("realistic young adult man", prompt)

    def test_riven_negative_includes_canon_bans(self) -> None:
        negative = self.provider.build_negative_prompt(self.request)
        for banned in ("anime", "giant scythe", "grim reaper", "fantasy armor", "3D render"):
            self.assertIn(banned, negative)

    def test_non_riven_prompt_untouched(self) -> None:
        request = GenerationRequest(
            shot_id="X", prompt="an empty city street at night",
            duration_seconds=2.0, fps=24, resolution="512x320",
        )
        self.assertEqual(self.provider.build_prompt(request), request.prompt)
        self.assertEqual(self.provider.build_negative_prompt(request), "")

    def test_canon_constants_match_master_spec(self) -> None:
        self.assertIn("19-22", RIVEN_POSITIVE_BASE)
        self.assertIn("black boots", RIVEN_POSITIVE_BASE)


class LTXAvailabilityHonestyTest(unittest.TestCase):
    """No faked success: without GPU/weights the provider reports truth."""

    def test_unavailable_environment_is_reported_not_faked(self) -> None:
        provider = get_provider(PROVIDER_ID)
        if provider.is_available():
            self.skipTest("GPU present in this environment; honesty path N/A")
        request = GenerationRequest(
            shot_id="NOGPU-001", prompt="p", duration_seconds=2.0,
            fps=24, resolution="512x320",
        )
        with self.assertRaises((RuntimeError, ImportError, Exception)):
            provider.generate(request)

    def test_is_available_false_without_torch_cuda(self) -> None:
        provider = get_provider(PROVIDER_ID)
        try:
            import torch

            if torch.cuda.is_available():
                self.skipTest("CUDA available")
        except ImportError:
            pass
        self.assertFalse(provider.is_available())


class LTXModelSourceTest(unittest.TestCase):
    """Verified model source (production-blocker fix).

    The intended model is LTX-Video 2B 0.9.6-distilled. It exists ONLY as the
    single-file checkpoint ltxv-2b-0.9.6-distilled-04-25.safetensors inside
    the public Lightricks/LTX-Video repo (verified via the live Hugging Face
    API: the old 'Lightricks/ltxv-2b-0.9.6-distilled' repo ID returns HTTP 401
    and never resolved; the 0.9.7-distilled diffusers repos are 13B-only).
    """

    def test_host_repo_is_public_ltx_video_repo(self) -> None:
        self.assertEqual(LTX_MODEL_ID, "Lightricks/LTX-Video")

    def test_checkpoint_is_the_2b_096_distilled_weights(self) -> None:
        self.assertEqual(
            LTX_CHECKPOINT_FILE, "ltxv-2b-0.9.6-distilled-04-25.safetensors"
        )

    def test_single_file_url_points_at_verified_checkpoint(self) -> None:
        self.assertEqual(
            LTX_SINGLE_FILE_URL,
            "https://huggingface.co/Lightricks/LTX-Video/resolve/main/"
            "ltxv-2b-0.9.6-distilled-04-25.safetensors",
        )

    def test_dead_repo_id_is_not_used(self) -> None:
        """Regression guard: the old ID does not resolve on Hugging Face."""
        self.assertNotIn("ltxv-2b-0.9.6-distilled", LTX_MODEL_ID.lower())

    def test_provider_uses_single_file_loading(self) -> None:
        """The hosting repo has no diffusers model_index.json; the provider
        must load the 2B checkpoint via from_single_file, not from_pretrained."""
        import inspect

        from automation.video import ltx_provider as module

        ensure_loaded_source = inspect.getsource(module.LTXLocalProvider.ensure_loaded)
        self.assertIn("LTXPipeline.from_single_file", ensure_loaded_source)
        self.assertNotIn("LTXPipeline.from_pretrained", ensure_loaded_source)
        self.assertIn("LTXConditionPipeline.from_single_file", inspect.getsource(module.LTXLocalProvider._condition_pipeline))
        self.assertNotIn("LTXConditionPipeline.from_pretrained", inspect.getsource(module.LTXLocalProvider._condition_pipeline))
        self.assertNotIn("LTXPipeline.from_pretrained", inspect.getsource(module.LTXLocalProvider._text_pipeline))

    def test_distilled_schedule_used(self) -> None:
        self.assertEqual(DEFAULT_STEPS, 8)

    def test_api_defaults_preserved(self) -> None:
        """Surgical fix: all generation defaults must survive unchanged."""
        self.assertEqual((DEFAULT_WIDTH, DEFAULT_HEIGHT), (512, 320))
        self.assertEqual(DEFAULT_FPS, 24)
        self.assertEqual(DEFAULT_STEPS, 8)


class LTXSingleFileSourceTest(unittest.TestCase):
    """Regression tests for the RTX 3050 runtime bug.

    Diffusers 0.40.0's ``_extract_repo_id_and_weights_name`` strips the Hub
    host prefix and matches an optional ``blob/main/`` segment but NOT
    ``resolve/main/``; a /resolve/main/ link produced
    ``.../resolve/main/resolve/main/<file>`` -> HTTP 404. The provider must
    therefore use the documented /blob/main/ link (or a local file path).
    """

    def setUp(self) -> None:
        self._old = os.environ.pop("DEATHBOUND_LTX_LOCAL_CHECKPOINT", None)

    def tearDown(self) -> None:
        if self._old is not None:
            os.environ["DEATHBOUND_LTX_LOCAL_CHECKPOINT"] = self._old
        else:
            os.environ.pop("DEATHBOUND_LTX_LOCAL_CHECKPOINT", None)

    def test_no_resolve_main_in_hub_source(self) -> None:
        """The doubled-/resolve/main/ bug must stay impossible."""
        self.assertIn("/blob/main/", LTX_SINGLE_FILE_URL)
        self.assertNotIn("/resolve/main/", LTX_SINGLE_FILE_URL)

    def test_blob_link_parses_to_repo_and_filename(self) -> None:
        """Functional guard using diffusers' own 0.40.0 parser (skips when
        diffusers is not installed, e.g. the repo test environment)."""
        try:
            from diffusers.loaders.single_file_utils import (
                _extract_repo_id_and_weights_name,
            )
        except ImportError:
            self.skipTest("diffusers not installed in this environment")
        repo_id, weights_name = _extract_repo_id_and_weights_name(LTX_SINGLE_FILE_URL)
        self.assertEqual(repo_id, LTX_MODEL_ID)
        self.assertEqual(weights_name, LTX_CHECKPOINT_FILE)
        self.assertFalse(weights_name.startswith("resolve/"))

    def test_default_source_is_documented_blob_link(self) -> None:
        source = resolve_ltx_checkpoint_source()
        self.assertEqual(source, LTX_SINGLE_FILE_URL)
        self.assertIn(LTX_MODEL_ID, source)
        self.assertTrue(source.endswith(LTX_CHECKPOINT_FILE))

    def test_explicit_local_checkpoint_path_is_accepted(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as handle:
            local_path = handle.name
        try:
            os.environ["DEATHBOUND_LTX_LOCAL_CHECKPOINT"] = local_path
            source = resolve_ltx_checkpoint_source()
            self.assertEqual(os.path.abspath(source), os.path.abspath(local_path))
        finally:
            os.unlink(local_path)

    def test_windows_style_local_path_is_accepted(self) -> None:
        """Windows paths (backslashes, drive letters) must pass through
        untouched — they hit diffusers' os.path.isfile branch, not URL parsing."""
        windows_path = "D:\\Deathbound\\cache\\ltxv-2b-0.9.6-distilled-04-25.safetensors"
        os.environ["DEATHBOUND_LTX_LOCAL_CHECKPOINT"] = windows_path
        try:
            if os.name == "nt":
                self.assertEqual(resolve_ltx_checkpoint_source(), windows_path)
            else:
                # On POSIX the file cannot exist, so the honest error fires.
                with self.assertRaises(Exception) as ctx:
                    resolve_ltx_checkpoint_source()
                self.assertIn("does not exist", str(ctx.exception))
        finally:
            os.environ.pop("DEATHBOUND_LTX_LOCAL_CHECKPOINT", None)

    def test_declared_but_missing_local_path_raises_no_silent_fallback(self) -> None:
        os.environ["DEATHBOUND_LTX_LOCAL_CHECKPOINT"] = "Z:/definitely/missing.safetensors"
        with self.assertRaises(Exception) as ctx:
            resolve_ltx_checkpoint_source()
        self.assertIn("DEATHBOUND_LTX_LOCAL_CHECKPOINT", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
