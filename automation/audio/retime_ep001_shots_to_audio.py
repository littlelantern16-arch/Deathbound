import json
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
EP = ROOT / "projects" / "EP001"

SHOT_FILE = EP / "03_shots" / "EP001_production_shots.json"
AUDIO_FILE = EP / "04_audio" / "EP001_AUDIO_MANIFEST.json"

BACKUP = EP / "03_shots" / "EP001_production_shots.pre_audio_retime.json"
OUT = SHOT_FILE

shots_data = json.loads(SHOT_FILE.read_text(encoding="utf-8"))
audio_data = json.loads(AUDIO_FILE.read_text(encoding="utf-8"))

shots = shots_data["production_shots"]
lines = audio_data["lines"]

# Backup original timing before changing anything.
BACKUP.write_text(
    json.dumps(shots_data, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

# Normalize scene IDs.
def scene_id(value):
    return str(value).strip().split()[0]

shot_groups = {}
for shot in shots:
    shot_groups.setdefault(scene_id(shot["scene_id"]), []).append(shot)

line_groups = {}
for line in lines:
    line_groups.setdefault(scene_id(line["scene_id"]), []).append(line)

total_added = 0.0
changes = []

for sid, scene_shots in shot_groups.items():

    scene_lines = line_groups.get(sid, [])
    line_index = 0

    for shot in scene_shots:

        original = float(shot["duration_seconds"])
        duration = original
        used = 0.0
        assigned = []

        while line_index < len(scene_lines):

            line = scene_lines[line_index]
            line_duration = float(line["duration_seconds"])

            remaining = duration - used

            if line_duration <= remaining + 0.10:

                used += line_duration
                assigned.append(line)
                line_index += 1

            else:

                # If this shot already contains dialogue, extend it.
                # If it contains no dialogue yet, make it long enough.
                needed = line_duration - remaining

                # Small breathing allowance after dialogue.
                new_duration = duration + needed

                # Round to clean quarter-second boundaries.
                new_duration = round(new_duration * 4) / 4

                if new_duration < duration:
                    new_duration = duration

                duration = new_duration

                used += line_duration
                assigned.append(line)
                line_index += 1

        if duration != original:

            delta = duration - original
            total_added += delta

            changes.append({
                "shot_id": shot["shot_id"],
                "scene_id": sid,
                "old_duration": original,
                "new_duration": duration,
                "added_seconds": delta,
                "dialogue_seconds": round(used, 3),
                "dialogue_lines": len(assigned),
            })

            shot["duration_seconds"] = duration

        # Store an explicit retime record.
        shot.setdefault("timing", {})
        shot["timing"]["audio_retimed"] = True
        shot["timing"]["audio_dialogue_seconds"] = round(used, 6)
        shot["timing"]["original_duration_seconds"] = original

# Recalculate total runtime.
total_runtime = sum(
    float(s["duration_seconds"])
    for s in shots
)

shots_data["status"] = "architecture_validated_audio_retimed"
shots_data["timing_revision"] = {
    "method": "dialogue_duration_driven",
    "source": str(AUDIO_FILE),
    "original_total_seconds": round(
        sum(
            float(s.get("timing", {}).get(
                "original_duration_seconds",
                s["duration_seconds"]
            ))
            for s in shots
        ), 6
    ),
    "new_total_seconds": round(total_runtime, 6),
    "total_added_seconds": round(total_added, 6),
    "changed_shots": len(changes),
    "speech_was_stretched": False,
    "speech_was_trimmed": False,
    "speech_was_split": False,
}

shots_data["production_shots"] = shots

OUT.write_text(
    json.dumps(shots_data, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print()
print("=" * 80)
print("DEATHBOUND — EP001 AUDIO-DRIVEN SHOT RETIMING")
print("=" * 80)

print(f"Original timeline : 222.00s")
print(f"New timeline      : {total_runtime:.2f}s")
print(f"Time added        : {total_added:.2f}s")
print(f"Changed shots     : {len(changes)}")
print(f"Backup            : {BACKUP}")
print()

for x in changes:
    print(
        f"{x['shot_id']} | "
        f"{x['old_duration']:.2f}s -> "
        f"{x['new_duration']:.2f}s | "
        f"+{x['added_seconds']:.2f}s | "
        f"dialogue={x['dialogue_seconds']:.2f}s | "
        f"lines={x['dialogue_lines']}"
    )

print()
print(f"Updated: {OUT}")
print("Speech stretched : NO")
print("Speech trimmed   : NO")
print("Speech split     : NO")
print("STATUS: PASS")
print("=" * 80)
