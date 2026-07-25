import os
import time

import requests

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://grafana:3000").rstrip("/")
GRAFANA_ADMIN_USER = os.environ.get("GRAFANA_ADMIN_USER", "admin")
GRAFANA_ADMIN_PASSWORD = os.environ.get("GRAFANA_ADMIN_PASSWORD", "admin")


def notify_slack(text: str) -> bool:
    """Best-effort Slack incoming-webhook post. No-ops (returns False) if
    SLACK_WEBHOOK_URL isn't configured — callers should not treat that as an
    error, just as "notifications aren't set up." Never raises.
    """
    if not SLACK_WEBHOOK_URL:
        return False
    try:
        r = requests.post(SLACK_WEBHOOK_URL, json={"text": text}, timeout=5)
        r.raise_for_status()
        return True
    except Exception:
        return False


def annotate_grafana(text: str, tags: list[str] | None = None) -> bool:
    """Best-effort: pushes a global annotation to Grafana's HTTP API so a restart
    shows up directly on the dashboard timeline, not just in audit-log.jsonl. Uses
    Grafana's default admin/admin basic auth over the internal Docker network —
    fine for a local demo instance, never raises on failure.
    """
    try:
        r = requests.post(
            f"{GRAFANA_URL}/api/annotations",
            json={"time": int(time.time() * 1000), "text": text, "tags": tags or ["overwatch"]},
            auth=(GRAFANA_ADMIN_USER, GRAFANA_ADMIN_PASSWORD),
            timeout=5,
        )
        r.raise_for_status()
        return True
    except Exception:
        return False
