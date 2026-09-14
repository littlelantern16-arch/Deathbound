import json
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(r"D:\Deathbound")

BIBLE_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "story_bible.json"
)

ARCHITECTURE_PATH = (
    ROOT
    / "config"
    / "ANIMATION_ARCHITECTURE.json"
)

SHOT_ENGINE_PATH = (
    ROOT
    / "automation"
    / "scripts"
    / "shot_spec_engine.py"
)

OUTPUT_PATH = (
    ROOT
    / "projects"
    / "EP001"
    / "scene_to_shot_director_output.json"
)


class DirectorError(Exception):
    pass


def load_json(path):
    try:
        with open(
            path,
            "r",
            encoding="utf-8-sig"
        ) as f:
            return json.load(f)
    except Exception as exc:
        raise DirectorError(
            f"Could not read {path}: {exc}"
        )


def load_shot_engine():

    namespace = {}

    source = SHOT_ENGINE_PATH.read_text(
        encoding="utf-8-sig"
    )

    exec(
        compile(
            source,
            str(SHOT_ENGINE_PATH),
            "exec"
        ),
        namespace
    )

    return namespace


def registry_ids(bible, registry_name):

    registry = bible.get(
        registry_name,
        {}
    )

    ids = set()

    if isinstance(registry, dict):

        for key, item in registry.items():

            if isinstance(item, dict):

                item_id = item.get("id")

                if item_id:
                    ids.add(item_id)

            elif isinstance(key, str):

                ids.add(key)

    elif isinstance(registry, list):

        for item in registry:

            if isinstance(item, dict):

                item_id = item.get("id")

                if item_id:
                    ids.add(item_id)

    return ids


def event_ids(bible):

    return {
        event.get("event_id")
        for event in bible.get(
            "causal_events",
            []
        )
        if isinstance(event, dict)
        and event.get("event_id")
    }


def create_scene_brief(
    scene_id,
    narrative_purpose,
    emotional_start,
    emotional_end,
    characters,
    location,
    props,
    dialogue_present,
    action_present,
    supernatural_present,
    causal_event_ids
):

    return {
        "scene_id": scene_id,
        "narrative_purpose": narrative_purpose,

        "emotional_arc": {
            "start": emotional_start,
            "end": emotional_end
        },

        "characters": characters,
        "location": location,
        "props": props,

        "dialogue_present": dialogue_present,
        "action_present": action_present,
        "supernatural_present": supernatural_present,

        "causal_event_ids": causal_event_ids
    }


def choose_animation_tier(
    dialogue_present,
    action_present,
    supernatural_present,
    emotional_start,
    emotional_end
):

    # Hero moments receive priority when the scene
    # contains meaningful emotional, supernatural,
    # or action-defining material.

    if (
        supernatural_present
        or action_present
        or emotional_start != emotional_end
    ):
        return "hero"

    if dialogue_present:
        return "standard"

    return "atmospheric"


def generate_director_plan(
    scene,
    bible,
    architecture,
    shot_engine
):

    scene_id = scene["scene_id"]

    characters = scene["characters"]

    location = scene["location"]

    props = scene["props"]

    causal_events = scene[
        "causal_event_ids"
    ]

    dialogue = scene[
        "dialogue_present"
    ]

    action = scene[
        "action_present"
    ]

    supernatural = scene[
        "supernatural_present"
    ]

    emotional_start = scene[
        "emotional_arc"
    ]["start"]

    emotional_end = scene[
        "emotional_arc"
    ]["end"]

    # ------------------------------------------------------------
    # COVERAGE LOGIC
    # ------------------------------------------------------------

    shots = []

    # Establishing shot.
    shots.append({
        "role": "establishing",
        "duration_seconds": 3.5,
        "animation_tier": "atmospheric",
        "shot_type": "wide",
        "movement": "slow_push_in"
    })

    # Character coverage.
    if characters:

        shots.append({
            "role": "character_coverage",
            "duration_seconds": 4.0,
            "animation_tier": "standard",
            "shot_type": "medium",
            "movement": "tracking"
        })

    # Dialogue coverage.
    if dialogue:

        shots.append({
            "role": "dialogue",
            "duration_seconds": 5.0,
            "animation_tier": "standard",
            "shot_type": "medium_close",
            "movement": "static"
        })

        shots.append({
            "role": "reaction",
            "duration_seconds": 3.0,
            "animation_tier": "standard",
            "shot_type": "close",
            "movement": "slow_push_in"
        })

    # Action coverage.
    if action:

        shots.append({
            "role": "action",
            "duration_seconds": 4.0,
            "animation_tier": "hero",
            "shot_type": "wide",
            "movement": "tracking"
        })

    # Supernatural coverage.
    if supernatural:

        shots.append({
            "role": "supernatural_payoff",
            "duration_seconds": 4.0,
            "animation_tier": "hero",
            "shot_type": "close",
            "movement": "push_in"
        })

    # Emotional resolution.
    if emotional_start != emotional_end:

        shots.append({
            "role": "emotional_resolution",
            "duration_seconds": 4.5,
            "animation_tier": "hero",
            "shot_type": "medium_close",
            "movement": "static"
        })

    # ------------------------------------------------------------
    # CONVERT DIRECTOR ROLES INTO SHOT SPECIFICATIONS
    # ------------------------------------------------------------

    production_shots = []

    selected_tier = choose_animation_tier(
        dialogue,
        action,
        supernatural,
        emotional_start,
        emotional_end
    )

    for index, plan in enumerate(
        shots,
        start=1
    ):

        shot_id = (
            f"{scene_id}-SHOT-{index:03d}"
        )

        tier = plan[
            "animation_tier"
        ]

        if tier == "atmospheric":

            body = ["idle"]

            face = ["neutral"]

            environment_motion = "moderate"

        elif tier == "hero":

            body = [
                "gesture"
            ]

            face = [
                "conflicted"
            ]

            environment_motion = "subtle"

        else:

            body = [
                "gesture"
            ]

            face = [
                "neutral"
            ]

            environment_motion = "subtle"

        speech_required = (
            dialogue
            and plan["role"] == "dialogue"
        )

        shot = shot_engine[
            "create_shot"
        ](
            shot_id=shot_id,
            scene_id=scene_id,
            sequence_id=(
                f"{scene_id}-SEQ-001"
            ),
            duration_seconds=(
                plan["duration_seconds"]
            ),
            animation_tier=tier,
            purpose=plan["role"],
            characters=characters,
            location=location,
            props=props,
            camera={
                "shot_type": plan[
                    "shot_type"
                ],
                "movement": (
                    "push_in"
                    if plan["movement"]
                    == "slow_push_in"
                    else plan["movement"]
                )
            },
            character_performance={
                "body": body,
                "face": face,
                "speech": {
                    "required_when_dialogue": True,
                    "lip_sync_required": True
                }
            },
            environment_motion=(
                environment_motion
            ),
            lighting={
                "continuity_required": True,
                "changes_require_cause": True
            },
            effects={
                "effects": (
                    ["supernatural_energy"]
                    if supernatural
                    and plan["role"]
                    == "supernatural_payoff"
                    else []
                ),
                "effects_require_narrative_justification": True
            },
            audio={
                "dialogue": (
                    ["scene_dialogue"]
                    if speech_required
                    else []
                ),
                "sfx": [],
                "music": (
                    "scene_specific"
                )
            },
            state_before={},
            state_after={},
            causal_event_ids=causal_events
        )

        production_shots.append(
            shot
        )

    # ------------------------------------------------------------
    # SEQUENCE METADATA
    # ------------------------------------------------------------

    return {
        "scene_id": scene_id,

        "director_strategy": {
            "narrative_purpose": scene[
                "narrative_purpose"
            ],

            "emotional_arc": scene[
                "emotional_arc"
            ],

            # Scene-level requirements are deliberately
            # carried into the director plan so that
            # sequence QA can verify the output against
            # the actual scene contract.
            "characters": list(
                scene["characters"]
            ),

            "location": scene[
                "location"
            ],

            "props": list(
                scene["props"]
            ),

            "dialogue_present": bool(
                scene["dialogue_present"]
            ),

            "action_present": bool(
                scene["action_present"]
            ),

            "supernatural_present": bool(
                scene["supernatural_present"]
            ),

            "causal_event_ids": list(
                scene["causal_event_ids"]
            ),

            "coverage_strategy": [
                shot["role"]
                for shot in shots
            ],

            "selected_primary_tier": (
                selected_tier
            )
        },

        "shots": production_shots
    }


def validate_sequence(
    plan,
    bible,
    architecture,
    shot_engine
):

    errors = []

    shots = plan.get(
        "shots",
        []
    )

    if not shots:

        errors.append(
            "Scene produced zero shots."
        )

        return errors

    previous = None

    for index, shot in enumerate(
        shots,
        start=1
    ):

        shot_errors = shot_engine[
            "validate_shot"
        ](
            shot,
            bible,
            architecture
        )

        for error in shot_errors:

            errors.append(
                f"Shot {index}: {error}"
            )

        # --------------------------------------------------------
        # SEQUENCE CONTINUITY
        # --------------------------------------------------------

        if previous:

            if (
                shot["scene_id"]
                != previous["scene_id"]
            ):

                errors.append(
                    f"Shot {index}: "
                    "scene changed inside sequence."
                )

            if (
                shot["location"]
                != previous["location"]
            ):

                errors.append(
                    f"Shot {index}: "
                    "location changed without "
                    "scene transition."
                )

            if not shot[
                "continuity"
            ].get(
                "inherits_previous_shot_state"
            ):

                errors.append(
                    f"Shot {index}: "
                    "does not inherit previous state."
                )

        previous = shot

    # ------------------------------------------------------------
    # REPETITION CHECK
    # ------------------------------------------------------------

    signatures = []

    for shot in shots:

        signatures.append(
            (
                shot["animation_tier"],
                shot["camera"]["shot_type"],
                shot["camera"]["movement"]
            )
        )

    if (
        len(signatures) >= 5
        and len(set(signatures))
        < len(signatures) * 0.4
    ):

        errors.append(
            "Excessive camera/animation repetition."
        )

    # ------------------------------------------------------------
    # REQUIRED NARRATIVE COVERAGE
    # ------------------------------------------------------------

    strategy = plan.get(
        "director_strategy",
        {}
    )

    emotional_arc = strategy.get(
        "emotional_arc",
        {}
    )

    # A cinematic sequence requires an establishing shot
    # so the viewer receives spatial context before coverage.
    if not any(
        shot.get("purpose")
        == "establishing"
        for shot in shots
    ):

        errors.append(
            "Sequence has no establishing coverage."
        )

    # Dialogue scenes require dedicated dialogue coverage.
    if strategy.get(
        "dialogue_present",
        False
    ):

        if not any(
            shot.get("purpose")
            == "dialogue"
            for shot in shots
        ):

            errors.append(
                "Dialogue scene has no dialogue coverage."
            )

    # Supernatural scenes require an explicit payoff shot.
    if strategy.get(
        "supernatural_present",
        False
    ):

        if not any(
            shot.get("purpose")
            == "supernatural_payoff"
            for shot in shots
        ):

            errors.append(
                "Supernatural scene has no supernatural payoff."
            )

    # ------------------------------------------------------------
    # CAUSAL COVERAGE
    # ------------------------------------------------------------

    # The director plan itself is the authoritative
    # sequence contract. Do not depend on a separate
    # "scene" object being present in the output.
    strategy = plan.get(
        "director_strategy",
        {}
    )

    expected_events = set(
        strategy.get(
            "causal_event_ids",
            []
        )
    )

    if expected_events:

        for index, shot in enumerate(
            shots,
            start=1
        ):

            shot_events = set(
                shot.get(
                    "causal_event_ids",
                    []
                )
            )

            if not expected_events.issubset(
                shot_events
            ):

                errors.append(
                    f"Shot {index}: "
                    "missing required causal reference."
                )

    # ------------------------------------------------------------
    # PROP CONTINUITY
    # ------------------------------------------------------------

    expected_props = set(
        strategy.get(
            "props",
            []
        )
    )

    if expected_props:

        for index, shot in enumerate(
            shots,
            start=1
        ):

            shot_props = set(
                shot.get(
                    "props",
                    []
                )
            )

            if not expected_props.issubset(
                shot_props
            ):

                errors.append(
                    f"Shot {index}: "
                    "required scene prop missing."
                )

    # ------------------------------------------------------------
    # EMOTIONAL RESOLUTION
    # ------------------------------------------------------------

    if (
        emotional_arc.get("start")
        != emotional_arc.get("end")
    ):

        if not any(
            shot.get("purpose")
            == "emotional_resolution"
            for shot in shots
        ):

            errors.append(
                "Emotional arc has no resolution shot."
            )

    return errors


def main():

    print("=" * 60)
    print(
        "DEATHBOUND — PHASE 5C"
    )
    print(
        "SCENE-TO-SHOT DIRECTOR"
    )
    print("=" * 60)

    bible = load_json(
        BIBLE_PATH
    )

    architecture = load_json(
        ARCHITECTURE_PATH
    )

    shot_engine = load_shot_engine()

    # ------------------------------------------------------------
    # BUILD TEMPORARY QA SCENE
    # ------------------------------------------------------------

    qa_bible = deepcopy(
        bible
    )

    qa_bible["scene_registry"] = {
        "scene-qa-director": {
            "id": "scene-qa-director",
            "name": "Director QA Scene",
            "status": "qa_only",
            "characters": [
                "riven"
            ],
            "location": (
                "loc-daniel-bedroom"
            ),
            "props": [
                "prop-reapers-ledger"
            ]
        }
    }

    qa_bible["causal_events"] = [
        {
            "event_id": "event-qa-director",
            "scene_id": "scene-qa-director",
            "shot_id": None,
            "actor": "riven",
            "action": "observes",
            "cause": "QA director test",
            "state_change": {},
            "consequences": [],
            "timestamp": "QA"
        }
    ]

    scene = create_scene_brief(
        scene_id="scene-qa-director",
        narrative_purpose=(
            "Demonstrate a character entering "
            "a supernatural situation."
        ),
        emotional_start="neutral",
        emotional_end="conflicted",
        characters=[
            "riven"
        ],
        location=(
            "loc-daniel-bedroom"
        ),
        props=[
            "prop-reapers-ledger"
        ],
        dialogue_present=True,
        action_present=False,
        supernatural_present=True,
        causal_event_ids=[
            "event-qa-director"
        ]
    )

    print(
        "PASS  Temporary QA scene created."
    )

    # ------------------------------------------------------------
    # GENERATE PLAN
    # ------------------------------------------------------------

    plan = generate_director_plan(
        scene,
        qa_bible,
        architecture,
        shot_engine
    )

    print(
        f"PASS  Director generated "
        f"{len(plan['shots'])} shots."
    )

    # ------------------------------------------------------------
    # VALIDATE
    # ------------------------------------------------------------

    errors = validate_sequence(
        plan,
        qa_bible,
        architecture,
        shot_engine
    )

    if errors:

        print(
            "FAIL  Director sequence validation:"
        )

        for error in errors:

            print(
                f"       {error}"
            )

        sys.exit(1)

    print(
        "PASS  Sequence-level validation."
    )

    # ------------------------------------------------------------
    # DIRECTOR QUALITY CHECKS
    # ------------------------------------------------------------

    shots = plan["shots"]

    roles = [
        shot["purpose"]
        for shot in shots
    ]

    checks = {

        "establishing_coverage":
            "establishing" in roles,

        "character_coverage":
            "character_coverage" in roles,

        "dialogue_coverage":
            "dialogue" in roles,

        "reaction_coverage":
            "reaction" in roles,

        "supernatural_payoff":
            "supernatural_payoff" in roles,

        "emotional_resolution":
            "emotional_resolution" in roles,

        "multiple_shot_sequence":
            len(shots) >= 4,

        "state_inheritance":
            all(
                shot[
                    "continuity"
                ].get(
                    "inherits_previous_shot_state"
                )
                for shot in shots
            ),

        "causal_references":
            all(
                "event-qa-director"
                in shot[
                    "causal_event_ids"
                ]
                for shot in shots
            )
    }

    for name, passed in checks.items():

        if passed:

            print(
                f"PASS  {name}"
            )

        else:

            print(
                f"FAIL  {name}"
            )

    # ------------------------------------------------------------
    # OUTPUT
    # ------------------------------------------------------------

    output = {
        "schema_version": "1.0",
        "episode": "EP001",
        "status": "qa_validated",
        "scene": scene,
        "director_plan": plan,
        "qa": {
            "checks": checks,
            "overall": all(
                checks.values()
            )
        },
        "provenance": {
            "qa_scene_only": True,
            "invented_canon": False,
            "production_episode_content": False
        }
    }

    with open(
        OUTPUT_PATH,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("-" * 60)

    if all(checks.values()):

        print(
            "OVERALL: PASS"
        )

        print()
        print(
            "Scene-to-shot director output written to:"
        )

        print(
            OUTPUT_PATH
        )

        sys.exit(0)

    print(
        "OVERALL: FAIL"
    )

    sys.exit(1)


if __name__ == "__main__":
    main()



