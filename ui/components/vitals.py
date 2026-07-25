"""Vitals derivation + the pulse-line signature element (see UI-DESIGN.md)."""

import math

import streamlit as st

STATUS_COLOR = {"healthy": "#35D0A6", "degraded": "#F5A623", "down": "#E4483C"}


def vitals_status(events) -> tuple[str, str]:
    """Derives status from the latest real ask/approve audit event — never a
    client-side guess, per the UI's 'owns no business logic' rule.

    Scans backward for the most recent ask/approve rather than trusting
    events[-1]: the backend appends librarian/report_generated events after
    approve, so the literal last event isn't always the one that carries
    status (e.g. approve -> librarian means events[-1]["type"] == "librarian").
    """
    if events is None:
        return "down", "backend unreachable"
    for event in reversed(events):
        event_type = event.get("type")
        if event_type == "approve":
            if event.get("result", {}).get("status") == "restarted":
                return "healthy", "recovering"
            continue
        if event_type == "ask":
            if event.get("recommended_action"):
                return "degraded", "awaiting approval"
            return "healthy", "healthy"
    return "healthy", "healthy"


def pulse_svg(status: str, tick: int, width: int = 600, height: int = 40, points: int = 48) -> str:
    """Heart-rate-style pulse line, shape keyed off the real derived vitals
    status — calm when healthy, irregular when degraded, flat when down.
    viewBox is fixed; the rendered <svg> stretches to fill its container."""
    mid = height / 2
    pts = []
    for i in range(points):
        x = i / (points - 1) * width
        t = i + tick
        if status == "healthy":
            y = mid + math.sin(t / 3) * (height * 0.22)
        elif status == "degraded":
            y = mid + math.sin(t / 1.1) * (height * 0.42) * (1 if i % 3 else -0.6)
        else:
            y = mid
        pts.append(f"{x:.1f},{y:.1f}")
    color = STATUS_COLOR[status]
    return (
        f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{" ".join(pts)}" fill="none" stroke="{color}" '
        f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    )


def render_strip(status: str, label: str, tick: int) -> None:
    st.markdown(
        f"""<div class="vitals-row">
        <span class="vitals-dot {status}"></span>
        <span class="vitals-name">target-app</span>
        <span class="vitals-pulse">{pulse_svg(status, tick, width=300, height=22, points=36)}</span>
        <span class="vitals-label">{label}</span>
        </div>""",
        unsafe_allow_html=True,
    )
