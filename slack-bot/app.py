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
import re
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
        is_rollback = action.get("type") == "rollback_container"
        verb = "roll back" if is_rollback else "restart"
        approve_label = "Approve rollback" if is_rollback else "Approve restart"
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":rotating_light: *Recommended:* {verb} `{action['container']}` — {action['reason']}",
                },
            }
        )
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": approve_label},
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


def _investigate_and_reply(question: str, reply) -> None:
    """Shared by the slash command and @mention handler - reply() is either
    respond() (slash command, has a response_url) or say() (event, posts to
    the channel directly). Runs in a background thread either way, since both
    need to stay responsive while the real agent call (tens of seconds) runs.
    """

    def worker():
        try:
            result = _ask_backend(question)
        except Exception as exc:
            reply(text=f":x: Investigation failed: {exc}")
            return
        reply(blocks=_answer_blocks(result), text=result["answer"][:2900])

    threading.Thread(target=worker, daemon=True).start()


@app.command("/overwatch")
def handle_overwatch(ack, respond, command):
    question = command["text"].strip()
    if not question:
        ack("Usage: `/overwatch <question>` — e.g. `/overwatch is target-app healthy?`")
        return
    ack(f":mag: Investigating: {question}")
    _investigate_and_reply(question, respond)


@app.event("app_mention")
def handle_mention(event, say):
    # event["text"] looks like "<@U0BKU6FLRB3> is target-app healthy?" - strip
    # the mention itself, whichever user/bot ID it resolves to.
    question = re.sub(r"^<@[^>]+>\s*", "", event.get("text", "")).strip()
    if not question:
        say(text="Mention me with a question — e.g. `@sreagent is target-app healthy?`")
        return
    say(text=f":mag: Investigating: {question}")
    _investigate_and_reply(question, say)


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
        status = result.get("status")
        if status == "restarted":
            respond(text=f":white_check_mark: Restarted `{result['container']}`.", replace_original=False)
        elif status in ("no_previous_image", "previous_image_found_not_executed"):
            respond(text=f":information_source: {result.get('message', status)}", replace_original=False)
        else:
            respond(text=f":x: Failed: {result.get('error', 'unknown error')}", replace_original=False)

    threading.Thread(target=worker, daemon=True).start()


@app.action("overwatch_dismiss")
def handle_dismiss(ack, respond):
    ack()
    respond(text=":no_entry_sign: Dismissed — no action taken.", replace_original=False)


if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()
