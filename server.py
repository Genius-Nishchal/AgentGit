import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agent_runtime import repo, run_agent_task, reset_sandbox, DB_PATH, WORKSPACE

app = FastAPI(title="AgentGit Mission Control")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class PromptRequest(BaseModel):
    prompt: str

@app.get("/api/state")
def get_state(last_reply: str = ""):
    commits_list = []
    for cid, node in repo.commits.items():
        commits_list.append({
            "commit_id": node.commit_id,
            "parent_id": node.parent_id,
            "branch": node.branch,
            "tool_name": node.tool_name,
            "args_summary": node.args_summary,
            "latency_ms": node.latency_ms,
            "status": node.status,
            "guard_reason": node.guard_reason,
            "diff": node.diff,
            "is_head": cid == repo.head,
        })
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT * FROM orders").fetchall()
    files = {f.name: f.read_text(errors="replace") for f in sorted(WORKSPACE.glob("*"))}
    return {
        "head": repo.head,
        "metrics": repo.get_metrics(),
        "commits": commits_list,
        "db_rows": rows,
        "files": files,
        "last_reply": last_reply,
    }

@app.post("/api/run")
def execute_prompt(req: PromptRequest):
    reply = run_agent_task(req.prompt)
    return get_state(last_reply=reply)

@app.post("/api/revert/{commit_id}")
def revert_commit(commit_id: str):
    try:
        repo.revert_to(commit_id)
        return get_state(last_reply=f"Time-traveled workspace & SQLite back to {commit_id}.")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/api/reset")
def reset_all():
    reset_sandbox()
    repo.commits.clear()
    repo._init_root()
    return get_state(last_reply="Sandbox reset to clean baseline.")

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    return Path("index.html").read_text(encoding="utf-8")
