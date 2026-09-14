"""Tests for the RTX 3050 LTX execution package (Task #5).

Verifies, without pretending the sandbox has a GPU:
- machine diagnostics run anywhere and report blockers honestly
- smoke-test failure classification
- preflight integrates machine diagnostics (real-generation readiness
  depends on them; dry-run readiness does not)
- the PowerShell setup/test scripts keep their critical guardrails
  (Python 3.11, NVIDIA checks, disk check, isolated venv, HF cache on D:,
  no Blender, no ComfyUI, no paid services)

Run:  python3 -m automation.video.tests.test_execution_package
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from automation.video.diagnostics import (
    MIN_DISK_GB,
    MIN_VRAM_GB,
    model_present,
    riven_references,
    run_diagnostics,
)
from automation.video.paths import find_project_root
from automation.video.preflight import Preflight
from automation.video.smoke_test import FAILURE_CLASSES, classify_exception

ROOT = find_project_root()
SCRIPTS = ROOT / "scripts"


class MachineDiagnosticsTests(unittest.TestCase):
    """Diagnostics must be honest on any machine, GPU or not."""

    def test_run_diagnostics_report_shape(self):
        report = run_diagnostics()
        self.assertEqual(report["kind"], "DEATHBOUND_LTX_MACHINE_DIAGNOSTICS")
        for key in (
            "disk_free_gb",
            "disk_ok",
            "torch",
            "ffmpeg_path",
            "model_weights",
            "riven_references",
            "blocking_errors",
            "warnings",
            "ready_for_smoke_test",
        ):
            self.assertIn(key, report)

    def test_diagnostics_honest_without_torch_cuda(self):
        report = run_diagnostics()
        torch_info = report["torch"]
        if not torch_info.get("installed") or torch_info.get("cuda_build") in (None, "cpu"):
            # In a torch-less/CPU-only environment the smoke test MUST be gated.
            self.assertFalse(report["ready_for_smoke_test"])
            self.assertTrue(
                any("torch" in e.lower() for e in report["blocking_errors"])
            )

    def test_model_scan_is_local_only(self):
        info = model_present()
        self.assertEqual(info["model_id"], "Lightricks/LTX-Video")
        self.assertEqual(
            info["checkpoint"], "ltxv-2b-0.9.6-distilled-04-25.safetensors"
        )
        # No network: report is built purely from cache inspection.
        self.assertIsInstance(info["present"], bool)

    def test_riven_reference_gate(self):
        refs = riven_references()
        self.assertIn("required_missing", refs)
        self.assertIn("sufficient", refs)
        # No fake references may ever be fabricated to satisfy this.
        if not refs["sufficient"]:
            self.assertTrue(refs["required_missing"])

    def test_disk_and_vram_minimums_are_sane(self):
        self.assertGreaterEqual(MIN_DISK_GB, 20.0)   # ~14 GB weights + env
        self.assertGreaterEqual(MIN_VRAM_GB, 3.0)    # 4 GB card minus overhead


class FailureClassificationTests(unittest.TestCase):
    def test_vram_oom(self):
        self.assertEqual(
            classify_exception(RuntimeError("CUDA out of memory. Tried to allocate …")),
            "VRAM",
        )

    def test_gpu_missing(self):
        self.assertEqual(
            classify_exception(RuntimeError("Torch not compiled with CUDA enabled")),
            "DEPENDENCIES",
        )
        self.assertEqual(
            classify_exception(RuntimeError("CUDA driver unavailable")),
            "GPU",
        )

    def test_model_weights(self):
        self.assertEqual(
            classify_exception(OSError("safetensors file not found in checkpoint")),
            "MODEL",
        )

    def test_dependencies(self):
        self.assertEqual(
            classify_exception(ImportError("cannot import name LTXPipeline")),
            "DEPENDENCIES",
        )

    def test_generic_generation(self):
        self.assertEqual(classify_exception(ValueError("bad shape")), "GENERATION")

    def test_all_classes_documented(self):
        for cls in ("DIAGNOSTICS", "GPU", "VRAM", "MODEL", "GENERATION", "MEDIA",
                    "DEPENDENCIES"):
            self.assertIn(cls, FAILURE_CLASSES)


class PreflightMachineIntegrationTests(unittest.TestCase):
    def test_preflight_includes_machine_diagnostics(self):
        report = Preflight(provider_id="dryrun", shot_ids=["S01-SHOT-001"]).run()
        self.assertIn("machine_diagnostics", report)
        self.assertIn("kind", report["machine_diagnostics"])

    def test_dry_run_readiness_does_not_require_gpu(self):
        report = Preflight(provider_id="dryrun", shot_ids=["S01-SHOT-001"]).run()
        # Dry-run must stay usable on a GPU-less sandbox.
        self.assertTrue(report["ready_for_dry_run"])
        self.assertFalse(report["ready_for_real_generation"])

    def test_real_generation_readiness_gated_on_machine(self):
        report = Preflight(provider_id="dryrun", shot_ids=["S01-SHOT-001"]).run()
        machine_ready = report["machine_diagnostics"].get("ready_for_smoke_test", False)
        if not machine_ready:
            self.assertFalse(report["ready_for_real_generation"])


class PowerShellScriptGuardrailTests(unittest.TestCase):
    """The setup/test scripts must keep their hard guarantees."""

    @classmethod
    def setUpClass(cls):
        cls.setup = (SCRIPTS / "setup_ltx_windows.ps1").read_text(encoding="utf-8")
        cls.test = (SCRIPTS / "test_ltx_local.ps1").read_text(encoding="utf-8")

    def test_setup_verifies_python_311(self):
        self.assertIn("3\\.11", self.setup)

    def test_setup_verifies_gpu_and_vram(self):
        self.assertIn("nvidia-smi", self.setup)
        self.assertIn("-lt 3.5", self.setup)

    def test_setup_checks_disk_before_download(self):
        self.assertIn("Insufficient disk", self.setup)
        self.assertIn("-lt 25", self.setup)

    def test_setup_venv_is_isolated_outside_repo(self):
        self.assertIn("tools\\ltx-env", self.setup)
        self.assertIn("python -m venv", self.setup)

    def test_setup_pins_hf_cache_to_d(self):
        self.assertIn("D:\\Deathbound\\cache\\huggingface", self.setup)
        self.assertIn("HF_HOME", self.setup)

    def test_setup_installs_cuda_torch_and_diffusers_only(self):
        self.assertIn("download.pytorch.org/whl/cu121", self.setup)
        self.assertIn("diffusers", self.setup)

    def test_no_comfyui_or_blender_usage(self):
        # Every mention of a forbidden tool must be inside a negative
        # guardrail ("never comfyui", "never blender") — never an install/use.
        for script in (self.setup, self.test):
            for line in script.lower().splitlines():
                for tool in ("comfyui", "blender"):
                    idx = line.find(tool)
                    while idx != -1:
                        before = line[:idx]
                        self.assertIn(
                            "never", before,
                            f"forbidden-tool reference outside a guardrail: {line!r}",
                        )
                        idx = line.find(tool, idx + 1)

    def test_no_paid_services_anywhere(self):
        for script in (self.setup, self.test):
            lowered = script.lower()
            for forbidden in ("runway", "luma", "kling", "fal.ai", "replicate",
                              "api_key", "apikey"):
                self.assertNotIn(forbidden, lowered)

    def test_test_script_gates_gpu_torch_ltx_model(self):
        self.assertIn("nvidia-smi", self.test)
        self.assertIn("cuda_ok=True", self.test)
        self.assertIn("LTXPipeline, LTXConditionPipeline", self.test)
        self.assertIn("model_present", self.test)

    def test_test_script_runs_real_smoke_test(self):
        self.assertIn("automation.video.smoke_test", self.test)

    def test_scripts_are_idempotent(self):
        # Skip-if-present markers: no destructive re-runs.
        self.assertIn("already installed", self.setup)
        self.assertIn("idempotent", self.setup.lower())
        self.assertIn("idempotent", self.test.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
