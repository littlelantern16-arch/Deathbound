"""EP001 V1 final assembly: narration rebuild + full-length mux + validation.

Assembles ``projects/EP001/08_output/EP001_V1.mp4`` from the already-rendered
visual master and the ORIGINAL per-line WAV assets. This module replaces the
broken assembly path; nothing is regenerated visually, nothing is simulated.

Root cause of the 0.128-second ``EP001_V1.mp4``
------------------------------------------------
The previous assembly script had three defects:

1. It rendered the narration track with FFmpeg's **AAC** encoder while naming
   the file ``narration.wav``. FFmpeg happily writes AAC into whatever
   container/extension you force, so the "WAV" was really AAC-in-WAV: ffprobe
   reports ``codec=aac`` and decoding it emits a wall of AAC errors.
2. It then muxed with ``-shortest``, so the 357.331-second visual master was
   truncated to the length of that broken narration track (0.128 s).
3. It called ``json.load`` on the audio timeline without ``import json``
   (``NameError``), which is why the audio stage could never be rerun cleanly.

Fix implemented here
--------------------
* Narration is rebuilt from scratch out of the original line WAVs referenced
  by ``projects/EP001/04_audio/EP001_AUDIO_TIMELINE.json``, each placed at its
  exact ``start_seconds`` (sample-accurate via ``adelay``), mixed, then
  loudness-normalised (``LOUDNORM_FILTER``, preserved from the previous
  behaviour) and written as a real **PCM** WAV (``-c:a pcm_s16le -f wav``).
  The corrupted ``narration.wav`` is never read: it is overwritten as PCM, and
  every source file is probe-checked to be PCM before it is used.
* The final mux stream-copies the visual master (``-c:v copy``), encodes the
  narration to AAC in the MP4, pads the audio with silence to the full visual
  duration (``-af apad -t <visual duration>``) and deliberately does **not**
  use ``-shortest``, so the complete 357.331-second timeline is preserved.
* After assembly the output is validated: h264, 1920x1080, duration ≈ visual
  master duration, a valid audio codec covering the full length, and a full
  decode pass that must report zero errors (no AAC corruption).

Usage (on the workstation or anywhere the repo + FFmpeg exist)::

    python -m automation.video.build_ep001_v1

Exit code 0 = assembled and validated; 1 = failure (nothing is faked).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .media import MediaToolkit
from .paths import find_project_root, load_json
from .qa import aggregate, check

EPISODE = "EP001"

# Loudness target used for the narration bus (EBU R128 / YouTube delivery).
# Preserved from the previous assembly behaviour; override with --loudnorm.
LOUDNORM_FILTER = "loudnorm=I=-16:TP=-1.5:LRA=11"

SAMPLE_RATE = 48000
CHANNELS = 2
PCM_CODEC = "pcm_s16le"
AAC_BITRATE = "192k"

EXPECTED_VIDEO_CODEC = "h264"
EXPECTED_AUDIO_CODEC = "aac"
EXPECTED_WIDTH = 1920
EXPECTED_HEIGHT = 1080

# Tolerances (seconds) for duration validation.
DURATION_TOLERANCE = 0.5
# A source WAV whose real length exceeds the timeline's declared length by
# more than this is a wrong/mismatched asset and must stop the assembly.
SOURCE_DRIFT_LIMIT = 0.5

# Deliberately never used anywhere in this module: -shortest
# (it truncated the 357.331 s master to the broken 0.128 s narration).


class AssemblyError(RuntimeError):
    """Raised when narration build, mux, or output validation fails."""


# ----------------------------------------------------------------------
# Paths / tool discovery
# ----------------------------------------------------------------------


def default_paths(project_root: Path) -> Dict[str, Path]:
    """Canonical EP001 V1 assembly paths inside the repository."""
    episode_root = Path(project_root) / "projects" / EPISODE
    work = episode_root / "08_output" / "_v1_work"
    return {
        "episode_root": episode_root,
        "timeline": episode_root / "04_audio" / f"{EPISODE}_AUDIO_TIMELINE.json",
        "lines_dir": episode_root / "04_audio" / "lines",
        "work": work,
        "visual": work / f"{EPISODE}_visual_v1.mp4",
        "narration": work / "narration.wav",
        "output": episode_root / "08_output" / f"{EPISODE}_V1.mp4",
    }


def _repo_local_tool(project_root: Path, name: str) -> Optional[str]:
    """FFmpeg tools bundled in the repository (tools/ffmpeg[/bin])."""
    folders = [
        Path(project_root) / "tools" / "ffmpeg",
        Path(project_root) / "tools" / "ffmpeg" / "bin",
    ]
    for folder in folders:
        for candidate in (folder / name, folder / f"{name}.exe"):
            if candidate.is_file():
                return str(candidate)
    return None


def resolve_tools(project_root: Path) -> Tuple[str, str]:
    """Resolve ffmpeg/ffprobe: env override -> PATH -> config -> tools/."""
    toolkit = MediaToolkit(project_root)
    ffmpeg = toolkit.resolve_ffmpeg()
    ffprobe = toolkit.resolve_ffprobe()
    if not ffmpeg:
        ffmpeg = _repo_local_tool(project_root, "ffmpeg")
    if not ffprobe:
        ffprobe = _repo_local_tool(project_root, "ffprobe")
    if not ffprobe and ffmpeg:
        base = Path(ffmpeg)
        for candidate in (base.parent / "ffprobe", base.parent / "ffprobe.exe"):
            if candidate.is_file():
                ffprobe = str(candidate)
                break
    if not ffmpeg or not ffprobe:
        raise AssemblyError(
            "FFmpeg/ffprobe not available. Set DEATHBOUND_FFMPEG and "
            "DEATHBOUND_FFPROBE, install FFmpeg, or place the binaries in "
            "tools/ffmpeg."
        )
    return ffmpeg, ffprobe


def _run(command: Sequence[str], label: str) -> subprocess.CompletedProcess:
    result = subprocess.run(list(command), capture_output=True, text=True)
    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise AssemblyError(
            f"{label} failed (exit {result.returncode}): "
            f"{stderr[-1500:] or 'no stderr output'}"
        )
    return result


# ----------------------------------------------------------------------
# Probing
# ----------------------------------------------------------------------


def probe_media(path: Any, ffprobe: str) -> Dict[str, Any]:
    """Probe a media file into ``{"video", "audio", "format"}`` dicts."""
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise AssemblyError(f"media file missing or empty: {path}")
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        (
            "stream=index,codec_type,codec_name,width,height,duration,"
            "nb_frames,sample_rate,channels:format=duration,format_name"
        ),
        "-of",
        "json",
        str(path),
    ]
    result = _run(command, f"ffprobe {path.name}")
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise AssemblyError(f"unparseable ffprobe output for {path}: {exc}")
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    duration = fmt.get("duration")

    def _stream(kind: str) -> Optional[Dict[str, Any]]:
        found = next(
            (s for s in streams if s.get("codec_type") == kind), None
        )
        if not found:
            return None
        return {
            "codec_name": found.get("codec_name"),
            "duration_seconds": float(found["duration"])
            if found.get("duration")
            else (float(duration) if duration else None),
            "width": found.get("width"),
            "height": found.get("height"),
            "nb_frames": int(found["nb_frames"]) if found.get("nb_frames") else None,
            "sample_rate": found.get("sample_rate"),
            "channels": found.get("channels"),
        }

    return {
        "path": str(path),
        "video": _stream("video"),
        "audio": _stream("audio"),
        "format_duration_seconds": float(duration) if duration else None,
        "format_name": fmt.get("format_name"),
    }


def decode_errors(ffmpeg: str, path: Any) -> List[str]:
    """Full decode pass; returns the error lines (empty == clean playback)."""
    result = subprocess.run(
        [ffmpeg, "-v", "error", "-i", str(path), "-f", "null", "-"],
        capture_output=True,
        text=True,
    )
    lines = [ln for ln in (result.stderr or "").splitlines() if ln.strip()]
    if result.returncode != 0:
        lines.append(f"ffmpeg decode exited {result.returncode}")
    return lines


# ----------------------------------------------------------------------
# Timeline
# ----------------------------------------------------------------------


def load_timeline(path: Any) -> Dict[str, Any]:
    """Load + structurally validate ``EP001_AUDIO_TIMELINE.json``."""
    path = Path(path)
    if not path.is_file():
        raise AssemblyError(f"audio timeline not found: {path}")
    try:
        data = load_json(path)  # local import-free helper (BOM tolerant)
    except json.JSONDecodeError as exc:
        raise AssemblyError(f"audio timeline is not valid JSON: {path}: {exc}")
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, list) or not entries:
        raise AssemblyError(f"audio timeline has no entries: {path}")
    for index, entry in enumerate(entries):
        for key in ("wav", "start_seconds", "duration_seconds"):
            if key not in entry:
                raise AssemblyError(
                    f"timeline entry #{index} is missing '{key}': {path}"
                )
        try:
            start = float(entry["start_seconds"])
            duration = float(entry["duration_seconds"])
        except (TypeError, ValueError):
            raise AssemblyError(
                f"timeline entry #{index} has non-numeric timing: {path}"
            )
        if start < 0 or duration <= 0:
            raise AssemblyError(
                f"timeline entry #{index} has invalid timing "
                f"(start={start}, duration={duration}): {path}"
            )
    return data


def _wav_filename(raw: str) -> str:
    return str(raw).replace("\\", "/").rsplit("/", 1)[-1]


def _same_path(left: Any, right: Any) -> bool:
    try:
        return str(Path(left).resolve()).lower() == str(
            Path(right).resolve()
        ).lower()
    except OSError:  # pragma: no cover - defensive
        return str(left).lower() == str(right).lower()


def resolve_entry_wav(entry: Dict[str, Any], lines_dir: Path) -> Path:
    """Resolve a timeline entry's WAV on this machine.

    The committed timeline stores absolute Windows paths (``D:\\Deathbound\\
    ...``); on a workstation checkout those resolve directly, and when the
    repository lives elsewhere the file is re-rooted under the episode's
    ``04_audio/lines`` directory by file name.
    """
    raw = str(entry.get("wav") or "")
    if not raw:
        raise AssemblyError(f"timeline entry has no wav path: {entry}")
    candidates = [Path(raw), Path(lines_dir) / _wav_filename(raw)]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise AssemblyError(
        "narration source WAV not found for line "
        f"{entry.get('line_id', '?')}: looked for {candidates[0]} and {candidates[1]}"
    )


# ----------------------------------------------------------------------
# Narration build
# ----------------------------------------------------------------------


def build_narration_command(
    ffmpeg: str,
    sources: Sequence[Tuple[Path, float]],
    total_seconds: float,
    output: Path,
    loudnorm: Optional[str] = LOUDNORM_FILTER,
) -> List[str]:
    """FFmpeg command that lays every source line on the timeline.

    ``sources`` is ``[(wav_path, start_seconds), ...]``. Output is a PCM WAV
    (never AAC), sized ``total_seconds`` — no ``-shortest`` anywhere.
    """
    if not sources:
        raise AssemblyError("no narration sources to mix")
    output = Path(output)
    for source, _start in sources:
        if _same_path(source, output):
            raise AssemblyError(
                f"refusing to read the narration output as an input: {output}"
            )

    parts: List[str] = []
    labels: List[str] = []
    for index, (_source, start) in enumerate(sources):
        delay_ms = int(round(float(start) * 1000))
        parts.append(
            f"[{index}:a]aresample={SAMPLE_RATE},"
            "aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"adelay={delay_ms}:all=1[a{index}]"
        )
        labels.append(f"[a{index}]")
    mixed = (
        "".join(labels)
        + f"amix=inputs={len(sources)}:normalize=0:dropout_transition=0[m]"
    )
    tail = (
        "[m]"
        + (f"{loudnorm}," if loudnorm else "")
        + f"aresample={SAMPLE_RATE},"
        f"aformat=sample_fmts=s16:channel_layouts=stereo[out]"
    )
    filter_complex = ";".join(parts) + ";" + mixed + ";" + tail

    command: List[str] = [ffmpeg, "-y", "-v", "error"]
    for source, _start in sources:
        command += ["-i", str(source)]
    command += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[out]",
        "-t",
        f"{float(total_seconds):.6f}",
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-c:a",
        PCM_CODEC,
        "-f",
        "wav",
        str(output),
    ]
    return command


def assert_pcm_wav(path: Any, ffprobe: str) -> Dict[str, Any]:
    """Fail unless ``path`` is a genuine PCM WAV (guards the AAC-in-.wav bug)."""
    path = Path(path)
    info = probe_media(path, ffprobe)
    audio = info.get("audio")
    if not audio:
        raise AssemblyError(f"no audio stream in {path}")
    codec = audio.get("codec_name") or ""
    if not codec.startswith("pcm_"):
        raise AssemblyError(
            f"{path} is not a PCM WAV (codec={codec or 'unknown'}). "
            "Refusing to use a corrupt/encoded file as narration."
        )
    return info


def build_narration(
    timeline_path: Any,
    output_path: Any,
    *,
    project_root: Any = None,
    lines_dir: Any = None,
    loudnorm: Optional[str] = LOUDNORM_FILTER,
) -> Dict[str, Any]:
    """Rebuild the narration track from the ORIGINAL line WAVs.

    Each line is placed at its exact ``start_seconds`` from the timeline. The
    output is a PCM WAV; any existing file at ``output_path`` (including the
    previously corrupted AAC-in-``.wav`` narration) is overwritten, never read.
    """
    root = find_project_root(project_root)
    paths = default_paths(root)
    timeline_path = Path(timeline_path)
    output_path = Path(output_path)
    lines_dir = Path(lines_dir) if lines_dir else paths["lines_dir"]
    ffmpeg, ffprobe = resolve_tools(root)

    timeline = load_timeline(timeline_path)
    entries = timeline["entries"]

    sources: List[Tuple[Path, float]] = []
    max_drift = 0.0
    max_end = 0.0
    for index, entry in enumerate(entries):
        wav = resolve_entry_wav(entry, lines_dir)
        if _same_path(wav, output_path):
            raise AssemblyError(
                f"timeline entry #{index} points at the narration output "
                f"itself ({wav}); refusing to consume the corrupted narration."
            )
        info = probe_media(wav, ffprobe)
        audio = info.get("audio")
        if not audio:
            raise AssemblyError(
                f"narration source has no audio stream (corrupt?): {wav}"
            )
        codec = audio.get("codec_name") or ""
        if not codec.startswith("pcm_"):
            raise AssemblyError(
                f"narration source is not a PCM WAV (codec={codec or 'unknown'}): "
                f"{wav}. The original line WAVs must be PCM; refusing to build "
                "narration from a corrupt/encoded file."
            )
        start = float(entry["start_seconds"])
        declared = float(entry["duration_seconds"])
        actual = audio.get("duration_seconds") or declared
        if actual - declared > SOURCE_DRIFT_LIMIT:
            raise AssemblyError(
                f"narration source is {actual:.3f}s but the timeline declares "
                f"{declared:.3f}s (mismatched asset): {wav}"
            )
        max_drift = max(max_drift, abs(actual - declared))
        max_end = max(max_end, start + declared, start + actual)
        sources.append((wav, start))

    declared_total = float(timeline.get("total_duration_seconds") or 0.0)
    total_seconds = max(declared_total, max_end)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_narration_command(
        ffmpeg, sources, total_seconds, output_path, loudnorm=loudnorm
    )
    _run(command, "narration build")

    built = assert_pcm_wav(output_path, ffprobe)
    built_duration = built["audio"]["duration_seconds"] or 0.0
    if abs(built_duration - total_seconds) > DURATION_TOLERANCE:
        raise AssemblyError(
            f"narration duration {built_duration:.3f}s != expected "
            f"{total_seconds:.3f}s"
        )

    return {
        "path": str(output_path),
        "timeline": str(timeline_path),
        "entries": len(sources),
        "codec": built["audio"]["codec_name"],
        "container": built["format_name"],
        "duration_seconds": round(built_duration, 6),
        "target_seconds": round(total_seconds, 6),
        "loudnorm": loudnorm,
        "max_source_drift_seconds": round(max_drift, 6),
    }


# ----------------------------------------------------------------------
# Final mux
# ----------------------------------------------------------------------


def build_mux_command(
    ffmpeg: str,
    visual: Any,
    narration: Any,
    output: Any,
    video_duration: float,
) -> List[str]:
    """Stream-copy the visual master and pad narration to its full length.

    No ``-shortest``: the audio is extended with silence (``apad``) and cut at
    the *visual* duration, so the whole visual timeline survives.
    """
    return [
        ffmpeg,
        "-y",
        "-v",
        "error",
        "-i",
        str(visual),
        "-i",
        str(narration),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        AAC_BITRATE,
        "-ar",
        str(SAMPLE_RATE),
        "-ac",
        str(CHANNELS),
        "-af",
        "apad",
        "-t",
        f"{float(video_duration):.6f}",
        "-movflags",
        "+faststart",
        str(output),
    ]


def assemble(
    visual_path: Any,
    narration_path: Any,
    output_path: Any,
    *,
    project_root: Any = None,
) -> Dict[str, Any]:
    """Mux the visual master + PCM narration into ``EP001_V1.mp4``."""
    root = find_project_root(project_root)
    ffmpeg, ffprobe = resolve_tools(root)
    visual_path = Path(visual_path)
    narration_path = Path(narration_path)
    output_path = Path(output_path)

    if not visual_path.is_file():
        raise AssemblyError(f"visual master not found: {visual_path}")
    # Never consume a corrupt narration track (the AAC-in-.wav failure mode).
    assert_pcm_wav(narration_path, ffprobe)

    visual = probe_media(visual_path, ffprobe)
    if not visual.get("video"):
        raise AssemblyError(f"visual master has no video stream: {visual_path}")
    video_duration = (
        visual["video"].get("duration_seconds")
        or visual.get("format_duration_seconds")
    )
    if not video_duration:
        raise AssemblyError(f"could not determine visual duration: {visual_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = build_mux_command(
        ffmpeg, visual_path, narration_path, output_path, video_duration
    )
    _run(command, "final mux")

    return {
        "output": str(output_path),
        "visual": str(visual_path),
        "visual_duration_seconds": round(float(video_duration), 6),
        "narration": str(narration_path),
        "video_codec": visual["video"].get("codec_name"),
        "resolution": f"{visual['video'].get('width')}x{visual['video'].get('height')}",
        "mux_command": command,
    }


# ----------------------------------------------------------------------
# Post-assembly validation
# ----------------------------------------------------------------------


def validate_output(
    output_path: Any,
    *,
    expect_duration: float,
    expect_width: int = EXPECTED_WIDTH,
    expect_height: int = EXPECTED_HEIGHT,
    expect_video_codec: str = EXPECTED_VIDEO_CODEC,
    expect_audio_codec: str = EXPECTED_AUDIO_CODEC,
    tolerance: float = DURATION_TOLERANCE,
    project_root: Any = None,
    ffmpeg: Optional[str] = None,
    ffprobe: Optional[str] = None,
) -> Dict[str, Any]:
    """Validate the assembled MP4: codec, geometry, duration, clean decode."""
    root = find_project_root(project_root)
    if not (ffmpeg and ffprobe):
        ffmpeg, ffprobe = resolve_tools(root)
    output_path = Path(output_path)

    info = probe_media(output_path, ffprobe)
    video = info.get("video")
    audio = info.get("audio")
    duration = info.get("format_duration_seconds")

    results = []
    results.append(
        check(
            "video_codec_h264",
            bool(video) and video.get("codec_name") == expect_video_codec,
            f"codec={video.get('codec_name') if video else None}",
        )
    )
    results.append(
        check(
            "resolution_1920x1080",
            bool(video)
            and video.get("width") == expect_width
            and video.get("height") == expect_height,
            f"{video.get('width')}x{video.get('height')}" if video else "no video",
        )
    )
    results.append(
        check(
            "duration_preserves_visual_timeline",
            duration is not None and abs(duration - expect_duration) <= tolerance,
            f"duration={duration} expected={expect_duration} "
            f"+/-{tolerance}s",
        )
    )
    results.append(
        check(
            "audio_codec_valid",
            bool(audio) and audio.get("codec_name") == expect_audio_codec,
            f"codec={audio.get('codec_name') if audio else None}",
        )
    )
    audio_duration = audio.get("duration_seconds") if audio else None
    results.append(
        check(
            "audio_covers_full_timeline",
            audio_duration is not None
            and audio_duration >= expect_duration - tolerance,
            f"audio_duration={audio_duration} expected>={expect_duration - tolerance}",
        )
    )
    decode_problems = decode_errors(ffmpeg, output_path)
    results.append(
        check(
            "decodes_without_errors",
            not decode_problems,
            "; ".join(decode_problems[:5]),
        )
    )

    report = aggregate(results)
    report.update(
        {
            "output": str(output_path),
            "duration_seconds": duration,
            "expected_duration_seconds": expect_duration,
            "video": video,
            "audio": audio,
            "decode_error_lines": decode_problems[:20],
        }
    )
    if not report["valid"]:
        raise AssemblyError(
            "EP001_V1.mp4 validation failed: "
            + "; ".join(
                f"{r['check']} ({r['detail']})" for r in report["checks"]
                if r["status"] != "pass"
            )
        )
    return report


# ----------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m automation.video.build_ep001_v1",
        description=(
            "Rebuild EP001 narration from the original WAVs, mux it onto the "
            "full-length visual master, and validate EP001_V1.mp4."
        ),
    )
    parser.add_argument("--root", help="Deathbound repository root")
    parser.add_argument("--timeline", help="EP001_AUDIO_TIMELINE.json path")
    parser.add_argument("--visual", help="EP001_visual_v1.mp4 path")
    parser.add_argument("--narration", help="narration WAV output path (PCM)")
    parser.add_argument("--output", help="EP001_V1.mp4 output path")
    parser.add_argument(
        "--loudnorm",
        default=LOUDNORM_FILTER,
        help=f"loudnorm filter (default: {LOUDNORM_FILTER}; 'none' to disable)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate an already-assembled output without rebuilding",
    )
    parser.add_argument(
        "--expected-duration",
        type=float,
        help="expected duration for --validate-only (else visual duration)",
    )
    args = parser.parse_args(argv)

    try:
        root = (
            find_project_root(Path(args.root)) if args.root else find_project_root()
        )
        paths = default_paths(root)
        timeline_path = Path(args.timeline) if args.timeline else paths["timeline"]
        visual_path = Path(args.visual) if args.visual else paths["visual"]
        narration_path = Path(args.narration) if args.narration else paths["narration"]
        output_path = Path(args.output) if args.output else paths["output"]
        loudnorm: Optional[str] = args.loudnorm
        if loudnorm.strip().lower() in ("none", "off", ""):
            loudnorm = None

        report: Dict[str, Any] = {"episode": EPISODE, "root": str(root)}

        if args.validate_only:
            expect = args.expected_duration
            if expect is None:
                _ffmpeg, ffprobe = resolve_tools(root)
                visual = probe_media(visual_path, ffprobe)
                if not visual.get("video"):
                    raise AssemblyError(
                        "no visual master to derive the expected duration; "
                        "pass --expected-duration"
                    )
                expect = float(
                    visual["video"].get("duration_seconds")
                    or visual["format_duration_seconds"]
                )
            report["validation"] = validate_output(
                output_path, expect_duration=expect, project_root=root
            )
        else:
            report["narration"] = build_narration(
                timeline_path,
                narration_path,
                project_root=root,
                lines_dir=paths["lines_dir"],
                loudnorm=loudnorm,
            )
            report["assembly"] = assemble(
                visual_path, narration_path, output_path, project_root=root
            )
            report["validation"] = validate_output(
                output_path,
                expect_duration=report["assembly"]["visual_duration_seconds"],
                project_root=root,
            )

        # stdout stays pure JSON (machine-readable); status goes to stderr.
        print(json.dumps(report, indent=2, default=str))
        print(
            f"EP001 V1 ASSEMBLY OK -> "
            f"{report.get('validation', {}).get('output')}",
            file=sys.stderr,
        )
        return 0
    except AssemblyError as exc:
        print(f"\nEP001 V1 ASSEMBLY FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
