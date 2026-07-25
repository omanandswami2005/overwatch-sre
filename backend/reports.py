import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import anthropic
import markdown as markdown_lib
import requests
from weasyprint import HTML

AUDIT_LOG = Path(os.environ.get("AUDIT_LOG_PATH", "/data/audit-log.jsonl"))
REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", "/data/reports"))
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5")
# cheap/fast model for the extraction stage - see _extract_brief(). Deliberately
# separate from MODEL: extraction is a compression/classification task Haiku
# handles at ~2-5% quality gap vs Sonnet for a fraction of the cost, so the
# expensive model's tokens go entirely toward the part that needs judgment
# (writing a coherent, well-structured report), not toward re-reading raw logs.
HAIKU_MODEL = os.environ.get("HAIKU_MODEL", "claude-haiku-4-5-20251001")

anthropic_client = anthropic.Anthropic()


def _read_audit() -> list[dict]:
    if not AUDIT_LOG.exists():
        return []
    return [json.loads(line) for line in AUDIT_LOG.read_text().splitlines() if line.strip()]


def _query_range(promql: str, start: float, end: float, step: str = "60s") -> list:
    try:
        r = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query_range",
            params={"query": promql, "start": start, "end": end, "step": step},
            timeout=10,
        )
        r.raise_for_status()
        result = r.json()["data"]["result"]
        return result[0]["values"] if result else []
    except Exception:
        return []


EXTRACT_BRIEF_TOOL = {
    "name": "extract_brief",
    "description": "Record a compressed, structured brief of the incident from the raw data provided.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string", "description": "one or two sentence factual summary"},
            "timeline": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"time": {"type": "string"}, "event": {"type": "string"}},
                    "required": ["time", "event"],
                },
            },
            "key_metrics": {
                "type": "array",
                "items": {"type": "string"},
                "description": "notable metric readings with values and times, e.g. 'app_leak_bytes: 10MB at 14:32, 60MB at 14:34'",
            },
            "key_log_lines": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["summary", "timeline", "key_metrics", "key_log_lines"],
    },
}

EXTRACT_SYSTEM_PROMPT = (
    "You compress raw incident data (an audit log, Prometheus time series) into a "
    "short, structured brief for a downstream report-writing model. You are NOT "
    "writing the final report - be terse, factual, and complete. Do not editorialize "
    "or recommend actions, just extract what happened, when, and the evidence for "
    "it. Only report what's actually present in the data - never invent values. "
    "Call extract_brief exactly once."
)


def _extract_brief(context: str, container: str = "target-app", lookback_hours: int = 2) -> dict:
    """Stage 1 (Haiku): raw data in, compressed structured brief out."""
    now = time.time()
    start = now - lookback_hours * 3600

    audit_events = [e for e in _read_audit() if e.get("ts", 0) >= start]
    leak_series = _query_range("app_leak_bytes", start, now)
    up_series = _query_range(f'up{{job="{container}"}}', start, now)

    raw = (
        f"Developer's context: {context}\n\n"
        f"Audit log events (last {lookback_hours}h, {len(audit_events)} events):\n"
        f"{json.dumps(audit_events, default=str)[:12000]}\n\n"
        f'app_leak_bytes over time ({len(leak_series)} points): {leak_series[:60]}\n\n'
        f'up{{job="{container}"}} over time ({len(up_series)} points): {up_series[:60]}\n'
    )

    response = anthropic_client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=2048,
        system=EXTRACT_SYSTEM_PROMPT,
        tools=[EXTRACT_BRIEF_TOOL],
        tool_choice={"type": "tool", "name": "extract_brief"},
        messages=[{"role": "user", "content": raw}],
    )

    for block in response.content:
        if block.type == "tool_use" and block.name == "extract_brief":
            return block.input
    return {"summary": "(extraction failed - no tool_use block returned)", "timeline": [], "key_metrics": [], "key_log_lines": []}


SYNTHESIZE_SYSTEM_PROMPT = (
    "You are Overwatch's incident report writer. Given a compressed brief of an "
    "incident and the on-call engineer's own plain-English context, write a "
    "postmortem in Markdown using EXACTLY these 7 sections, in this order, each "
    "as a level-2 header (##): Summary, Impact, Timeline, Root Cause, Resolution, "
    "Detection, Action Items. Be specific and cite real values/timestamps from the "
    "brief - never invent data that isn't in it. If a section has nothing to "
    "report (e.g. no action items), say so briefly rather than omitting it."
)


def _synthesize_report(brief: dict, context: str) -> str:
    """Stage 2 (Sonnet): compressed brief + human context in, polished report out."""
    user_content = f"Developer's context: {context}\n\nIncident brief:\n{json.dumps(brief, indent=2)}"
    response = anthropic_client.messages.create(
        model=MODEL,
        max_tokens=2048,
        system=SYNTHESIZE_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )
    return "".join(block.text for block in response.content if block.type == "text")


def generate_report(context: str, container: str = "target-app") -> dict:
    report_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6]
    brief = _extract_brief(context, container)
    body = _synthesize_report(brief, context)

    header = f"# Incident Report — {report_id}\n\n*Generated {datetime.now(timezone.utc).isoformat()}*\n\n"
    full_markdown = header + body

    path = REPORTS_DIR / f"{report_id}.md"
    path.write_text(full_markdown)

    return {"id": report_id, "created_at": time.time()}


def get_report_markdown(report_id: str) -> str:
    path = REPORTS_DIR / f"{report_id}.md"
    if not path.exists():
        raise FileNotFoundError(report_id)
    return path.read_text()


PDF_CSS = """
@page { size: A4; margin: 2.2cm; }
body { font-family: Helvetica, Arial, sans-serif; color: #1a1a1a; line-height: 1.5; }
h1 { font-size: 22pt; border-bottom: 2px solid #35D0A6; padding-bottom: 8pt; }
h2 { font-size: 14pt; color: #0B0F14; margin-top: 20pt; border-left: 4px solid #35D0A6; padding-left: 8pt; }
code, pre { font-family: monospace; background: #f2f2f2; padding: 2px 4px; }
"""


def get_report_pdf(report_id: str) -> bytes:
    md_text = get_report_markdown(report_id)
    html_body = markdown_lib.markdown(md_text, extensions=["extra", "sane_lists"])
    html_doc = f"<html><head><style>{PDF_CSS}</style></head><body>{html_body}</body></html>"
    return HTML(string=html_doc).write_pdf()


def list_reports() -> list[dict]:
    reports = []
    for path in sorted(REPORTS_DIR.glob("*.md"), reverse=True):
        text = path.read_text()
        title_line = next((line for line in text.splitlines() if line.startswith("# ")), path.stem)
        reports.append({"id": path.stem, "title": title_line.lstrip("# ").strip()})
    return reports
