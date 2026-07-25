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


def check_once(docker_client, on_trigger) -> None:
    """Runs the cheap, deterministic checks. on_trigger(question) is called once
    per tripped, non-cooled-down check — kept as a callback rather than importing
    app.py directly, to avoid a circular import (app.py imports this module).
    """
    for container in WATCH_CONTAINERS:
        leak_key = (container, "leak")
        try:
            leaked = _query_instant("app_leak_bytes")
        except Exception:
            leaked = None
        if leaked is not None and leaked >= LEAK_THRESHOLD_BYTES and _cooldown_ok(leak_key):
            _last_trigger[leak_key] = time.time()
            on_trigger(
                f"Proactive check: {container}'s app_leak_bytes metric is at {leaked:.0f} "
                f"bytes, over the {LEAK_THRESHOLD_BYTES}-byte watch threshold. Investigate "
                f"and recommend an action if warranted."
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
