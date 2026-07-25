import json
import os
import time
import uuid
from pathlib import Path

import anthropic
import docker
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="overwatch-sre-backend")

AUDIT_LOG = Path(os.environ.get("AUDIT_LOG_PATH", "/data/audit-log.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
MAX_TOOL_ROUNDS = 6

docker_client = docker.from_env()
anthropic_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

# action_id -> {"type": "restart_container", "container": "...", "reason": "..."}
_pending_actions: dict[str, dict] = {}


class AskRequest(BaseModel):
    question: str


def _audit(event: dict) -> None:
    event["ts"] = time.time()
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(event) + "\n")


# --- read-only investigation tools + one propose-only tool. None of these,
# including propose_restart, ever call docker_client.containers.restart() —
# that only happens in POST /approve/{action_id}, after a human clicks Approve. ---


def _query_prometheus(query: str) -> dict:
    r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=10)
    r.raise_for_status()
    return r.json()


def _get_container_status(container: str) -> dict:
    c = docker_client.containers.get(container)
    c.reload()
    state = c.attrs.get("State", {})
    return {
        "name": c.name,
        "status": c.status,
        "health": state.get("Health", {}).get("Status"),
        "restart_count": c.attrs.get("RestartCount"),
        "exit_code": state.get("ExitCode"),
        "started_at": state.get("StartedAt"),
    }


def _get_container_logs(container: str, tail: int = 50) -> str:
    c = docker_client.containers.get(container)
    return c.logs(tail=tail).decode(errors="replace")


TOOLS = [
    {
        "name": "query_prometheus",
        "description": (
            "Run a PromQL instant query against Prometheus. Use this to check metrics "
            "like memory usage, request latency, or error rates."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "PromQL expression, e.g. app_leak_bytes"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_container_status",
        "description": "Get a container's current status: running/exited, health, restart count, last exit code.",
        "input_schema": {
            "type": "object",
            "properties": {"container": {"type": "string", "description": "container name, e.g. target-app"}},
            "required": ["container"],
        },
    },
    {
        "name": "get_container_logs",
        "description": "Fetch the most recent log lines from a container.",
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {"type": "string"},
                "tail": {"type": "integer", "description": "number of lines, default 50"},
            },
            "required": ["container"],
        },
    },
    {
        "name": "propose_restart",
        "description": (
            "Recommend restarting a container to remediate an issue. This does NOT restart "
            "it — it only records a proposal that a human must approve. Call this once "
            "you've diagnosed a problem that a restart would plausibly fix."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "container": {"type": "string"},
                "reason": {"type": "string", "description": "one-sentence justification"},
            },
            "required": ["container", "reason"],
        },
    },
]

SYSTEM_PROMPT = (
    "You are Overwatch, an on-call SRE copilot. You investigate a small Dockerized system "
    "using the tools available to you — Prometheus metrics and container status/logs. You "
    "are strictly read-only: you can look at anything, but you can never restart or modify "
    "a container yourself. If you diagnose a problem that a restart would plausibly fix, "
    "call propose_restart to recommend it — a human decides whether to approve it. Be "
    "concise and specific: cite the metric or log line that supports your diagnosis."
)

READ_ONLY_TOOL_IMPL = {
    "query_prometheus": lambda i: _query_prometheus(i["query"]),
    "get_container_status": lambda i: _get_container_status(i["container"]),
    "get_container_logs": lambda i: _get_container_logs(i["container"], i.get("tail", 50)),
}


def _run_agent(question: str) -> tuple[str, dict | None]:
    messages = [{"role": "user", "content": question}]
    proposed_action = None

    for _ in range(MAX_TOOL_ROUNDS):
        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            return text, proposed_action

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "propose_restart":
                proposed_action = {
                    "type": "restart_container",
                    "container": block.input["container"],
                    "reason": block.input["reason"],
                }
                result = {"status": "recorded — pending human approval"}
            else:
                try:
                    result = READ_ONLY_TOOL_IMPL[block.name](block.input)
                except Exception as exc:
                    result = {"error": str(exc)}
            tool_results.append(
                {"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(result, default=str)}
            )
        messages.append({"role": "user", "content": tool_results})

    return "Investigation took too many steps — try a narrower question.", proposed_action


@app.post("/ask")
def ask(req: AskRequest):
    try:
        answer, proposed = _run_agent(req.question)
    except Exception as exc:
        _audit({"type": "ask_error", "question": req.question, "error": str(exc)})
        raise HTTPException(status_code=502, detail=f"agent call failed: {exc}") from exc

    action_id = None
    if proposed:
        action_id = str(uuid.uuid4())
        _pending_actions[action_id] = proposed

    _audit(
        {
            "type": "ask",
            "question": req.question,
            "answer": answer,
            "action_id": action_id,
            "recommended_action": proposed,
        }
    )
    return {"answer": answer, "recommended_action": proposed, "action_id": action_id}


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
