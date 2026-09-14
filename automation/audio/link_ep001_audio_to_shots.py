import json
import re
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
EP = ROOT / "projects" / "EP001"

SHOT_FILE = EP / "03_shots" / "EP001_production_shots.json"
AUDIO_FILE = EP / "04_audio" / "EP001_AUDIO_MANIFEST.json"
OUT = EP / "03_shots" / "EP001_SHOT_AUDIO_LINK.json"

shots_data = json.loads(SHOT_FILE.read_text(encoding="utf-8"))
audio_data = json.loads(AUDIO_FILE.read_text(encoding="utf-8"))

shots = shots_data["production_shots"]
lines = audio_data["lines"]

def scene_id(value):
    m = re.match(r"^(S\d+)", str(value).strip())
    return m.group(1) if m else str(value).strip()

shot_groups = {}
for shot in shots:
    shot_groups.setdefault(scene_id(shot["scene_id"]), []).append(shot)

line_groups = {}
for line in lines:
    line_groups.setdefault(scene_id(line["scene_id"]), []).append(line)

errors = []
linked_shots = []
scene_reports = []

for sid, scene_shots in shot_groups.items():

    scene_lines = line_groups.get(sid, [])

    if not scene_lines:
        errors.append(f"{sid}: no audio lines")
        continue

    # ---------------------------------------------------------
    # Duration-aware sequential allocation
    # ---------------------------------------------------------

    line_index = 0

    for shot in scene_shots:

        shot_duration = float(shot["duration_seconds"])
        shot_start = 0.0

        assigned = []
        used = 0.0

        while line_index < len(scene_lines):

            line = scene_lines[line_index]
            duration = float(line["duration_seconds"])

            remaining = shot_duration - used

            # Give every shot a tiny tolerance for waveform edges.
            # Never split a spoken line between shots.
            if duration <= remaining + 0.10:

                start = used
                end = used + duration

                assigned.append({
                    "line_id": line["line_id"],
                    "speaker": line["speaker"],
                    "text": line["text"],
                    "wav": line["wav"],
                    "start_shot_seconds": round(start, 6),
                    "end_shot_seconds": round(end, 6),
                    "duration_seconds": round(duration, 6),
                })

                used = end
                line_index += 1

            else:
                break

        linked_shots.append({
            "shot_id": shot["shot_id"],
            "scene_id": sid,
            "duration_seconds": shot_duration,
            "purpose": shot["purpose"],
            "dialogue_line_ids": [x["line_id"] for x in assigned],
            "dialogue_duration_seconds": round(used, 6),
            "dialogue": assigned,
            "unused_seconds": round(max(0.0, shot_duration - used), 6),
            "audio_policy": {
                "dialogue_order_locked": True,
                "speech_must_not_be_stretched": True,
                "speech_must_not_be_split": True,
                "unused_time_reserved_for_breathing_sfx_music": True,
            },
        })

    # Anything remaining means the scene's fixed shot duration
    # cannot contain the generated speech.
    if line_index < len(scene_lines):
        remaining_lines = scene_lines[line_index:]

        errors.append(
            f"{sid}: {len(remaining_lines)} dialogue lines could not fit "
            f"inside the existing {sum(float(s['duration_seconds']) for s in scene_shots):.2f}s shot timeline"
        )

    scene_audio = sum(float(x["duration_seconds"]) for x in scene_lines)
    scene_shots_duration = sum(float(x["duration_seconds"]) for x in scene_shots)

    scene_reports.append({
        "scene_id": sid,
        "shot_count": len(scene_shots),
        "line_count": len(scene_lines),
        "shot_duration_seconds": round(scene_shots_duration, 6),
        "spoken_audio_seconds": round(scene_audio, 6),
        "unused_seconds": round(
            max(0.0, scene_shots_duration - scene_audio), 6
        ),
        "unassigned_lines": max(
            0,
            len(scene_lines) - line_index
        ),
    })

# ---------------------------------------------------------
# Global validation
# ---------------------------------------------------------

assigned_ids = [
    line_id
    for shot in linked_shots
    for line_id in shot["dialogue_line_ids"]
]

expected_ids = [x["line_id"] for x in lines]

missing = [x for x in expected_ids if x not in assigned_ids]
duplicates = sorted(set(
    x for x in assigned_ids
    if assigned_ids.count(x) > 1
))

if missing:
    errors.append(f"Missing audio lines: {missing}")

if duplicates:
    errors.append(f"Duplicate audio lines: {duplicates}")

result = {
    "schema_version": "1.1",
    "episode": "EP001",
    "title": "The Billionaire Had 10 Minutes Left",
    "status": "linked" if not errors else "failed",
    "allocation_method": "duration_aware_sequential",
    "source_shot_package": str(SHOT_FILE),
    "source_audio_manifest": str(AUDIO_FILE),
    "shot_count": len(shots),
    "audio_line_count": len(lines),
    "total_shot_duration_seconds": round(
        sum(float(x["duration_seconds"]) for x in shots), 6
    ),
    "total_spoken_audio_seconds": round(
        sum(float(x["duration_seconds"]) for x in lines), 6
    ),
    "scene_reports": scene_reports,
    "shots": linked_shots,
    "qa_errors": errors,
}

OUT.write_text(
    json.dumps(result, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print()
print("=" * 80)
print("DEATHBOUND — DURATION-AWARE SHOT / AUDIO LINK")
print("=" * 80)

print(f"Shots       : {len(shots)}")
print(f"Audio lines : {len(lines)}")
print(f"Shot time   : {result['total_shot_duration_seconds']:.2f}s")
print(f"Speech time : {result['total_spoken_audio_seconds']:.2f}s")
print()

for report in scene_reports:
    status = "PASS" if report["unassigned_lines"] == 0 else "FAIL"

    print(
        f"{status} {report['scene_id']} | "
        f"shots={report['shot_count']} | "
        f"lines={report['line_count']} | "
        f"speech={report['spoken_audio_seconds']:.2f}s | "
        f"unused={report['unused_seconds']:.2f}s | "
        f"unassigned={report['unassigned_lines']}"
    )

print()
print(f"Output: {OUT}")

if errors:
    print()
    print("QA ERRORS:")
    for error in errors:
        print(" -", error)
    print()
    print("STATUS: FAIL")
else:
    print()
    print("All 75 audio lines fit and are assigned exactly once.")
    print("STATUS: PASS")

print("=" * 80)
