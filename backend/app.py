import json
import os
import time
import uuid
from pathlib import Path

import anthropic
import docker
import requests
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel

import reports
import watcher
from librarian import WIKI_DIR, run_librarian
from notifications import annotate_grafana, notify_slack
from toolsets import (
    DockerToolset,
    JaegerToolset,
    PrometheusToolset,
    RemediationToolset,
    RunbookToolset,
    ToolsetRegistry,
    WikiToolset,
)

app = FastAPI(title="overwatch-sre-backend")

AUDIT_LOG = Path(os.environ.get("AUDIT_LOG_PATH", "/data/audit-log.jsonl"))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
RUNBOOK_PATH = Path(os.environ.get("RUNBOOK_PATH", "runbook.md"))

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
JAEGER_QUERY_URL = os.environ.get("JAEGER_QUERY_URL", "http://jaeger:16686")
TARGET_APP_URL = os.environ.get("TARGET_APP_URL", "http://target-app:8080")
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
        "jaeger": lambda: JaegerToolset(JAEGER_QUERY_URL),
        "runbook": lambda: RunbookToolset(RUNBOOK_PATH),
    }
    enabled = [factory() for key, factory in available.items() if config.get(key, {}).get("enabled", True)]
    return ToolsetRegistry(enabled)


registry = _build_registry()

SYSTEM_PROMPT = (
    "You are Overwatch, an on-call SRE copilot. You investigate a small Dockerized system "
    "using the tools available to you — Prometheus metrics, container status/logs, request "
    "traces (query_traces), a wiki of past incidents (search_wiki / read_wiki_page) maintained "
    "by a separate archivist agent, and a human-authored runbook (search_runbook / "
    "read_runbook) that codifies what this team has decided to always do for known failure "
    "types. You are strictly read-only: you can look at anything, but you can never restart, "
    "modify a container, or write to the wiki/runbook yourself.\n\n"
    "Before proposing any action: (1) check search_runbook for this failure type — it may "
    "specify a different or additional step beyond a plain restart; (2) check search_wiki for "
    "how many times this exact failure has happened on this container recently. If this is "
    "the 2nd+ occurrence, you MUST say so explicitly in your answer and recommend escalation "
    "(e.g. 'this is the Nth occurrence — recommend filing a ticket / escalating to the service "
    "owner') — do not present a recurring problem as a fresh, isolated one. Always verify "
    "wiki/runbook guidance against live metrics/logs/traces too, since the wiki can be stale.\n\n"
    "Use query_traces when a question is about latency or which specific request/operation is "
    "slow, not just whether the service is up. If you diagnose a problem that a restart would "
    "plausibly fix, call propose_restart. If instead this container was already restarted very "
    "recently for this same problem and it clearly didn't help (check restart_count and the "
    "wiki for a very recent prior restart of this exact container) — a crash loop — call "
    "propose_rollback instead of proposing the same restart again, and say explicitly that a "
    "repeat restart already failed once. Either way, a human decides whether to approve it. Be "
    "concise and specific: cite the metric, log line, or span that supports your diagnosis."
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
    hands every tool_use block to registry.call(). propose_restart/propose_rollback
    are the two tool names this loop recognizes by convention, to lift their result
    into recommended_action; neither ever calls docker_client directly — that only
    happens in POST /approve/{action_id}, after a human clicks Approve.
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
            if block.name in ("propose_restart", "propose_rollback") and "error" not in result:
                action_type = "restart_container" if block.name == "propose_restart" else "rollback_container"
                proposed_action = {
                    "type": action_type,
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


def _execute_restart(container_name: str) -> dict:
    try:
        container = docker_client.containers.get(container_name)
        container.restart(timeout=10)
        return {"status": "restarted", "container": container_name}
    except Exception as exc:
        return {"status": "failed", "container": container_name, "error": str(exc)}


def _execute_rollback(container_name: str) -> dict:
    """Honest, deliberately conservative: this system has no image-versioning
    infrastructure (nothing tags a ':previous' image on build), so there is
    usually nothing real to roll back to. Checks for real, doesn't fake success.
    Even when a previous-tagged image IS found, this does not attempt the actual
    container swap automatically — recreating a running container with a
    different image (preserving network/env/volumes) is real surgery that
    deserves its own tested code path, not something to rush under time
    pressure onto an otherwise-working, demo-critical restart flow.
    """
    previous_tag = f"{container_name}:previous"
    try:
        docker_client.images.get(previous_tag)
    except docker.errors.ImageNotFound:
        return {
            "status": "no_previous_image",
            "container": container_name,
            "message": (
                f"No image tagged '{previous_tag}' exists — this stack doesn't tag "
                "previous builds, so there's nothing to roll back to yet. A restart "
                "is the only remediation currently available."
            ),
        }
    except Exception as exc:
        return {"status": "failed", "container": container_name, "error": str(exc)}
    return {
        "status": "previous_image_found_not_executed",
        "container": container_name,
        "message": (
            f"Found '{previous_tag}', but automated rollback execution isn't wired up yet — "
            "swapping a running container's image safely (network/env/volumes) needs its own "
            "tested path. Roll back manually for now: docker compose up -d --no-deps "
            f"--force-recreate {container_name} after retagging."
        ),
    }


@app.post("/approve/{action_id}")
def approve(action_id: str):
    action = _pending_actions.pop(action_id, None)
    if not action:
        raise HTTPException(status_code=404, detail="unknown or already-resolved action_id")

    container_name = action["container"]
    if action.get("type") == "rollback_container":
        result = _execute_rollback(container_name)
    else:
        result = _execute_restart(container_name)

    _audit({"type": "approve", "action_id": action_id, "action": action, "result": result})

    if result["status"] == "restarted":
        notify_slack(f":white_check_mark: Restarted *{container_name}*. Reason: {action['reason']}")
        annotate_grafana(f"Restarted {container_name}: {action['reason']}", tags=["overwatch", "restart", container_name])
    elif result["status"] in ("no_previous_image", "previous_image_found_not_executed"):
        notify_slack(f":information_source: Rollback for *{container_name}*: {result['message']}")
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

    `actionable` distinguishes "still approvable right now" from "was proposed,
    never approved, but the backend has restarted since" — _pending_actions is an
    in-memory dict, cleared on every process restart, so an old unapproved
    action_id from before a restart will 404 on /approve forever even though the
    audit log still shows it as unapproved. Without this flag, a UI that
    auto-surfaces pending proposals (so a watcher-triggered one doesn't require
    someone to ask first) would show permanently-stuck, un-clickable cards after
    any restart during development.
    """
    events = _read_audit()
    asks = {e["action_id"]: e for e in events if e.get("type") == "ask" and e.get("action_id")}
    approves = {e["action_id"]: e for e in events if e.get("type") == "approve"}

    result = [
        {
            "action_id": action_id,
            "question": ask_event["question"],
            "answer": ask_event["answer"],
            "source": ask_event.get("source", "user"),
            "recommended_action": ask_event["recommended_action"],
            "asked_at": ask_event["ts"],
            "approved": action_id in approves,
            "actionable": action_id in _pending_actions,
            "result": approves[action_id]["result"] if action_id in approves else None,
            "resolved_at": approves[action_id]["ts"] if action_id in approves else None,
        }
        for action_id, ask_event in asks.items()
    ]
    result.sort(key=lambda i: i["asked_at"], reverse=True)
    return result


class ReportRequest(BaseModel):
    context: str
    container: str = "target-app"


@app.post("/report/generate")
def report_generate(req: ReportRequest):
    """Two-stage pipeline (backend/reports.py): Haiku compresses raw audit-log +
    Prometheus range data into a structured brief, Sonnet writes the actual
    7-section postmortem from that brief + the developer's own context. Not an
    agent tool - triggered directly by a human request, same reasoning as every
    other side-effecting action in this system: deterministic trigger, not model
    discretion over when to run.
    """
    try:
        result = reports.generate_report(req.context, req.container)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"report generation failed: {exc}") from exc
    _audit({"type": "report_generated", "report_id": result["id"], "context": req.context})
    return result


@app.get("/reports")
def reports_list():
    return reports.list_reports()


@app.get("/report/{report_id}/md")
def report_get_md(report_id: str):
    try:
        text = reports.get_report_markdown(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unknown report id")
    return PlainTextResponse(text, media_type="text/markdown")


@app.get("/report/{report_id}/pdf")
def report_get_pdf(report_id: str):
    try:
        pdf_bytes = reports.get_report_pdf(report_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="unknown report id")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"PDF render failed: {exc}") from exc
    return Response(
        pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{report_id}.pdf"'},
    )


WORKER_SERVICE_URL = os.environ.get("WORKER_SERVICE_URL", "http://worker-service:8090")

_DEMO_TRIGGER_SERVICES = {
    "target-app": ({"leak", "crash", "slow", "reset"}, TARGET_APP_URL),
    "worker-service": ({"jam", "reset"}, WORKER_SERVICE_URL),
}


@app.post("/demo/trigger/{service}/{mode}")
def demo_trigger(service: str, mode: str):
    """Demo convenience only - proxies to a watched service's own failure-injection
    endpoints so a UI button (or scripts/demo-trigger.sh) doesn't need to know
    the service's internal URL. Not part of the real API contract in CLAUDE.md;
    this is purely for making live demos reliable, not a capability the agent
    can reach.
    """
    if service not in _DEMO_TRIGGER_SERVICES:
        raise HTTPException(status_code=400, detail=f"service must be one of {set(_DEMO_TRIGGER_SERVICES)}")
    modes, base_url = _DEMO_TRIGGER_SERVICES[service]
    if mode not in modes:
        raise HTTPException(status_code=400, detail=f"mode for {service} must be one of {modes}")
    try:
        r = requests.get(f"{base_url}/{mode}", timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"{service} call failed: {exc}") from exc


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# Started once, at import time — cheap deterministic checks (Prometheus/Docker,
# no LLM) every WATCH_INTERVAL_SECONDS; a tripped check runs the same
# _handle_ask() path a user question would, tagged source="watcher". This is
# what makes the copilot notice a problem before anyone asks about it.
watcher.start(docker_client, on_trigger=lambda question: _handle_ask(question, source="watcher"))
