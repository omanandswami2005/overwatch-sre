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
