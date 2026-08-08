import asyncio
import base64
import json
import os
import uuid

import httpx

LLM_URL = "http://127.0.0.1:10048/v1/chat/completions"
COMFY_URL = "http://127.0.0.1:10047"
VIDEO_URL = "http://127.0.0.1:10050"
TTS_URL = "http://127.0.0.1:10049"

WF_PATH = "/data/liyangyang/ai_drama/workflows/sdxl_txt2img.json"
OUT_ROOT = "/data/liyangyang/ai_drama/output"

STYLE_EN = {
    "写实": "photorealistic, cinematic film still, realistic lighting",
    "动漫": "anime style, high quality anime screenshot, cel shading",
    "古风": "chinese ancient style, traditional costume, cinematic, ink painting atmosphere",
    "都市": "modern urban, cinematic film still, realistic",
    "悬疑": "dark cinematic lighting, film noir, suspense atmosphere",
    "科幻": "sci-fi, futuristic, cinematic lighting",
}

DEFAULT_STYLE = "cinematic film still, dramatic lighting, highly detailed"


async def llm_json(system: str, user: str, retries: int = 3, timeout: float = 300.0):
    last = None
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient(timeout=timeout) as cli:
                r = await cli.post(LLM_URL, json={
                    "model": "qwen35-9b",
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    "temperature": 0.7,
                    "response_format": {"type": "json_object"},
                    "max_tokens": 3000,
                })
                r.raise_for_status()
                content = r.json()["choices"][0]["message"]["content"]
                return json.loads(content)
        except Exception as e:
            last = e
            await asyncio.sleep(2)
    raise RuntimeError(f"LLM failed after {retries} tries: {last}")


async def comfy_txt2img(prompt_en: str, seed: int, prefix: str, timeout: float = 300.0):
    wf = json.load(open(WF_PATH))
    wf["6"]["inputs"]["text"] = prompt_en
    wf["3"]["inputs"]["seed"] = seed
    wf["9"]["inputs"]["filename_prefix"] = prefix
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(f"{COMFY_URL}/prompt", json={"prompt": wf})
        r.raise_for_status()
        prompt_id = r.json()["prompt_id"]
        t0 = asyncio.get_event_loop().time()
        while True:
            await asyncio.sleep(2)
            h = await cli.get(f"{COMFY_URL}/history/{prompt_id}")
            h.raise_for_status()
            data = h.json()
            if prompt_id in data and data[prompt_id].get("status", {}).get("completed"):
                outs = data[prompt_id]["outputs"]
                for node in outs.values():
                    if "images" in node:
                        img = node["images"][0]
                        break
                else:
                    raise RuntimeError("no image output")
                break
            if asyncio.get_event_loop().time() - t0 > timeout:
                raise TimeoutError("comfy timeout")
        v = await cli.get(f"{COMFY_URL}/view", params={
            "filename": img["filename"], "subfolder": img.get("subfolder", ""),
            "type": img.get("type", "output")})
        v.raise_for_status()
        return v.content


async def video_generate(prompt: str, job_id: str, seed: int = 42, size: str = "480*832",
                         frame_num: int = 65, timeout: float = 3600.0, progress_cb=None):
    async with httpx.AsyncClient(timeout=60) as cli:
        r = await cli.post(f"{VIDEO_URL}/generate", json={
            "prompt": prompt, "job_id": job_id, "seed": seed,
            "size": size, "frame_num": frame_num})
        r.raise_for_status()
        t0 = asyncio.get_event_loop().time()
        errors = 0
        while True:
            await asyncio.sleep(5)
            try:
                s = await cli.get(f"{VIDEO_URL}/progress/{job_id}")
                info = s.json()
                errors = 0
            except Exception:
                errors += 1
                if errors > 12:
                    raise
                continue
            if progress_cb and info.get("step"):
                await progress_cb(info["step"], info.get("total_steps", 50))
            if info.get("status") == "done":
                return info["video"]
            if info.get("status") == "failed":
                raise RuntimeError(f"video failed: {info.get('error', '')[-500:]}")
            if asyncio.get_event_loop().time() - t0 > timeout:
                raise TimeoutError("video timeout")


async def tts_generate(text: str, spk: str, job_id: str, speed: float = 1.0,
                       emotion: str | None = None, retries: int = 2):
    last = None
    for _ in range(retries):
        try:
            async with httpx.AsyncClient(timeout=120) as cli:
                r = await cli.post(f"{TTS_URL}/tts", json={
                    "text": text, "spk": spk, "job_id": job_id,
                    "speed": speed, "emotion": emotion})
                r.raise_for_status()
                return r.json()
        except Exception as e:
            last = e
            await asyncio.sleep(1)
    raise RuntimeError(f"tts failed: {last}")


async def comfy_free():
    """释放 ComfyUI 显存（视频生成前调用）"""
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(f"{COMFY_URL}/free", json={"unload_models": True, "free_memory": True})
    except Exception:
        pass


async def service_health():
    out = {}
    async with httpx.AsyncClient(timeout=5) as cli:
        for name, url in [("llm", "http://127.0.0.1:10048/v1/models"),
                          ("comfy", f"{COMFY_URL}/system_stats"),
                          ("video", f"{VIDEO_URL}/health"),
                          ("tts", f"{TTS_URL}/health")]:
            try:
                r = await cli.get(url)
                out[name] = r.status_code == 200
            except Exception:
                out[name] = False
    return out
