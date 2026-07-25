import json
import os
import re
import subprocess
import time
import uuid
from pathlib import Path

import docker
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="overwatch-sre-backend")

AUDIT_LOG = Path(os.environ.get("AUDIT_LOG_PATH", "/data/audit-log.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

docker_client = docker.from_env()

# action_id -> {"type": "restart_container", "container": "..."}
_pending_actions: dict[str, dict] = {}

# crude signal for "does this diagnosis warrant offering a restart" — good enough
# for a hackathon demo; swap for a structured holmes response if time allows.
RESTART_TRIGGERS = re.compile(r"leak|oom|crash|unhealthy|restart|memory|exited", re.IGNORECASE)


class AskRequest(BaseModel):
    question: str


def _audit(event: dict) -> None:
    event["ts"] = time.time()
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(event) + "\n")


def _ask_holmes(question: str) -> str:
    # NOTE: verify this invocation against `python /app/holmes_cli.py ask --help`
    # on first build — exact flags weren't confirmed ahead of time.
    result = subprocess.run(
        ["python", "/app/holmes_cli.py", "ask", question],
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "holmes exited non-zero")
    return result.stdout.strip()


@app.post("/ask")
def ask(req: AskRequest):
    try:
        answer = _ask_holmes(req.question)
    except Exception as exc:
        _audit({"type": "ask_error", "question": req.question, "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"holmes call failed: {exc}") from exc

    recommended_action = None
    action_id = None
    if RESTART_TRIGGERS.search(answer):
        action_id = str(uuid.uuid4())
        recommended_action = {"type": "restart_container", "container": "target-app"}
        _pending_actions[action_id] = recommended_action

    _audit(
        {
            "type": "ask",
            "question": req.question,
            "answer": answer,
            "action_id": action_id,
            "recommended_action": recommended_action,
        }
    )
    return {"answer": answer, "recommended_action": recommended_action, "action_id": action_id}


@app.post("/approve/{action_id}")
def approve(action_id: str):
    action = _pending_actions.pop(action_id, None)
    if not action:
        raise HTTPException(status_code=404, detail="unknown or already-resolved action_id")

    container_name = action["container"]
    try:
        container = docker_client.containers.get(container_name)
        container.restart(timeout=10)
        result = {"status": "restarted", "container": container_name}
    except Exception as exc:
        result = {"status": "failed", "container": container_name, "error": str(exc)}

    _audit({"type": "approve", "action_id": action_id, "action": action, "result": result})
    return result


@app.get("/audit")
def audit():
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@app.get("/healthz")
def healthz():
    return {"status": "ok"}
