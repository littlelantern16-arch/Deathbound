"""Diagnostics honesty tests: t5_encoder_present + run_diagnostics shape.

Guards the Phase A T5-XXL encoder availability scan added alongside the
tiered-memory architecture:
- the pinned DEATHBOUND_T5_LOCAL_PATH directory (config.json + model.safetensors)
- the HF cache snapshot of city96/t5-v1_1-xxl-encoder-bf16 (~9.5 GB bf16)
and refuses to bless the forbidden fp32-sized text_encoder/ pair (19.05 GB)
that belongs to the Lightricks hosting repo.
"""

import os
import tempfile
import unittest
from pathlib import Path


def _sparse(path: Path, size_bytes: int) -> None:
    """Create a size-accurate file without allocating disk (seek + 1 byte)."""
    with open(path, "wb") as handle:
        handle.seek(size_bytes - 1)
        handle.write(b"\0")


class T5EncoderPresentTest(unittest.TestCase):
    """The Phase A encoder scan must honor pins, cache snapshots, and sizes."""

    BF16_BYTES = 9_524_648_592
    FP32_BYTES = 19_050_000_000

    def setUp(self) -> None:
        self._old_local = os.environ.pop("DEATHBOUND_T5_LOCAL_PATH", None)
        self._old_hf_home = os.environ.pop("HF_HOME", None)

    def tearDown(self) -> None:
        for key, value in (
            ("DEATHBOUND_T5_LOCAL_PATH", self._old_local),
            ("HF_HOME", self._old_hf_home),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_pinned_local_path_with_weights_is_present(self) -> None:
        from automation.video.diagnostics import t5_encoder_present

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            _sparse(root / "model.safetensors", self.BF16_BYTES)
            (root / "config.json").write_text("{}", encoding="utf-8")
            os.environ["DEATHBOUND_T5_LOCAL_PATH"] = td
            report = t5_encoder_present()
            self.assertTrue(report["present"])
            self.assertEqual(report["file"], "model.safetensors")
            self.assertGreater(report["size_gb"], 0.0)

    def test_missing_pinned_path_falls_back_to_repo_source(self) -> None:
        from automation.video.diagnostics import t5_encoder_present

        os.environ["DEATHBOUND_T5_LOCAL_PATH"] = str(
            Path(tempfile.gettempdir()) / "deathbound-no-such-t5-dir"
        )
        report = t5_encoder_present()
        self.assertFalse(report["present"])
        # The misconfiguration is surfaced, never raised — diagnostics can't crash.
        self.assertIn("pin_error", report)
        # And the sanctioned city96 repo is named for the fallback.
        self.assertIn("city96/t5-v1_1-xxl-encoder-bf16", report["pin_error"])

    def test_hf_cache_snapshot_detected(self) -> None:
        from automation.video import diagnostics as module

        with tempfile.TemporaryDirectory() as td:
            os.environ["HF_HOME"] = td
            module.HF_CACHE_ENV_VARS = ["HF_HOME"]
            snapshot = (
                Path(td) / "hub" / "models--city96--t5-v1_1-xxl-encoder-bf16"
                / "snapshots" / "abc123"
            )
            snapshot.mkdir(parents=True)
            _sparse(snapshot / "model.safetensors", self.BF16_BYTES)
            (snapshot / "config.json").write_text("{}", encoding="utf-8")
            report = module.t5_encoder_present()
            self.assertTrue(report["present"])
            self.assertIn("model.safetensors", str(report["file"]))

    def test_fp32_sized_text_encoder_pair_rejected(self) -> None:
        """A ~19 GB fp32 pair is the forbidden Lightricks text_encoder/ folder."""
        from automation.video import diagnostics as module

        with tempfile.TemporaryDirectory() as td:
            os.environ["HF_HOME"] = td
            module.HF_CACHE_ENV_VARS = ["HF_HOME"]
            fp32 = Path(td) / "hub" / "fp32-encoder" / "snapshots" / "def456"
            fp32.mkdir(parents=True)
            _sparse(fp32 / "model.safetensors", self.FP32_BYTES)
            (fp32 / "config.json").write_text("{}", encoding="utf-8")
            report = module.t5_encoder_present()
            self.assertFalse(report["present"])

    def test_run_diagnostics_reports_t5_encoder(self) -> None:
        """run_diagnostics exposes the Phase A scan and warns when absent."""
        from automation.video import diagnostics as module

        with tempfile.TemporaryDirectory() as td:
            os.environ["HF_HOME"] = td
            module.HF_CACHE_ENV_VARS = ["HF_HOME"]
            report = module.run_diagnostics(min_disk_gb=0.0)
            self.assertIn("t5_encoder", report)
            self.assertFalse(report["t5_encoder"]["present"])
            warnings = "\n".join(report["warnings"])
            self.assertIn("T5-XXL encoder", warnings)
            self.assertIn("44.54 GB", warnings)  # the forbidden download is named


if __name__ == "__main__":
    unittest.main()
