import asyncio
import os
import re
import time
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

WAN_DIR = "/data/liyangyang/Wan2.1"
CKPT_DIR = "/data/liyangyang/models/Wan2.1-T2V-1.3B"
PYTHON = "/data/liyangyang/qwen35_env/bin/python"
OUT_DIR = "/data/liyangyang/ai_drama/output/video_clips"
LOG_DIR = "/data/liyangyang/ai_drama/logs/video"

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

app = FastAPI(title="Wan2.1 Video Service")

jobs = {}
queue = asyncio.Queue()
worker_task = None


class GenReq(BaseModel):
    prompt: str
    size: str = "480*832"
    frame_num: int = 65
    seed: int = 42
    steps: int = 50
    job_id: str | None = None


async def worker():
    while True:
        job_id, req = await queue.get()
        jobs[job_id]["status"] = "running"
        jobs[job_id]["started"] = time.time()
        tag = f"{job_id}"
        log_path = os.path.join(LOG_DIR, f"{tag}.log")
        cmd = [
            PYTHON, "generate.py",
            "--task", "t2v-1.3B",
            "--size", req.size,
            "--frame_num", str(req.frame_num),
            "--ckpt_dir", CKPT_DIR,
            "--base_seed", str(req.seed),
            "--sample_steps", str(req.steps),
            "--offload_model", "True",
            "--t5_cpu",
            "--prompt", req.prompt,
        ]
        env = dict(os.environ)
        env["CUDA_VISIBLE_DEVICES"] = "0"
        env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
        env["PYTHONUNBUFFERED"] = "1"
        with open(log_path, "w") as lf:
            proc = await asyncio.create_subprocess_exec(
                *cmd, cwd=WAN_DIR, stdout=lf, stderr=asyncio.subprocess.STDOUT, env=env)
            await proc.wait()
        mp4 = find_output(log_path)
        if proc.returncode == 0 and mp4 and os.path.exists(mp4):
            final = os.path.join(OUT_DIR, f"{job_id}.mp4")
            os.replace(mp4, final)
            jobs[job_id].update(status="done", video=f"video_clips/{job_id}.mp4",
                                elapsed=time.time() - jobs[job_id]["started"])
        else:
            tail = ""
            try:
                tail = open(log_path).read()[-1500:]
            except Exception:
                pass
            jobs[job_id].update(status="failed", error=tail)
        queue.task_done()


def find_output(log_path):
    try:
        text = open(log_path, errors="ignore").read()
    except Exception:
        return None
    m = re.findall(r"Saving generated video to (\S+\.mp4)", text)
    if m:
        p = m[-1]
        if not os.path.isabs(p):
            p = os.path.join(WAN_DIR, p)
        return p
    return None


@app.on_event("startup")
async def startup():
    global worker_task
    worker_task = asyncio.create_task(worker())


@app.post("/generate")
async def generate(req: GenReq):
    job_id = req.job_id or uuid.uuid4().hex[:12]
    jobs[job_id] = {"status": "queued", "queue": queue.qsize()}
    await queue.put((job_id, req))
    return {"job_id": job_id, "position": queue.qsize()}


@app.get("/status/{job_id}")
async def status(job_id: str):
    return jobs.get(job_id, {"status": "unknown"})


@app.get("/progress/{job_id}")
async def progress(job_id: str):
    log_path = os.path.join(LOG_DIR, f"{job_id}.log")
    info = jobs.get(job_id, {"status": "unknown"})
    if os.path.exists(log_path):
        try:
            text = open(log_path, errors="ignore").read()
            m = re.findall(r"(\d+)/50 \[", text)
            if m:
                info["step"] = int(m[-1])
                info["total_steps"] = 50
        except Exception:
            pass
    return info


@app.get("/health")
async def health():
    return {"ok": True, "queue": queue.qsize(), "jobs": len(jobs)}
