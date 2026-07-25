#!/usr/bin/env bash
# One-command demo trigger — for live demos where typing raw curl under
# pressure is the last thing you want. Talks to target-app/backend on
# localhost, assumes `docker compose up` is already running.
#
# Usage:
#   scripts/demo-trigger.sh leak     # default — pushes app_leak_bytes over the
#                                     # watch threshold, then asks the copilot
#   scripts/demo-trigger.sh crash    # hard-kills target-app, then asks
#   scripts/demo-trigger.sh slow     # injects latency, then asks
#   scripts/demo-trigger.sh reset    # clears target-app state, no ask
#   scripts/demo-trigger.sh leak --no-ask   # trigger only, let the
#                                            # proactive watcher find it on
#                                            # its own within ~30s instead
#                                            # (the more impressive beat)

set -euo pipefail

TARGET_APP_URL="${TARGET_APP_URL:-http://localhost:8080}"
BACKEND_URL="${BACKEND_URL:-http://localhost:8000}"
MODE="${1:-leak}"
ASK=true
[[ "${2:-}" == "--no-ask" ]] && ASK=false

echo "==> resetting target-app"
curl -sf "$TARGET_APP_URL/reset" > /dev/null

case "$MODE" in
  leak)
    echo "==> pushing target-app over the leak threshold (6x /leak, 10MB each)"
    for _ in 1 2 3 4 5 6; do curl -sf "$TARGET_APP_URL/leak" > /dev/null; done
    STATE=$(curl -sf "$TARGET_APP_URL/")
    echo "    $STATE"
    QUESTION="why is target-app unhealthy? check its metrics and logs."
    ;;
  crash)
    echo "==> crashing target-app"
    curl -sf "$TARGET_APP_URL/crash" > /dev/null 2>&1 || true
    QUESTION="target-app seems down, what happened?"
    ;;
  slow)
    echo "==> injecting latency into target-app"
    curl -sf "$TARGET_APP_URL/slow" > /dev/null
    QUESTION="is target-app responding slowly right now?"
    ;;
  reset)
    echo "==> done (state reset only, nothing triggered)"
    exit 0
    ;;
  *)
    echo "unknown mode: $MODE (expected: leak | crash | slow | reset)" >&2
    exit 1
    ;;
esac

if [[ "$ASK" == false ]]; then
  echo "==> not asking — the proactive watcher (backend/watcher.py) should pick this up"
  echo "    on its own within WATCH_INTERVAL_SECONDS (default 30s). Watch:"
  echo "      docker compose logs -f backend | grep -i watcher"
  echo "      curl -s $BACKEND_URL/audit | python3 -m json.tool   # look for source: \"watcher\""
  exit 0
fi

echo "==> asking the copilot: \"$QUESTION\""
curl -sf -X POST "$BACKEND_URL/ask" \
  -H "Content-Type: application/json" \
  -d "{\"question\": \"$QUESTION\"}" | python3 -m json.tool

echo
echo "==> next: approve via  POST $BACKEND_URL/approve/<action_id>  (from the response above)"
echo "    or open the UI at http://localhost:8501 and click Approve there"
