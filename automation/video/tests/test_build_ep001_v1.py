"""Regression tests for the EP001 V1 audio/final assembly pipeline.

Root causes covered (the 0.128-second ``EP001_V1.mp4``):

* narration must be a **PCM** WAV — the old renderer wrote AAC into a file
  named ``narration.wav`` (ffprobe: ``codec=aac``), which cannot be decoded;
  ``test_corrupt_aac_wav_is_detected_and_refused`` reproduces exactly that
  container/codec mismatch and asserts the pipeline rejects it.
* lines are placed at the timeline's exact ``start_seconds`` and the rebuilt
  narration is verified sample-window by sample-window.
* the final mux must stream-copy the visual master and preserve its FULL
  duration — ``-shortest`` (the truncation bug) must never appear, and a
  deliberately truncated output must fail validation.
* geometry/codec validation: h264, 1920x1080, valid audio codec, clean decode.

Run:
    python3 -m automation.video.tests.test_build_ep001_v1
    (from the repository root; DEATHBOUND_ROOT is auto-detected)

The full-scale rehearsal (357.331 s 1920x1080 visual + the real EP001
timeline) is opt-in because it takes ~2 minutes:
    DEATHBOUND_EP001_FULL_SCALE=1 python3 -m automation.video.tests.test_build_ep001_v1
"""

from __future__ import annotations

import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT_ROOT))

from automation.video.build_ep001_v1 import (  # noqa: E402
    AssemblyError,
    assemble,
    build_narration,
    build_narration_command,
    build_mux_command,
    decode_errors,
    default_paths,
    load_timeline,
    probe_media,
    resolve_entry_wav,
    resolve_tools,
    validate_output,
)

# Visual master facts asserted by the real EP001 V1 spec.
VISUAL_DURATION = 357.331380
VISUAL_WIDTH = 1920
VISUAL_HEIGHT = 1080
VISUAL_FPS = 24
TIMELINE_DURATION = 165.209978

try:
    FFMPEG, FFPROBE = resolve_tools(PROJECT_ROOT)
    TOOLS_OK = True
except AssemblyError:
    FFMPEG, FFPROBE = "", ""
    TOOLS_OK = False


# ----------------------------------------------------------------------
# Fixtures (real FFmpeg/WAV artifacts — synthetic AV, not fake success)
# ----------------------------------------------------------------------

_TONE_CYCLE: Dict[int, List[int]] = {}


def _tone_samples(seconds: float, freq: int = 440, amp: float = 0.25) -> bytes:
    """PCM s16 mono samples for a sine tone (cached integer cycles)."""
    sr = 48000
    cycle = _TONE_CYCLE.get(freq)
    if cycle is None:
        cycle = [
            int(amp * 32767 * math.sin(2 * math.pi * freq * i / sr))
            for i in range(sr)
        ]
        _TONE_CYCLE[freq] = cycle
    total = int(round(seconds * sr))
    full, rem = divmod(total, sr)
    samples = cycle * full + cycle[:rem]
    return struct.pack(f"<{len(samples)}h", *samples)


def write_wav(path: Path, seconds: float, freq: int = 440) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(48000)
        handle.writeframes(_tone_samples(seconds, freq=freq))
    return path


def write_visual(
    path: Path, seconds: float, size: str = "1920x1080", fps: int = VISUAL_FPS
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"testsrc2=size={size}:rate={fps}",
            "-t",
            f"{seconds}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"fixture encode failed: {result.stderr[-500:]}")
    return path


def write_corrupt_narration(path: Path, seconds: float = 1.0) -> Path:
    """Reproduce the original bug: AAC data in a file named ``*.wav``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            FFMPEG,
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={seconds}",
            "-ar",
            "48000",
            "-ac",
            "1",
            "-c:a",
            "aac",
            "-f",
            "wav",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"corrupt fixture failed: {result.stderr[-500:]}")
    return path


def write_timeline(path: Path, entries: Sequence[Dict[str, Any]]) -> Path:
    payload = {
        "schema_version": "1.0",
        "episode": "EP001",
        "timeline_type": "spoken_audio_sequential_baseline",
        "total_duration_seconds": max(
            float(e["start_seconds"]) + float(e["duration_seconds"])
            for e in entries
        ),
        "entries": list(entries),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def window_rms(path: Path, start: float, end: float) -> float:
    """RMS of the [start, end) window of a PCM WAV, normalised to [-1, 1]."""
    with wave.open(str(path), "rb") as handle:
        sr = handle.getframerate()
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        handle.setpos(int(start * sr))
        frames = handle.readframes(max(0, int((end - start) * sr)))
    if width != 2:
        raise AssertionError(f"expected 16-bit fixture, got {width * 8}-bit")
    count = len(frames) // 2
    if count == 0:
        return 0.0
    samples = struct.unpack(f"<{count}h", frames)
    if channels > 1:  # keep it simple: mix down
        samples = [
            sum(samples[i : i + channels]) / channels
            for i in range(0, len(samples), channels)
        ]
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0


class EP001AssemblyBase(unittest.TestCase):
    """Shared temp workspace + three-line timeline fixture."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ep001_v1_")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.lines = self.root / "lines"
        self.work = self.root / "work"

        self.specs: List[Tuple[str, float, float]] = [
            # (line_id, start_seconds, duration_seconds)
            ("L001", 0.0, 1.0),
            ("L002", 2.0, 1.5),
            ("L003", 5.0, 1.2),
        ]
        self.entries = []
        for line_id, start, duration in self.specs:
            wav = write_wav(self.lines / f"{line_id}.wav", duration)
            self.entries.append(
                {
                    "line_id": line_id,
                    "scene_id": "S01",
                    "speaker": "NARRATOR",
                    "text": f"line {line_id}",
                    "wav": str(wav),
                    "start_seconds": start,
                    "end_seconds": start + duration,
                    "duration_seconds": duration,
                }
            )
        self.timeline = write_timeline(
            self.root / "EP001_AUDIO_TIMELINE.json", self.entries
        )
        self.narration = self.work / "narration.wav"
        self.output = self.root / "EP001_V1.mp4"


@unittest.skipUnless(TOOLS_OK, "ffmpeg/ffprobe not available")
class NarrationBuildTest(EP001AssemblyBase):
    """PCM narration rebuilt from the original WAVs at exact start_seconds."""

    def test_narration_is_pcm_wav_not_aac(self) -> None:
        """Root cause #1: narration must never be AAC-in-.wav again."""
        report = build_narration(
            self.timeline, self.narration, project_root=PROJECT_ROOT
        )
        self.assertTrue(self.narration.is_file())
        self.assertTrue(report["codec"].startswith("pcm_"), report)
        self.assertIn("wav", report["container"])
        self.assertEqual(report["entries"], 3)

        info = probe_media(self.narration, FFPROBE)
        self.assertTrue(info["audio"]["codec_name"].startswith("pcm_"))
        self.assertIn("wav", info["format_name"])

    def test_narration_duration_matches_timeline(self) -> None:
        report = build_narration(
            self.timeline, self.narration, project_root=PROJECT_ROOT
        )
        self.assertAlmostEqual(report["duration_seconds"], 6.2, delta=0.5)

    def test_lines_placed_at_exact_start_seconds(self) -> None:
        build_narration(self.timeline, self.narration, project_root=PROJECT_ROOT)
        # Speech energy present inside every declared line window ...
        for line_id, start, duration in self.specs:
            mid = window_rms(
                self.narration, start + 0.15, start + max(0.4, duration - 0.1)
            )
            self.assertGreater(mid, 0.01, f"{line_id} silent at {start}s")
        # ... and silence in the gaps between them (proves the offsets).
        self.assertLess(window_rms(self.narration, 1.2, 1.9), 0.002)
        self.assertLess(window_rms(self.narration, 3.7, 4.7), 0.002)

    def test_onset_of_third_line_is_within_150ms_of_start(self) -> None:
        build_narration(self.timeline, self.narration, project_root=PROJECT_ROOT)
        before = window_rms(self.narration, 4.5, 4.85)
        onset = window_rms(self.narration, 5.0, 5.3)
        self.assertGreater(onset, 0.01)
        self.assertLess(before, onset / 10)

    def test_overwrites_existing_corrupt_narration(self) -> None:
        """The corrupted narration output is replaced, never consumed."""
        write_corrupt_narration(self.narration, 0.5)
        self.assertEqual(
            probe_media(self.narration, FFPROBE)["audio"]["codec_name"], "aac"
        )
        report = build_narration(
            self.timeline, self.narration, project_root=PROJECT_ROOT
        )
        self.assertTrue(report["codec"].startswith("pcm_"))

    def test_corrupt_aac_wav_is_detected_and_refused(self) -> None:
        """Root cause regression: AAC-in-.wav sources must abort the build."""
        corrupt = write_corrupt_narration(self.lines / "L001.wav", 1.0)
        self.assertEqual(
            probe_media(corrupt, FFPROBE)["audio"]["codec_name"], "aac"
        )
        with self.assertRaises(AssemblyError) as ctx:
            build_narration(self.timeline, self.narration, project_root=PROJECT_ROOT)
        self.assertIn("not a PCM WAV", str(ctx.exception))
        self.assertIn("aac", str(ctx.exception))
        self.assertFalse(self.narration.exists())

    def test_missing_source_wav_reports_line(self) -> None:
        (self.lines / "L002.wav").unlink()
        with self.assertRaises(AssemblyError) as ctx:
            build_narration(self.timeline, self.narration, project_root=PROJECT_ROOT)
        self.assertIn("L002", str(ctx.exception))

    def test_windows_timeline_paths_re_root_to_repo_lines_dir(self) -> None:
        entries = [dict(self.entries[0])]
        entries[0]["wav"] = (
            "D:\\Deathbound\\projects\\EP001\\04_audio\\lines\\L001.wav"
        )
        timeline = write_timeline(self.root / "win_timeline.json", entries)
        report = build_narration(
            timeline,
            self.narration,
            project_root=PROJECT_ROOT,
            lines_dir=self.lines,
        )
        self.assertTrue(report["codec"].startswith("pcm_"))
        self.assertEqual(
            resolve_entry_wav(entries[0], self.lines),
            self.lines / "L001.wav",
        )

    def test_narration_output_cannot_be_used_as_input(self) -> None:
        with self.assertRaises(AssemblyError) as ctx:
            build_narration_command(
                FFMPEG,
                [(self.narration, 0.0)],
                1.0,
                self.narration,
            )
        self.assertIn("refusing to read", str(ctx.exception))

    def test_loudnorm_behaviour_is_preserved(self) -> None:
        report = build_narration(
            self.timeline, self.narration, project_root=PROJECT_ROOT
        )
        self.assertEqual(report["loudnorm"], "loudnorm=I=-16:TP=-1.5:LRA=11")
        # loudnorm is present in the command it produces
        command = build_narration_command(
            FFMPEG,
            [(Path(self.entries[0]["wav"]), 0.0)],
            6.2,
            self.narration,
        )
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", " ".join(command))


class CommandShapeTest(unittest.TestCase):
    """Pure command-construction guards (no FFmpeg required)."""

    def test_narration_command_is_pcm_and_never_shortest(self) -> None:
        sources: List[Tuple[Path, float]] = [
            (Path("/x/L001.wav"), 0.0),
            (Path("/x/L002.wav"), 2.5),
        ]
        command = build_narration_command(
            "ffmpeg", sources, 6.2, Path("/out/narration.wav")
        )
        joined = " ".join(command)
        self.assertEqual(command[command.index("-c:a") + 1], "pcm_s16le")
        self.assertEqual(command[command.index("-f") + 1], "wav")
        self.assertNotIn("aac", joined)
        self.assertNotIn("-shortest", joined)
        self.assertIn("adelay=2500", joined)  # exact start_seconds placement
        self.assertIn("loudnorm=I=-16:TP=-1.5:LRA=11", joined)
        self.assertIn("-filter_complex", command)

    def test_narration_command_honours_disabled_loudnorm(self) -> None:
        command = build_narration_command(
            "ffmpeg",
            [(Path("/x/L001.wav"), 0.0)],
            1.0,
            Path("/out/n.wav"),
            loudnorm=None,
        )
        self.assertNotIn("loudnorm", " ".join(command))

    def test_mux_command_copies_video_and_avoids_shortest(self) -> None:
        command = build_mux_command(
            "ffmpeg",
            Path("/in/visual.mp4"),
            Path("/in/narration.wav"),
            Path("/out/EP001_V1.mp4"),
            VISUAL_DURATION,
        )
        self.assertEqual(command[command.index("-c:v") + 1], "copy")
        self.assertNotIn("-shortest", command)  # truncation root cause
        self.assertEqual(command[command.index("-t") + 1], f"{VISUAL_DURATION:.6f}")
        self.assertIn("apad", command[command.index("-af") + 1])
        self.assertEqual(command[command.index("-movflags") + 1], "+faststart")
        self.assertEqual(command[command.index("-map") + 1], "0:v:0")


class TimelineValidationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="ep001_tl_")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def test_load_timeline_requires_json_import_path(self) -> None:
        """The timeline really is JSON (the old script forgot ``import json``)."""
        path = self.root / "t.json"
        path.write_text(
            json.dumps({"total_duration_seconds": 1.0, "entries": [
                {"wav": "a.wav", "start_seconds": 0.0, "duration_seconds": 1.0}
            ]}),
            encoding="utf-8",
        )
        data = load_timeline(path)
        self.assertEqual(data["entries"][0]["start_seconds"], 0.0)

    def test_missing_start_seconds_rejected(self) -> None:
        path = self.root / "bad.json"
        path.write_text(
            json.dumps({"entries": [{"wav": "a.wav", "duration_seconds": 1.0}]}),
            encoding="utf-8",
        )
        with self.assertRaises(AssemblyError) as ctx:
            load_timeline(path)
        self.assertIn("start_seconds", str(ctx.exception))

    def test_empty_entries_rejected(self) -> None:
        path = self.root / "empty.json"
        path.write_text(json.dumps({"entries": []}), encoding="utf-8")
        with self.assertRaises(AssemblyError):
            load_timeline(path)

    def test_broken_json_rejected_with_clear_error(self) -> None:
        path = self.root / "broken.json"
        path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(AssemblyError) as ctx:
            load_timeline(path)
        self.assertIn("not valid JSON", str(ctx.exception))


@unittest.skipUnless(TOOLS_OK, "ffmpeg/ffprobe not available")
class AssemblyAndValidationTest(EP001AssemblyBase):
    """Full mux + post-assembly validation against a real 1920x1080 master."""

    def setUp(self) -> None:
        super().setUp()
        self.visual = write_visual(self.root / "EP001_visual_v1.mp4", 8.0)
        build_narration(self.timeline, self.narration, project_root=PROJECT_ROOT)
        self.assembly = assemble(
            self.visual, self.narration, self.output, project_root=PROJECT_ROOT
        )

    def test_output_keeps_full_visual_duration(self) -> None:
        info = probe_media(self.output, FFPROBE)
        self.assertAlmostEqual(info["format_duration_seconds"], 8.0, delta=0.3)
        # audio padded with silence instead of truncating the video
        self.assertAlmostEqual(
            info["audio"]["duration_seconds"], 8.0, delta=0.3
        )

    def test_video_stream_is_copied_not_reencoded(self) -> None:
        source = probe_media(self.visual, FFPROBE)
        output = probe_media(self.output, FFPROBE)
        self.assertEqual(source["video"]["nb_frames"], output["video"]["nb_frames"])
        self.assertEqual(output["video"]["codec_name"], "h264")

    def test_validation_passes_on_good_output(self) -> None:
        report = validate_output(
            self.output, expect_duration=8.0, project_root=PROJECT_ROOT
        )
        self.assertTrue(report["valid"])
        self.assertEqual(report["failed_checks"], [])
        self.assertEqual(report["audio"]["codec_name"], "aac")

    def test_validation_rejects_truncated_output(self) -> None:
        """Root cause #2: a -shortest-style truncation must fail loudly."""
        truncated = self.root / "truncated.mp4"
        subprocess.run(
            [
                FFMPEG, "-y", "-v", "error", "-i", str(self.output),
                "-c", "copy", "-t", "1.5", str(truncated),
            ],
            check=True,
            capture_output=True,
        )
        with self.assertRaises(AssemblyError) as ctx:
            validate_output(
                truncated, expect_duration=8.0, project_root=PROJECT_ROOT
            )
        self.assertIn("duration_preserves_visual_timeline", str(ctx.exception))

    def test_validation_rejects_wrong_resolution(self) -> None:
        small = write_visual(self.root / "small.mp4", 3.0, size="640x360")
        with self.assertRaises(AssemblyError) as ctx:
            validate_output(
                small,
                expect_duration=3.0,
                expect_width=VISUAL_WIDTH,
                expect_height=VISUAL_HEIGHT,
                project_root=PROJECT_ROOT,
            )
        self.assertIn("resolution_1920x1080", str(ctx.exception))

    def test_validation_rejects_missing_audio(self) -> None:
        silent = self.root / "silent.mp4"
        subprocess.run(
            [
                FFMPEG, "-y", "-v", "error", "-i", str(self.visual),
                "-c", "copy", "-an", str(silent),
            ],
            check=True,
            capture_output=True,
        )
        with self.assertRaises(AssemblyError) as ctx:
            validate_output(
                silent, expect_duration=8.0, project_root=PROJECT_ROOT
            )
        self.assertIn("audio_codec_valid", str(ctx.exception))

    def test_assemble_refuses_corrupt_narration_input(self) -> None:
        corrupt = write_corrupt_narration(self.root / "bad_narration.wav", 1.0)
        with self.assertRaises(AssemblyError) as ctx:
            assemble(
                self.visual, corrupt, self.root / "out.mp4", project_root=PROJECT_ROOT
            )
        self.assertIn("not a PCM WAV", str(ctx.exception))

    def test_output_decodes_cleanly(self) -> None:
        self.assertEqual(decode_errors(FFMPEG, self.output), [])


@unittest.skipUnless(TOOLS_OK, "ffmpeg/ffprobe not available")
class EP001SpecFactsTest(unittest.TestCase):
    """Guard the real episode facts the assembly must honour."""

    def test_committed_timeline_matches_spec_durations(self) -> None:
        paths = default_paths(PROJECT_ROOT)
        timeline = load_timeline(paths["timeline"])
        self.assertAlmostEqual(
            float(timeline["total_duration_seconds"]),
            TIMELINE_DURATION,
            delta=0.001,
        )
        entries = timeline["entries"]
        self.assertEqual(len(entries), 75)
        # exact, gapless, sequential placement
        previous_end = 0.0
        for entry in entries:
            self.assertAlmostEqual(
                float(entry["start_seconds"]), previous_end, delta=1e-6
            )
            self.assertGreater(float(entry["duration_seconds"]), 0)
            self.assertTrue(str(entry["wav"]).lower().endswith(".wav"))
            previous_end = float(entry["end_seconds"])
        self.assertAlmostEqual(previous_end, TIMELINE_DURATION, delta=0.001)

    def test_default_paths_target_ep001_v1_output(self) -> None:
        paths = default_paths(PROJECT_ROOT)
        self.assertEqual(paths["output"].name, "EP001_V1.mp4")
        self.assertEqual(paths["output"].parent.name, "08_output")
        self.assertEqual(paths["visual"].name, "EP001_visual_v1.mp4")
        self.assertEqual(paths["narration"].name, "narration.wav")
        self.assertEqual(paths["narration"].parent.name, "_v1_work")


@unittest.skipUnless(
    TOOLS_OK and os.environ.get("DEATHBOUND_EP001_FULL_SCALE") == "1",
    "set DEATHBOUND_EP001_FULL_SCALE=1 to run the full-scale rehearsal",
)
class FullScaleRehearsalTest(unittest.TestCase):
    """357.331 s 1920x1080 visual + the real 165.210 s EP001 timeline.

    Uses the committed timeline's exact start/end/duration values with
    synthesized stand-in line audio (the rendered assets stay on the
    workstation), and asserts the assembled file preserves the full visual
    timeline with a clean-decoding AAC track.
    """

    def test_full_scale_assembly(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ep001_full_") as tmp:
            root = Path(tmp)
            paths = default_paths(PROJECT_ROOT)
            timeline = load_timeline(paths["timeline"])

            entries = []
            for index, entry in enumerate(timeline["entries"]):
                duration = float(entry["duration_seconds"])
                wav = write_wav(
                    root / "lines" / f"L{index:03d}.wav",
                    duration,
                    freq=330 + (index % 5) * 55,
                )
                entries.append({**entry, "wav": str(wav)})
            scaled = write_timeline(root / "timeline.json", entries)

            visual = write_visual(root / "EP001_visual_v1.mp4", VISUAL_DURATION)
            narration = root / "narration.wav"
            output = root / "EP001_V1.mp4"

            narration_report = build_narration(
                scaled, narration, project_root=PROJECT_ROOT
            )
            self.assertAlmostEqual(
                narration_report["duration_seconds"],
                TIMELINE_DURATION,
                delta=1.0,
            )
            self.assertTrue(narration_report["codec"].startswith("pcm_"))

            assembly = assemble(
                visual, narration, output, project_root=PROJECT_ROOT
            )
            self.assertAlmostEqual(
                assembly["visual_duration_seconds"], VISUAL_DURATION, delta=0.01
            )

            validation = validate_output(
                output,
                expect_duration=VISUAL_DURATION,
                expect_width=VISUAL_WIDTH,
                expect_height=VISUAL_HEIGHT,
                project_root=PROJECT_ROOT,
            )
            self.assertTrue(validation["valid"], validation)
            self.assertAlmostEqual(
                validation["duration_seconds"], VISUAL_DURATION, delta=0.5
            )
            self.assertEqual(validation["video"]["codec_name"], "h264")
            self.assertEqual(
                (validation["video"]["width"], validation["video"]["height"]),
                (VISUAL_WIDTH, VISUAL_HEIGHT),
            )
            self.assertEqual(validation["audio"]["codec_name"], "aac")
            self.assertAlmostEqual(
                validation["audio"]["duration_seconds"],
                VISUAL_DURATION,
                delta=0.5,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
