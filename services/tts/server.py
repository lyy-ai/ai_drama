import asyncio
import os
import sys
import time
import uuid

import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

COSY_DIR = "/data/liyangyang/ai_drama/services/tts/CosyVoice"
sys.path.append(COSY_DIR)
sys.path.append(os.path.join(COSY_DIR, "third_party", "Matcha-TTS"))

MODEL_DIR = "/data/liyangyang/models/CosyVoice-300M-SFT"
OUT_DIR = "/data/liyangyang/ai_drama/output/audio"
os.makedirs(OUT_DIR, exist_ok=True)

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "1")

from cosyvoice.cli.cosyvoice import CosyVoice as CosyVoiceModel

app = FastAPI(title="CosyVoice2 TTS Service")

model = None
spks = []
lock = asyncio.Lock()


class TTSReq(BaseModel):
    text: str
    spk: str = "中文女"
    speed: float = 1.0
    emotion: str | None = None
    job_id: str | None = None


@app.on_event("startup")
async def startup():
    global model, spks
    def _load():
        m = CosyVoiceModel(MODEL_DIR, load_jit=False, load_trt=False, fp16=False)
        return m, m.list_available_spks()
    global model, spks
    model, spks = await asyncio.to_thread(_load)


@app.post("/tts")
async def tts(req: TTSReq):
    if model is None:
        raise HTTPException(503, "model not ready")
    if req.spk not in spks:
        raise HTTPException(400, f"unknown spk {req.spk}, available: {spks}")
    job_id = req.job_id or uuid.uuid4().hex[:12]
    text = req.text
    if req.emotion:
        text = f"[{req.emotion}]{text}"
    t0 = time.time()

    def _run():
        outs = []
        for out in model.inference_sft(text, req.spk, stream=False, speed=req.speed):
            outs.append(out["tts_speech"])
        return outs

    async with lock:
        outs = await asyncio.to_thread(_run)
    if not outs:
        raise HTTPException(500, "no audio generated")
    audio = torch.cat(outs, dim=1)
    path = os.path.join(OUT_DIR, f"{job_id}.wav")
    sf.write(path, audio.squeeze(0).cpu().numpy(), model.sample_rate)
    dur = audio.shape[1] / model.sample_rate
    return {"job_id": job_id, "audio": f"audio/{job_id}.wav", "duration": round(dur, 3),
            "elapsed": round(time.time() - t0, 2)}


@app.get("/speakers")
async def speakers():
    return {"speakers": spks}


@app.get("/health")
async def health():
    return {"ok": model is not None, "speakers": len(spks)}
