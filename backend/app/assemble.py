import asyncio
import os

OUT_ROOT = "/data/liyangyang/ai_drama/output"


async def run(cmd: list[str]):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    _, err = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{err.decode(errors='ignore')[-800:]}")


async def ffprobe_duration(path: str) -> float:
    proc = await asyncio.create_subprocess_exec(
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", path,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    return float(out.decode().strip())


async def concat_wavs(wavs: list[str], out: str, gap: float = 0.25, head: float = 0.2):
    parts = []
    for w in wavs:
        parts += ["-i", w]
    n = len(wavs)
    sil = f"anullsrc=r=24000:cl=mono"
    fc = []
    labels = []
    idx = 0
    fc.append(f"{sil},atrim=duration={head}[s0]")
    labels.append("[s0]")
    for i in range(n):
        fc.append(f"[{idx}:a]aresample=24000[a{idx}]")
        labels.append(f"[a{idx}]")
        idx += 1
        if i < n - 1:
            g = f"g{i}"
            fc.append(f"{sil},atrim=duration={gap}[{g}]")
            labels.append(f"[{g}]")
    fc.append(f"{''.join(labels)}concat=n={len(labels)}:v=0:a=1[out]")
    await run(["ffmpeg", "-y", *parts, "-filter_complex", ";".join(fc),
               "-map", "[out]", out])


async def merge_shot(clip: str, audio: str | None, out: str, width=480, height=832):
    dv = await ffprobe_duration(clip)
    da = await ffprobe_duration(audio) if audio else 0.0
    dur = max(dv, da, 1.0)
    inputs = ["-i", clip]
    fc = [f"[0:v]tpad=stop_mode=clone:stop_duration={max(dur - dv, 0):.3f},setsar=1[v]"]
    if audio:
        inputs += ["-i", audio]
        fc.append(f"[1:a]apad=whole_dur={dur:.3f},aresample=24000[a]")
        amap = ["-map", "[v]", "-map", "[a]"]
    else:
        fc.append(f"anullsrc=r=24000:cl=mono,atrim=duration={dur:.3f}[a]")
        amap = ["-map", "[v]", "-map", "[a]"]
    await run(["ffmpeg", "-y", *inputs, "-filter_complex", ";".join(fc),
               *amap, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "16",
               "-c:a", "aac", "-b:a", "96k", "-t", f"{dur:.3f}", out])
    return dur


def srt_time(t: float) -> str:
    h = int(t // 3600); t -= h * 3600
    m = int(t // 60); t -= m * 60
    s = int(t); ms = int(round((t - s) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


async def assemble_episode(shot_files: list[str], subtitles: list[dict], out: str):
    """subtitles: [{start, end, text}] in episode timeline seconds"""
    list_file = out + ".list"
    with open(list_file, "w") as f:
        for p in shot_files:
            f.write(f"file '{p}'\n")
    srt = out + ".srt"
    with open(srt, "w", encoding="utf-8") as f:
        for i, sub in enumerate(subtitles, 1):
            f.write(f"{i}\n{srt_time(sub['start'])} --> {srt_time(sub['end'])}\n{sub['text']}\n\n")
    await run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
               "-vf", f"subtitles={srt}:force_style='FontSize=11,PrimaryColour=&HFFFFFF,OutlineColour=&H80000000,BorderStyle=3,Alignment=2,MarginV=30'",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", out])


async def concat_episodes(ep_files: list[str], out: str):
    if len(ep_files) == 1:
        await run(["ffmpeg", "-y", "-i", ep_files[0], "-c", "copy", out])
        return
    list_file = out + ".list"
    with open(list_file, "w") as f:
        for p in ep_files:
            f.write(f"file '{p}'\n")
    await run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", out])
