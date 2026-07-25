"""Collapsed-by-default audit trail — every step, monospace, newest first."""

import streamlit as st


def render(events: list[dict] | None) -> None:
    with st.expander(f"audit trail ({len(events or [])} events)"):
        for event in (events or [])[::-1]:
            st.code(str(event), language=None)
