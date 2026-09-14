import json
from pathlib import Path


ROOT = Path(r"D:\Deathbound")
SCHEMA_PATH = ROOT / "config" / "SHOT_SEQUENCE_INTEGRATION_SCHEMA.json"

with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
    SCHEMA = json.load(f)


def result(errors):
    return {
        "valid": len(errors) == 0,
        "errors": errors
    }


def camera_signature(shot):
    camera = shot.get("camera_state", {})
    return (
        camera.get("shot_type"),
        camera.get("movement")
    )


def performance_signature(shot):
    performance = shot.get("performance", {})
    return (
        performance.get("intent"),
        performance.get("emotion"),
        performance.get("action")
    )


def complete_signature(shot):
    return (
        camera_signature(shot),
        performance_signature(shot)
    )


def validate_sequence(sequence):
    errors = []

    # =========================================================
    # SEQUENCE CONTRACT
    # =========================================================

    for field in SCHEMA["sequence_contract"]["required_fields"]:
        if field not in sequence:
            errors.append(f"Missing sequence field: {field}")

    if errors:
        return result(errors)

    shots = sequence.get("shots")

    if not isinstance(shots, list):
        return result(["shots must be a list."])

    if len(shots) < SCHEMA["sequence_contract"]["minimum_shots"]:
        return result(["Sequence contains no valid shots."])

    # =========================================================
    # SHOT CONTRACT
    # =========================================================

    required_fields = SCHEMA["shot_contract"]["required_fields"]

    for index, shot in enumerate(shots):

        for field in required_fields:
            if field not in shot:
                errors.append(
                    f"Shot {index} missing required field: {field}"
                )

        duration = shot.get("duration_seconds")

        if not isinstance(duration, (int, float)):
            errors.append(
                f"Shot {index} duration must be numeric."
            )
        elif duration <= 0:
            errors.append(
                f"Shot {index} duration must be positive."
            )

    if errors:
        return result(errors)

    # =========================================================
    # SHOT ID UNIQUENESS
    # =========================================================

    shot_ids = [shot["shot_id"] for shot in shots]

    if len(shot_ids) != len(set(shot_ids)):
        errors.append("Duplicate shot_id detected.")

    # =========================================================
    # SHOT-TO-SHOT CONTINUITY
    # =========================================================

    for i in range(1, len(shots)):

        previous = shots[i - 1]
        current = shots[i]

        # -----------------------------------------------------
        # MASTER STATE
        # -----------------------------------------------------

        if previous["state_after"] != current["state_before"]:

            if not current.get("causal_state_transition"):
                errors.append(
                    f"Shot {i} state_before does not match previous state_after."
                )

        # -----------------------------------------------------
        # CHARACTER
        # -----------------------------------------------------

        if previous["character_state"] != current["character_state"]:

            if not current.get("character_state_change_event"):
                errors.append(
                    f"Shot {i} character state changed without causal event."
                )

        # -----------------------------------------------------
        # SPATIAL
        # -----------------------------------------------------

        if previous["spatial_state"] != current["spatial_state"]:

            if not current.get("spatial_transition_event"):
                errors.append(
                    f"Shot {i} spatial state changed without transition event."
                )

        # -----------------------------------------------------
        # PROPS
        # -----------------------------------------------------

        if previous["props"] != current["props"]:

            if not current.get("prop_transition_event"):
                errors.append(
                    f"Shot {i} prop state changed without transition event."
                )

        # -----------------------------------------------------
        # ENVIRONMENT
        # -----------------------------------------------------

        if previous["environment"] != current["environment"]:

            if not current.get("environment_transition_event"):
                errors.append(
                    f"Shot {i} environment changed without transition event."
                )

        # -----------------------------------------------------
        # LIGHTING
        # -----------------------------------------------------

        if previous["lighting"] != current["lighting"]:

            if not current.get("lighting_transition_event"):
                errors.append(
                    f"Shot {i} lighting changed without causal event."
                )

        # -----------------------------------------------------
        # CAMERA
        #
        # Normal editorial shot changes are allowed.
        #
        # BUT if the sequence explicitly declares that the camera
        # remains connected across the shot boundary, transition
        # metadata is mandatory.
        # -----------------------------------------------------

        if current.get("connected_camera_motion"):

            transition = current.get("camera_transition")

            if not isinstance(transition, dict) or not transition:
                errors.append(
                    f"Shot {i} connected camera motion lacks transition metadata."
                )

        # -----------------------------------------------------
        # AUDIO / SPEAKER
        # -----------------------------------------------------

        previous_audio = previous["audio_state"]
        current_audio = current["audio_state"]

        previous_speaker = previous_audio.get("speaker")
        current_speaker = current_audio.get("speaker")

        if (
            previous_speaker
            and current_speaker
            and previous_speaker != current_speaker
        ):

            if not (
                current_audio.get("multi_speaker_overlap")
                or current.get("scene_boundary")
                or current.get("dialogue_boundary")
            ):
                errors.append(
                    f"Shot {i} audio speaker changed without boundary."
                )

    # =========================================================
    # CAUSAL EVENT UNIQUENESS
    # =========================================================

    seen_events = set()

    for i, shot in enumerate(shots):

        events = shot.get("causal_event_ids", [])

        if not isinstance(events, list):
            errors.append(
                f"Shot {i} causal_event_ids must be a list."
            )
            continue

        for event in events:

            if event in seen_events:
                errors.append(
                    f"Shot {i} reuses causal event {event}."
                )

        seen_events.update(events)

    # =========================================================
    # PERFORMANCE REPETITION
    # =========================================================

    previous = None
    run = 0

    for i, shot in enumerate(shots):

        current = performance_signature(shot)

        if current == previous:
            run += 1
        else:
            run = 1

        if run > SCHEMA["repetition_rules"][
            "maximum_identical_performance_signature_run"
        ]:
            errors.append(
                f"Shot {i} exceeds identical performance repetition limit."
            )

        previous = current

    # =========================================================
    # CAMERA REPETITION
    # =========================================================

    previous = None
    run = 0

    for i, shot in enumerate(shots):

        current = camera_signature(shot)

        if current == previous:
            run += 1
        else:
            run = 1

        if run > SCHEMA["repetition_rules"][
            "maximum_identical_camera_signature_run"
        ]:
            errors.append(
                f"Shot {i} exceeds identical camera repetition limit."
            )

        previous = current

    # =========================================================
    # COMPLETE SIGNATURE REPETITION
    # =========================================================

    previous = None
    run = 0

    for i, shot in enumerate(shots):

        current = complete_signature(shot)

        if current == previous:
            run += 1
        else:
            run = 1

        if run > SCHEMA["repetition_rules"][
            "maximum_identical_complete_signature_run"
        ]:
            errors.append(
                f"Shot {i} exceeds complete-signature repetition limit."
            )

        previous = current

    # =========================================================
    # LONG-SEQUENCE DIVERSITY
    # =========================================================

    if len(shots) >= SCHEMA["repetition_rules"]["long_sequence_threshold"]:

        distinct = len({
            complete_signature(shot)
            for shot in shots
        })

        minimum = SCHEMA["repetition_rules"][
            "minimum_distinct_signatures_for_long_sequence"
        ]

        if distinct < minimum:
            errors.append(
                "Long sequence lacks sufficient cinematic signature diversity."
            )

    # =========================================================
    # SLIDESHOW DEFENSE
    # =========================================================

    static_run = 0

    for i, shot in enumerate(shots):

        performance = shot["performance"]
        camera = shot["camera_state"]

        no_character_action = performance.get("action") in (
            None,
            "",
            "none"
        )

        static_camera = camera.get("movement") in (
            None,
            "",
            "static"
        )

        if no_character_action and static_camera:
            static_run += 1
        else:
            static_run = 0

        if static_run > SCHEMA["slideshow_defense"][
            "static_shot_run_threshold"
        ]:
            errors.append(
                f"Shot {i} creates a prolonged static-frame run."
            )

        if (
            shot.get("static_character_with_only_camera_change")
            and SCHEMA["slideshow_defense"][
                "static_character_with_only_camera_change"
            ]
        ):
            errors.append(
                f"Shot {i} uses camera movement as a substitute for character animation."
            )

        if (
            shot.get("voiceover_over_repeated_static_frames")
            and SCHEMA["slideshow_defense"][
                "voiceover_over_repeated_static_frames"
            ]
        ):
            errors.append(
                f"Shot {i} uses voiceover over repeated static frames."
            )

        if (
            shot.get("effect_overlay_as_performance")
            and SCHEMA["slideshow_defense"][
                "effect_overlay_cannot_count_as_character_performance"
            ]
        ):
            errors.append(
                f"Shot {i} uses effects as a substitute for performance."
            )

        if (
            shot.get("camera_movement_as_action")
            and SCHEMA["slideshow_defense"][
                "camera_movement_alone_cannot_count_as_action"
            ]
        ):
            errors.append(
                f"Shot {i} uses camera movement as a substitute for action."
            )

    return result(errors)


if __name__ == "__main__":
    print("Deathbound Shot Sequence Integration Engine")
    print("Schema:", SCHEMA_PATH)
