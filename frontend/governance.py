"""Review, controls, audit, and report pages."""

import streamlit as st

from frontend.client import ApiClient, ApiError

DECISIONS = (
    ("accepted_for_tracking", "Accepted for internal tracking"),
    ("accepted_with_conditions", "Accepted with conditions"),
    ("changes_requested", "Changes requested"),
    ("not_accepted", "Not accepted"),
)
CONTROL_STATUSES = (
    ("not_started", "Not started"),
    ("in_place", "In place"),
    ("gap", "Gap"),
    ("not_applicable", "Not applicable"),
)


def render_review(client: ApiClient) -> None:
    """Open review queue, a decision, and remediation for the selected system."""
    st.header("Review")
    st.caption("A decision here is an internal governance record. It is not a legal approval.")
    try:
        queue = client.list_review_tasks("open")
    except ApiError as exc:
        st.error(exc.message)
        return
    st.subheader("Open queue")
    if not queue:
        st.info("No open reviews.")
    for task in queue:
        with st.container(border=True):
            st.markdown(f"**{task['system_name']}** · screening {task['assessment_id']}")
            if st.button("Open", key=f"review-open-{task['id']}"):
                st.session_state["system_id"] = task["ai_system_id"]
                st.session_state["assessment_id"] = task["assessment_id"]
                st.rerun()
    system_id = st.session_state.get("system_id")
    if system_id is None:
        return
    try:
        assessments = client.list_assessments(system_id)
    except ApiError as exc:
        st.error(exc.message)
        return
    if not assessments:
        st.info("This system has no screening to review.")
        return
    selected = st.session_state.get("assessment_id", assessments[-1]["id"])
    if selected not in {item["id"] for item in assessments}:
        selected = assessments[-1]["id"]
    assessment_id = st.selectbox(
        "Screening",
        options=[item["id"] for item in assessments],
        index=[item["id"] for item in assessments].index(selected),
        format_func=lambda item: f"Screening {item}",
    )
    try:
        review = client.get_review(assessment_id)
        actions = client.list_remediation(assessment_id)
    except ApiError as exc:
        st.error(exc.message)
        return
    if review["decision"] is None:
        with st.form("decision"):
            decision = st.selectbox("Decision", [label for _value, label in DECISIONS])
            rationale = st.text_area("Rationale")
            submitted = st.form_submit_button("Record decision", type="primary")
        if submitted:
            value = next(item for item, label in DECISIONS if label == decision)
            try:
                client.record_decision(assessment_id, value, rationale)
            except ApiError as exc:
                st.error(exc.message)
            else:
                st.rerun()
    else:
        stored = review["decision"]
        st.success(f"{stored['decision']} by {stored['reviewer_name']}")
        st.write(stored["rationale"])
    st.subheader("Remediation")
    for action in actions:
        overdue = " · overdue" if action["overdue"] else ""
        st.markdown(f"**{action['title']}** — {action['status']}{overdue}")
        st.caption(f"Owner {action['owner']}")
        for evidence in action["evidence"]:
            st.caption(f"Evidence ({evidence['review_status']}): {evidence['note']}")
    with st.form("remediation"):
        title = st.text_input("Action")
        description = st.text_area("What needs to be done")
        owner = st.text_input("Owner")
        submitted = st.form_submit_button("Assign action")
    if submitted:
        try:
            client.create_remediation(assessment_id, title, description, owner)
        except ApiError as exc:
            st.error(exc.message)
        else:
            st.rerun()


def render_controls(client: ApiClient) -> None:
    """Status of the controls cited by the selected screening."""
    st.header("Controls")
    st.caption("A status here records follow-up work. It does not mean the legal duty is met.")
    assessment_id = _selected_assessment(client)
    if assessment_id is None:
        return
    try:
        controls = client.list_controls(assessment_id)
    except ApiError as exc:
        st.error(exc.message)
        return
    if not controls:
        st.info("This screening does not cite any controls.")
        return
    for control in controls:
        with st.form(f"control-{control['control_id']}"):
            st.markdown(f"**{control['title']}**")
            st.caption(control["summary"])
            st.caption("Citations: " + ", ".join(control["citations"]))
            labels = [label for _value, label in CONTROL_STATUSES]
            current = next(label for value, label in CONTROL_STATUSES if value == control["status"])
            status = st.selectbox("Status", labels, index=labels.index(current))
            notes = st.text_input("Notes", value=control["notes"] or "")
            if st.form_submit_button("Save control"):
                value = next(item for item, label in CONTROL_STATUSES if label == status)
                try:
                    client.save_control(assessment_id, control["control_id"], value, notes)
                except ApiError as exc:
                    st.error(exc.message)
                else:
                    st.rerun()


def render_audit(client: ApiClient) -> None:
    """Newest recorded actions for the open system, or for every system."""
    st.header("Audit trail")
    system_id = st.session_state.get("system_id")
    scope = st.radio("Show", ["This system", "All systems"], horizontal=True, disabled=system_id is None)
    try:
        events = client.list_audit(system_id if scope == "This system" else None)
    except ApiError as exc:
        st.error(exc.message)
        return
    if not events:
        st.info("No audit events yet.")
        return
    for event in events:
        st.markdown(f"**{event['event_type']}** · {event['actor']}")
        st.write(event["summary"])
        st.caption(event["created_at"])


def render_reports(client: ApiClient) -> None:
    """Generate a new report version and download an earlier one."""
    st.header("Reports")
    st.caption("Each generation is kept. A new report does not replace the previous file.")
    assessment_id = _selected_assessment(client)
    if assessment_id is None:
        return
    if st.button("Generate report", type="primary"):
        try:
            created = client.create_report(assessment_id)
        except ApiError as exc:
            st.error(exc.message)
        else:
            st.session_state["report_id"] = created["id"]
            st.rerun()
    try:
        reports = client._request("GET", f"/api/assessments/{assessment_id}/reports")
    except ApiError as exc:
        st.error(exc.message)
        return
    if not reports:
        st.info("No report is stored for this screening.")
        return
    for report in reports:
        st.markdown(f"**Version {report['version_number']}** · {report['generated_by']}")
        st.caption(report["content_sha256"])
        try:
            markdown = client.download_report(report["id"])
        except ApiError as exc:
            st.error(exc.message)
            continue
        st.download_button(
            "Download Markdown",
            data=markdown,
            file_name=f"governance-report-{assessment_id}-v{report['version_number']}.md",
            mime="text/markdown",
            key=f"download-{report['id']}",
        )


def _selected_assessment(client: ApiClient) -> int | None:
    system_id = st.session_state.get("system_id")
    if system_id is None:
        st.info("Open a system from the inventory first.")
        return None
    try:
        assessments = client.list_assessments(system_id)
    except ApiError as exc:
        st.error(exc.message)
        return None
    if not assessments:
        st.info("Screen this system before continuing.")
        return None
    return assessments[-1]["id"]
