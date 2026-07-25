"""Design tokens + global CSS for the Overwatch UI.

Canonical palette/type source is docs/UI-DESIGN.md — this module applies
those tokens and extends them (border/haze/panel_deep) for the landing
treatment without overriding anything documented there.

Layout note: the whole landing narrative (hero through "try it") is meant
to be rendered as ONE html string via components/landing.py, not one
st.markdown() call per section — Streamlit wraps every markdown call in
its own bordered element-container with its own default margins, and
stacking six of those is what reads as "a pile of boxes" instead of a
page. One container, our own spacing rhythm, borders used exactly once
(the safety panel) instead of on every card.
"""

import streamlit as st

COLORS = {
    "ink": "#0B0F14",
    "panel": "#121821",
    "panel_deep": "#0E141C",
    "border": "#1E2733",
    "vital": "#35D0A6",
    "alert": "#F5A623",
    "critical": "#E4483C",
    "paper": "#E8ECEF",
    "haze": "#BEC4C9",
    "muted": "#5B6672",
}

_FONT_IMPORT = (
    "https://fonts.googleapis.com/css2?"
    "family=Space+Grotesk:wght@500;700&family=Inter:wght@400;500&"
    "family=JetBrains+Mono:wght@400;500&display=swap"
)


def inject() -> None:
    c = COLORS
    st.markdown(
        f"""<style>
@import url('{_FONT_IMPORT}');

html, body, [class*="css"] {{ font-family: 'Inter', sans-serif; }}
h1, h2, h3 {{ font-family: 'Space Grotesk', sans-serif; }}
code, pre {{ font-family: 'JetBrains Mono', monospace; }}
button:focus-visible {{ outline: 2px solid {c['vital']} !important; outline-offset: 2px; }}

/* give the page real room to breathe instead of Streamlit's narrow centered column */
.block-container {{ max-width: 1320px; padding-top: 2.5rem; padding-bottom: 5rem; }}
.hero-tagline {{ max-width: 42rem; }}

/* --- landing: one continuous flow, spacing owned entirely by us --- */
.landing > * {{ margin-bottom: 3rem; }}
.landing > *:last-child {{ margin-bottom: 2.5rem; }}

/* --- hero --- */
.hero {{ position: relative; }}
.hero-eyebrow {{
  font-family: 'JetBrains Mono', monospace; font-size: 0.78rem;
  letter-spacing: 0.18em; color: {c['vital']}; text-transform: uppercase;
}}
.hero-wordmark {{
  font-family: 'Space Grotesk', sans-serif; font-weight: 700;
  font-size: 3.4rem; line-height: 1.15; letter-spacing: -0.01em; color: {c['paper']};
  margin: 0.5rem 0 1rem;
}}
.hero-wordmark-sub {{
  font-weight: 500; font-size: 0.48em; color: {c['haze']}; letter-spacing: 0;
}}
.hero-tagline {{
  font-family: 'Inter', sans-serif; font-size: 1.1rem;
  color: {c['haze']}; max-width: 34rem; line-height: 1.6;
}}
.status-pill {{
  display: inline-flex; align-items: center; gap: 0.45rem;
  font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: {c['muted']};
  border: 1px solid {c['border']}; border-radius: 999px; padding: 0.32rem 0.75rem;
  background: {c['panel']}; margin-bottom: 1.6rem;
}}
.status-dot {{ height: 7px; width: 7px; border-radius: 50%; display: inline-block; }}
.status-dot.up {{ background: {c['vital']}; box-shadow: 0 0 6px {c['vital']}; }}
.status-dot.down {{ background: {c['critical']}; box-shadow: 0 0 6px {c['critical']}; }}
.hero-pulse {{ margin-top: 1.8rem; line-height: 0; }}
.hero-pulse svg {{ width: 100%; height: 48px; display: block; }}
.meta-row {{ display: flex; gap: 0.55rem; margin-top: 1.3rem; flex-wrap: wrap; }}
.meta-chip {{
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: {c['muted']};
  border: 1px solid {c['border']}; border-radius: 999px; padding: 0.3rem 0.7rem;
}}

/* --- section label (precedes each landing section) --- */
.section-label {{
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; letter-spacing: 0.16em;
  color: {c['muted']}; text-transform: uppercase; margin: 0 0 1rem;
}}

/* --- how-it-works step pipeline --- */
.step-row {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 1.5rem 1.2rem; }}
.step-card {{ border-top: 2px solid {c['vital']}; padding: 0.9rem 0 0; }}
.step-index {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: {c['vital']}; letter-spacing: 0.08em; }}
.step-title {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1.05rem; color: {c['paper']}; margin: 0.4rem 0 0.4rem; }}
.step-desc {{ font-family: 'Inter', sans-serif; font-size: 0.87rem; color: {c['haze']}; line-height: 1.5; }}

/* --- card grids (proactive + stack) --- */
.feature-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1.1rem; }}
.feature-card {{ background: {c['panel']}; border-radius: 8px; padding: 1.1rem 1.2rem; }}
.feature-port {{
  display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
  color: {c['ink']}; background: {c['vital']}; border-radius: 3px; padding: 0.1rem 0.4rem;
  margin-bottom: 0.55rem; font-weight: 600; letter-spacing: 0.02em;
}}
.feature-name {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; color: {c['paper']}; font-size: 1.02rem; margin-bottom: 0.35rem; }}
.feature-desc {{ font-family: 'Inter', sans-serif; font-size: 0.85rem; color: {c['haze']}; line-height: 1.5; }}

/* --- safety panel: the one bordered, bold accent moment on the page --- */
.safety-panel {{
  background: {c['panel']}; border: 1px solid {c['vital']}; border-radius: 8px; padding: 1.5rem 1.6rem;
}}
.safety-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; letter-spacing: 0.16em; color: {c['vital']}; text-transform: uppercase; margin-bottom: 0.7rem; }}
.safety-body {{ font-family: 'Inter', sans-serif; font-size: 1rem; color: {c['paper']}; line-height: 1.65; }}
.safety-body strong {{ color: {c['vital']}; }}
.safety-body code {{ background: {c['panel_deep']}; padding: 0.1rem 0.35rem; border-radius: 3px; font-size: 0.88em; }}

/* --- CTA panel (try it) --- */
.cta-panel {{ background: {c['panel']}; border-radius: 8px; padding: 1.5rem 1.6rem; }}
.cta-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; letter-spacing: 0.16em; color: {c['vital']}; text-transform: uppercase; margin-bottom: 1.1rem; }}
.cta-steps {{ display: flex; flex-direction: column; gap: 0.7rem; margin-bottom: 1.4rem; }}
.cta-step {{ display: flex; gap: 0.8rem; align-items: baseline; font-family: 'Inter', sans-serif; font-size: 0.92rem; color: {c['paper']}; line-height: 1.5; }}
.cta-step-num {{ font-family: 'JetBrains Mono', monospace; color: {c['muted']}; min-width: 1.3rem; flex-shrink: 0; }}
.cta-button {{
  display: inline-flex; align-items: center; gap: 0.4rem; background: {c['vital']}; color: {c['ink']};
  font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 0.88rem;
  padding: 0.65rem 1.2rem; border-radius: 6px; text-decoration: none;
}}
.cta-button:hover {{ filter: brightness(1.08); }}
.cta-button:focus-visible {{ outline: 2px solid {c['paper']}; outline-offset: 2px; }}

/* --- decisions panel (why these choices) --- */
.decisions-panel {{ background: {c['panel']}; border-radius: 8px; padding: 0.3rem 1.6rem; }}
.decision {{ padding: 0.9rem 0; border-bottom: 1px solid {c['panel_deep']}; }}
.decision:last-child {{ border-bottom: none; }}
.decision-term {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; color: {c['paper']}; font-size: 0.9rem; display: block; margin-bottom: 0.25rem; }}
.decision-body {{ font-family: 'Inter', sans-serif; font-size: 0.84rem; color: {c['haze']}; line-height: 1.5; }}

/* --- verified checklist --- */
.verified-panel {{ background: {c['panel']}; border-radius: 8px; padding: 1.4rem 1.6rem; }}
.check-item {{ display: flex; gap: 0.65rem; align-items: baseline; font-family: 'Inter', sans-serif; font-size: 0.88rem; color: {c['paper']}; padding: 0.35rem 0; line-height: 1.5; }}
.check-mark {{ font-family: 'JetBrains Mono', monospace; color: {c['vital']}; flex-shrink: 0; }}
.verified-caption {{ font-family: 'Inter', sans-serif; font-size: 0.8rem; color: {c['muted']}; margin-top: 0.9rem; line-height: 1.5; }}

/* --- vitals readout row (live tool, not landing) --- */
.vitals-row {{
  display: flex; align-items: center; gap: 0.9rem; padding: 0.7rem 1rem;
  background: {c['panel']}; border-radius: 8px; margin-bottom: 1.3rem;
}}
.vitals-dot {{ height: 10px; width: 10px; border-radius: 50%; display: inline-block; flex-shrink: 0; }}
.vitals-dot.healthy {{ background: {c['vital']}; box-shadow: 0 0 8px {c['vital']}; }}
.vitals-dot.degraded {{ background: {c['alert']}; box-shadow: 0 0 8px {c['alert']}; animation: pulse 1.2s infinite; }}
.vitals-dot.down {{ background: {c['critical']}; box-shadow: 0 0 8px {c['critical']}; }}
@keyframes pulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.35; }} }}
@media (prefers-reduced-motion: reduce) {{ .vitals-dot.degraded {{ animation: none; }} }}
.vitals-name {{ font-family: 'JetBrains Mono', monospace; color: {c['paper']}; min-width: 6.5rem; }}
.vitals-pulse {{ display: inline-flex; }}
.vitals-pulse svg {{ width: 150px; height: 22px; display: block; }}
.vitals-label {{ color: {c['muted']}; margin-left: auto; font-size: 0.85rem; }}
</style>""",
        unsafe_allow_html=True,
    )
