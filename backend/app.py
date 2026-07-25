import json
import os
import time
import uuid
from pathlib import Path

import anthropic
import docker
import yaml
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from toolsets import DockerToolset, PrometheusToolset, RemediationToolset, ToolsetRegistry

app = FastAPI(title="overwatch-sre-backend")

AUDIT_LOG = Path(os.environ.get("AUDIT_LOG_PATH", "/data/audit-log.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
TOOLSETS_CONFIG_PATH = Path(os.environ.get("TOOLSETS_CONFIG_PATH", "toolsets.yaml"))
MAX_TOOL_ROUNDS = 6

docker_client = docker.from_env()
anthropic_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

# action_id -> {"type": "restart_container", "container": "...", "reason": "..."}
_pending_actions: dict[str, dict] = {}


def _load_toolsets_config() -> dict:
    if not TOOLSETS_CONFIG_PATH.exists():
        return {}
    return (yaml.safe_load(TOOLSETS_CONFIG_PATH.read_text()) or {}).get("toolsets", {})


def _build_registry() -> ToolsetRegistry:
    """Every toolset here matches the Toolset protocol (toolsets/base.py). To add
    a new capability: write a module, register its factory below, flip it on in
    toolsets.yaml — nothing else in the agent loop has to change.
    """
    config = _load_toolsets_config()
    available = {
        "prometheus": lambda: PrometheusToolset(PROMETHEUS_URL),
        "docker": lambda: DockerToolset(docker_client),
        "remediation": lambda: RemediationToolset(),
    }
    enabled = [factory() for key, factory in available.items() if config.get(key, {}).get("enabled", True)]
    return ToolsetRegistry(enabled)


registry = _build_registry()

SYSTEM_PROMPT = (
    "You are Overwatch, an on-call SRE copilot. You investigate a small Dockerized system "
    "using the tools available to you — Prometheus metrics and container status/logs. You "
    "are strictly read-only: you can look at anything, but you can never restart or modify "
    "a container yourself. If you diagnose a problem that a restart would plausibly fix, "
    "call propose_restart to recommend it — a human decides whether to approve it. Be "
    "concise and specific: cite the metric or log line that supports your diagnosis."
)


class AskRequest(BaseModel):
    question: str


def _audit(event: dict) -> None:
    event["ts"] = time.time()
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(event) + "\n")


def _run_agent(question: str) -> tuple[str, dict | None]:
    """Generic tool-use loop — has no idea which toolset owns which tool, it just
    hands every tool_use block to registry.call(). propose_restart is the one
    tool name this loop recognizes by convention, to lift its result into
    recommended_action; it never calls docker_client.containers.restart() —
    that only happens in POST /approve/{action_id}, after a human clicks Approve.
    """
    messages = [{"role": "user", "content": question}]
    proposed_action = None

    for _ in range(MAX_TOOL_ROUNDS):
        response = anthropic_client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            tools=registry.schemas,
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
            result = registry.call(block.name, block.input)
            if block.name == "propose_restart" and "error" not in result:
                proposed_action = {
                    "type": "restart_container",
                    "container": result["container"],
                    "reason": result["reason"],
                }
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
