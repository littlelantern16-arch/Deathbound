import json
from collections import Counter
from pathlib import Path


BASE = Path(r"D:\Deathbound")
SCHEMA_PATH = BASE / "config" / "CAMERA_REPETITION_SCHEMA.json"


def load_schema():
    with open(SCHEMA_PATH, "r", encoding="utf-8-sig") as f:
        return json.load(f)


def success():
    return {
        "accepted": True,
        "errors": []
    }


def failure(errors):
    return {
        "accepted": False,
        "errors": errors
    }


def normalize(value):
    return {
        "slow_push_in": "push_in",
        "slow_pull_out": "pull_out",
        "medium-close": "medium_close",
        "extreme-wide": "extreme_wide",
        "extreme-close": "extreme_close"
    }.get(value, value)


def camera_signature(shot):
    camera = shot.get("camera", {})

    return (
        normalize(camera.get("shot_type")),
        normalize(camera.get("movement"))
    )


def composition_signature(shot):
    composition = shot.get("composition", {})

    return (
        composition.get("subject_priority"),
        composition.get("framing_intent"),
        composition.get("visual_focus"),
        composition.get("depth_strategy")
    )


def full_signature(shot):
    return (
        camera_signature(shot),
        composition_signature(shot)
    )


def valid_signature(signature):
    return all(
        value is not None
        for group in signature
        for value in (
            group if isinstance(group, tuple)
            else (group,)
        )
    )


def has_motif(shot):
    motif = shot.get("visual_motif")

    return isinstance(motif, dict) and bool(
        motif.get("id")
    ) and bool(
        motif.get("intent")
    )


def consecutive_run(values):
    runs = []

    if not values:
        return runs

    start = 0

    for index in range(1, len(values) + 1):
        if (
            index == len(values)
            or values[index] != values[start]
        ):
            runs.append(
                (start, index - 1, index - start)
            )
            start = index

    return runs


def repeated_cycle(values, cycle_length):
    if len(values) < cycle_length * 2:
        return False

    for start in range(
        0,
        len(values) - cycle_length * 2 + 1
    ):
        cycle = values[
            start:start + cycle_length
        ]

        repetitions = 1

        cursor = start + cycle_length

        while (
            cursor + cycle_length <= len(values)
            and values[
                cursor:cursor + cycle_length
            ] == cycle
        ):
            repetitions += 1
            cursor += cycle_length

        if repetitions >= 2:
            return True

    return False


def validate_repetition(
    sequence,
    schema=None
):
    if schema is None:
        schema = load_schema()

    errors = []

    if not isinstance(sequence, list):
        return failure([
            "Sequence must be a list of shots."
        ])

    if not sequence:
        return failure([
            "Sequence cannot be empty."
        ])

    signatures = [
        full_signature(shot)
        for shot in sequence
    ]

    camera_signatures = [
        camera_signature(shot)
        for shot in sequence
    ]

    composition_signatures = [
        composition_signature(shot)
        for shot in sequence
    ]

    # Validate signatures.
    for index, signature in enumerate(signatures):
        if not valid_signature(signature):
            errors.append(
                f"Shot {index + 1} has incomplete repetition signature."
            )

    # Consecutive identical full signatures.
    for start, end, length in consecutive_run(
        signatures
    ):
        if length > schema["repetition_rules"][
            "identical_full_signature_limit"
        ]:
            motif_allowed = all(
                has_motif(sequence[i])
                for i in range(start, end + 1)
            )

            if not motif_allowed:
                errors.append(
                    f"Repeated full composition signature across shots {start + 1}-{end + 1}."
                )

    # Camera signature repetition.
    camera_counter = Counter(
        camera_signatures
    )

    for signature, count in camera_counter.items():
        if count > schema["repetition_rules"][
            "identical_camera_signature_limit"
        ]:
            indices = [
                i + 1
                for i, value in enumerate(
                    camera_signatures
                )
                if value == signature
            ]

            errors.append(
                f"Camera signature {signature} repeated {count} times at shots {indices}."
            )

    # Composition signature repetition.
    composition_counter = Counter(
        composition_signatures
    )

    for signature, count in composition_counter.items():
        if count > schema["repetition_rules"][
            "identical_composition_signature_limit"
        ]:
            indices = [
                i + 1
                for i, value in enumerate(
                    composition_signatures
                )
                if value == signature
            ]

            errors.append(
                f"Composition signature {signature} repeated {count} times."
            )

    # Framing intent repetition.
    framing_values = [
        shot.get("composition", {}).get(
            "framing_intent"
        )
        for shot in sequence
    ]

    for start, end, length in consecutive_run(
        framing_values
    ):
        if (
            framing_values[start] is not None
            and length
            > schema["repetition_rules"][
                "identical_framing_intent_limit"
            ]
        ):
            errors.append(
                f"Framing intent repeated across shots {start + 1}-{end + 1}."
            )

    # Visual focus repetition.
    focus_values = [
        shot.get("composition", {}).get(
            "visual_focus"
        )
        for shot in sequence
    ]

    for start, end, length in consecutive_run(
        focus_values
    ):
        if (
            focus_values[start] is not None
            and length
            > schema["repetition_rules"][
                "identical_visual_focus_limit"
            ]
        ):
            errors.append(
                f"Visual focus repeated across shots {start + 1}-{end + 1}."
            )

    # Monotonic shot progression.
    shot_types = [
        normalize(
            shot.get("camera", {}).get(
                "shot_type"
            )
        )
        for shot in sequence
    ]

    if len(sequence) >= schema[
        "template_patterns"
    ]["monotonic_shot_progression"]["minimum_length"]:

        order = {
            "extreme_wide": 0,
            "wide": 1,
            "medium": 2,
            "medium_close": 3,
            "close": 4,
            "extreme_close": 5
        }

        numeric = [
            order.get(value, -1)
            for value in shot_types
        ]

        if (
            all(
                numeric[i] < numeric[i + 1]
                for i in range(len(numeric) - 1)
            )
            or
            all(
                numeric[i] > numeric[i + 1]
                for i in range(len(numeric) - 1)
            )
        ):
            errors.append(
                "Monotonic shot-type progression detected."
            )

    # Same movement across a long run.
    movements = [
        normalize(
            shot.get("camera", {}).get(
                "movement"
            )
        )
        for shot in sequence
    ]

    for start, end, length in consecutive_run(
        movements
    ):
        if (
            movements[start] is not None
            and length >= schema[
                "template_patterns"
            ]["same_movement_every_shot"]["minimum_length"]
        ):
            errors.append(
                f"Same camera movement repeated across shots {start + 1}-{end + 1}."
            )

    # Same shot type across a long run.
    for start, end, length in consecutive_run(
        shot_types
    ):
        if (
            shot_types[start] is not None
            and length >= schema[
                "template_patterns"
            ]["same_shot_type_every_shot"]["minimum_length"]
        ):
            errors.append(
                f"Same shot type repeated across shots {start + 1}-{end + 1}."
            )

    # Repeating cycles.
    for cycle_length in (
        2,
        3,
        4
    ):
        if repeated_cycle(
            movements,
            cycle_length
        ):
            errors.append(
                f"Camera movement cycle of length {cycle_length} detected."
            )

        if repeated_cycle(
            composition_signatures,
            cycle_length
        ):
            errors.append(
                f"Composition cycle of length {cycle_length} detected."
            )

    # Diversity gates.
    if len(sequence) >= 6:
        unique_camera = len(
            set(camera_signatures)
        )

        unique_composition = len(
            set(composition_signatures)
        )

        if unique_camera < schema[
            "diversity_rules"
        ]["minimum_unique_camera_signatures_for_6_shots"]:
            errors.append(
                "Insufficient camera-signature diversity for six-shot sequence."
            )

        if unique_composition < schema[
            "diversity_rules"
        ]["minimum_unique_composition_signatures_for_6_shots"]:
            errors.append(
                "Insufficient composition-signature diversity for six-shot sequence."
            )

    if len(sequence) >= 8:
        unique_camera = len(
            set(camera_signatures)
        )

        unique_composition = len(
            set(composition_signatures)
        )

        if unique_camera < schema[
            "diversity_rules"
        ]["minimum_unique_camera_signatures_for_8_shots"]:
            errors.append(
                "Insufficient camera-signature diversity for eight-shot sequence."
            )

        if unique_composition < schema[
            "diversity_rules"
        ]["minimum_unique_composition_signatures_for_8_shots"]:
            errors.append(
                "Insufficient composition-signature diversity for eight-shot sequence."
            )

    return {
        "accepted": not errors,
        "errors": errors
    }
