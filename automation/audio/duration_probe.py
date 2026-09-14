import re
import subprocess
from pathlib import Path

SCRIPT = Path(r"D:\Deathbound\projects\EP001\04_audio\EP001_audio_script.txt")
MODEL = Path(r"D:\Deathbound\tools\piper\voices\en_US-john-medium.onnx")
TMP = Path(r"D:\Deathbound\automation\audio\duration_probe")

TMP.mkdir(parents=True, exist_ok=True)

lines = SCRIPT.read_text(encoding="utf-8").splitlines()

scene = None
total = 0.0
count = 0

print("Generating duration probe...")
print()

for line in lines:
    line = line.strip()

    if not line:
        continue

    if line.startswith("==="):
        match = re.match(r"^===\s*(.*?)\s*===", line)
        if match:
            scene = match.group(1).strip()
        continue

    match = re.match(r"^([^:]+):\s*(.+)$", line)

    if not match:
        continue

    speaker, text = match.groups()
    count += 1

    txt = TMP / f"{count:03d}.txt"
    wav = TMP / f"{count:03d}.wav"

    txt.write_text(text, encoding="utf-8")

    subprocess.run(
        [
            "python",
            "-m",
            "piper",
            "-m",
            str(MODEL),
            "-i",
            str(txt),
            "-f",
            str(wav),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(wav),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    duration = float(result.stdout.strip())
    total += duration

    print(
        f"{count:02d} | {scene:<30} | "
        f"{speaker:<8} | {duration:5.2f}s | {text}"
    )

print()
print("=" * 90)
print(f"LINES: {count}")
print(f"TOTAL SPOKEN AUDIO: {total:.2f}s ({total / 60:.2f} min)")
print(f"CURRENT SHOT TIMELINE: 222.00s (3.70 min)")
print(f"WITH 20% BREATHING ROOM: {total * 1.20:.2f}s ({total * 1.20 / 60:.2f} min)")
print("=" * 90)
