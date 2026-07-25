"""Slack bot — second first-class interface, pure HTTP client of the same
/ask -> /approve/{id} contract ui/ uses. Socket Mode (no public URL needed in
Compose). Runs as its own container so a dropped Slack WebSocket can't affect
backend or ui.

Slash command: /overwatch <question>
Slack requires an ack within 3 seconds, so the real agent call (which can take
tens of seconds) runs in a background thread; the result is delivered via
respond() (uses the interaction's response_url under the hood).
"""

import logging
import os
import threading

import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

logging.basicConfig(level=logging.INFO)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://backend:8000")

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def _ask_backend(question: str) -> dict:
    r = requests.post(f"{BACKEND_URL}/ask", json={"question": question}, timeout=95)
    r.raise_for_status()
    return r.json()


def _approve_backend(action_id: str) -> dict:
    r = requests.post(f"{BACKEND_URL}/approve/{action_id}", timeout=15)
    r.raise_for_status()
    return r.json()


def _answer_blocks(result: dict) -> list[dict]:
    blocks = [{"type": "section", "text": {"type": "mrkdwn", "text": result["answer"][:2900]}}]
    action = result.get("recommended_action")
    action_id = result.get("action_id")
    if action and action_id:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":rotating_light: *Recommended:* restart `{action['container']}` — {action['reason']}",
                },
            }
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve restart"},
                        "style": "primary",
                        "action_id": "overwatch_approve",
                        "value": action_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Dismiss"},
                        "action_id": "overwatch_dismiss",
                        "value": action_id,
                    },
                ],
            }
        )
    return blocks


@app.command("/overwatch")
def handle_overwatch(ack, respond, command):
    question = command["text"].strip()
    if not question:
        ack("Usage: `/overwatch <question>` — e.g. `/overwatch is target-app healthy?`")
        return
    ack(f":mag: Investigating: {question}")

    def worker():
        try:
            result = _ask_backend(question)
        except Exception as exc:
            respond(text=f":x: Investigation failed: {exc}")
            return
        respond(blocks=_answer_blocks(result), text=result["answer"][:2900])

    threading.Thread(target=worker, daemon=True).start()


@app.action("overwatch_approve")
def handle_approve(ack, body, respond):
    ack()
    action_id = body["actions"][0]["value"]

    def worker():
        try:
            result = _approve_backend(action_id)
        except Exception as exc:
            respond(text=f":x: Approve failed: {exc}", replace_original=False)
            return
        if result.get("status") == "restarted":
            respond(text=f":white_check_mark: Restarted `{result['container']}`.", replace_original=False)
        else:
            respond(text=f":x: Restart failed: {result.get('error', 'unknown error')}", replace_original=False)

    threading.Thread(target=worker, daemon=True).start()


@app.action("overwatch_dismiss")
def handle_dismiss(ack, respond):
    ack()
    respond(text=":no_entry_sign: Dismissed — no action taken.", replace_original=False)


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
