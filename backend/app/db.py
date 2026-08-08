import json
import os
import sqlite3
import time

DB_PATH = "/data/liyangyang/ai_drama/backend/data/drama.db"
OUT_ROOT = "/data/liyangyang/ai_drama/output"

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with conn() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS projects(
            id TEXT PRIMARY KEY,
            title TEXT,
            synopsis TEXT,
            style TEXT,
            episodes INTEGER,
            shots_per_episode INTEGER,
            status TEXT,
            stage TEXT,
            created REAL,
            updated REAL
        )""")
        c.commit()


def create_project(pid, title, synopsis, style, episodes, shots_per_episode):
    now = time.time()
    with conn() as c:
        c.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?,?,?)",
                  (pid, title, synopsis, style, episodes, shots_per_episode,
                   "created", "script", now, now))
        c.commit()


def update_project(pid, **kw):
    kw["updated"] = time.time()
    sets = ",".join(f"{k}=?" for k in kw)
    with conn() as c:
        c.execute(f"UPDATE projects SET {sets} WHERE id=?", (*kw.values(), pid))
        c.commit()


def get_project(pid):
    with conn() as c:
        r = c.execute("SELECT * FROM projects WHERE id=?", (pid,)).fetchone()
    return dict(r) if r else None


def list_projects():
    with conn() as c:
        rows = c.execute("SELECT * FROM projects ORDER BY created DESC").fetchall()
    return [dict(r) for r in rows]


def script_path(pid):
    return os.path.join(OUT_ROOT, pid, "script.json")


def load_script(pid):
    p = script_path(pid)
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return None


def save_script(pid, script):
    p = script_path(pid)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump(script, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
