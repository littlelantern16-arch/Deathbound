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
        """A 1080p delivery request infers natively at the largest exact-16:9
        /32-divisible canvas inside the 4 GB area budget: 512x288.
        (768x512 is 3:2 — it would distort 16:9 delivery; 768x432 is 16:9 but
        not /32-divisible. The FFmpeg delivery step upscales 512x288 to the
        exact requested frame size, same aspect.)"""
        request = GenerationRequest(
            shot_id="X", prompt="p", duration_seconds=2.0,
            fps=24, resolution="1920x1080",
        )
        width, height = LTXLocalProvider._target_resolution(request)
        self.assertEqual((width, height), (512, 288))
        self.assertEqual(width % 32, 0)
        self.assertEqual(height % 32, 0)
        self.assertEqual(width * 9, height * 16)  # aspect preserved exactly

    def test_native_never_exceeds_deliverable(self) -> None:
        """Native inference geometry is bounded by the delivery frame itself,
        so tiny/smoke requests never balloon up to the area ceiling."""
        for resolution in ("512x320", "640x360", "256x256", "320x320"):
            request = GenerationRequest(
                shot_id="X", prompt="p", duration_seconds=2.0,
                fps=24, resolution=resolution,
            )
            deliverable = LTXLocalProvider._deliverable_resolution(request)
            native = LTXLocalProvider._native_resolution(*deliverable)
            self.assertLessEqual(native[0], deliverable[0], resolution)
            self.assertLessEqual(native[1], deliverable[1], resolution)

    def test_tiny_resolution_floor(self) -> None:
        """Sub-256px requests floor at the /32 grid minimum WITHOUT ballooning
        to the area ceiling (regression: 64x64 once produced 576x576)."""
        request = GenerationRequest(
            shot_id="X", prompt="p", duration_seconds=2.0,
            fps=24, resolution="64x64",
        )
        width, height = LTXLocalProvider._target_resolution(request)
        self.assertEqual((width, height), (256, 256))
        self.assertLessEqual(width * height, 768 * 432)

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
        """The /blob/main/ form is REQUIRED: diffusers 0.40.0's Hub-link parser
        matches an optional blob/main/ segment but not resolve/main/ (a
        resolve link builds a doubled URL and 404s). Verified against the
        installed diffusers source and the live Hub."""
        self.assertEqual(
            LTX_SINGLE_FILE_URL,
            "https://huggingface.co/Lightricks/LTX-Video/blob/main/"
            "ltxv-2b-0.9.6-distilled-04-25.safetensors",
        )

    def test_dead_repo_id_is_not_used(self) -> None:
        """Regression guard: the old ID does not resolve on Hugging Face."""
        self.assertNotIn("ltxv-2b-0.9.6-distilled", LTX_MODEL_ID.lower())

    def test_provider_uses_single_file_loading(self) -> None:
        """The hosting repo has no diffusers model_index.json; the provider
        must load the 2B checkpoint via from_single_file, not from_pretrained.
        The tiered architecture builds both pipelines through the shared
        ``_tiered_pipeline`` builder (text-encoder-free Phase B)."""
        import inspect

        from automation.video import ltx_provider as module

        tiered_source = inspect.getsource(module.LTXLocalProvider._tiered_pipeline)
        self.assertIn("from_single_file", tiered_source)
        self.assertNotIn("from_pretrained", tiered_source)
        ensure_source = inspect.getsource(module.LTXLocalProvider._ensure_pipeline)
        self.assertIn("LTXConditionPipeline", ensure_source)
        self.assertIn("LTXPipeline", ensure_source)
        module_source = inspect.getsource(module)
        self.assertNotIn("LTXPipeline.from_pretrained", module_source)
        self.assertNotIn("LTXConditionPipeline.from_pretrained", module_source)
        # Phase B must never receive a text encoder into the pipeline.
        self.assertIn("text_encoder=None", tiered_source)

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


class T5EncoderSourceSafetyTest(unittest.TestCase):
    """Phase A download-safety: the 44.54 GB fp32 repo is never loadable.

    The production blocker this guards against: a stale
    ``DEATHBOUND_T5_ENCODER=google/t5-v1_1-xxl`` environment value left over
    from earlier experiments must raise, never start the forbidden download.
    """

    FORBIDDEN = "google/t5-v1_1-xxl"
    SANCTIONED = "city96/t5-v1_1-xxl-encoder-bf16"

    def setUp(self) -> None:
        self._old_encoder = os.environ.pop("DEATHBOUND_T5_ENCODER", None)
        self._old_local = os.environ.pop("DEATHBOUND_T5_LOCAL_PATH", None)

    def tearDown(self) -> None:
        for key, value in (
            ("DEATHBOUND_T5_ENCODER", self._old_encoder),
            ("DEATHBOUND_T5_LOCAL_PATH", self._old_local),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _resolve(self):
        from automation.video.ltx_provider import resolve_t5_encoder_source

        return resolve_t5_encoder_source()

    def test_default_source_is_sanctioned_bf16_encoder(self) -> None:
        self.assertEqual(self._resolve(), self.SANCTIONED)

    def test_sanctioned_encoder_env_override_accepted(self) -> None:
        os.environ["DEATHBOUND_T5_ENCODER"] = self.SANCTIONED
        self.assertEqual(self._resolve(), self.SANCTIONED)

    def test_forbidden_fp32_repo_is_refused(self) -> None:
        os.environ["DEATHBOUND_T5_ENCODER"] = self.FORBIDDEN
        with self.assertRaises(Exception) as ctx:
            self._resolve()
        message = str(ctx.exception)
        self.assertIn("44", message)  # the 44.54 GB fact is named
        self.assertIn(self.SANCTIONED, message)  # the fix is named

    def test_forbidden_repo_with_trailing_slash_refused(self) -> None:
        os.environ["DEATHBOUND_T5_ENCODER"] = self.FORBIDDEN + "/"
        with self.assertRaises(Exception):
            self._resolve()

    def test_forbidden_repo_under_any_prefix_refused(self) -> None:
        os.environ["DEATHBOUND_T5_ENCODER"] = "mirror.example.com/" + self.FORBIDDEN
        with self.assertRaises(Exception):
            self._resolve()

    def test_local_pin_bypasses_env_lookup_without_forbidden_check(self) -> None:
        """A valid local directory pin wins; no network source is consulted."""
        with tempfile.TemporaryDirectory() as td:
            os.environ["DEATHBOUND_T5_LOCAL_PATH"] = td
            self.assertEqual(self._resolve(), td)


class _FakeTorchDevice:
    def __init__(self, spec: str) -> None:
        self.spec = spec


class _FakeTorch:
    """Minimal torch stand-in: `_apply_group_offload` only calls torch.device."""

    @staticmethod
    def device(spec: str) -> _FakeTorchDevice:
        return _FakeTorchDevice(spec)


class _RecordingOffloadPipeline:
    """Records which offload mechanism the provider chooses."""

    def __init__(self, group_error: bool = False, with_group_method: bool = True) -> None:
        self.components = {"transformer": object(), "vae": object()}
        self.calls: list = []
        self._group_error = group_error
        if not with_group_method:
            # Simulate pre-group-offload diffusers (no such method at all).
            self.enable_group_offload = None  # type: ignore[assignment]

    def enable_group_offload(self, **kwargs):  # noqa: ANN003 - test double
        self.calls.append(("group", dict(kwargs)))
        if self._group_error:
            raise ValueError("simulated group offload incompatibility")

    def enable_model_cpu_offload(self) -> None:
        self.calls.append(("model_cpu_offload", {}))

    def to(self, device: str) -> None:
        self.calls.append(("to", device))


class _ExcludePipeline(_RecordingOffloadPipeline):
    """diffusers >= 0.40 shape: enable_group_offload(exclude_modules=...)."""

    def enable_group_offload(self, onload_device, exclude_modules=None, **extra):  # noqa: ANN001
        recorded = dict(extra)
        if exclude_modules is not None:
            recorded["exclude_modules"] = exclude_modules
        self.calls.append(("group", recorded))
        if self._group_error:
            raise ValueError("simulated group offload incompatibility")


class _StrictPipeline(_RecordingOffloadPipeline):
    """Older shape: enable_group_offload without exclude_modules support.

    Group offloading such a pipeline would hook the VAE with the exact
    broken hook, so the provider must refuse the group path entirely.
    """

    def enable_group_offload(self, onload_device, offload_device):  # noqa: ANN001
        self.calls.append(("group", {}))


class LTXVAEDevicePolicyTest(unittest.TestCase):
    """VAE device/offload regression tests (the 4 GB decode fix).

    Root cause verified against diffusers 0.40.0 source: pipeline-level
    ``enable_group_offload`` hooks the VAE, but the hook only fires from
    ``nn.Module.__call__`` while both LTX pipelines call ``vae.decode()``
    directly — leaving decoder weights on CPU against a CUDA latent
    ("Input type (CUDABFloat16Type) and weight type (CPUBFloat16Type)").
    The fix excludes the VAE from group offload (diffusers' own
    ``exclude_modules=["vae"]`` mechanism) so the hook-free VAE is placed
    on CUDA; older diffusers falls back to ``enable_model_cpu_offload``
    whose accelerate hook fires on decode via ``@apply_forward_hook``.
    """

    def setUp(self) -> None:
        from automation.video import ltx_provider as module

        self._module = module
        # GROUP_OFFLOAD_ENABLED / VAE_OFFLOAD_EXCLUDED are import-time module
        # constants (env is only consulted at import), so tests patch the
        # flags directly and restore them afterwards.
        self._saved_flags = (module.GROUP_OFFLOAD_ENABLED, module.VAE_OFFLOAD_EXCLUDED)
        module.GROUP_OFFLOAD_ENABLED = True
        module.VAE_OFFLOAD_EXCLUDED = True

    def tearDown(self) -> None:
        (
            self._module.GROUP_OFFLOAD_ENABLED,
            self._module.VAE_OFFLOAD_EXCLUDED,
        ) = self._saved_flags

    def _offload(self, pipeline):
        import sys
        from automation.video import ltx_provider as module

        provider = module.LTXLocalProvider.__new__(module.LTXLocalProvider)
        fake_torch = _FakeTorch()
        had_torch = "torch" in sys.modules
        real_torch = sys.modules.get("torch")
        sys.modules["torch"] = fake_torch
        try:
            module.LTXLocalProvider._apply_group_offload(provider, pipeline)
        finally:
            if had_torch:
                sys.modules["torch"] = real_torch
            else:
                sys.modules.pop("torch", None)
        return pipeline

    def test_group_offload_excludes_vae(self) -> None:
        """diffusers >= 0.40: VAE excluded, transformer keeps streaming."""
        pipeline = self._offload(_ExcludePipeline())
        mechanisms = [name for name, _ in pipeline.calls]
        self.assertEqual(mechanisms, ["group"])
        kwargs = pipeline.calls[0][1]
        self.assertEqual(kwargs["exclude_modules"], ["vae"])
        self.assertEqual(kwargs["offload_type"], "block_level")

    def test_no_exclude_support_falls_back_to_model_cpu_offload(self) -> None:
        """Older diffusers (enable_group_offload without exclude_modules):
        group offload would hook the VAE with the exact broken hook, so the
        pipeline must NOT be group-offloaded at all — the whole-component
        offloader is the device-safe route."""
        pipeline = _StrictPipeline()
        self._offload(pipeline)
        mechanisms = [name for name, _ in pipeline.calls]
        self.assertEqual(mechanisms, ["model_cpu_offload"])

    def test_group_offload_failure_falls_back_to_model_cpu_offload(self) -> None:
        pipeline = _ExcludePipeline(group_error=True)
        self._offload(pipeline)
        mechanisms = [name for name, _ in pipeline.calls]
        self.assertEqual(mechanisms[0], "group")
        self.assertIn("model_cpu_offload", mechanisms)

    def test_signature_without_exclude_modules_refuses_group_path(self) -> None:
        """Older diffusers whose enable_group_offload lacks exclude_modules
        would hook the VAE with the broken hook — the provider must NOT
        group-offload such a pipeline at all (device-safe fallback only)."""
        pipeline = _StrictPipeline()
        self._offload(pipeline)
        self.assertEqual([name for name, _ in pipeline.calls], ["model_cpu_offload"])

    def test_missing_group_offload_method_uses_model_cpu_offload(self) -> None:
        """Pre-group-offload diffusers: whole-component offloader only."""
        pipeline = _RecordingOffloadPipeline(with_group_method=False)
        self._offload(pipeline)
        self.assertEqual([name for name, _ in pipeline.calls], ["model_cpu_offload"])

    def test_group_offload_disabled_moves_everything_to_cuda(self) -> None:
        """The >12 GB VRAM opt-out (DEATHBOUND_GROUP_OFFLOAD=0 at import) is
        untouched: everything resident on CUDA."""
        self._module.GROUP_OFFLOAD_ENABLED = False
        pipeline = _ExcludePipeline()
        self._offload(pipeline)
        self.assertEqual(pipeline.calls, [("to", "cuda")])

    def test_vae_offload_opt_out_keeps_group_offload_on_transformer(self) -> None:
        """DEATHBOUND_VAE_OFFLOAD=0 (import-time) restores upstream default
        behavior: group offload WITHOUT exclusion (documented as unsafe for
        LTX until upstream fixes decode-hook dispatch, but user-overridable)."""
        self._module.VAE_OFFLOAD_EXCLUDED = False
        pipeline = _ExcludePipeline()
        self._offload(pipeline)
        self.assertEqual([name for name, _ in pipeline.calls], ["group"])
        self.assertIsNone(pipeline.calls[0][1].get("exclude_modules"))

    def test_no_manual_vae_to_calls(self) -> None:
        """The manual `pipeline.vae.to('cuda')` patch is a logged no-op while
        the VAE carries its group hook (ModelMixin.to). The supported fix is
        exclude_modules inside enable_group_offload — the CODE must never
        re-grow a manual VAE .to() call (the docstring MAY document why)."""
        import inspect

        from automation.video import ltx_provider as module

        offload_source = inspect.getsource(module.LTXLocalProvider._apply_group_offload)
        # Strip the docstring so documentation about the forbidden patch
        # cannot trip the guard; only executable code is inspected.
        code_only = offload_source.split('"""', 2)[-1]
        self.assertNotIn(".vae.to(", code_only)
        self.assertNotIn("vae.to(device", code_only)
        module_source = inspect.getsource(module)
        self.assertNotIn("pipeline.vae.to(", module_source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
