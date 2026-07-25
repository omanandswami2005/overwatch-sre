# UI Design — Overwatch-SRE

**Purpose:** the visual identity and page layout for the Streamlit UI (Lane C). In a 6.5-hour hackathon the UI is the demo — this is the thing judges actually look at, so it gets more design detail than the other docs. Read alongside [README.md](../README.md) (architecture, API contract), [architecture.md](architecture.md) (system + sequence diagrams), and [CHECKLIST.md](CHECKLIST.md) (C-1/C-2/C-3 tasks this doc governs).

## Direction

The subject is an on-call engineer's console — a NOC wall, a vitals monitor, a terminal that's been staring at a service for hours. Dark isn't a trend pick here, it's what every real ops tool looks like for a reason: low-glare, high-contrast-where-it-counts, legible at a glance during an incident. What makes it *ours* and not generic dark-mode-with-an-accent: two semantic accents instead of one (teal = healthy, amber = degraded), red held back exclusively for genuinely-down/critical so it never cries wolf, and one signature element — a live pulse line per watched service, styled like a heart-rate monitor — that makes "the app has a heartbeat and you're watching it" the whole visual thesis. Triage, diagnosis, vitals: the ER metaphor is already in our own vocabulary (approve, root cause, audit), the UI just makes it literal.

## Tokens

**Color**
| Name | Hex | Use |
|---|---|---|
| `ink` | `#0B0F14` | app background — near-black, slight blue cast |
| `panel` | `#121821` | card/panel/chat-bubble background |
| `vital` | `#35D0A6` | healthy state, primary accent, Approve button |
| `alert` | `#F5A623` | degraded/pending state, warnings |
| `critical` | `#E4483C` | down/critical only — never decorative |
| `paper` | `#E8ECEF` | body text on dark background |
| `muted` | `#5B6672` | timestamps, labels, secondary text |

**Type**
| Role | Face | Where |
|---|---|---|
| Display | Space Grotesk | header, section labels, button text |
| Body | Inter | chat messages, diagnosis card prose |
| Data/mono | JetBrains Mono | audit log lines, metric values, container IDs, PromQL |

**Signature element:** the vitals strip — one pulse line per watched service. Teal and calm when healthy, amber and irregular when degraded, flatlines red when down. Real data drives it (from `/metrics`), not decoration.

## Layout (single screen, three zones)

```
┌──────────────────────────────────────────────────────────┐
│ OVERWATCH · SRE COPILOT                        ● connected │  header bar
├──────────────────────────────────────────────────────────┤
│  target-app   ∿∿∿∿∿∿‾‾‾‾∿∿∿∿   healthy                     │  vitals strip
├──────────────────────────────────────────────────────────┤
│  [Copilot] memory on target-app climbed 40%→92% in 3m      │
│    ┌─────────────────────────────────────────────┐        │
│    │ ROOT CAUSE        likely memory leak          │        │
│    │ evidence           mem_usage_bytes ↑, no GC    │        │  diagnosis card
│    │ logs                "OOM warning" ×14 / 2m      │        │  (inline in chat)
│    │  [ Approve restart ]        [ Dismiss ]         │        │
│    └─────────────────────────────────────────────┘        │
│                                    you: why is it slow?    │  triage chat
├──────────────────────────────────────────────────────────┤
│ ▸ audit trail (3 events)                        collapsed  │  audit drawer
└──────────────────────────────────────────────────────────┘
```

- **Header bar** — product name + a live connection dot (teal = backend reachable, red = not). Static otherwise.
- **Vitals strip** — one row per service (just `target-app` for the demo). Signature element.
- **Triage chat** — native chat: copilot left, user right. The **diagnosis card** appears inline as its own message when Holmes recommends an action — not a modal, stays in the conversation's timeline.
- **Audit drawer** — collapsed by default, monospace log lines, expands on click.

## Copy (write in the interface's voice, not a person's)

- Idle/empty state: *"No incidents yet. Ask what's happening, or wait — Overwatch speaks up first if something breaks."*
- Approve button: **Approve restart** (not "Submit" — names the real action)
- Reject button: **Dismiss** (not "Cancel" — nothing was in progress to cancel)
- Post-approval confirmation: *"Restarted target-app."* (matches the button's own verb)
- Backend unreachable: *"Can't reach the backend. Check `docker compose ps` and retry."* (states what broke + the fix, no apology)
- Vitals status text: `healthy` / `degraded` / `down` — plain words, paired with color, never color alone.

## Streamlit implementation notes

Streamlit fights custom design less than people expect if you stay inside these lanes:

- `.streamlit/config.toml` — set `base="dark"`, `primaryColor="#35D0A6"`, `backgroundColor="#0B0F14"`, `secondaryBackgroundColor="#121821"`, `textColor="#E8ECEF"`. This alone gets buttons/widgets on-brand with zero CSS.
- Custom fonts (Streamlit's `font=` key only accepts generic families) — one `st.markdown("<style>@import url(...);</style>", unsafe_allow_html=True)` block at the top of `ui/app.py`, importing Space Grotesk / Inter / JetBrains Mono from Google Fonts and setting `font-family` on `html, body, [class*="css"]`.
- Chat — use native `st.chat_message()` / `st.chat_input()`, don't hand-roll bubbles. Skin them with the CSS variables above; still reads as ours because the palette/type carries the identity.
- Diagnosis card — `st.container(border=True)` + markdown for evidence bullets + two `st.columns()` for the Approve/Dismiss buttons.
- Audit drawer — `st.expander("Audit trail")` + `st.code()` per line for the monospace log look.
- Vitals strip, realistic scope: a pulsing colored dot + sparkline built from the last N `/metrics` points is achievable in the time budget (small inline SVG via `st.markdown`, redrawn each rerun). A true animated waveform is a stretch goal, not the plan — don't burn Wave-2 time chasing it if the dot+sparkline already sells the metaphor.
- Baseline quality bar regardless of time pressure: visible focus states on the two buttons that matter (Approve/Dismiss), and don't rely on color alone for status (already covered by pairing color + word above).

## Where this plugs into the build

Governs [CHECKLIST.md](CHECKLIST.md) tasks C-1 (skeleton + fixture), C-2 (wire to `/ask`), C-3 (wire Approve to `/approve/{action_id}`). API shape it renders against is defined in [README.md](../README.md#tech-stack-final).
