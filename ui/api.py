"""Thin HTTP client against the backend.

This is the only module in ui/ that talks to the network. Per CLAUDE.md,
the UI owns no business logic beyond rendering what these calls return.
"""

import requests

BACKEND_URL = "http://backend:8000"


def fetch_audit():
    try:
        r = requests.get(f"{BACKEND_URL}/audit", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def ask(question: str) -> dict:
    r = requests.post(f"{BACKEND_URL}/ask", json={"question": question}, timeout=95)
    r.raise_for_status()
    return r.json()


def approve(action_id: str) -> dict:
    r = requests.post(f"{BACKEND_URL}/approve/{action_id}", timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_incidents():
    """Unlike fetch_audit (the raw log), this is pre-grouped per action_id with
    an `approved` flag - used to surface proposals from ANY source (the
    watcher, the Slack bot, scripts/demo-trigger.sh) as actionable cards in
    this console, not just ones the user typed here themselves.
    """
    try:
        r = requests.get(f"{BACKEND_URL}/incidents", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def generate_report(context: str) -> dict:
    r = requests.post(f"{BACKEND_URL}/report/generate", json={"context": context}, timeout=60)
    r.raise_for_status()
    return r.json()


def list_reports():
    try:
        r = requests.get(f"{BACKEND_URL}/reports", timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


def report_markdown(report_id: str) -> str:
    r = requests.get(f"{BACKEND_URL}/report/{report_id}/md", timeout=10)
    r.raise_for_status()
    return r.text


def report_pdf(report_id: str) -> bytes:
    r = requests.get(f"{BACKEND_URL}/report/{report_id}/pdf", timeout=20)
    r.raise_for_status()
    return r.content
