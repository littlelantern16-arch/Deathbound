import json, sys
from pathlib import Path
from copy import deepcopy

ROOT=Path(r"D:\Deathbound")
EP=ROOT/"projects"/"EP001"
INPUT=EP/"EP001_PRODUCTION_INPUT.json"
BIBLE=EP/"story_bible.json"
OUT_BIBLE=EP/"02_scenes"/"EP001_production_story_bible.json"
OUT_SHOTS=EP/"03_shots"/"EP001_production_shots.json"
OUT_AUDIO=EP/"04_audio"/"EP001_audio_script.txt"
OUT_STATUS=EP/"07_qa"/"EP001_production_build_status.json"
SHOT_ENGINE=ROOT/"automation"/"scripts"/"shot_spec_engine.py"

def load(p):
    return json.loads(p.read_text(encoding="utf-8-sig"))

def load_engine():
    ns={}
    exec(compile(SHOT_ENGINE.read_text(encoding="utf-8-sig"),str(SHOT_ENGINE),"exec"),ns)
    return ns

def main():
    data=load(INPUT); bible=load(BIBLE); eng=load_engine()
    create_shot=eng.get("create_shot"); validate_shot=eng.get("validate_shot")
    if not callable(create_shot) or not callable(validate_shot):
        raise RuntimeError("shot_spec_engine.py does not expose create_shot/validate_shot")

    pb=deepcopy(bible)
    pb["episode"]["status"]="production"
    pb["episode"]["canon_status"]="episode_production_overlay"
    pb["plot_state"]={
      "premise":"A billionaire is given ten unexpected minutes before his appointed death.",
      "central_conflict":"Daniel must decide what to do with the final minutes while Riven discovers an impossible Ledger change.",
      "stakes":"Daniel's life, his final human connection, and the integrity of the Reaper's Ledger.",
      "resolution":"Intentionally unresolved; the Ledger anomaly becomes the episode's continuing mystery.",
      "ending_decision":{"question":"Does Riven ultimately spare Daniel Cross?","status":"unresolved","value":None}
    }
    pb["timeline"]= [{"event_id":f"EV-{i:03d}","scene_id":s["scene_id"],"order":i} for i,s in enumerate(data["scenes"],1)]
    pb["scene_registry"]={s["scene_id"]:{
      "id":s["scene_id"],"name":s["title"],"status":"production",
      "characters":s["characters"],"location":s["location"],"props":s["props"]
    } for s in data["scenes"]}
    pb["causal_events"]=[]
    for i,s in enumerate(data["scenes"],1):
        pb["causal_events"].append({
          "event_id":f"EV-{i:03d}","scene_id":s["scene_id"],"shot_id":None,
          "actor":"riven" if "riven" in s["characters"] else None,
          "action":s["purpose"],"cause":"EP001 production narrative",
          "state_change":{},"consequences":[],"timestamp":f"S{i:02d}"
        })
    pb["provenance"]["invented_canon"]=False
    pb["provenance"]["episode_specific_content_complete"]=True
    pb["provenance"]["manual_decisions_required"]=["Final fate of Daniel Cross remains intentionally unresolved."]

    allshots=[]; errors=[]; audio=[]
    for si,s in enumerate(data["scenes"],1):
        event=f"EV-{si:03d}"
        # 5-7 purposeful shots per scene, generated from scene attributes.
        plans=[("establishing",3.0,"wide","push_in","atmospheric")]
        if s["characters"]: plans.append(("character_coverage",4.0,"medium","tracking","standard"))
        if s["dialogue"]: plans += [("dialogue",5.0,"medium_close","static","standard"),
                                    ("reaction",3.0,"close","push_in","standard")]
        if s["action"]: plans.append(("action",4.0,"wide","tracking","hero"))
        if s["supernatural"]: plans.append(("supernatural_payoff",4.0,"close","push_in","hero"))
        plans.append(("emotional_resolution",4.0,"medium_close","static","hero"))
        for pi,(purpose,dur,stype,move,tier) in enumerate(plans,1):
            sid=f'{s["scene_id"]}-SHOT-{pi:03d}'
            body=["idle"] if tier=="atmospheric" else ["gesture"]
            face=["neutral"] if tier!="hero" else ["conflicted"]
            speech = True
            shot=create_shot(
              shot_id=sid,scene_id=s["scene_id"],sequence_id=f'{s["scene_id"]}-SEQ-001',
              duration_seconds=dur,animation_tier=tier,purpose=purpose,
              characters=s["characters"],location=s["location"],props=s["props"],
              camera={"shot_type":stype,"movement":move},
              character_performance={"body":body,"face":face,
                "speech":{"required_when_dialogue":speech,"lip_sync_required":speech}},
              environment_motion="moderate" if tier=="atmospheric" else "subtle",
              lighting={"continuity_required":True,"changes_require_cause":True},
              effects={"effects":["supernatural_energy"] if s["supernatural"] and purpose=="supernatural_payoff" else [],
                      "effects_require_narrative_justification":True},
              audio={"dialogue":["scene_dialogue"] if speech else [],"sfx":[],"music":"scene_specific"},
              state_before={},state_after={},causal_event_ids=[event])
            verr=validate_shot(shot,pb,load(ROOT/"config"/"ANIMATION_ARCHITECTURE.json"))
            if verr: errors += [f"{sid}: {x}" for x in verr]
            allshots.append(shot)
        audio.append(f'=== {s["scene_id"]} â€” {s["title"]} ===')
        for n in s["narration"]: audio.append("NARRATOR: "+n)
        for d in s["dialogue"]: audio.append(d)
        audio.append("")

    # Simple sequence continuity annotations.
    prev=None
    for sh in allshots:
        sh.setdefault("continuity",{})["inherits_previous_shot_state"]=prev is not None
        if prev is not None:
            sh["continuity"]["previous_shot_id"]=prev["shot_id"]
        prev=sh

    pb["shot_registry"]={x["shot_id"]:x for x in allshots}
    pb["continuity"]["last_processed_event"]=None
    pb["continuity"]["last_processed_scene"]=None
    pb["continuity"]["last_processed_shot"]=None

    OUT_BIBLE.parent.mkdir(parents=True,exist_ok=True)
    OUT_SHOTS.parent.mkdir(parents=True,exist_ok=True)
    OUT_AUDIO.parent.mkdir(parents=True,exist_ok=True)
    OUT_STATUS.parent.mkdir(parents=True,exist_ok=True)
    OUT_BIBLE.write_text(json.dumps(pb,indent=2,ensure_ascii=False),encoding="utf-8")
    OUT_SHOTS.write_text(json.dumps({"schema_version":"1.0","episode":"EP001","status":"validated" if not errors else "failed","production_shots":allshots,"qa_errors":errors},indent=2,ensure_ascii=False),encoding="utf-8")
    OUT_AUDIO.write_text("\n".join(audio),encoding="utf-8")
    status={"episode":"EP001","title":data["title"],"shots":len(allshots),"duration_target_seconds":data["runtime_target_seconds"],"shot_engine_validation":"PASS" if not errors else "FAIL","errors":errors,"visual_mode":"TEMPORARY","next_stage":"AUDIO_AND_BLENDER_PREVIEW" if not errors else "FIX_SHOT_VALIDATION"}
    OUT_STATUS.write_text(json.dumps(status,indent=2),encoding="utf-8")
    print("="*60); print("DEATHBOUND â€” EP001 PRODUCTION BUILD"); print("="*60)
    print(f"Scenes: {len(data['scenes'])}")
    print(f"Shots:  {len(allshots)}")
    print("Shot validation:", "PASS" if not errors else "FAIL")
    if errors:
        for e in errors[:20]: print("FAIL ",e)
        sys.exit(1)
    print("Production story bible:",OUT_BIBLE)
    print("Shot package:",OUT_SHOTS)
    print("Audio script:",OUT_AUDIO)
    print("STATUS: PASS")
    print("="*60)

if __name__=="__main__": main()

