import os
import queue
import threading
import time
import traceback
import uuid

from fastapi import FastAPI
from pydantic import BaseModel

MODEL_DIR = "/data/liyangyang/models/MiniMax-H3-NF4"
BASE_DIR = "/data/liyangyang/models/MiniMax-H3"
OUT_DIR = "/data/liyangyang/ai_drama/output/video_clips"

os.makedirs(OUT_DIR, exist_ok=True)

app = FastAPI(title="MiniMax-H3 Video Service")

jobs = {}
job_queue = queue.Queue()
pipe = None
model_ready = threading.Event()
FPS = 24


class GenReq(BaseModel):
    prompt: str
    size: str = "480*832"
    frame_num: int = 65
    seed: int = 42
    steps: int = 50
    job_id: str | None = None


def snap_frames(frame_num: int) -> int:
    target = max(round(frame_num * FPS / 16), 22)
    n = max(round((target - 5) / 17), 1)
    return 17 * n + 5


def load_pipe():
    global pipe
    import torch
    from diffsynth.pipelines.minimax_h3_audio_video import MiniMaxH3Pipeline, ModelConfig
    vram_config = {
        "offload_dtype": "disk",
        "offload_device": "disk",
        "onload_dtype": torch.bfloat16,
        "onload_device": "cpu",
        "preparing_dtype": torch.bfloat16,
        "preparing_device": "cuda",
        "computation_dtype": torch.bfloat16,
        "computation_device": "cuda",
    }
    free_gb = torch.cuda.mem_get_info("cuda")[1] / (1024 ** 3)
    pipe = MiniMaxH3Pipeline.from_pretrained(
        torch_dtype=torch.bfloat16,
        device="cuda",
        model_configs=[
            ModelConfig(path=f"{MODEL_DIR}/minimax-h3-fl2va-nf4.safetensors", **vram_config),
            ModelConfig(path=f"{MODEL_DIR}/minimax-h3-text-encoder-nf4.safetensors", **vram_config),
            ModelConfig(path=f"{MODEL_DIR}/video_vae_nf4.safetensors", **vram_config),
            ModelConfig(path=f"{MODEL_DIR}/audio_vae_nf4.safetensors", **vram_config),
        ],
        processor_config=ModelConfig(path=f"{BASE_DIR}/FL2VA/processor"),
        vram_limit=max(free_gb - 4, 4),
    )
    model_ready.set()


def make_pbar(job_id):
    def pbar(iterable):
        for i, x in enumerate(iterable):
            jobs[job_id]["step"] = i + 1
            yield x
    return pbar


def worker():
    from diffsynth.utils.data.audio_video import write_video_audio
    while True:
        job_id, req = job_queue.get()
        model_ready.wait()
        jobs[job_id].update(status="running", started=time.time())
        try:
            w, h = (int(x) for x in req.size.replace("x", "*").split("*"))
            frames = snap_frames(req.frame_num)
            jobs[job_id]["total_steps"] = req.steps
            video, audio = pipe(
                prompt=req.prompt,
                height=h, width=w,
                num_frames=frames,
                num_inference_steps=req.steps,
                seed=req.seed,
                progress_bar_cmd=make_pbar(job_id),
            )
            final = os.path.join(OUT_DIR, f"{job_id}.mp4")
            write_video_audio(video=video, audio=audio, output_path=final,
                              fps=FPS, audio_sample_rate=32000)
            jobs[job_id].update(status="done", video=f"video_clips/{job_id}.mp4",
                                elapsed=time.time() - jobs[job_id]["started"])
        except Exception:
            jobs[job_id].update(status="failed", error=traceback.format_exc()[-1500:])
        finally:
            jobs[job_id].pop("step", None)
            job_queue.task_done()


@app.on_event("startup")
async def startup():
    threading.Thread(target=load_pipe, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()


@app.post("/generate")
async def generate(req: GenReq):
    job_id = req.job_id or uuid.uuid4().hex[:12]
    jobs[job_id] = {"status": "queued", "queue": job_queue.qsize()}
    job_queue.put((job_id, req))
    return {"job_id": job_id, "position": job_queue.qsize()}


@app.get("/status/{job_id}")
async def status(job_id: str):
    return jobs.get(job_id, {"status": "unknown"})


@app.get("/progress/{job_id}")
async def progress(job_id: str):
    return jobs.get(job_id, {"status": "unknown"})


@app.get("/health")
async def health():
    return {"ok": True, "model_ready": model_ready.is_set(),
            "queue": job_queue.qsize(), "jobs": len(jobs)}
