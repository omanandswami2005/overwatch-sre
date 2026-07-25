"""The /docs route - the architecture briefing, in-app instead of a
separate link that can go stale or become unshareable. Content mirrors the
published Artifact briefing; kept here so it's always live with the demo.
"""

import streamlit as st

from components import mermaid

LANDING_PAGE = None
MAIN_PAGE = None


def _eyebrow(num: str, label: str) -> None:
    st.markdown(f'<div class="docs-eyebrow"><span class="num">{num}</span>{label}</div>', unsafe_allow_html=True)


def _dek(text: str) -> None:
    st.markdown(f'<p class="docs-dek">{text}</p>', unsafe_allow_html=True)


def _callout(mark: str, text: str, alert: bool = False) -> None:
    cls = "docs-callout alert" if alert else "docs-callout"
    st.markdown(f'<div class="{cls}"><span class="mark">{mark}</span><span>{text}</span></div>', unsafe_allow_html=True)


_SYSTEM_DIAGRAM = """
flowchart TB
    subgraph observed["Observed system"]
        TA["target-app (FastAPI)<br/>/crash /leak /slow /reset /metrics<br/>OpenTelemetry-instrumented"]
        CAD["cadvisor<br/>container-level metrics"]
    end
    PROM["prometheus<br/>scrapes every 5s"]
    JAEGER["jaeger<br/>trace storage + query API"]
    GRAFANA["grafana<br/>dashboards :3000"]
    subgraph copilot["backend (single container)"]
        WATCHER["watcher thread<br/>cheap checks, no LLM, every 30s"]
        AGENT["chat agent<br/>query_prometheus, get_container_status/logs,<br/>query_traces, search_wiki (read-only) . propose_restart"]
        API["FastAPI<br/>/ask /approve /audit /incidents /report/*"]
        DOCKERPY["docker-py<br/>restart container"]
        AUDIT[("audit-log.jsonl")]
        LIB["librarian agent<br/>write_wiki_pages only"]
        WIKI[("wiki/*.md")]
        REPORTS["Haiku extract to Sonnet write<br/>postmortem pipeline"]
    end
    UI["ui (Streamlit)<br/>landing + console + docs"]
    HUMAN(("on-call human"))
    DOCKERD[["Docker daemon"]]
    CLAUDE[["Claude API"]]
    SLACK[["Slack (optional)"]]

    TA -->|"/metrics"| PROM
    TA -.->|"OTLP traces"| JAEGER
    CAD --> PROM
    PROM --> GRAFANA
    JAEGER --> GRAFANA
    WATCHER -.->|"trips a check"| API
    API --> AGENT
    AGENT --> CLAUDE
    AGENT -->|"query"| PROM
    AGENT -->|"query"| JAEGER
    AGENT -->|"read"| DOCKERD
    AGENT -->|"read"| WIKI
    API --> AUDIT
    API -->|"only after /approve"| DOCKERPY
    DOCKERPY --> DOCKERD
    API -.->|"after approved restart"| LIB
    API -.->|"annotate"| GRAFANA
    API -.->|"notify"| SLACK
    LIB --> WIKI
    API -->|"on request"| REPORTS
    REPORTS --> AUDIT
    UI <-->|"HTTP"| API
    HUMAN -->|"asks / approves"| UI
"""

_LOOP_DIAGRAM = """
sequenceDiagram
    actor H as On-call human
    participant UI as ui
    participant BE as backend
    participant AG as chat agent
    participant DK as Docker daemon
    participant AU as audit-log.jsonl

    H->>UI: "why is target-app unhealthy?"
    UI->>BE: POST /ask
    BE->>AG: run tool-use loop
    AG->>AG: query metrics, logs, traces, wiki (read-only)
    AG-->>BE: diagnosis + propose_restart
    BE->>AU: append ask event
    BE-->>UI: answer + action_id
    UI-->>H: diagnosis card, Approve / Dismiss

    H->>UI: clicks Approve
    UI->>BE: POST /approve/action_id
    BE->>DK: container.restart()
    BE->>AU: append approve event
    BE-->>UI: restarted
"""

_AGENTS_DIAGRAM = """
flowchart LR
    subgraph chat["Chat agent - read-only + propose"]
        CT["query_prometheus"]
        CD["get_container_status / logs"]
        CJ["query_traces"]
        CW["search_wiki / read_wiki_page"]
        CP["propose_restart"]
    end
    subgraph lib["Librarian agent - isolated"]
        LW["write_wiki_pages<br/>(only tool it has)"]
    end
    PROM[(Prometheus)]
    JAEGER[(Jaeger)]
    DOCKERD[["Docker daemon"]]
    WIKI[("wiki/*.md")]
    HUMAN(("human"))

    CT --> PROM
    CJ --> JAEGER
    CD --> DOCKERD
    CW --> WIKI
    CP -.->|"recorded, not executed"| PENDING["pending action"]
    PENDING --> HUMAN
    HUMAN -->|"POST /approve"| RESTART["container.restart()"]
    RESTART --> DOCKERD
    RESTART -.->|"triggers, best-effort"| LW
    LW --> WIKI
"""

_WATCHER_DIAGRAM = """
flowchart LR
    TIMER(("every 30s")) --> CHECK{"cheap checks<br/>no LLM call"}
    CHECK -->|"leak over threshold"| TRIP["tripped"]
    CHECK -->|"container not running"| TRIP
    CHECK -->|"nothing"| TIMER
    TRIP --> COOL{"cooldown<br/>elapsed?"}
    COOL -->|"no - skip"| TIMER
    COOL -->|"yes"| ASK["same tool-use loop<br/>a typed question runs"]
    ASK --> AUDIT[("audit-log.jsonl<br/>source: watcher")]
"""

_REPORTS_DIAGRAM = """
flowchart LR
    RAW["raw audit-log +<br/>Prometheus range data"] --> HAIKU["Claude Haiku<br/>extract_brief (forced tool call)"]
    HAIKU --> BRIEF["compressed,<br/>structured brief"]
    BRIEF --> SONNET["Claude Sonnet<br/>writes the report"]
    CTX["developer's own<br/>plain-English context"] --> SONNET
    SONNET --> MD["Markdown<br/>(source of truth)"]
    MD --> PDF["PDF, on demand<br/>(WeasyPrint)"]
"""

_TOOLSET_DIAGRAM = """
classDiagram
    class Toolset {
        <<Protocol>>
        +str name
        +bool read_only
        +schemas() list
        +call(tool_name, tool_input) dict
    }
    class PrometheusToolset { query_prometheus }
    class DockerToolset { get_container_status  get_container_logs }
    class JaegerToolset { query_traces }
    class WikiToolset { search_wiki  read_wiki_page }
    class RemediationToolset { propose_restart (record only) }
    class ToolsetRegistry { +schemas  +call() }
    Toolset <|.. PrometheusToolset
    Toolset <|.. DockerToolset
    Toolset <|.. JaegerToolset
    Toolset <|.. WikiToolset
    Toolset <|.. RemediationToolset
    ToolsetRegistry o-- Toolset
"""


def render() -> None:
    links = st.columns([1, 1, 6])
    if LANDING_PAGE is not None:
        links[0].page_link(LANDING_PAGE, label="About", icon=":material/arrow_back:")
    if MAIN_PAGE is not None:
        links[1].page_link(MAIN_PAGE, label="Console", icon=":material/terminal:")

    st.markdown('<div class="docs-page">', unsafe_allow_html=True)

    st.markdown(
        '<div class="hero-eyebrow">ARCHITECTURE BRIEFING</div>'
        '<div class="hero-wordmark" style="font-size:2.2rem;">One chat window, one approval gate,<br>a full incident trail.</div>'
        '<p class="hero-tagline">Overwatch investigates a live Dockerized system across metrics, logs, and '
        "traces &mdash; including its own incident history &mdash; then proposes a fix. Nothing it recommends "
        "executes until a human clicks Approve, and everything it does, including documenting and reporting "
        "on itself, follows that same rule.</p>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="meta-row">'
        '<span class="meta-chip"><b>7</b> containers</span>'
        '<span class="meta-chip"><b>5</b> pluggable toolsets</span>'
        '<span class="meta-chip"><b>2</b> isolated agents</span>'
        '<span class="meta-chip"><b>1</b> approval gate</span>'
        '<span class="meta-chip"><b>0</b> autonomous writes</span>'
        "</div>",
        unsafe_allow_html=True,
    )

    _eyebrow("01", "SYSTEM OVERVIEW")
    st.markdown("### Seven containers, one direction of trust")
    _dek(
        "Metrics, logs, and traces flow up into the copilot. Reasoning flows out as a chat answer. "
        "The only thing that ever flows back down into the observed system is a restart &mdash; and "
        "only after a human approves it."
    )
    mermaid.render(_SYSTEM_DIAGRAM, height=520)

    _eyebrow("02", "THE CORE LOOP")
    st.markdown("### Propose &rarr; approve &rarr; execute &rarr; audit")
    _dek("This sequence is the entire point of the project. Everything else exists to make it possible and observable.")
    mermaid.render(_LOOP_DIAGRAM, height=460)
    _callout("&rarr;", "Nothing executes between the diagnosis and the human's click. If Approve is never clicked, the action_id simply expires &mdash; no code path reaches the Docker daemon.")

    _eyebrow("03", "TWO AGENTS, ONE BOUNDARY")
    st.markdown("### Read access is shared. Write access isn't.")
    _dek(
        "The chat agent can look at almost everything, including the system's own incident history "
        "&mdash; but it holds no write tool at all. A second, isolated agent, the librarian, is the "
        "only thing that can write to the wiki, and it only runs after a human-approved restart."
    )
    mermaid.render(_AGENTS_DIAGRAM, height=420)

    _eyebrow("04", "PROACTIVE WATCHING")
    st.markdown("### The copilot speaks first")
    _dek(
        "A background thread runs two cheap, deterministic checks per watched container every 30 "
        "seconds, no LLM call, and only escalates to the real investigation once something trips."
    )
    mermaid.render(_WATCHER_DIAGRAM, height=340)
    _callout("verified", "Pushed target-app over threshold with zero manual questions &mdash; it investigated, cited a prior wiki incident, and proposed a restart on its own.")

    _eyebrow("05", "METRICS, LOGS, AND TRACES")
    st.markdown("### Not just talk &mdash; the agent actually uses all three")
    _dek(
        "Prometheus + cAdvisor cover metrics, docker-py covers logs, OpenTelemetry auto-instrumentation "
        "exporting to Jaeger covers traces, with a query_traces tool so the agent can answer "
        '"which specific request is slow," not just "is it up."'
    )
    _callout("verified", 'Asked the live agent "check target-app\'s recent traces, is anything unusually slow?" &mdash; it called query_traces and answered with real span durations, not a guess.')
    _callout("real limitation, not hidden", "cAdvisor on this host doesn't expose per-container name/image labels (a Docker Desktop cgroup-visibility gap) &mdash; the Grafana dashboard's container panels aggregate across all containers rather than silently show \"no data.\"", alert=True)

    _eyebrow("06", "CONTEXT OPTIMIZATION")
    st.markdown("### A cheap model compresses. The smart model writes.")
    _dek("Incident postmortems read raw audit-log history plus Prometheus range data. Rather than feeding all of it to the expensive model on every report, a fast/cheap model compresses first.")
    mermaid.render(_REPORTS_DIAGRAM, height=340)
    _callout("verified", "Generated a real report against this project's own incident history &mdash; cites real action IDs and timestamps from the real audit log, no invented data.")

    _eyebrow("07", "PLUGIN ARCHITECTURE")
    st.markdown("### Adding a capability is: write a module, flip a flag")
    _dek("Every toolset matches one structural Protocol. A registry aggregates whichever are enabled into one Claude tool list. The agent loop itself never changes when a toolset is added.")
    mermaid.render(_TOOLSET_DIAGRAM, height=420)

    _eyebrow("08", "BUILT VS. INTEGRATED")
    st.markdown("### What's ours, and what we stood on")
    st.markdown(
        '<table class="docs-compare">'
        "<tr><th>Piece</th><th>Status</th></tr>"
        '<tr><td>Agent loop, toolset framework, approval gate, audit trail, librarian/wiki split, watcher, report pipeline</td><td><span class="docs-pill ours">hand-written</span></td></tr>'
        '<tr><td>LLM reasoning (chat, librarian, report extraction/writing)</td><td><span class="docs-pill dep">Claude &middot; Sonnet + Haiku</span></td></tr>'
        '<tr><td>Metrics collection &amp; storage</td><td><span class="docs-pill dep">Prometheus (CNCF, graduated) + cAdvisor</span></td></tr>'
        '<tr><td>Tracing</td><td><span class="docs-pill dep">OpenTelemetry (CNCF, graduated 2026) + Jaeger (CNCF, graduated)</span></td></tr>'
        '<tr><td>Dashboards</td><td><span class="docs-pill dep">Grafana</span></td></tr>'
        '<tr><td>Container control</td><td><span class="docs-pill dep">Docker Engine API via docker-py</span></td></tr>'
        "</table>",
        unsafe_allow_html=True,
    )

    _eyebrow("09", "HONEST ASSESSMENT")
    st.markdown("### Modular monolith. Not horizontally scalable &mdash; on purpose.")
    _dek("The backend is one process, cleanly split into swappable modules. Optimized for one demo host in a time-boxed build, not production scale &mdash; a deliberate trade-off.")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            '<div class="feature-card"><div class="feature-name" style="color:#35D0A6;">Holds up</div>'
            '<div class="feature-desc">New capabilities are additive modules, not edits to the agent loop.<br>'
            "Two-agent write isolation has no shared-state race to worry about.<br>"
            "Cheap-model-first keeps report generation cost bounded as history grows.</div></div>",
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            '<div class="feature-card"><div class="feature-name" style="color:#F5A623;">Real limits</div>'
            '<div class="feature-desc">Pending actions live in an in-memory dict &mdash; one process only.<br>'
            "audit-log.jsonl is a single flat file, not safe for concurrent writers.<br>"
            "One Docker socket, one host &mdash; no cluster-spanning remediation.</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
