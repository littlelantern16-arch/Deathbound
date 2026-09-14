import json, shutil, sys
from pathlib import Path

WORKFLOW = Path(r"C:\ComfyUI\Deathbound_Riven_FaceID.json")
BACKUP = WORKFLOW.with_name(WORKFLOW.stem + ".pre_visual_lock.backup.json")
DNA = Path(r"D:\Deathbound\config\DEATHBOUND_VISUAL_STYLE_DNA.json")

POSITIVE = """young adult man, slim lean ordinary build, believable human face, natural masculine facial proportions, subtle facial asymmetry, normal sized eyes, natural nose and jaw, slightly messy black hair, pale slightly desaturated skin with subtle natural texture, dark eyes, calm observant expression, understated attractiveness, charcoal black hooded coat, dark fitted shirt, black trousers, practical black boots, minimal silver details, ordinary contemporary American city at night, cinematic motivated lighting, natural human anatomy, realistic hair and fabric, restrained cinematic animation stylization, premium mature supernatural drama, atmospheric depth, natural perspective"""

NEGATIVE = """anime, manga, cartoon face, oversized eyes, giant eyes, kawaii, chibi, pretty boy, feminine face, feminine body, fashion model, flawless skin, plastic skin, glamour, influencer portrait, child, teenager, old man, bodybuilder, exaggerated anatomy, oversized head, fantasy armor, ornate costume, grim reaper, skull face, giant scythe, giant cloak, medieval fantasy, Roblox, voxel, blocky anatomy, low poly, 3D game character, game avatar, toy-like character, 3D render, photorealistic influencer, excessive beauty retouching, beach, ocean, sunset, duplicate person, extra limbs, extra fingers, malformed hands, distorted face"""

def main():
    if not WORKFLOW.exists():
        raise SystemExit(f"Workflow not found: {WORKFLOW}")
    if not BACKUP.exists():
        shutil.copy2(WORKFLOW, BACKUP)

    data = json.loads(WORKFLOW.read_text(encoding="utf-8"))

    nodes = data.get("prompt", data)
    if not isinstance(nodes, dict):
        raise SystemExit("Unsupported workflow JSON structure.")

    changed = []
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        ct = node.get("class_type", "")
        inputs = node.get("inputs", {})
        if "CheckpointLoader" in ct:
            old = inputs.get("ckpt_name")
            if old:
                inputs["ckpt_name"] = "Realistic_Vision_V6.0_B1_pruned.safetensors"
                changed.append(f"{node_id}: checkpoint")
        if ct == "CLIPTextEncode":
            text = inputs.get("text", "")
            if isinstance(text, str):
                if any(x in text.lower() for x in ["female", "woman", "girl", "anime", "roblox", "young adult man", "riven"]):
                    # Determine positive/negative by whether the current text contains common negative anchors.
                    if any(x in text.lower() for x in ["female", "woman", "girl", "anime", "roblox", "extra fingers"]):
                        inputs["text"] = NEGATIVE
                        changed.append(f"{node_id}: negative prompt")
                    else:
                        inputs["text"] = POSITIVE
                        changed.append(f"{node_id}: positive prompt")
        if ct == "IPAdapterFaceID":
            if "weight" in inputs:
                inputs["weight"] = 0.75
                changed.append(f"{node_id}: FaceID weight")
            if "weight_faceidv2" in inputs:
                inputs["weight_faceidv2"] = 2.0
                changed.append(f"{node_id}: FaceID V2 weight")
        if ct == "KSampler":
            if "steps" in inputs:
                inputs["steps"] = 28
            if "cfg" in inputs:
                inputs["cfg"] = 6.0
            if "sampler_name" in inputs:
                inputs["sampler_name"] = "dpmpp_2m"
            if "scheduler" in inputs:
                inputs["scheduler"] = "karras"
            changed.append(f"{node_id}: sampler defaults")

    WORKFLOW.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print("VISUAL LOCK APPLIED")
    print(f"Backup: {BACKUP}")
    print("Changes:")
    for x in changed:
        print(" -", x)

if __name__ == "__main__":
    main()
