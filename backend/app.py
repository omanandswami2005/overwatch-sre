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

import watcher
from librarian import WIKI_DIR, run_librarian
from notifications import notify_slack
from toolsets import DockerToolset, PrometheusToolset, RemediationToolset, ToolsetRegistry, WikiToolset

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
        # read-only wiki access for the chat agent — the librarian's write_wiki_pages
        # tool is intentionally never registered here, see librarian.py.
        "wiki": lambda: WikiToolset(WIKI_DIR),
    }
    enabled = [factory() for key, factory in available.items() if config.get(key, {}).get("enabled", True)]
    return ToolsetRegistry(enabled)


registry = _build_registry()

SYSTEM_PROMPT = (
    "You are Overwatch, an on-call SRE copilot. You investigate a small Dockerized system "
    "using the tools available to you — Prometheus metrics, container status/logs, and a "
    "wiki of past incidents (search_wiki / read_wiki_page) maintained by a separate "
    "archivist agent. You are strictly read-only: you can look at anything, but you can "
    "never restart, modify a container, or write to the wiki yourself. Check the wiki for "
    "prior occurrences of a similar symptom, but always verify against live metrics/logs "
    "too — the wiki can be stale. If you diagnose a problem that a restart would plausibly "
    "fix, call propose_restart to recommend it — a human decides whether to approve it. Be "
    "concise and specific: cite the metric or log line that supports your diagnosis."
)


class AskRequest(BaseModel):
    question: str


def _audit(event: dict) -> None:
    event["ts"] = time.time()
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(event) + "\n")


def _read_audit() -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    lines = AUDIT_LOG.read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


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
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=registry.schemas,
            messages=messages,
        )

        if response.stop_reason == "max_tokens":
            # got cut off mid-response (often mid-thinking, before any answer text
            # was written) — don't silently return a blank/truncated answer.
            return (
                "The investigation response was cut off before finishing — try asking "
                "again, ideally a narrower question.",
                proposed_action,
            )

        if response.stop_reason != "tool_use":
            text = "".join(block.text for block in response.content if block.type == "text")
            return text or "No diagnosis text was returned — try rephrasing the question.", proposed_action

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


def _handle_ask(question: str, source: str = "user") -> dict:
    """Shared by POST /ask and the background watcher, so a proactively-triggered
    investigation gets exactly the same audit trail, pending-action registration,
    and Slack notification as a user-typed question — the only difference is
    `source`, so the audit log (and eventually the UI) can tell them apart.
    """
    try:
        answer, proposed = _run_agent(question)
    except Exception as exc:
        _audit({"type": "ask_error", "question": question, "source": source, "error": str(exc)})
        raise

    action_id = None
    if proposed:
        action_id = str(uuid.uuid4())
        _pending_actions[action_id] = proposed

    _audit(
        {
            "type": "ask",
            "question": question,
            "source": source,
            "answer": answer,
            "action_id": action_id,
            "recommended_action": proposed,
        }
    )

    if proposed:
        prefix = ":mag:" if source == "watcher" else ":rotating_light:"
        notify_slack(
            f"{prefix} Overwatch proposes restarting *{proposed['container']}* — "
            f"{proposed['reason']}\nApprove: `POST /approve/{action_id}`"
        )

    return {"answer": answer, "recommended_action": proposed, "action_id": action_id}


@app.post("/ask")
def ask(req: AskRequest):
    try:
        return _handle_ask(req.question, source="user")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"agent call failed: {exc}") from exc


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

    if result["status"] == "restarted":
        notify_slack(f":white_check_mark: Restarted *{container_name}*. Reason: {action['reason']}")
    else:
        notify_slack(f":x: Restart of *{container_name}* failed: {result.get('error', 'unknown error')}")

    if result["status"] == "restarted":
        # Best-effort: the archivist agent documents the incident after the fact.
        # A librarian failure must never affect the /approve response — the restart
        # already happened, and that's the safety-critical part.
        ask_event = next(
            (e for e in _read_audit() if e.get("type") == "ask" and e.get("action_id") == action_id), None
        )
        try:
            written = run_librarian(
                {
                    "container": container_name,
                    "question": ask_event["question"] if ask_event else "(unknown)",
                    "answer": ask_event["answer"] if ask_event else "(unknown)",
                    "reason": action["reason"],
                    "result": result,
                    "action_id": action_id,
                    "ts": time.time(),
                }
            )
            _audit({"type": "librarian", "action_id": action_id, "wrote": written})
        except Exception as exc:
            _audit({"type": "librarian_error", "action_id": action_id, "error": str(exc)})

    return result


@app.get("/audit")
def audit():
    return _read_audit()


@app.get("/incidents")
def incidents():
    """Groups audit events into per-action_id incidents: the diagnosis, whether it
    was approved, and the outcome. Asks with no proposed action (informational-only
    questions) are omitted — they're not incidents.
    """
    events = _read_audit()
    asks = {e["action_id"]: e for e in events if e.get("type") == "ask" and e.get("action_id")}
    approves = {e["action_id"]: e for e in events if e.get("type") == "approve"}

    result = [
        {
            "action_id": action_id,
            "question": ask_event["question"],
            "answer": ask_event["answer"],
            "recommended_action": ask_event["recommended_action"],
            "asked_at": ask_event["ts"],
            "approved": action_id in approves,
            "result": approves[action_id]["result"] if action_id in approves else None,
            "resolved_at": approves[action_id]["ts"] if action_id in approves else None,
        }
        for action_id, ask_event in asks.items()
    ]
    result.sort(key=lambda i: i["asked_at"], reverse=True)
    return result


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# Started once, at import time — cheap deterministic checks (Prometheus/Docker,
# no LLM) every WATCH_INTERVAL_SECONDS; a tripped check runs the same
# _handle_ask() path a user question would, tagged source="watcher". This is
# what makes the copilot notice a problem before anyone asks about it.
watcher.start(docker_client, on_trigger=lambda question: _handle_ask(question, source="watcher"))
