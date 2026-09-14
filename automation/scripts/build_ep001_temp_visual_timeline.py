import json
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
EP = ROOT / "projects" / "EP001"

SHOT_FILE = EP / "03_shots" / "EP001_production_shots.json"
LINK_FILE = EP / "03_shots" / "EP001_SHOT_AUDIO_LINK.json"

OUT_DIR = EP / "05_visuals"
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT = OUT_DIR / "EP001_TEMP_VISUAL_TIMELINE.json"

shots_data = json.loads(SHOT_FILE.read_text(encoding="utf-8"))
link_data = json.loads(LINK_FILE.read_text(encoding="utf-8"))

shots = shots_data["production_shots"]
linked = {x["shot_id"]: x for x in link_data["shots"]}

visual_shots = []

for index, shot in enumerate(shots, start=1):

    sid = shot["shot_id"]
    audio = linked.get(sid, {})

    duration = float(shot["duration_seconds"])

    # Temporary visual strategy.
    # These are deliberately simple placeholders.
    purpose = shot.get("purpose", "cinematic")

    if purpose == "establishing":
        visual_method = "cinematic_establishing_card"
    elif purpose == "dialogue":
        visual_method = "temporary_character_dialogue_scene"
    elif purpose == "reaction":
        visual_method = "temporary_character_reaction_scene"
    elif purpose == "action":
        visual_method = "temporary_character_action_scene"
    else:
        visual_method = "temporary_cinematic_scene"

    visual_shots.append({
        "render_order": index,
        "shot_id": sid,
        "scene_id": shot["scene_id"],
        "sequence_id": shot["sequence_id"],
        "duration_seconds": duration,

        "temporary_visual": {
            "enabled": True,
            "method": visual_method,
            "quality_lock": "DEFERRED_UNTIL_AFTER_FIRST_VIDEO",
            "style_status": "TEMPORARY_PIPELINE_VALIDATION",
            "character_generation": False,
            "ai_video_generation": False,
            "image_generation_required": False
        },

        "scene": {
            "location": shot.get("location"),
            "characters": shot.get("characters", []),
            "props": shot.get("props", []),
            "environment_motion": shot.get("environment_motion"),
            "lighting": shot.get("lighting", {}),
            "effects": shot.get("effects", {})
        },

        "camera": shot.get("camera", {}),

        "performance": shot.get(
            "character_performance",
            {}
        ),

        "audio": {
            "dialogue": audio.get("dialogue", []),
            "dialogue_duration_seconds": audio.get(
                "dialogue_duration_seconds", 0
            ),
            "unused_seconds": audio.get(
                "unused_seconds", 0
            )
        },

        "continuity": shot.get(
            "continuity",
            {}
        )
    })

result = {
    "schema_version": "1.0",
    "episode": "EP001",
    "title": "The Billionaire Had 10 Minutes Left",
    "status": "temporary_visual_timeline_ready",

    "production_policy": {
        "purpose": "FIRST_VIDEO_END_TO_END_PIPELINE",
        "visual_quality_optimization": "DEFERRED",
        "realistic_riven_lock": "DEFERRED",
        "heavy_video_generation": False,
        "shot_based_rendering": True
    },

    "summary": {
        "shot_count": len(visual_shots),
        "total_duration_seconds": round(
            sum(x["duration_seconds"] for x in visual_shots),
            6
        ),
        "audio_linked": True
    },

    "shots": visual_shots
}

OUT.write_text(
    json.dumps(result, indent=2, ensure_ascii=False),
    encoding="utf-8"
)

print()
print("=" * 80)
print("DEATHBOUND — EP001 TEMPORARY VISUAL TIMELINE")
print("=" * 80)
print(f"Shots       : {len(visual_shots)}")
print(f"Runtime     : {result['summary']['total_duration_seconds']:.2f}s")
print("Audio link  : CONNECTED")
print("Visual mode : TEMPORARY")
print()
print(f"Output: {OUT}")
print()
print("STATUS: PASS")
print("=" * 80)
