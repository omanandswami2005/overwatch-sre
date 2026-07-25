"""Footer-weight reference content (why these choices, what's verified),
rendered as one HTML block for the same reason components/landing.py is —
avoid Streamlit stacking two more boxes with their own default margins.
"""

import streamlit as st

from . import decisions, verified


def render() -> None:
    st.markdown(
        f'<div class="landing">{decisions.html()}{verified.html()}</div>',
        unsafe_allow_html=True,
    )
