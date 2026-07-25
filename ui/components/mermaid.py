"""Mermaid diagram rendering for the /docs page.

Streamlit has no built-in Mermaid support (unlike the Artifact this page's
content originated from), so this loads mermaid.js from a CDN inside a
components.html() sandboxed iframe - that's a normal browser context, not
the CSP-restricted Artifact sandbox, so a CDN script tag is fine here.
"""

import streamlit.components.v1 as components

_THEME_VARS = """{
  'background':'#121821','primaryColor':'#171F2A','primaryTextColor':'#E8ECEF',
  'primaryBorderColor':'#35D0A6','lineColor':'#5B6672','secondaryColor':'#171F2A',
  'tertiaryColor':'#0B0F14','fontFamily':'JetBrains Mono, monospace','fontSize':'13px'
}"""


def render(code: str, height: int = 380) -> None:
    html = f"""
    <div style="background:#0B0F14; padding:4px;">
      <pre class="mermaid" style="margin:0;">{code}</pre>
    </div>
    <script type="module">
      import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
      mermaid.initialize({{ startOnLoad: true, theme: 'base', themeVariables: {_THEME_VARS} }});
    </script>
    """
    components.html(html, height=height, scrolling=True)
