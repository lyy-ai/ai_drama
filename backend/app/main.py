import asyncio
import uuid

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import clients, db, pipeline

app = FastAPI(title="AI Drama Platform")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

db.init()

OUT_ROOT = "/data/liyangyang/ai_drama/output"
app.mount("/static/output", StaticFiles(directory=OUT_ROOT), name="output")


class CreateReq(BaseModel):
    synopsis: str
    style: str = "都市"
    episodes: int = 1
    shots_per_episode: int = 6
    auto_produce: bool = False


@app.post("/api/projects")
async def create_project(req: CreateReq):
    pid = uuid.uuid4().hex[:10]
    db.create_project(pid, "生成中...", req.synopsis, req.style,
                      req.episodes, req.shots_per_episode)

    async def _run():
        try:
            await pipeline.run_script_task(pid, req.synopsis, req.style,
                                           req.episodes, req.shots_per_episode)
            if req.auto_produce:
                pipeline.start_production(pid)
        except Exception:
            pass
    asyncio.create_task(_run())
    return {"project_id": pid}


@app.get("/api/projects")
async def list_projects():
    return {"projects": db.list_projects()}


@app.get("/api/projects/{pid}")
async def get_project(pid: str):
    p = db.get_project(pid)
    if not p:
        raise HTTPException(404)
    script = db.load_script(pid)
    return {"project": p, "script": script}


@app.put("/api/projects/{pid}/script")
async def save_script(pid: str, script: dict):
    if not db.get_project(pid):
        raise HTTPException(404)
    script.pop("_status", None)
    old = db.load_script(pid)
    if old and "_status" in old:
        script["_status"] = old["_status"]
    pipeline.validate_script(script)
    db.save_script(pid, script)
    return {"ok": True}


@app.post("/api/projects/{pid}/produce")
async def produce(pid: str):
    if not db.load_script(pid):
        raise HTTPException(400, "script not ready")
    ok = pipeline.start_production(pid)
    return {"started": ok}


@app.post("/api/projects/{pid}/regen_script")
async def regen_script(pid: str):
    p = db.get_project(pid)
    if not p:
        raise HTTPException(404)
    asyncio.create_task(pipeline.run_script_task(
        pid, p["synopsis"], p["style"], p["episodes"], p["shots_per_episode"]))
    return {"ok": True}


@app.post("/api/projects/{pid}/characters/{name}/regen")
async def regen_character(pid: str, name: str):
    script = db.load_script(pid)
    char = next((c for c in script["characters"] if c["name"] == name), None)
    if not char:
        raise HTTPException(404)
    rel = await pipeline.gen_character(pid, script, char)
    return {"ok": True, "image": rel}


@app.post("/api/projects/{pid}/shots/{ep_idx}/{shot_id}/regen")
async def regen_shot(pid: str, ep_idx: int, shot_id: int, stage: str):
    script = db.load_script(pid)
    target = None
    for ep, shot in pipeline.all_shots(script):
        if ep["index"] == ep_idx and shot["shot_id"] == shot_id:
            target = (ep, shot)
    if not target:
        raise HTTPException(404)
    ep, shot = target
    status = pipeline.get_status(script)
    key = pipeline.shot_key(ep, shot)
    if stage == "keyframe":
        rel = await pipeline.gen_keyframe(pid, script, ep, shot)
        status["shots"][key]["keyframe"] = "done"
    elif stage == "video":
        rel = await pipeline.gen_video_for_shot(pid, script, ep, shot)
        status["shots"][key]["video"] = "done"
    else:
        raise HTTPException(400, "stage must be keyframe/video")
    db.save_script(pid, script)
    return {"ok": True, "result": rel}


@app.get("/api/health/services")
async def health():
    return await clients.service_health()


@app.websocket("/ws/{pid}")
async def ws(ws: WebSocket, pid: str):
    await ws.accept()
    pipeline.subscribers.setdefault(pid, set()).add(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        pipeline.subscribers.get(pid, set()).discard(ws)
