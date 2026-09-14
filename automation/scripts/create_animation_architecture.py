import json
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

OUTPUT_PATH = (
    ROOT
    / "config"
    / "ANIMATION_ARCHITECTURE.json"
)

architecture = {
    "schema_version": "1.0",
    "system": "Deathbound Animation Architecture",
    "status": "production_ready_blueprint",

    "purpose": (
        "Convert approved Deathbound story scenes into "
        "cinematic animated shots while preserving "
        "character, environment, object, emotional, "
        "chronological and causal continuity."
    ),

    "hardware_target": {
        "gpu": "RTX 3050 Laptop",
        "vram_gb": 4,
        "cpu": "i7-12700H",
        "ram_gb": 16,
        "optimization_required": True,
        "heavy_video_generation_default": False,
        "render_strategy": "shot_based"
    },

    "production_principles": [
        "Animation first, slideshow never.",
        "Shot based production instead of image sequence dependency.",
        "Characters must visibly move when narrative requires movement.",
        "Dialogue requires facial performance and lip synchronization.",
        "Camera movement must serve cinematography.",
        "Environment motion should be used where appropriate.",
        "Lighting must remain continuous across connected shots.",
        "Character identity must remain stable.",
        "State changes require narrative causes.",
        "Every shot must be traceable to a story event or cinematic purpose."
    ],

    "animation_tiers": {

        "hero": {
            "id": "ANIM-HERO",
            "purpose": "Major emotional, supernatural or story-defining moments.",
            "requirements": [
                "Full character performance",
                "Facial expression",
                "Body movement",
                "Hand/arm gestures where appropriate",
                "Camera movement",
                "Depth and parallax",
                "Environmental motion where relevant",
                "Lighting interaction",
                "Effects where narratively justified",
                "Synchronized audio"
            ],
            "usage_target": "10-25 percent of shots"
        },

        "standard": {
            "id": "ANIM-STANDARD",
            "purpose": "Normal dialogue and narrative progression.",
            "requirements": [
                "Character movement",
                "Facial performance",
                "Lip synchronization when speaking",
                "Controlled camera movement",
                "Environment continuity",
                "Relevant prop interaction"
            ],
            "usage_target": "50-70 percent of shots"
        },

        "atmospheric": {
            "id": "ANIM-ATMOSPHERIC",
            "purpose": "Establishing shots, transitions and tension building.",
            "requirements": [
                "Environmental movement",
                "Camera movement or deliberate composition",
                "Lighting continuity",
                "Atmospheric depth",
                "Particles or weather where appropriate"
            ],
            "usage_target": "10-25 percent of shots"
        }
    },

    "shot_schema": {
        "required_fields": [
            "shot_id",
            "scene_id",
            "sequence_id",
            "duration_seconds",
            "animation_tier",
            "purpose",
            "characters",
            "location",
            "props",
            "camera",
            "character_performance",
            "environment_motion",
            "lighting",
            "effects",
            "audio",
            "continuity",
            "state_before",
            "state_after",
            "causal_event_ids"
        ],

        "camera": {
            "shot_type": [
                "extreme_wide",
                "wide",
                "medium",
                "medium_close",
                "close",
                "extreme_close"
            ],
            "movement": [
                "static",
                "push_in",
                "pull_out",
                "pan",
                "tilt",
                "tracking",
                "orbit",
                "handheld",
                "crane"
            ],
            "lens_behavior": "cinematic_consistency_required",
            "composition": "story_driven"
        },

        "character_performance": {
            "body": [
                "idle",
                "walk",
                "run",
                "turn",
                "sit",
                "stand",
                "gesture",
                "interact",
                "fight",
                "collapse",
                "other"
            ],
            "face": [
                "neutral",
                "curious",
                "concerned",
                "fear",
                "anger",
                "sadness",
                "relief",
                "conflicted",
                "sarcastic",
                "supernatural"
            ],
            "speech": {
                "required_when_dialogue_exists": True,
                "lip_sync_required": True
            }
        },

        "environment_motion": [
            "none",
            "subtle",
            "moderate",
            "heavy"
        ],

        "lighting": {
            "continuity_required": True,
            "changes_require_cause": True
        },

        "effects": {
            "examples": [
                "ledger_glow",
                "eye_activation",
                "shadow_motion",
                "fog",
                "rain",
                "dust",
                "particles",
                "supernatural_energy"
            ],
            "effects_require_narrative_justification": True
        }
    },

    "continuity_contract": {
        "character_identity": "immutable",
        "character_clothing": "immutable_without_cause",
        "character_age": "immutable",
        "body_proportions": "immutable",
        "facial_structure": "immutable",
        "location_identity": "immutable_within_scene",
        "prop_identity": "immutable",
        "prop_position": "tracked",
        "lighting": "tracked",
        "weather": "tracked",
        "time": "tracked",
        "emotional_state": "state_driven",
        "knowledge_state": "event_driven",
        "relationships": "event_driven",
        "supernatural_changes": "cause_required"
    },

    "shot_transition_rules": [
        {
            "rule": "Connected shots must inherit unresolved visual state.",
            "severity": "critical"
        },
        {
            "rule": "A character cannot teleport between positions without a movement event.",
            "severity": "critical"
        },
        {
            "rule": "Props cannot disappear without a narrative or physical cause.",
            "severity": "critical"
        },
        {
            "rule": "Clothing cannot change between connected shots without an explicit event.",
            "severity": "critical"
        },
        {
            "rule": "Emotional transitions must be believable.",
            "severity": "high"
        },
        {
            "rule": "Knowledge cannot change without an information event.",
            "severity": "critical"
        },
        {
            "rule": "Lighting changes require environmental or narrative cause.",
            "severity": "high"
        },
        {
            "rule": "Supernatural visual effects require a causal event.",
            "severity": "critical"
        }
    ],

    "render_strategy": {
        "default_resolution": "1920x1080",
        "preview_resolution": "1280x720",
        "preview_fps": 24,
        "final_fps": 24,
        "color_pipeline": "consistent_project_pipeline",
        "gpu_memory_strategy": [
            "Render shots independently.",
            "Unload unnecessary assets between shots.",
            "Prefer lightweight rigs.",
            "Use proxy assets during blocking.",
            "Use preview renders before final renders.",
            "Avoid loading multiple heavyweight models simultaneously.",
            "Cache reusable animation data."
        ]
    },

    "shot_lifecycle": [
        "CREATE",
        "VALIDATE",
        "BLOCK",
        "ANIMATE",
        "AUDIO_SYNC",
        "PREVIEW_RENDER",
        "CONTINUITY_QA",
        "FINAL_RENDER",
        "POST_RENDER_QA",
        "APPROVE"
    ],

    "quality_gates": {
        "character_continuity": {
            "required": True,
            "failure_action": "REPAIR"
        },
        "story_continuity": {
            "required": True,
            "failure_action": "REPAIR"
        },
        "scene_continuity": {
            "required": True,
            "failure_action": "REPAIR"
        },
        "animation_presence": {
            "required": True,
            "failure_action": "REPAIR"
        },
        "lip_sync": {
            "required_when_dialogue": True,
            "failure_action": "REPAIR"
        },
        "audio_sync": {
            "required": True,
            "failure_action": "REPAIR"
        },
        "slideshow_detection": {
            "required": True,
            "failure_action": "REJECT"
        }
    },

    "slideshow_rejection_rules": [
        "Static frame used where character movement is required.",
        "Repeated asset with negligible meaningful change.",
        "Long camera-only movement with no performance.",
        "Dialogue without visible facial or mouth performance.",
        "Repeated generic zoom transitions.",
        "Character pose unchanged despite active dialogue or action.",
        "Background continuity failure.",
        "Character identity drift.",
        "Audio/video synchronization failure.",
        "Shot feels like narrated artwork instead of animation."
    ],

    "state_integration": {
        "story_bible": (
            "D:\\Deathbound\\projects\\EP001\\story_bible.json"
        ),
        "synced_story_bible": (
            "D:\\Deathbound\\projects\\EP001\\story_bible_synced.json"
        ),
        "riven_state": (
            "D:\\Deathbound\\projects\\EP001\\characters\\riven.json"
        ),
        "event_history": (
            "D:\\Deathbound\\projects\\EP001\\characters\\riven_event_history.json"
        ),
        "snapshots": (
            "D:\\Deathbound\\projects\\EP001\\characters\\riven_state_snapshots.json"
        ),
        "rule": (
            "Shot generation must consume state; "
            "it must not silently rewrite canonical state."
        )
    },

    "future_pipeline": [
        "Approved idea",
        "Living Story Bible",
        "Script",
        "Scene breakdown",
        "Shot Director",
        "State resolution",
        "Asset resolution",
        "Animation method selection",
        "Blocking",
        "Character animation",
        "Facial performance",
        "Lip synchronization",
        "Camera animation",
        "Environment animation",
        "Lighting and effects",
        "Audio synchronization",
        "Preview render",
        "Continuity QA",
        "Final render",
        "Post-render QA",
        "Episode assembly"
    ],

    "decision_placeholders": {
        "animation_engine": None,
        "character_rig_system": None,
        "facial_animation_system": None,
        "lip_sync_system": None,
        "motion_generation_system": None,
        "asset_generation_system": None,
        "compositing_system": None
    },

    "provenance": {
        "invented_canon": False,
        "episode_specific_content_generated": False,
        "manual_decisions_required": [
            "Select final animation engine.",
            "Select Riven rigging approach.",
            "Select facial animation approach.",
            "Select lip-sync implementation.",
            "Select lightweight asset generation workflow."
        ]
    }
}


with open(
    OUTPUT_PATH,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        architecture,
        f,
        indent=2,
        ensure_ascii=False
    )

print("=" * 60)
print("DEATHBOUND — PHASE 5A")
print("ANIMATION ARCHITECTURE")
print("=" * 60)

required = [
    "hardware_target",
    "production_principles",
    "animation_tiers",
    "shot_schema",
    "continuity_contract",
    "shot_transition_rules",
    "render_strategy",
    "shot_lifecycle",
    "quality_gates",
    "slideshow_rejection_rules",
    "state_integration",
    "future_pipeline"
]

for key in required:
    if key in architecture:
        print(f"PASS  {key}")

print("-" * 60)

if all(key in architecture for key in required):
    print("OVERALL: PASS")
    print()
    print("Architecture written to:")
    print(OUTPUT_PATH)
else:
    print("OVERALL: FAIL")
