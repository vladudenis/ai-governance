"""Streamlit pages for the inventory, the fact form, and a stored screening."""

from datetime import date

import streamlit as st

from frontend.client import ApiClient, ApiError
from frontend.forms import (
    ANNEX_OPTIONS,
    CLASSIFICATION_FIELDS,
    IDENTITY_FIELDS,
    NOTICE,
    PROHIBITED_FIELDS,
    ROLE_OPTIONS,
    SCOPE_FIELDS,
    STATUS_NOTES,
    TRANSPARENCY_FIELDS,
    YES_NO_OPTIONS,
    DraftAnswer,
    answers_from_use_case,
    blank_answers,
    build_use_case,
    fact_label,
    status_label,
    OUTCOME_LABELS,
)


def render_inventory(client: ApiClient) -> None:
    """Search registered systems and open one."""
    st.header("AI inventory")
    st.caption(NOTICE)
    query = st.text_input("Search by name", placeholder="Recruitment")
    status_filter = st.selectbox(
        "Assessment status",
        ["All", "Not screened", *STATUS_NOTES.keys()],
        format_func=lambda value: "All" if value == "All" else status_label(None if value == "Not screened" else value),
    )
    try:
        systems = client.list_systems(query.strip() or None)
    except ApiError as exc:
        st.error(exc.message)
        return
    if status_filter == "Not screened":
        systems = [system for system in systems if system["latest_assessment_status"] is None]
    elif status_filter != "All":
        systems = [system for system in systems if system["latest_assessment_status"] == status_filter]
    _metrics(systems)
    if not systems:
        if query.strip() or status_filter != "All":
            st.info("No systems match this search.")
        else:
            st.info("No systems registered yet. Use Register a new system.")
        return
    for system in systems:
        with st.container(border=True):
            title, action = st.columns([6, 1])
            title.markdown(f"**{system['name']}**")
            caption = (
                f"{status_label(system['latest_assessment_status'])}"
                f" · Snapshot {system['version_number']}"
            )
            if system.get("reassessment_required"):
                caption += " · Reassessment needed"
            title.caption(caption)
            if action.button("Open", key=f"open-{system['id']}", type="primary"):
                _open_system(system["id"], "Screening" if system["latest_assessment_status"] else "Use case")


def render_use_case(client: ApiClient) -> None:
    """Create or replace the current fact snapshot."""
    system_id = st.session_state.get("system_id")
    st.header("Use case" if system_id else "Register a use case")
    st.caption("Unanswered questions stay unknown. Yes and no need a short evidence note from the description.")
    try:
        draft = _draft(client, system_id)
    except ApiError as exc:
        st.error(exc.message)
        return
    system_key = "new" if system_id is None else str(system_id)
    with st.form(f"use-case-{system_key}"):
        name = st.text_input("Name", value=draft["name"])
        purpose = st.text_area("Intended purpose", value=draft["purpose"])
        answers: dict[str, DraftAnswer] = {}
        answers["operator_role"] = _choice("Who operates it?", "operator_role", ROLE_OPTIONS, draft, system_key)
        _section("Identity", IDENTITY_FIELDS, answers, draft, system_key)
        with st.expander("Scope exclusions"):
            _fields(SCOPE_FIELDS, answers, draft, system_key)
        with st.expander("Prohibited-practice questions"):
            _fields(PROHIBITED_FIELDS, answers, draft, system_key)
        with st.expander("Classification", expanded=True):
            answers["annex_iii_use"] = _choice("Annex III use", "annex_iii_use", ANNEX_OPTIONS, draft, system_key)
            _fields(CLASSIFICATION_FIELDS, answers, draft, system_key)
        with st.expander("Transparency and general-purpose models"):
            _fields(TRANSPARENCY_FIELDS, answers, draft, system_key)
        submitted = st.form_submit_button("Save snapshot", type="primary")
    if not submitted:
        return
    payload, errors = build_use_case(name, purpose, answers)
    if errors or payload is None:
        for error in errors:
            st.error(error)
        return
    try:
        if system_id is None:
            created = client.create_system(payload)
            st.session_state["system_id"] = created["id"]
        else:
            client.update_system(system_id, payload)
    except ApiError as exc:
        st.error(exc.message)
        return
    st.session_state["draft_for"] = None
    st.session_state["pending_page"] = "Screening"
    st.rerun()


def render_screening(client: ApiClient) -> None:
    """Run the rules engine and show findings with their legal citations."""
    system_id = st.session_state.get("system_id")
    st.header("Screening")
    st.caption(NOTICE)
    if system_id is None:
        st.info("Open a system from the inventory, or register one first.")
        return
    try:
        system = client.get_system(system_id)
        assessments = client.list_assessments(system_id)
    except ApiError as exc:
        st.error(exc.message)
        return
    st.subheader(system["name"])
    st.caption(f"Current snapshot {system['version_number']}")
    assessed_on = st.date_input("Assessment date", value=date.today())
    if st.button("Run screening", type="primary"):
        try:
            created = client.create_assessment(system_id, assessed_on.isoformat())
        except ApiError as exc:
            st.error(exc.message)
            return
        st.session_state["assessment_id"] = created["id"]
        st.rerun()
    if not assessments:
        st.info("No screening is stored for this system yet.")
        return
    labels = {item["id"]: f"Screening {item['id']} · snapshot {item['use_case_version']} · {status_label(item['status'])}" for item in assessments}
    selected = st.session_state.get("assessment_id", assessments[-1]["id"])
    if selected not in labels:
        selected = assessments[-1]["id"]
    assessment_id = st.selectbox(
        "Stored screening",
        options=list(labels),
        index=list(labels).index(selected),
        format_func=lambda item: labels[item],
    )
    try:
        detail = client.get_assessment(assessment_id)
    except ApiError as exc:
        st.error(exc.message)
        return
    _show_result(client, detail)


def _metrics(systems: list[dict]) -> None:
    counts = {status: 0 for status in STATUS_NOTES}
    unscreened = 0
    for system in systems:
        status = system["latest_assessment_status"]
        if status in counts:
            counts[status] += 1
        else:
            unscreened += 1
    columns = st.columns(6)
    columns[0].metric("Systems", len(systems))
    columns[1].metric("Unscreened", unscreened)
    columns[2].metric("Missing facts", counts["needs_further_information"])
    columns[3].metric("Legal review", counts["requires_legal_review"])
    columns[4].metric("High-risk flag", counts["potentially_high_risk"])
    columns[5].metric("Not indicated", counts["no_indicated_prohibited_or_high_risk_practice"])


def _show_result(client: ApiClient, detail: dict) -> None:
    status = detail["status"]
    st.markdown(f"### {status_label(status)}")
    st.write(STATUS_NOTES.get(status, detail["notice"]))
    st.caption(
        f"Rule set {detail['rule_set_version']} · {detail['celex']}"
        + (f" · text {detail['content_sha256']}" if detail["content_sha256"] else " · no imported act linked")
    )
    if detail["contradictions"]:
        for message in detail["contradictions"]:
            st.warning(message)
    if detail["information_gaps"]:
        st.info("Missing facts: " + ", ".join(fact_label(name) for name in detail["information_gaps"]))
    if detail["categories"]:
        st.caption("Topics: " + ", ".join(detail["categories"]))
    st.subheader("Findings")
    if not detail["findings"]:
        st.write("This screening has no findings that need action.")
    for finding in detail["findings"]:
        _finding(finding)
    with st.expander(f"Rules not indicated ({len(detail['checks'])})"):
        for check in detail["checks"]:
            citations = ", ".join(reference["citation"] for reference in check["legal_references"])
            st.markdown(f"**{check['rule_id']}** · {citations}")
            st.caption(check["explanation"])
    _provision(client)


def _finding(finding: dict) -> None:
    with st.container(border=True):
        st.markdown(f"**{finding['rule_id']}** · {OUTCOME_LABELS.get(finding['outcome'], finding['outcome'])}")
        st.caption(f"Rule version {finding['rule_version']} · {finding['category']}")
        st.write(finding["explanation"])
        if finding["missing_facts"]:
            st.caption("Missing: " + ", ".join(fact_label(name) for name in finding["missing_facts"]))
        if finding["applicable_from"]:
            reached = finding["application_reached"]
            when = f"Applies from {finding['applicable_from']}"
            if reached is True:
                when += " on the assessment date"
            elif reached is False:
                when += ". That date is after the assessment date"
            st.caption(when)
        for reference in finding["legal_references"]:
            label = f"{reference['citation']}"
            if st.button(label, key=f"cite-{finding['rule_id']}-{reference['provision_key']}"):
                st.session_state["provision_key"] = reference["provision_key"]
                st.rerun()


def _provision(client: ApiClient) -> None:
    provision_key = st.session_state.get("provision_key")
    if not provision_key:
        return
    st.subheader("Cited provision")
    try:
        provision = client.find_provision(provision_key)
    except ApiError as exc:
        st.error(exc.message)
        return
    if provision is None:
        st.warning(f"{provision_key} is not in the current imported act.")
        return
    st.markdown(f"**{provision['citation']}**")
    if provision.get("heading"):
        st.caption(provision["heading"])
    st.caption(f"{provision['celex']} · {provision['content_sha256']}")
    st.text(provision["text"])


def _draft(client: ApiClient, system_id: int | None) -> dict:
    if "draft" in st.session_state and st.session_state.get("draft_for") == system_id:
        return st.session_state["draft"]
    if system_id is None:
        draft = {"name": "", "purpose": "", "answers": blank_answers()}
    else:
        use_case = client.get_system(system_id)["use_case"]
        purpose = use_case["intended_purpose"]["value"] or ""
        draft = {"name": use_case["name"], "purpose": purpose, "answers": answers_from_use_case(use_case)}
    st.session_state["draft"] = draft
    st.session_state["draft_for"] = system_id
    return draft


def _section(title: str, fields: tuple, answers: dict, draft: dict, system_key: str) -> None:
    st.markdown(f"**{title}**")
    _fields(fields, answers, draft, system_key)


def _fields(fields: tuple, answers: dict, draft: dict, system_key: str) -> None:
    for field_name, label in fields:
        answers[field_name] = _choice(label, field_name, YES_NO_OPTIONS, draft, system_key)


def _choice(label: str, field_name: str, options: tuple, draft: dict, system_key: str) -> DraftAnswer:
    values = [value for value, _text in options]
    labels = [text for _value, text in options]
    current = draft["answers"][field_name].value
    index = values.index(current) if current in values else 0
    picked = st.selectbox(label, labels, index=index, key=f"{system_key}:{field_name}")
    evidence = st.text_input(
        f"Evidence for {label}",
        value=draft["answers"][field_name].evidence,
        key=f"{system_key}:{field_name}:evidence",
        placeholder="Required when the answer is yes or no",
    )
    return DraftAnswer(values[labels.index(picked)], evidence)


def _open_system(system_id: int, page: str) -> None:
    st.session_state["system_id"] = system_id
    st.session_state["draft_for"] = None
    st.session_state["assessment_id"] = None
    st.session_state["pending_page"] = page
    st.rerun()
