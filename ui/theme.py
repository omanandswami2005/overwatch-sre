"""Design tokens + global CSS for the Overwatch UI.

Canonical palette/type source is docs/UI-DESIGN.md — this module applies
those tokens and extends them (border/haze/panel_deep) for the hero band
without overriding anything documented there.
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

/* --- hero (landing) band --- */
.hero {{
  position: relative;
  background: linear-gradient(180deg, {c['panel']} 0%, {c['panel_deep']} 100%);
  border: 1px solid {c['border']};
  border-radius: 6px;
  padding: 1.7rem 1.9rem 1.5rem;
  margin-bottom: 1.1rem;
  overflow: hidden;
}}
.hero::before {{
  content: "";
  position: absolute; inset: 0;
  background-image: repeating-linear-gradient(
    to bottom, rgba(232, 236, 239, 0.035) 0px, rgba(232, 236, 239, 0.035) 1px,
    transparent 1px, transparent 7px
  );
  pointer-events: none;
}}
.hero-top {{
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 1rem; position: relative; z-index: 1;
}}
.hero-eyebrow {{
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem;
  letter-spacing: 0.16em; color: {c['muted']}; text-transform: uppercase;
}}
.hero-wordmark {{
  font-family: 'Space Grotesk', sans-serif; font-weight: 700;
  font-size: 2.15rem; letter-spacing: 0.005em; color: {c['paper']};
  margin: 0.2rem 0 0.35rem;
}}
.hero-tagline {{
  font-family: 'Inter', sans-serif; font-size: 0.95rem;
  color: {c['haze']}; max-width: 32rem; line-height: 1.5;
}}
.status-pill {{
  display: flex; align-items: center; gap: 0.45rem; flex-shrink: 0;
  font-family: 'JetBrains Mono', monospace; font-size: 0.74rem; color: {c['muted']};
  border: 1px solid {c['border']}; border-radius: 999px; padding: 0.32rem 0.75rem;
  background: {c['ink']};
}}
.status-dot {{ height: 7px; width: 7px; border-radius: 50%; display: inline-block; }}
.status-dot.up {{ background: {c['vital']}; box-shadow: 0 0 6px {c['vital']}; }}
.status-dot.down {{ background: {c['critical']}; box-shadow: 0 0 6px {c['critical']}; }}
.hero-pulse {{ margin-top: 1rem; position: relative; z-index: 1; line-height: 0; }}
.hero-pulse svg {{ width: 100%; height: 40px; display: block; }}
.meta-row {{ display: flex; gap: 0.55rem; margin-top: 1rem; flex-wrap: wrap; position: relative; z-index: 1; }}
.meta-chip {{
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: {c['muted']};
  border: 1px solid {c['border']}; border-radius: 999px; padding: 0.3rem 0.7rem;
}}

/* --- section label (precedes each landing section) --- */
.section-label {{
  font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; letter-spacing: 0.16em;
  color: {c['muted']}; text-transform: uppercase; margin: 0 0 0.7rem;
}}

/* --- how-it-works step pipeline --- */
.step-row {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 0.85rem; margin-bottom: 1.5rem;
}}
.step-card {{
  background: {c['panel']}; border: 1px solid {c['border']}; border-top: 2px solid {c['vital']};
  border-radius: 4px; padding: 0.95rem 1.05rem 1.05rem;
}}
.step-index {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; color: {c['vital']}; letter-spacing: 0.08em; }}
.step-title {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 1rem; color: {c['paper']}; margin: 0.4rem 0 0.35rem; }}
.step-desc {{ font-family: 'Inter', sans-serif; font-size: 0.84rem; color: {c['haze']}; line-height: 1.45; }}

/* --- service stack grid --- */
.feature-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 0.85rem; margin-bottom: 1.5rem;
}}
.feature-card {{ background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 4px; padding: 0.9rem 1.05rem; }}
.feature-port {{
  display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
  color: {c['ink']}; background: {c['vital']}; border-radius: 3px; padding: 0.1rem 0.4rem;
  margin-bottom: 0.5rem; font-weight: 600; letter-spacing: 0.02em;
}}
.feature-name {{ font-family: 'Space Grotesk', sans-serif; font-weight: 700; color: {c['paper']}; font-size: 0.98rem; margin-bottom: 0.3rem; }}
.feature-desc {{ font-family: 'Inter', sans-serif; font-size: 0.83rem; color: {c['haze']}; line-height: 1.4; }}

/* --- CTA panel (try it) --- */
.cta-panel {{
  background: linear-gradient(160deg, {c['panel']} 0%, {c['panel_deep']} 100%);
  border: 1px solid {c['border']}; border-radius: 6px; padding: 1.3rem 1.4rem 1.4rem;
  margin-bottom: 1.5rem;
}}
.cta-label {{ font-family: 'JetBrains Mono', monospace; font-size: 0.72rem; letter-spacing: 0.16em; color: {c['vital']}; text-transform: uppercase; margin-bottom: 0.85rem; }}
.cta-steps {{ display: flex; flex-direction: column; gap: 0.6rem; margin-bottom: 1.2rem; }}
.cta-step {{ display: flex; gap: 0.75rem; align-items: baseline; font-family: 'Inter', sans-serif; font-size: 0.9rem; color: {c['paper']}; line-height: 1.4; }}
.cta-step-num {{ font-family: 'JetBrains Mono', monospace; color: {c['muted']}; min-width: 1.3rem; flex-shrink: 0; }}
.cta-button {{
  display: inline-flex; align-items: center; gap: 0.4rem; background: {c['vital']}; color: {c['ink']};
  font-family: 'Space Grotesk', sans-serif; font-weight: 700; font-size: 0.85rem;
  padding: 0.6rem 1.1rem; border-radius: 5px; text-decoration: none;
}}
.cta-button:hover {{ filter: brightness(1.08); }}
.cta-button:focus-visible {{ outline: 2px solid {c['paper']}; outline-offset: 2px; }}

/* --- vitals readout row --- */
.vitals-row {{
  display: flex; align-items: center; gap: 0.9rem; padding: 0.6rem 0.95rem;
  background: {c['panel']}; border: 1px solid {c['border']}; border-radius: 6px;
  margin-bottom: 1.1rem;
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
