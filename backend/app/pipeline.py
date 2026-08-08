import asyncio
import os
import re
import traceback

from . import assemble, clients, db, prompts

OUT_ROOT = "/data/liyangyang/ai_drama/output"
VIDEO_SIZE = "480*832"
FRAME_NUM = 65

produce_tasks = {}
subscribers = {}


def pid_dir(pid):
    d = os.path.join(OUT_ROOT, pid)
    for sub in ["characters", "keyframes", "shots"]:
        os.makedirs(os.path.join(d, sub), exist_ok=True)
    return d


async def broadcast(pid, event: dict):
    event["project_id"] = pid
    for ws in list(subscribers.get(pid, [])):
        try:
            await ws.send_json(event)
        except Exception:
            subscribers[pid].discard(ws)


def shot_key(ep, shot):
    return f"e{ep['index']}_s{shot['shot_id']}"


def all_shots(script):
    for ep in script.get("episodes", []):
        for shot in ep.get("shots", []):
            yield ep, shot


def get_status(script):
    return script.setdefault("_status", {})


async def run_script_task(pid, synopsis, style, episodes, shots_per_episode):
    db.update_project(pid, status="running", stage="script")
    await broadcast(pid, {"type": "stage", "stage": "script", "status": "running"})
    try:
        script = await clients.llm_json(
            prompts.SCRIPT_SYSTEM,
            prompts.script_user(synopsis, style, episodes, shots_per_episode))
        validate_script(script)
        script["_status"] = {
            "characters": {c["name"]: "pending" for c in script["characters"]},
            "shots": {shot_key(ep, s): {"keyframe": "pending", "video": "pending"}
                      for ep, s in all_shots(script)},
        }
        db.save_script(pid, script)
        db.update_project(pid, title=script.get("title", ""), status="script_done", stage="script")
        await broadcast(pid, {"type": "stage", "stage": "script", "status": "done"})
        return script
    except Exception as e:
        traceback.print_exc()
        db.update_project(pid, status="failed", stage="script")
        await broadcast(pid, {"type": "stage", "stage": "script", "status": "failed", "error": str(e)})
        raise


def validate_script(script):
    assert isinstance(script.get("characters"), list) and script["characters"], "characters missing"
    assert isinstance(script.get("episodes"), list) and script["episodes"], "episodes missing"
    names = {c["name"] for c in script["characters"]}
    for c in script["characters"]:
        c.setdefault("appearance", c["name"])
    for ep, shot in all_shots(script):
        shot.setdefault("duration", 4)
        shot.setdefault("dialogue", [])
        shot.setdefault("camera", "中景")
        assert shot.get("first_frame_prompt"), "first_frame_prompt missing"
        assert shot.get("video_prompt"), "video_prompt missing"
        for d in shot["dialogue"]:
            if d.get("character") not in names:
                d["character"] = script["characters"][0]["name"]
            d.setdefault("emotion", "平静")


async def gen_character(pid, script, char):
    from .clients import STYLE_EN, DEFAULT_STYLE
    style_en = STYLE_EN.get(db.get_project(pid).get("style", ""), DEFAULT_STYLE)
    prompt = f"portrait of {char['appearance']}, {style_en}, upper body, looking at camera, masterpiece, best quality"
    seed = abs(hash(pid + char["name"])) % (2**31)
    img = await clients.comfy_txt2img(prompt, seed, f"{pid}_char_{char['name']}")
    path = os.path.join(pid_dir(pid), "characters", f"{char['name']}.png")
    with open(path, "wb") as f:
        f.write(img)
    return f"{pid}/characters/{char['name']}.png"


async def gen_keyframe(pid, script, ep, shot):
    from .clients import STYLE_EN, DEFAULT_STYLE
    style_en = STYLE_EN.get(db.get_project(pid).get("style", ""), DEFAULT_STYLE)
    prompt = f"{shot['first_frame_prompt']}, {style_en}, vertical composition"
    seed = abs(hash(pid + shot_key(ep, shot))) % (2**31)
    key = shot_key(ep, shot)
    img = await clients.comfy_txt2img(prompt, seed, f"{pid}_{key}")
    path = os.path.join(pid_dir(pid), "keyframes", f"{key}.png")
    with open(path, "wb") as f:
        f.write(img)
    return f"{pid}/keyframes/{key}.png"


def h3_prompt(script, shot):
    """video_prompt + 台词语音指令（H3 原生音画同步）"""
    chars = {c["name"]: c for c in script["characters"]}
    speech = []
    for d in shot.get("dialogue", []):
        gender = chars.get(d["character"], {}).get("gender")
        voice = "女声" if gender == "female" else "男声"
        emotion = d.get("emotion", "平静")
        speech.append(f'{d["character"]}用{emotion}的{voice}说："{d["line"]}"')
    prompt = shot["video_prompt"].rstrip("。")
    if speech:
        prompt += "。" + "；".join(speech)
    return prompt


async def gen_video_for_shot(pid, script, ep, shot, progress_cb=None):
    key = shot_key(ep, shot)
    seed = abs(hash(pid + key + "video")) % (2**31)
    kf = os.path.join(OUT_ROOT, pid, "keyframes", f"{key}.png")
    video_rel = await clients.video_generate(
        h3_prompt(script, shot), f"{pid}_{key}", seed=seed,
        size=VIDEO_SIZE, frame_num=FRAME_NUM,
        keyframe=kf if os.path.exists(kf) else None, progress_cb=progress_cb)
    return video_rel


async def run_production(pid):
    script = db.load_script(pid)
    if not script:
        raise RuntimeError("script not found")
    status = get_status(script)
    try:
        # S1 characters
        db.update_project(pid, status="running", stage="characters")
        for char in script["characters"]:
            if status["characters"].get(char["name"]) == "done":
                continue
            await broadcast(pid, {"type": "character", "name": char["name"], "status": "running"})
            try:
                await gen_character(pid, script, char)
                status["characters"][char["name"]] = "done"
            except Exception as e:
                status["characters"][char["name"]] = "failed"
                await broadcast(pid, {"type": "character", "name": char["name"], "status": "failed", "error": str(e)})
                raise
            db.save_script(pid, script)
            await broadcast(pid, {"type": "character", "name": char["name"], "status": "done"})

        # S2 keyframes
        db.update_project(pid, stage="keyframes")
        for ep, shot in all_shots(script):
            key = shot_key(ep, shot)
            if status["shots"][key]["keyframe"] == "done":
                continue
            await broadcast(pid, {"type": "shot", "shot": key, "stage": "keyframe", "status": "running"})
            try:
                await gen_keyframe(pid, script, ep, shot)
                status["shots"][key]["keyframe"] = "done"
            except Exception as e:
                status["shots"][key]["keyframe"] = "failed"
                await broadcast(pid, {"type": "shot", "shot": key, "stage": "keyframe", "status": "failed", "error": str(e)})
                raise
            db.save_script(pid, script)
            await broadcast(pid, {"type": "shot", "shot": key, "stage": "keyframe", "status": "done"})

        # S3 videos（H3 原生音画同步，无需单独配音）
        db.update_project(pid, stage="videos")
        await clients.comfy_free()
        for ep, shot in all_shots(script):
            key = shot_key(ep, shot)
            if status["shots"][key]["video"] == "done":
                continue
            await broadcast(pid, {"type": "shot", "shot": key, "stage": "video", "status": "running"})

            async def pcb(step, total, key=key):
                await broadcast(pid, {"type": "shot", "shot": key, "stage": "video",
                                      "status": "running", "step": step, "total": total})
            try:
                await gen_video_for_shot(pid, script, ep, shot, pcb)
                status["shots"][key]["video"] = "done"
            except Exception as e:
                status["shots"][key]["video"] = "failed"
                await broadcast(pid, {"type": "shot", "shot": key, "stage": "video", "status": "failed", "error": str(e)})
                raise
            db.save_script(pid, script)
            await broadcast(pid, {"type": "shot", "shot": key, "stage": "video", "status": "done"})

        # S4 assemble（视频已自带同步音频，直接拼接 + 烧字幕）
        db.update_project(pid, stage="assembling")
        await broadcast(pid, {"type": "stage", "stage": "assemble", "status": "running"})
        ep_files = []
        for ep in script["episodes"]:
            clip_files = []
            subtitles = []
            t = 0.0
            for shot in ep["shots"]:
                key = shot_key(ep, shot)
                clip = os.path.join(OUT_ROOT, "video_clips", f"{pid}_{key}.mp4")
                dur = await assemble.ffprobe_duration(clip)
                lines = shot.get("dialogue", [])
                if lines:
                    weights = [max(len(d["line"]), 1) for d in lines]
                    total = sum(weights)
                    tt = t + 0.3
                    for d, w in zip(lines, weights):
                        seg = max((dur - 0.6) * w / total, 0.8)
                        subtitles.append({"start": tt, "end": min(tt + seg, t + dur),
                                          "text": f"{d['character']}：{d['line']}"})
                        tt += seg
                t += dur
                clip_files.append(clip)
            ep_out = os.path.join(pid_dir(pid), f"episode_{ep['index']}.mp4")
            await assemble.assemble_episode(clip_files, subtitles, ep_out)
            ep_files.append(ep_out)
        final = os.path.join(pid_dir(pid), "final.mp4")
        await assemble.concat_episodes(ep_files, final)
        db.update_project(pid, status="done", stage="done")
        await broadcast(pid, {"type": "stage", "stage": "assemble", "status": "done"})
        await broadcast(pid, {"type": "project", "status": "done", "final": f"{pid}/final.mp4"})
    except Exception as e:
        traceback.print_exc()
        db.update_project(pid, status="failed")
        await broadcast(pid, {"type": "project", "status": "failed", "error": str(e)})
        raise
    finally:
        produce_tasks.pop(pid, None)


def start_production(pid):
    if pid in produce_tasks and not produce_tasks[pid].done():
        return False
    produce_tasks[pid] = asyncio.create_task(run_production(pid))
    return True
