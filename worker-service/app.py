import logging
import time
from threading import Lock

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker-service")

app = FastAPI(title="worker-service")

_state_lock = Lock()
_jammed = False
_queue_depth = 0

worker_jammed = Gauge("worker_jammed", "1 if the worker's queue processing is stuck, 0 if healthy")
worker_queue_depth = Gauge("worker_queue_depth", "Number of items waiting in the worker's queue")


@app.get("/")
def root():
    return {"service": "worker-service", "jammed": _jammed, "queue_depth": _queue_depth}


@app.get("/work")
def work():
    """A normal unit of work — processes one queued item. If jammed, the queue
    keeps growing instead of draining, since nothing is actually processed.
    """
    global _queue_depth
    with _state_lock:
        if _jammed:
            _queue_depth += 1
            worker_queue_depth.set(_queue_depth)
            log.warning("queue processing stuck: item enqueued but not processed, depth=%d", _queue_depth)
            return {"status": "enqueued", "queue_depth": _queue_depth, "processed": False}
        _queue_depth = max(0, _queue_depth - 1) if _queue_depth else 0
        worker_queue_depth.set(_queue_depth)
    return {"status": "processed", "queue_depth": _queue_depth}


@app.get("/jam")
def jam():
    """Simulates a stuck worker — e.g. a deadlocked consumer or a poison-pill
    message that never gets acked. Distinct failure signature from target-app's
    memory leak: this is a stuck-state signal (worker_jammed gauge), not a
    growing-resource signal.
    """
    global _jammed
    with _state_lock:
        _jammed = True
        worker_jammed.set(1)
    log.error("FATAL: worker queue processing jammed — no items being consumed")
    return {"status": "jammed"}


@app.get("/reset")
def reset():
    global _jammed, _queue_depth
    with _state_lock:
        _jammed = False
        _queue_depth = 0
        worker_jammed.set(0)
        worker_queue_depth.set(0)
    log.info("state reset")
    return {"status": "reset"}


@app.get("/metrics")
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)
