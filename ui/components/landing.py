"""Renders the entire landing narrative (hero through "try it") as ONE
st.markdown() call. Streamlit gives every markdown call its own
element-container with its own default margins; six separate calls read as
a stack of boxes instead of a page. One container, one continuous flow,
spacing owned by .landing's own CSS (theme.py).
"""

import streamlit as st

from . import features, how_it_works, proactive, safety, stack, try_it
from . import hero as hero_module


def render(status: str, tick: int) -> None:
    sections = "".join(
        [
            hero_module.html(status, tick),
            features.html(),
            how_it_works.html(),
            proactive.html(),
            safety.html(),
            stack.html(),
            try_it.html(),
        ]
    )
    st.markdown(f'<div class="landing">{sections}</div>', unsafe_allow_html=True)
