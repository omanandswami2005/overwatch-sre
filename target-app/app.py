import logging
import os
import time
from threading import Lock

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("target-app")

app = FastAPI(title="target-app")

_leak_store: list[bytearray] = []
_leak_lock = Lock()
_slow_until = 0.0

mem_leak_bytes = Gauge("app_leak_bytes", "Bytes intentionally held by the /leak endpoint")


@app.get("/")
def root():
    return {
        "service": "target-app",
        "leaking": len(_leak_store) > 0,
        "leaked_bytes": len(_leak_store) * 10_000_000,
        "slow_mode": time.time() < _slow_until,
    }


@app.get("/crash")
def crash():
    log.error("FATAL: unrecoverable state hit on purpose via /crash — exiting")
    os._exit(1)  # noqa: SLF001 — intentional hard kill, not a normal exit


@app.get("/leak")
def leak():
    with _leak_lock:
        _leak_store.append(bytearray(10_000_000))  # +10MB per call
        mem_leak_bytes.set(len(_leak_store) * 10_000_000)
    log.warning("OOM warning: leaked chunk added, total=%d bytes", len(_leak_store) * 10_000_000)
    return {"leaked_chunks": len(_leak_store), "total_bytes": len(_leak_store) * 10_000_000}


@app.get("/slow")
def slow():
    global _slow_until
    _slow_until = time.time() + 120
    log.warning("latency injected: /slow triggered, elevated response times for 120s")
    time.sleep(3)
    return {"status": "slow mode engaged for 120s"}


@app.get("/reset")
def reset():
    global _slow_until
    with _leak_lock:
        _leak_store.clear()
        mem_leak_bytes.set(0)
    _slow_until = 0.0
    log.info("state reset")
    return {"status": "reset"}


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
