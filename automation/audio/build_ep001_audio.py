import json
import re
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(r"D:\Deathbound")
EP = ROOT / "projects" / "EP001"
SCRIPT = EP / "04_audio" / "EP001_audio_script.txt"
MODEL = ROOT / "tools" / "piper" / "voices" / "en_US-john-medium.onnx"

AUDIO = EP / "04_audio"
LINES = AUDIO / "lines"
MANIFEST = AUDIO / "EP001_AUDIO_MANIFEST.json"
TIMELINE = AUDIO / "EP001_AUDIO_TIMELINE.json"

LINES.mkdir(parents=True, exist_ok=True)

# Temporary voice map for Video #1.
# We will cast dedicated voices after the first video.
VOICE_MAP = {
    "NARRATOR": MODEL,
    "Riven": MODEL,
    "Daniel": MODEL,
    "Daughter": MODEL,
}

text = SCRIPT.read_text(encoding="utf-8")

scene_id = None
scene_title = None
line_counter = 0
entries = []

for raw in text.splitlines():
    line = raw.strip()

    if not line:
        continue

    # Scene heading
    if line.startswith("==="):
        match = re.match(r"^===\s*(.*?)\s*===", line)
        if match:
            heading = match.group(1).strip()
            scene_match = re.match(r"(S\d+)\s*[—-]\s*(.*)", heading)

            if scene_match:
                scene_id = scene_match.group(1)
                scene_title = scene_match.group(2).strip()
            else:
                scene_id = heading
                scene_title = heading

        continue

    # Dialogue / narration
    match = re.match(r"^([^:]+):\s*(.+)$", line)

    if not match:
        continue

    speaker = match.group(1).strip()
    spoken_text = match.group(2).strip()

    if speaker not in VOICE_MAP:
        raise RuntimeError(
            f"Unknown speaker '{speaker}'. "
            f"Known speakers: {list(VOICE_MAP)}"
        )

    line_counter += 1

    line_id = f"{scene_id}_L{line_counter:03d}"
    wav_name = f"{line_id}.wav"
    wav_path = LINES / wav_name

    txt_path = LINES / f"{line_id}.txt"
    txt_path.write_text(spoken_text + "\n", encoding="utf-8")

    print(f"[{line_counter:02d}/75] {scene_id} | {speaker} | {spoken_text}")

    subprocess.run(
        [
            "python",
            "-m",
            "piper",
            "-m",
            str(VOICE_MAP[speaker]),
            "-i",
            str(txt_path),
            "-f",
            str(wav_path),
        ],
        check=True,
    )

    duration_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(wav_path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    duration = float(duration_result.stdout.strip())

    entries.append(
        {
            "line_id": line_id,
            "scene_id": scene_id,
            "scene_title": scene_title,
            "speaker": speaker,
            "text": spoken_text,
            "wav": str(wav_path),
            "duration_seconds": round(duration, 6),
            "voice_model": str(VOICE_MAP[speaker]),
        }
    )

total_duration = sum(x["duration_seconds"] for x in entries)

manifest = {
    "schema_version": "1.0",
    "episode": "EP001",
    "episode_id": "YR-001",
    "title": "The Billionaire Had 10 Minutes Left",
    "status": "generated",
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "voice_mode": "temporary_single_voice",
    "voice_policy": {
        "note": "Temporary John Piper voice used for all speakers for Video #1.",
        "upgrade_after_first_video": True,
    },
    "line_count": len(entries),
    "total_duration_seconds": round(total_duration, 6),
    "lines": entries,
}

MANIFEST.write_text(
    json.dumps(manifest, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

# Build a simple sequential audio timeline.
cursor = 0.0
timeline_entries = []

for item in entries:
    start = cursor
    end = start + item["duration_seconds"]

    timeline_entries.append(
        {
            "line_id": item["line_id"],
            "scene_id": item["scene_id"],
            "speaker": item["speaker"],
            "text": item["text"],
            "wav": item["wav"],
            "start_seconds": round(start, 6),
            "end_seconds": round(end, 6),
            "duration_seconds": item["duration_seconds"],
        }
    )

    cursor = end

timeline = {
    "schema_version": "1.0",
    "episode": "EP001",
    "timeline_type": "spoken_audio_sequential_baseline",
    "total_duration_seconds": round(cursor, 6),
    "entries": timeline_entries,
}

TIMELINE.write_text(
    json.dumps(timeline, indent=2, ensure_ascii=False),
    encoding="utf-8",
)

print()
print("=" * 80)
print("DEATHBOUND — EP001 AUDIO GENERATION")
print("=" * 80)
print(f"Lines generated : {len(entries)}")
print(f"Audio duration  : {total_duration:.2f}s")
print(f"Audio duration  : {total_duration / 60:.2f} min")
print()
print(f"Manifest        : {MANIFEST}")
print(f"Timeline        : {TIMELINE}")
print()
print("STATUS: PASS")
print("=" * 80)
