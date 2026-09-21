"""Real media artifact handling: FFmpeg discovery, probing, hashing, frames.

Prepares the pipeline (commit 48e75b0) for real ``.mp4`` clips and ``.png``
final frames without changing any existing interface. Design rules:

- Use the existing FFmpeg installation when available; never hard-code one
  machine-specific path. Discovery order:
      1. ``DEATHBOUND_FFMPEG`` / ``DEATHBOUND_FFPROBE`` env overrides
      2. ``PATH``
      3. ``config/paths.json`` (existing Deathbound config, Windows path)
- Only existing executables are returned; absence is reported, not fatal.
- Atomic writes (temp file + os.replace) for artifacts that must never be
  observed half-written (frames used as next-shot conditioning).
- Simulated behavior stays exclusive to DryRunProvider/tests; real extraction
  is used whenever a real MP4 exists.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .paths import find_project_root, load_json


class MediaError(RuntimeError):
    """Raised when media probing/extraction fails on a real artifact."""


class MediaToolkit:
    """FFmpeg/ffprobe discovery, media validation, hashing, frame extraction."""

    def __init__(self, project_root: Optional[Any] = None) -> None:
        self.project_root = find_project_root(project_root)
        self._ffmpeg: Optional[str] = None
        self._ffprobe: Optional[str] = None

    # ------------------------------------------------------------------
    # Discovery (env override -> PATH -> config/paths.json)
    # ------------------------------------------------------------------

    def _from_paths_json(self, key: str) -> Optional[str]:
        paths_json = self.project_root / "config" / "paths.json"
        if not paths_json.exists():
            return None
        value = load_json(paths_json).get(key)
        if not value:
            return None
        base = Path(value).expanduser()
        candidates = [base]
        if base.suffix == "":
            candidates += [base / "ffmpeg.exe", base / "ffmpeg"]
        for candidate in candidates:
            # paths.json may point at a bin/ directory (the Windows install
            # does); only a real executable FILE is usable — returning the
            # directory would fail at subprocess spawn time.
            if candidate.is_file():
                return str(candidate)
        return None

    def resolve_ffmpeg(self) -> Optional[str]:
        if self._ffmpeg is None:
            self._ffmpeg = (
                os.environ.get("DEATHBOUND_FFMPEG")
                or shutil.which("ffmpeg")
                or self._from_paths_json("ffmpeg")
            )
        return self._ffmpeg

    def resolve_ffprobe(self) -> Optional[str]:
        if self._ffprobe is None:
            env = os.environ.get("DEATHBOUND_FFPROBE")
            if env:
                self._ffprobe = env
            elif shutil.which("ffprobe"):
                self._ffprobe = shutil.which("ffprobe")
            else:
                # Windows FFmpeg builds ship ffprobe next to ffmpeg.
                self._ffprobe = self._probe_next_to(self.resolve_ffmpeg())
        return self._ffprobe

    def _probe_next_to(self, ffmpeg_path: Optional[str]) -> Optional[str]:
        if not ffmpeg_path:
            return None
        base = Path(ffmpeg_path)
        for candidate in (base.parent / "ffprobe.exe", base.parent / "ffprobe"):
            if candidate.exists():
                return str(candidate)
        return None

    # ------------------------------------------------------------------
    # Probing / validation
    # ------------------------------------------------------------------

    def probe(self, path: Any) -> Dict[str, Any]:
        """ffprobe a media file; raises MediaError on corruption/absence."""
        path = Path(path)
        if not path.exists() or path.stat().st_size == 0:
            raise MediaError(f"media file missing or empty: {path}")
        ffprobe = self.resolve_ffprobe()
        if not ffprobe:
            raise MediaError(
                "ffprobe not available; cannot validate real media. "
                "Set DEATHBOUND_FFPROBE or install FFmpeg."
            )
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,duration:format=duration,size",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise MediaError(f"ffprobe failed for {path}: {result.stderr.strip()}")
        data = json.loads(result.stdout)
        stream = (data.get("streams") or [{}])[0]
        duration = stream.get("duration") or data.get("format", {}).get("duration")
        return {
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "width": stream.get("width"),
            "height": stream.get("height"),
            "fps": self._parse_rate(stream.get("r_frame_rate")),
            "duration_seconds": float(duration) if duration else None,
            "corrupted": False,
        }

    @staticmethod
    def _parse_rate(rate: Optional[str]) -> Optional[float]:
        if not rate:
            return None
        try:
            num, _, den = rate.partition("/")
            value = float(num) / (float(den) if den else 1.0)
            return round(value, 3)
        except (ValueError, ZeroDivisionError):
            return None

    def validate_media(
        self,
        path: Any,
        *,
        expect_duration: Optional[float] = None,
        expect_fps: Optional[int] = None,
        expect_resolution: Optional[str] = None,
        tolerance: float = 1.0,
    ) -> Dict[str, Any]:
        """Validate real media against expectations; raises MediaError."""
        info = self.probe(path)
        errors: list = []
        if expect_duration and info["duration_seconds"]:
            if abs(info["duration_seconds"] - expect_duration) > tolerance:
                errors.append(
                    f"duration {info['duration_seconds']}s != expected {expect_duration}s"
                )
        if expect_fps and info["fps"] and round(info["fps"]) != int(expect_fps):
            errors.append(f"fps {info['fps']} != expected {expect_fps}")
        if expect_resolution and info["width"] and info["height"]:
            expected_w, expected_h = (int(x) for x in expect_resolution.lower().split("x"))
            if (info["width"], info["height"]) != (expected_w, expected_h):
                errors.append(
                    f"resolution {info['width']}x{info['height']} != expected {expect_resolution}"
                )
        if errors:
            raise MediaError(
                "media validation failed: " + "; ".join(errors)
            )
        return info

    # ------------------------------------------------------------------
    # Hashing / atomic writes
    # ------------------------------------------------------------------

    @staticmethod
    def sha256_file(path: Any, chunk_size: int = 1 << 20) -> str:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def atomic_write_bytes(path: Any, data: bytes) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
            os.replace(temp_name, path)
        except BaseException:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
            raise

    def atomic_write_json(self, path: Any, payload: Dict[str, Any]) -> None:
        self.atomic_write_bytes(
            path, json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        )

    # ------------------------------------------------------------------
    # Real last-frame extraction
    # ------------------------------------------------------------------

    def extract_last_frame(self, video_path: Any, output_png: Any) -> Dict[str, Any]:
        """Extract the final valid frame of an MP4 to PNG (atomic write).

        Uses the seek-to-end trick: jump 1s before the end (or to 0 for very
        short clips) and take the last decoded frame. Raises MediaError if
        FFmpeg is unavailable or extraction fails.
        """
        video_path, output_png = Path(video_path), Path(output_png)
        info = self.probe(video_path)  # corruption gate
        ffmpeg = self.resolve_ffmpeg()
        if not ffmpeg:
            raise MediaError(
                "FFmpeg not available; cannot extract real final frame. "
                "Set DEATHBOUND_FFMPEG or install FFmpeg."
            )
        duration = info.get("duration_seconds") or 0.0
        output_png.parent.mkdir(parents=True, exist_ok=True)

        # -sseof -1.0 seeks to max(stream_start, end - 1s), so it also covers
        # clips shorter than one second (clamped to the first frame).
        command = [
            ffmpeg,
            "-y",
            "-sseof",
            "-1.0",
            "-i",
            str(video_path),
            "-update",
            "1",
            "-frames:v",
            "1",
            "-q:v",
            "1",
        ]
        fd, temp_name = tempfile.mkstemp(dir=str(output_png.parent), suffix=".png")
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            result = subprocess.run(
                command + [str(temp_path)],
                capture_output=True,
                text=True,
            )
            if result.returncode != 0 or not temp_path.exists() or temp_path.stat().st_size == 0:
                raise MediaError(
                    f"final-frame extraction failed for {video_path}: {result.stderr.strip()[:400]}"
                )
            os.replace(temp_path, output_png)
        finally:
            if temp_path.exists():
                os.unlink(temp_path)

        return {
            "path": str(output_png),
            "sha256": self.sha256_file(output_png),
            "size_bytes": output_png.stat().st_size,
            "source_video": str(video_path),
            "source_duration_seconds": duration,
        }
