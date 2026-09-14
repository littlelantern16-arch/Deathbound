import json, sys
from pathlib import Path

p = Path(r"D:\Deathbound\config\DEATHBOUND_VISUAL_STYLE_DNA.json")
if not p.exists():
    print("FAIL: visual DNA not found")
    sys.exit(1)
d = json.loads(p.read_text(encoding="utf-8"))
required = [
    ("status", "authoritative_locked"),
    ("riven.identity_lock", None),
    ("rendering.realism_level", "high"),
    ("generation_defaults.checkpoint", "Realistic_Vision_V6.0_B1_pruned.safetensors"),
    ("generation_defaults.ipadapter_preset", "FACEID PLUS V2")
]
def get(path):
    x=d
    for k in path.split("."):
        x=x[k]
    return x
for path, expected in required:
    v=get(path)
    if expected is not None and v != expected:
        print(f"FAIL {path}: {v}")
        sys.exit(1)
print("PASS: Deathbound visual DNA is locked and internally consistent.")
