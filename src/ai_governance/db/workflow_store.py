"""Persist review, remediation, controls, audit events, and reports.

Functions flush and do not commit.
"""

from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ai_governance.assessment.catalog import CONTROLS_BY_ID, RULE_SET_VERSION
from ai_governance.db.inventory import AISystem, Assessment, AssessmentFinding
from ai_governance.db.inventory_store import current_act_sha, record_to_use_case
from ai_governance.db.workflow import (
    AuditEvent,
    ControlAssessment,
    EvidenceRecord,
    GovernanceReport,
    RemediationAction,
    ReviewerDecision,
    ReviewTask,
)
from ai_governance.reporting.report import render_governance_report, report_sha256
from ai_governance.workflow.reasons import reassessment_reasons


class WorkflowError(Exception):
    """A workflow action the route turns into an HTTP error."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


def open_review_task(session: Session, assessment: Assessment) -> ReviewTask:
    """Create the open review that belongs to a new screening."""
    now = datetime.now(timezone.utc)
    task = ReviewTask(
        assessment_id=assessment.id,
        ai_system_id=assessment.ai_system_id,
        status="open",
        created_at=now,
        updated_at=now,
    )
    session.add(task)
    session.flush()
    return task


def record_event(
    session: Session,
    *,
    event_type: str,
    summary: str,
    actor: str,
    ai_system_id: int | None = None,
    assessment_id: int | None = None,
    details: dict | None = None,
) -> AuditEvent:
    """Append one audit row."""
    event = AuditEvent(
        ai_system_id=ai_system_id,
        assessment_id=assessment_id,
        event_type=event_type,
        summary=summary,
        actor=actor,
        details=details or {},
        created_at=datetime.now(timezone.utc),
    )
    session.add(event)
    session.flush()
    return event


def system_reassessment_reasons(session: Session, system: AISystem) -> list[str]:
    """Compare the latest screening with the current snapshot, rules, and act text."""
    latest = system.assessments[-1] if system.assessments else None
    return reassessment_reasons(
        has_assessment=latest is not None,
        latest_record_id=latest.use_case_record_id if latest else None,
        current_record_id=system.records[-1].id,
        latest_rule_version=latest.rule_set_version if latest else None,
        current_rule_version=RULE_SET_VERSION,
        latest_content_sha256=latest.content_sha256 if latest else None,
        current_content_sha256=current_act_sha(session),
    )


def list_review_tasks(session: Session, status: str | None) -> list[tuple[ReviewTask, str]]:
    """Return review tasks with the current system name."""
    statement = (
        select(ReviewTask, AISystem.name)
        .join(AISystem, ReviewTask.ai_system_id == AISystem.id)
        .order_by(ReviewTask.id)
    )
    if status is not None:
        statement = statement.where(ReviewTask.status == status)
    return list(session.execute(statement).all())


def get_review_task(session: Session, assessment_id: int) -> ReviewTask | None:
    """Load the review task and its decision."""
    return session.scalar(
        select(ReviewTask)
        .where(ReviewTask.assessment_id == assessment_id)
        .options(selectinload(ReviewTask.decision))
    )


def record_decision(
    session: Session,
    assessment_id: int,
    *,
    decision: str,
    rationale: str,
    reviewer_name: str,
) -> ReviewerDecision:
    """Record the single decision for a screening and close its review task."""
    task = get_review_task(session, assessment_id)
    if task is None:
        raise WorkflowError(404, "not_found", f"Assessment {assessment_id} has no review task.")
    if task.decision is not None:
        raise WorkflowError(409, "already_decided", "This screening already has a reviewer decision.")
    now = datetime.now(timezone.utc)
    stored = ReviewerDecision(
        review_task_id=task.id,
        assessment_id=assessment_id,
        decision=decision,
        reviewer_name=reviewer_name,
        rationale=rationale.strip(),
        decided_at=now,
    )
    task.status = "decided"
    task.updated_at = now
    task.decision = stored
    session.add(stored)
    session.flush()
    record_event(
        session,
        event_type="review_decision_recorded",
        summary=f"Recorded decision {decision} on screening {assessment_id}.",
        actor=reviewer_name,
        ai_system_id=task.ai_system_id,
        assessment_id=assessment_id,
        details={"decision": decision},
    )
    return stored


def list_remediation(session: Session, assessment_id: int) -> list[RemediationAction]:
    """Return remediation actions and their evidence."""
    return list(
        session.scalars(
            select(RemediationAction)
            .where(RemediationAction.assessment_id == assessment_id)
            .options(selectinload(RemediationAction.evidence))
            .order_by(RemediationAction.id)
        )
    )


def add_remediation(
    session: Session,
    assessment: Assessment,
    *,
    title: str,
    description: str,
    owner: str,
    due_on: date | None,
    finding_id: int | None,
    actor: str,
) -> RemediationAction:
    """Assign a remediation action to a screening."""
    if finding_id is not None:
        finding = session.get(AssessmentFinding, finding_id)
        if finding is None or finding.assessment_id != assessment.id:
            raise WorkflowError(404, "not_found", "That finding is not part of this screening.")
    now = datetime.now(timezone.utc)
    action = RemediationAction(
        ai_system_id=assessment.ai_system_id,
        assessment_id=assessment.id,
        finding_id=finding_id,
        title=title.strip(),
        description=description.strip(),
        owner=owner.strip(),
        status="open",
        due_on=due_on,
        created_at=now,
        updated_at=now,
    )
    session.add(action)
    session.flush()
    record_event(
        session,
        event_type="remediation_created",
        summary=f"Assigned remediation “{action.title}” on screening {assessment.id}.",
        actor=actor,
        ai_system_id=assessment.ai_system_id,
        assessment_id=assessment.id,
        details={"remediation_id": action.id, "status": action.status},
    )
    return action


def update_remediation_status(session: Session, action_id: int, status: str, actor: str) -> RemediationAction:
    """Change a remediation status and keep the previous status in the audit row."""
    action = session.scalar(
        select(RemediationAction)
        .where(RemediationAction.id == action_id)
        .options(selectinload(RemediationAction.evidence))
    )
    if action is None:
        raise WorkflowError(404, "not_found", f"Remediation {action_id} was not found.")
    previous = action.status
    action.status = status
    action.updated_at = datetime.now(timezone.utc)
    session.flush()
    record_event(
        session,
        event_type="remediation_status_changed",
        summary=f"Remediation {action.id} moved from {previous} to {status}.",
        actor=actor,
        ai_system_id=action.ai_system_id,
        assessment_id=action.assessment_id,
        details={"remediation_id": action.id, "from": previous, "to": status},
    )
    return action


def add_evidence(session: Session, action_id: int, note: str, actor: str) -> EvidenceRecord:
    """Submit evidence for a remediation action."""
    action = session.get(RemediationAction, action_id)
    if action is None:
        raise WorkflowError(404, "not_found", f"Remediation {action_id} was not found.")
    evidence = EvidenceRecord(
        remediation_action_id=action.id,
        note=note.strip(),
        submitted_by=actor,
        review_status="submitted",
        created_at=datetime.now(timezone.utc),
    )
    session.add(evidence)
    session.flush()
    record_event(
        session,
        event_type="evidence_submitted",
        summary=f"Evidence submitted for remediation {action.id}.",
        actor=actor,
        ai_system_id=action.ai_system_id,
        assessment_id=action.assessment_id,
        details={"evidence_id": evidence.id, "remediation_id": action.id},
    )
    return evidence


def review_evidence(
    session: Session,
    evidence_id: int,
    *,
    review_status: str,
    review_note: str,
    actor: str,
) -> EvidenceRecord:
    """Accept or not accept submitted evidence."""
    evidence = session.scalar(
        select(EvidenceRecord)
        .where(EvidenceRecord.id == evidence_id)
        .options(selectinload(EvidenceRecord.remediation_action))
    )
    if evidence is None:
        raise WorkflowError(404, "not_found", f"Evidence {evidence_id} was not found.")
    if evidence.review_status != "submitted":
        raise WorkflowError(409, "already_reviewed", "This evidence has already been reviewed.")
    evidence.review_status = review_status
    evidence.review_note = review_note.strip()
    evidence.reviewed_by = actor
    evidence.reviewed_at = datetime.now(timezone.utc)
    session.flush()
    action = evidence.remediation_action
    record_event(
        session,
        event_type="evidence_reviewed",
        summary=f"Evidence {evidence.id} marked {review_status}.",
        actor=actor,
        ai_system_id=action.ai_system_id,
        assessment_id=action.assessment_id,
        details={"evidence_id": evidence.id, "review_status": review_status},
    )
    return evidence


def control_rows(session: Session, assessment: Assessment) -> list[dict]:
    """Return cited controls with their stored status, defaulting to not started."""
    cited: list[str] = []
    for finding in assessment.findings:
        if finding.bucket != "finding":
            continue
        for control_id in finding.control_ids:
            if control_id not in cited and control_id in CONTROLS_BY_ID:
                cited.append(control_id)
    stored = {
        row.control_id: row
        for row in session.scalars(
            select(ControlAssessment).where(ControlAssessment.assessment_id == assessment.id)
        )
    }
    for control_id in stored:
        if control_id not in cited and control_id in CONTROLS_BY_ID:
            cited.append(control_id)
    rows: list[dict] = []
    for control_id in cited:
        control = CONTROLS_BY_ID[control_id]
        current = stored.get(control_id)
        rows.append(
            {
                "control_id": control_id,
                "title": control.title,
                "summary": control.summary,
                "status": current.status if current else "not_started",
                "notes": current.notes if current else None,
                "citations": [reference.citation for reference in control.references],
            }
        )
    return rows


def save_control(
    session: Session,
    assessment: Assessment,
    control_id: str,
    *,
    status: str,
    notes: str | None,
    actor: str,
) -> dict:
    """Store the status of one catalog control for this screening."""
    if control_id not in CONTROLS_BY_ID:
        raise WorkflowError(404, "not_found", f"Control {control_id} is not in the catalog.")
    current = session.scalar(
        select(ControlAssessment).where(
            ControlAssessment.assessment_id == assessment.id,
            ControlAssessment.control_id == control_id,
        )
    )
    now = datetime.now(timezone.utc)
    previous = current.status if current else "not_started"
    if current is None:
        current = ControlAssessment(
            assessment_id=assessment.id,
            control_id=control_id,
            status=status,
            notes=notes,
            updated_at=now,
        )
        session.add(current)
    else:
        current.status = status
        current.notes = notes
        current.updated_at = now
    session.flush()
    record_event(
        session,
        event_type="control_status_changed",
        summary=f"Control {control_id} set to {status}.",
        actor=actor,
        ai_system_id=assessment.ai_system_id,
        assessment_id=assessment.id,
        details={"control_id": control_id, "from": previous, "to": status},
    )
    return next(row for row in control_rows(session, assessment) if row["control_id"] == control_id)


def list_events(session: Session, ai_system_id: int | None, limit: int) -> list[AuditEvent]:
    """Return newest audit events, optionally for one system."""
    statement = select(AuditEvent).order_by(AuditEvent.id.desc()).limit(limit)
    if ai_system_id is not None:
        statement = statement.where(AuditEvent.ai_system_id == ai_system_id)
    return list(session.scalars(statement))


def generate_report(session: Session, assessment: Assessment, actor: str) -> GovernanceReport:
    """Store the next report version for a screening."""
    use_case = record_to_use_case(assessment.use_case_record)
    findings = [
        {
            "rule_id": row.rule_id,
            "outcome": row.outcome,
            "explanation": row.explanation,
            "citations": [item["citation"] for item in row.legal_references],
        }
        for row in assessment.findings
        if row.bucket == "finding"
    ]
    task = get_review_task(session, assessment.id)
    decision = None
    if task is not None and task.decision is not None:
        decision = {
            "decision": task.decision.decision,
            "reviewer_name": task.decision.reviewer_name,
            "rationale": task.decision.rationale,
        }
    actions = []
    for action in list_remediation(session, assessment.id):
        actions.append(
            {
                "title": action.title,
                "status": action.status,
                "owner": action.owner,
                "due_on": action.due_on.isoformat() if action.due_on else None,
                "evidence": [
                    {"review_status": item.review_status, "note": item.note}
                    for item in action.evidence
                ],
            }
        )
    version = session.scalar(
        select(func.coalesce(func.max(GovernanceReport.version_number), 0)).where(
            GovernanceReport.assessment_id == assessment.id
        )
    )
    next_version = int(version or 0) + 1
    generated_at = datetime.now(timezone.utc)
    purpose = use_case.intended_purpose.value
    markdown = render_governance_report(
        system_name=assessment.use_case_record.name,
        snapshot_version=assessment.use_case_record.version_number,
        purpose=purpose,
        assessment_id=assessment.id,
        assessment_status=assessment.status,
        rule_set_version=assessment.rule_set_version,
        celex=assessment.celex,
        content_sha256=assessment.content_sha256,
        assessed_on=assessment.assessed_on,
        notice=assessment.notice,
        findings=findings,
        controls=control_rows(session, assessment),
        remediations=actions,
        decision=decision,
        report_version=next_version,
        generated_by=actor,
        generated_at=generated_at,
    )
    report = GovernanceReport(
        assessment_id=assessment.id,
        ai_system_id=assessment.ai_system_id,
        version_number=next_version,
        content_markdown=markdown,
        content_sha256=report_sha256(markdown),
        generated_by=actor,
        created_at=generated_at,
    )
    session.add(report)
    session.flush()
    record_event(
        session,
        event_type="report_generated",
        summary=f"Generated report version {report.version_number} for screening {assessment.id}.",
        actor=actor,
        ai_system_id=assessment.ai_system_id,
        assessment_id=assessment.id,
        details={"report_id": report.id, "version_number": report.version_number, "content_sha256": report.content_sha256},
    )
    return report


def list_reports(session: Session, assessment_id: int) -> list[GovernanceReport]:
    """Return report versions oldest first."""
    return list(
        session.scalars(
            select(GovernanceReport)
            .where(GovernanceReport.assessment_id == assessment_id)
            .order_by(GovernanceReport.version_number)
        )
    )


def get_report(session: Session, report_id: int) -> GovernanceReport | None:
    """Load one stored report."""
    return session.get(GovernanceReport, report_id)
