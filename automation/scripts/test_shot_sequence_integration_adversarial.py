import sys
from pathlib import Path

ROOT = Path(r"D:\Deathbound")
sys.path.insert(0, str(ROOT / "automation" / "scripts"))

from shot_sequence_integration_engine import validate_sequence


def shot(
    shot_id,
    state="STATE-A",
    camera=("medium", "static"),
    performance=("observe", "neutral", "none"),
    character="idle",
    spatial="A",
    props="P1",
    environment="office_night",
    lighting="night",
    speaker=None,
    events=None
):
    return {
        "shot_id": shot_id,
        "duration_seconds": 3,

        "state_before": state,
        "state_after": state,

        "character_state": character,

        "camera_state": {
            "shot_type": camera[0],
            "movement": camera[1]
        },

        "spatial_state": spatial,
        "props": props,
        "environment": environment,
        "lighting": lighting,

        "effects": [],

        "performance": {
            "intent": performance[0],
            "emotion": performance[1],
            "action": performance[2]
        },

        "audio_state": {
            "speaker": speaker
        },

        "causal_event_ids": events or []
    }


def sequence(shots):
    return {
        "sequence_id": "SEQ-001",
        "scene_id": "SCENE-001",
        "shots": shots
    }


def run_test(name, value, should_pass):
    result = validate_sequence(value)
    passed = result["valid"] == should_pass

    print(f"{'PASS' if passed else 'FAIL'} | {name}")

    if not passed:
        print("  errors:", result["errors"])

    return passed


tests = []

# =========================================================
# VALID
# =========================================================

tests.append(run_test(
    "VALID-001 single valid shot",
    sequence([
        shot("S001")
    ]),
    True
))

tests.append(run_test(
    "VALID-002 unchanged state chain",
    sequence([
        shot("S001", state="STATE-A"),
        shot("S002", state="STATE-A")
    ]),
    True
))

tests.append(run_test(
    "VALID-003 intentional camera cut",
    sequence([
        shot(
            "S001",
            camera=("wide", "static")
        ),
        dict(
            shot(
                "S002",
                camera=("close", "push_in")
            ),
            intentional_cut=True
        )
    ]),
    True
))

tests.append(run_test(
    "VALID-004 causal character transition",
    sequence([
        shot(
            "S001",
            state="STATE-A",
            character="idle"
        ),
        dict(
            shot(
                "S002",
                state="STATE-B",
                character="walking"
            ),
            character_state_change_event="EV-WALK",
            causal_state_transition=True,
            spatial_transition_event="EV-MOVE"
        )
    ]),
    True
))

tests.append(run_test(
    "VALID-005 prop transition with cause",
    sequence([
        shot(
            "S001",
            props="PHONE_TABLE"
        ),
        dict(
            shot(
                "S002",
                props="PHONE_HAND"
            ),
            prop_transition_event="EV-PICKUP"
        )
    ]),
    True
))

tests.append(run_test(
    "VALID-006 environment transition with cause",
    sequence([
        shot(
            "S001",
            environment="office_clear"
        ),
        dict(
            shot(
                "S002",
                environment="office_rain"
            ),
            environment_transition_event="EV-STORM"
        )
    ]),
    True
))

# FIX: the state transition itself must be represented.
tests.append(run_test(
    "VALID-007 lighting transition with cause",
    sequence([
        shot(
            "S001",
            state="STATE-A",
            lighting="night"
        ),
        dict(
            shot(
                "S002",
                state="STATE-B",
                lighting="reaper_darkness"
            ),
            causal_state_transition=True,
            lighting_transition_event="EV-POWER"
        )
    ]),
    True
))

tests.append(run_test(
    "VALID-008 audio speaker boundary",
    sequence([
        shot(
            "S001",
            speaker="riven"
        ),
        dict(
            shot(
                "S002",
                speaker="daniel"
            ),
            dialogue_boundary=True
        )
    ]),
    True
))

tests.append(run_test(
    "VALID-009 multi-speaker overlap",
    sequence([
        shot(
            "S001",
            speaker="riven"
        ),
        dict(
            shot(
                "S002",
                speaker="daniel"
            ),
            audio_state={
                "speaker": "daniel",
                "multi_speaker_overlap": True
            }
        )
    ]),
    True
))

# Camera changes between ordinary shots are legitimate.
tests.append(run_test(
    "VALID-010 diverse cinematic sequence",
    sequence([
        shot(
            "S001",
            camera=("wide", "static"),
            performance=("observe", "neutral", "none")
        ),

        shot(
            "S002",
            camera=("medium", "tracking"),
            performance=("investigate", "curious", "walk")
        ),

        dict(
            shot(
                "S003",
                state="STATE-B",
                camera=("close", "push_in"),
                performance=("react", "surprised", "none")
            ),
            causal_state_transition=True,
            character_state_change_event="EV-REACT",
            spatial_transition_event="EV-REACT"
        ),

        dict(
            shot(
                "S004",
                state="STATE-C",
                camera=("medium_close", "static"),
                performance=("speak", "neutral", "none"),
                speaker="riven"
            ),
            causal_state_transition=True,
            character_state_change_event="EV-SPEAK"
        ),

        dict(
            shot(
                "S005",
                state="STATE-D",
                camera=("wide", "pull_out"),
                performance=("decide", "determined", "none")
            ),
            causal_state_transition=True,
            character_state_change_event="EV-DECIDE"
        ),

        dict(
            shot(
                "S006",
                state="STATE-E",
                camera=("close", "push_in"),
                performance=("supernatural_activation", "determined", "activate"),
                events=["EV-SUPERNATURAL"]
            ),
            causal_state_transition=True,
            character_state_change_event="EV-ACTIVATE",
            lighting_transition_event="EV-ACTIVATE"
        )
    ]),
    True
))

# Connected camera movement requires explicit transition metadata.
tests.append(run_test(
    "VALID-011 connected camera movement",
    sequence([
        shot(
            "S001",
            camera=("medium", "tracking")
        ),
        dict(
            shot(
                "S002",
                camera=("medium", "tracking")
            ),
            connected_camera_motion=True,
            camera_transition={
                "type": "continuous_tracking"
            }
        )
    ]),
    True
))

# =========================================================
# INVALID
# =========================================================

tests.append(run_test(
    "INVALID-001 state mismatch",
    sequence([
        shot("S001", state="STATE-A"),
        shot("S002", state="STATE-B")
    ]),
    False
))

tests.append(run_test(
    "INVALID-002 character teleport",
    sequence([
        shot("S001", character="position_A"),
        shot("S002", character="position_B")
    ]),
    False
))

tests.append(run_test(
    "INVALID-003 spatial jump without cause",
    sequence([
        shot("S001", spatial="A"),
        shot("S002", spatial="B")
    ]),
    False
))

tests.append(run_test(
    "INVALID-004 prop jump without cause",
    sequence([
        shot("S001", props="TABLE"),
        shot("S002", props="HAND")
    ]),
    False
))

tests.append(run_test(
    "INVALID-005 environment jump without cause",
    sequence([
        shot("S001", environment="office"),
        shot("S002", environment="street")
    ]),
    False
))

tests.append(run_test(
    "INVALID-006 lighting jump without cause",
    sequence([
        shot("S001", lighting="night"),
        shot("S002", lighting="day")
    ]),
    False
))

tests.append(run_test(
    "INVALID-007 connected camera discontinuity",
    sequence([
        shot(
            "S001",
            camera=("medium", "tracking")
        ),
        dict(
            shot(
                "S002",
                camera=("medium", "tracking")
            ),
            connected_camera_motion=True
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-008 speaker change without boundary",
    sequence([
        shot("S001", speaker="riven"),
        shot("S002", speaker="daniel")
    ]),
    False
))

tests.append(run_test(
    "INVALID-009 duplicate causal event",
    sequence([
        shot(
            "S001",
            events=["EV-001"]
        ),
        shot(
            "S002",
            events=["EV-001"]
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-010 excessive performance repetition",
    sequence([
        shot("S001", performance=("observe", "neutral", "none")),
        shot("S002", performance=("observe", "neutral", "none")),
        shot("S003", performance=("observe", "neutral", "none")),
        shot("S004", performance=("observe", "neutral", "none"))
    ]),
    False
))

tests.append(run_test(
    "INVALID-011 excessive camera repetition",
    sequence([
        shot("S001", camera=("medium", "static")),
        shot("S002", camera=("medium", "static")),
        shot("S003", camera=("medium", "static")),
        shot("S004", camera=("medium", "static"))
    ]),
    False
))

tests.append(run_test(
    "INVALID-012 excessive complete repetition",
    sequence([
        shot(
            "S001",
            camera=("medium", "static"),
            performance=("observe", "neutral", "none")
        ),
        shot(
            "S002",
            camera=("medium", "static"),
            performance=("observe", "neutral", "none")
        ),
        shot(
            "S003",
            camera=("medium", "static"),
            performance=("observe", "neutral", "none")
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-013 long sequence lacks diversity",
    sequence([
        shot("S001"),
        shot("S002"),
        shot("S003"),
        shot("S004"),
        shot("S005"),
        shot("S006")
    ]),
    False
))

tests.append(run_test(
    "INVALID-014 camera-only slideshow",
    sequence([
        shot("S001"),
        dict(
            shot(
                "S002",
                camera=("medium", "push_in")
            ),
            static_character_with_only_camera_change=True
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-015 voiceover slideshow",
    sequence([
        shot("S001"),
        dict(
            shot("S002"),
            voiceover_over_repeated_static_frames=True
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-016 effects replacing performance",
    sequence([
        shot("S001"),
        dict(
            shot("S002"),
            effect_overlay_as_performance=True
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-017 camera movement replacing action",
    sequence([
        shot("S001"),
        dict(
            shot(
                "S002",
                camera=("wide", "tracking")
            ),
            camera_movement_as_action=True
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-018 duplicate shot IDs",
    sequence([
        shot("S001"),
        shot("S001")
    ]),
    False
))

tests.append(run_test(
    "INVALID-019 invalid shot duration",
    sequence([
        dict(
            shot("S001"),
            duration_seconds=0
        )
    ]),
    False
))

tests.append(run_test(
    "INVALID-020 missing required shot system",
    {
        "sequence_id": "SEQ-001",
        "scene_id": "SCENE-001",
        "shots": [
            {
                "shot_id": "S001"
            }
        ]
    },
    False
))

passed = sum(tests)
total = len(tests)

print("")
print("==============================================")
print("DEATHBOUND — PHASE 5M")
print("SHOT SEQUENCE INTEGRATION ADVERSARIAL QA")
print(f"TESTS: {total}  PASS: {passed}  FAIL: {total - passed}")
print("OVERALL:", "PASS" if passed == total else "FAIL")
print("==============================================")

if passed != total:
    raise SystemExit(1)
