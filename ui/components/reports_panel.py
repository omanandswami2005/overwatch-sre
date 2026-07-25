"""Incident report generation - context in, a 7-section Markdown postmortem
and a downloadable PDF out (backend/reports.py's Haiku-extract/Sonnet-write
pipeline). No sidebar in this app's actual layout, so this renders as a
collapsed-by-default section on the console, next to the audit drawer.
"""

import streamlit as st

import api


def render() -> None:
    with st.expander("generate incident report", icon=":material/description:"):
        context = st.text_area(
            "What happened? (plain English - the report cites real audit-log/metric data, this just adds the human framing)",
            key="report_context",
            placeholder="e.g. the repeated memory leak we saw earlier today",
        )
        if st.button("Generate report", key="generate_report_btn", disabled=not context.strip()):
            with st.spinner("Extracting a brief, then writing the report..."):
                try:
                    result = api.generate_report(context.strip())
                    st.session_state["last_report_id"] = result["id"]
                    st.success(f"Report {result['id']} generated.")
                except Exception as exc:
                    st.error(f"Report generation failed: {exc}")

        last_id = st.session_state.get("last_report_id")
        if last_id:
            _render_report(last_id)

        st.markdown("---")
        _render_report_list()


def _render_report(report_id: str) -> None:
    try:
        md_text = api.report_markdown(report_id)
    except Exception as exc:
        st.error(f"Couldn't load report {report_id}: {exc}")
        return

    # a container, not st.expander - this already renders inside the outer
    # "generate incident report" expander, and Streamlit doesn't allow
    # expanders nested inside expanders (confirmed the hard way, via a real
    # StreamlitAPIException while testing this against the live app).
    with st.container(border=True):
        st.markdown(f"**report: {report_id}**")
        st.markdown(md_text)
        c1, c2 = st.columns(2)
        c1.download_button(
            "Download .md",
            data=md_text,
            file_name=f"{report_id}.md",
            mime="text/markdown",
            key=f"dl-md-{report_id}",
        )
        try:
            pdf_bytes = api.report_pdf(report_id)
            c2.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name=f"{report_id}.pdf",
                mime="application/pdf",
                key=f"dl-pdf-{report_id}",
            )
        except Exception as exc:
            c2.error(f"PDF unavailable: {exc}")


def _render_report_list() -> None:
    reports = api.list_reports()
    if reports is None:
        st.caption("Can't reach the backend to list past reports.")
        return
    if not reports:
        st.caption("No reports generated yet.")
        return
    st.caption(f"past reports ({len(reports)})")
    for r in reports:
        if st.button(r["title"], key=f"open-report-{r['id']}", use_container_width=True):
            st.session_state["last_report_id"] = r["id"]
            st.rerun()
