"""The one claim this whole project rests on, stated plainly — condensed
from docs/architecture.md's "What we're actually building" #2. This is the
single bold visual accent on the page (the only bordered panel); everything
else stays quiet.
"""


def html() -> str:
    return """<div class="safety-panel">
    <div class="safety-label">the hard rule</div>
    <div class="safety-body">
      The chat agent's tools are <strong>all read-only or propose-only</strong> —
      it can query Prometheus, read container status/logs, and search the wiki,
      but it holds no tool that touches the Docker daemon. The only code path
      that can restart a container is <code>POST /approve/{action_id}</code>,
      hand-written outside any tool the model can call, and it only runs after
      a human clicks <strong>Approve restart</strong> in this UI. Same principle
      for writes to the wiki: a structurally separate librarian agent holds the
      only write tool, triggered by backend code, never by its own judgment.
    </div>
    </div>"""
