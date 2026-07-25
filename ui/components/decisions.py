"""Why these choices — condensed from docs/architecture.md's Design
decisions section. Not sequential, so no numbering: an independent list of
term -> rationale, footer-weight content for anyone who wants the "why."
"""

_DECISIONS = [
    ("One backend container, not several",
     "The safety boundary is the /approve gate and the read-only tool set, "
     "not process isolation — splitting reasoning from execution would add a "
     "network hop for no isolation benefit."),
    ("A hand-written tool-use loop, not a wrapped agent framework",
     "Calling the Anthropic API directly with a handful of tool schemas is small, "
     "fully-owned, and easy to debug under a hackathon clock. HolmesGPT was "
     "evaluated first and dropped — see docs/holmes-gpt-reference.md."),
    ("A separate librarian agent, not a write tool on the chat agent",
     "Wiki writes are lower-stakes than a restart, but giving the chat agent "
     "write access \"just for docs\" would erode the one guarantee the whole "
     "project rests on — so it's structurally impossible, not policy-enforced."),
    ("The watcher's checks are deterministic Python, not an LLM polling loop",
     "Running the full agent every 30s would burn API spend and latency for "
     "no benefit — cheap comparisons decide when to escalate, the LLM only "
     "gets involved once something concrete has already tripped."),
    ("JSONL flat file, not a database, for the audit log",
     "The trail needs to be append-only, human-readable, and demoable with "
     "tail -f — a database adds a migration story for a feature that's "
     "fundamentally \"log every step.\""),
    ("Claude via the Anthropic API, not a local model",
     "Docker Model Runner is Apple-Silicon-tuned; on Intel hosts it's CPU-only "
     "and demo-flaky. ANTHROPIC_API_KEY avoids that risk entirely."),
]


def html() -> str:
    rows = "".join(
        f"""<div class="decision">
        <span class="decision-term">{term}</span>
        <span class="decision-body">{body}</span>
        </div>"""
        for term, body in _DECISIONS
    )
    return f'<div><div class="section-label">why these choices</div><div class="decisions-panel">{rows}</div></div>'
