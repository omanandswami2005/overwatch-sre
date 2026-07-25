import os

import requests

SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "").strip()


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
