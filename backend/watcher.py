import os
import threading
import time

import requests

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
WATCH_ENABLED = os.environ.get("WATCH_ENABLED", "true").strip().lower() not in ("false", "0", "")
WATCH_INTERVAL_SECONDS = int(os.environ.get("WATCH_INTERVAL_SECONDS", "30"))
WATCH_CONTAINERS = [c.strip() for c in os.environ.get("WATCH_CONTAINERS", "target-app").split(",") if c.strip()]
LEAK_THRESHOLD_BYTES = int(os.environ.get("LEAK_THRESHOLD_BYTES", "50000000"))
COOLDOWN_SECONDS = int(os.environ.get("WATCH_COOLDOWN_SECONDS", "300"))

# (container, check_name) -> last time this check fired an investigation. Cheap
# checks run every WATCH_INTERVAL_SECONDS, but a tripped check only triggers the
# (comparatively expensive) LLM investigation once per COOLDOWN_SECONDS, so an
# ongoing, un-remediated issue doesn't spam a new proposal every 30s.
_last_trigger: dict[tuple[str, str], float] = {}


def _cooldown_ok(key: tuple[str, str]) -> bool:
    return (time.time() - _last_trigger.get(key, 0)) >= COOLDOWN_SECONDS


def _query_instant(promql: str) -> float | None:
    r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": promql}, timeout=5)
    r.raise_for_status()
    result = r.json()["data"]["result"]
    return float(result[0]["value"][1]) if result else None


# Per-service metric checks — deliberately explicit, not a generic framework.
# Two known services, two known failure signatures; add an entry here for a
# new service's own metric rather than reusing another service's check
# (an earlier version queried the bare "app_leak_bytes" metric name with no
# job filter, which happened to work with one service but would have silently
# mislabeled a second one — every query here is scoped with job="...").
SERVICE_METRIC_CHECKS = {
    "target-app": [
        {
            "name": "leak",
            "query": 'app_leak_bytes{job="target-app"}',
            "trip": lambda v: v >= LEAK_THRESHOLD_BYTES,
            "describe": lambda v: (
                f"app_leak_bytes metric is at {v:.0f} bytes, over the "
                f"{LEAK_THRESHOLD_BYTES}-byte watch threshold"
            ),
        },
    ],
    "worker-service": [
        {
            "name": "jammed",
            "query": 'worker_jammed{job="worker-service"}',
            "trip": lambda v: v >= 1,
            "describe": lambda v: (
                "worker_jammed metric is 1 (stuck) — queue processing appears halted, "
                "items may be enqueuing without draining"
            ),
        },
    ],
}


def check_once(docker_client, on_trigger) -> None:
    """Runs the cheap, deterministic checks. on_trigger(question) is called once
    per tripped, non-cooled-down check — kept as a callback rather than importing
    app.py directly, to avoid a circular import (app.py imports this module).
    """
    for container in WATCH_CONTAINERS:
        for check in SERVICE_METRIC_CHECKS.get(container, []):
            metric_key = (container, check["name"])
            try:
                value = _query_instant(check["query"])
            except Exception:
                value = None
            if value is not None and check["trip"](value) and _cooldown_ok(metric_key):
                _last_trigger[metric_key] = time.time()
                on_trigger(
                    f"Proactive check: {container}'s {check['describe'](value)}. "
                    f"Investigate and recommend an action if warranted."
                )

        status_key = (container, "status")
        try:
            c = docker_client.containers.get(container)
            c.reload()
            status = c.status
        except Exception:
            status = "unreachable"
        if status != "running" and _cooldown_ok(status_key):
            _last_trigger[status_key] = time.time()
            on_trigger(
                f"Proactive check: {container}'s status is '{status}', not running. "
                f"Investigate and recommend an action if warranted."
            )


def start(docker_client, on_trigger) -> None:
    if not WATCH_ENABLED:
        return

    def _loop():
        while True:
            try:
                check_once(docker_client, on_trigger)
            except Exception:
                pass  # a failed watch cycle should never kill the background thread
            time.sleep(WATCH_INTERVAL_SECONDS)

    threading.Thread(target=_loop, daemon=True, name="overwatch-watcher").start()
