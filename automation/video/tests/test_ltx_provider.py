"""LTX provider tests (no GPU/weights required to run).

These validate the parts of the LTX provider that are machine-independent:
capability honesty, ₹0 policy compliance, registry integration, generation
geometry clamping, canonical Riven prompt locking, lazy-import robustness
(in environments without torch), and honest unavailability reporting.
GPU/weight-dependent behavior is covered by LTX_SETUP.md on the target
machine and by the provider acceptance suite.
"""

from __future__ import annotations

import sys
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
    LTX_MODEL_ID,
    LTXLocalProvider,
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


class LTXModelChoiceTest(unittest.TestCase):
    """Task #3 decision encoded: exactly the selected ₹0 backend."""

    def test_selected_model_is_ltx_2b_distilled(self) -> None:
        self.assertIn("ltxv-2b", LTX_MODEL_ID)
        self.assertIn("distilled", LTX_MODEL_ID)
        self.assertIn("Lightricks", LTX_MODEL_ID)

    def test_distilled_schedule_used(self) -> None:
        self.assertEqual(DEFAULT_STEPS, 8)


if __name__ == "__main__":
    unittest.main(verbosity=2)
