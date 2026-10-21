"""Review, remediation, controls, audit, and report routes."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from ai_governance.api.deps import get_actor, get_session
from ai_governance.api.errors import ApiError
from ai_governance.db.inventory_store import get_assessment
from ai_governance.db.workflow import DECISIONS, REMEDIATION_STATUSES
from ai_governance.db.workflow_store import (
    WorkflowError,
    add_evidence,
    add_remediation,
    control_rows,
    generate_report,
    get_report,
    get_review_task,
    list_events,
    list_remediation,
    list_reports,
    list_review_tasks,
    record_decision,
    review_evidence,
    save_control,
    update_remediation_status,
)

router = APIRouter(prefix="/api")


class DecisionCreate(BaseModel):
    """A reviewer's internal decision. It is not a legal approval."""

    model_config = ConfigDict(extra="forbid")

    decision: str
    rationale: str = Field(min_length=1, max_length=4000)


class DecisionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    assessment_id: int
    decision: str
    reviewer_name: str
    rationale: str
    decided_at: str


class ReviewTaskRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    assessment_id: int
    ai_system_id: int
    system_name: str
    status: str
    created_at: str
    decision: DecisionRecord | None = None


class RemediationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    owner: str = Field(min_length=1, max_length=200)
    due_on: date | None = None
    finding_id: int | None = None


class RemediationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: str = Field(min_length=1, max_length=4000)


class EvidenceReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_status: str
    review_note: str = Field(min_length=1, max_length=2000)


class EvidenceRecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    note: str
    submitted_by: str
    review_status: str
    reviewed_by: str | None
    review_note: str | None


class RemediationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    assessment_id: int
    finding_id: int | None
    title: str
    description: str
    owner: str
    status: str
    due_on: date | None
    overdue: bool
    evidence: list[EvidenceRecordModel]


class ControlRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    control_id: str
    title: str
    summary: str
    status: str
    notes: str | None
    citations: list[str]


class ControlUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str
    notes: str | None = Field(default=None, max_length=2000)


class AuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    ai_system_id: int | None
    assessment_id: int | None
    event_type: str
    summary: str
    actor: str
    created_at: str


class ReportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    assessment_id: int
    version_number: int
    content_sha256: str
    generated_by: str
    created_at: str


@router.get("/review-tasks", response_model=list[ReviewTaskRecord], tags=["review"])
def read_review_queue(
    status: str | None = Query(default="open"),
    session: Session = Depends(get_session),
) -> list[ReviewTaskRecord]:
    """List review tasks. The default queue is the tasks still open."""
    if status is not None and status not in {"open", "decided"}:
        raise ApiError(422, "validation_error", "Status must be open or decided.")
    rows = []
    for task, system_name in list_review_tasks(session, status):
        rows.append(_task_record(task, system_name))
    return rows


@router.get("/assessments/{assessment_id}/review", response_model=ReviewTaskRecord, tags=["review"])
def read_review(assessment_id: int, session: Session = Depends(get_session)) -> ReviewTaskRecord:
    """Return the review task for one screening."""
    task = _require_task(session, assessment_id)
    return _task_record(task, task_system_name(session, task.ai_system_id))


@router.post("/assessments/{assessment_id}/review", response_model=ReviewTaskRecord, status_code=201, tags=["review"])
def create_review_decision(
    assessment_id: int,
    body: DecisionCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> ReviewTaskRecord:
    """Record one internal decision and close the review task."""
    _require_named_actor(actor)
    if body.decision not in DECISIONS:
        raise ApiError(422, "validation_error", "The decision is not one of the stored choices.")
    _call(lambda: record_decision(
        session,
        assessment_id,
        decision=body.decision,
        rationale=body.rationale,
        reviewer_name=actor,
    ))
    task = _require_task(session, assessment_id)
    return _task_record(task, task_system_name(session, task.ai_system_id))


@router.get("/assessments/{assessment_id}/remediation", response_model=list[RemediationRecord], tags=["remediation"])
def read_remediation(assessment_id: int, session: Session = Depends(get_session)) -> list[RemediationRecord]:
    """List remediation actions for one screening."""
    _require_assessment(session, assessment_id)
    return [_remediation_record(action) for action in list_remediation(session, assessment_id)]


@router.post(
    "/assessments/{assessment_id}/remediation",
    response_model=RemediationRecord,
    status_code=201,
    tags=["remediation"],
)
def create_remediation(
    assessment_id: int,
    body: RemediationCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> RemediationRecord:
    """Assign a remediation action."""
    _require_named_actor(actor)
    assessment = _require_assessment(session, assessment_id)
    action = _call(lambda: add_remediation(
        session,
        assessment,
        title=body.title,
        description=body.description,
        owner=body.owner,
        due_on=body.due_on,
        finding_id=body.finding_id,
        actor=actor,
    ))
    return _remediation_record(action)


@router.patch("/remediation/{action_id}", response_model=RemediationRecord, tags=["remediation"])
def patch_remediation(
    action_id: int,
    body: RemediationUpdate,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> RemediationRecord:
    """Change a remediation status."""
    _require_named_actor(actor)
    if body.status not in REMEDIATION_STATUSES:
        raise ApiError(422, "validation_error", "The remediation status is not one of the stored choices.")
    action = _call(lambda: update_remediation_status(session, action_id, body.status, actor))
    return _remediation_record(action)


@router.post("/remediation/{action_id}/evidence", response_model=EvidenceRecordModel, status_code=201, tags=["remediation"])
def create_evidence(
    action_id: int,
    body: EvidenceCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> EvidenceRecordModel:
    """Submit evidence for a remediation action."""
    _require_named_actor(actor)
    evidence = _call(lambda: add_evidence(session, action_id, body.note, actor))
    return _evidence_record(evidence)


@router.post("/evidence/{evidence_id}/review", response_model=EvidenceRecordModel, tags=["remediation"])
def create_evidence_review(
    evidence_id: int,
    body: EvidenceReview,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> EvidenceRecordModel:
    """Accept or not accept submitted evidence."""
    _require_named_actor(actor)
    if body.review_status not in {"accepted", "not_accepted"}:
        raise ApiError(422, "validation_error", "Evidence review must be accepted or not_accepted.")
    evidence = _call(lambda: review_evidence(
        session,
        evidence_id,
        review_status=body.review_status,
        review_note=body.review_note,
        actor=actor,
    ))
    return _evidence_record(evidence)


@router.get("/assessments/{assessment_id}/controls", response_model=list[ControlRecord], tags=["controls"])
def read_controls(assessment_id: int, session: Session = Depends(get_session)) -> list[ControlRecord]:
    """List controls cited by the screening, with their stored status."""
    assessment = _require_assessment(session, assessment_id)
    return [ControlRecord.model_validate(row) for row in control_rows(session, assessment)]


@router.put("/assessments/{assessment_id}/controls/{control_id}", response_model=ControlRecord, tags=["controls"])
def update_control(
    assessment_id: int,
    control_id: str,
    body: ControlUpdate,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> ControlRecord:
    """Set the status of one cited control."""
    _require_named_actor(actor)
    if body.status not in {"not_started", "in_place", "gap", "not_applicable"}:
        raise ApiError(422, "validation_error", "The control status is not one of the stored choices.")
    assessment = _require_assessment(session, assessment_id)
    row = _call(lambda: save_control(
        session,
        assessment,
        control_id,
        status=body.status,
        notes=body.notes,
        actor=actor,
    ))
    return ControlRecord.model_validate(row)


@router.get("/audit", response_model=list[AuditRecord], tags=["audit"])
def read_audit(
    ai_system_id: int | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_session),
) -> list[AuditRecord]:
    """Return newest audit events. Filter with ``ai_system_id`` for one system."""
    return [_audit_record(event) for event in list_events(session, ai_system_id, limit)]


@router.post("/assessments/{assessment_id}/reports", response_model=ReportRecord, status_code=201, tags=["reports"])
def create_report(
    assessment_id: int,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> ReportRecord:
    """Store the next report version. Earlier versions stay downloadable."""
    _require_named_actor(actor)
    assessment = _require_assessment(session, assessment_id)
    report = generate_report(session, assessment, actor)
    return _report_record(report)


@router.get("/assessments/{assessment_id}/reports", response_model=list[ReportRecord], tags=["reports"])
def read_reports(assessment_id: int, session: Session = Depends(get_session)) -> list[ReportRecord]:
    """List stored report versions for one screening."""
    _require_assessment(session, assessment_id)
    return [_report_record(report) for report in list_reports(session, assessment_id)]


@router.get("/reports/{report_id}", tags=["reports"])
def download_report(report_id: int, session: Session = Depends(get_session)) -> Response:
    """Download one stored report as Markdown."""
    report = get_report(session, report_id)
    if report is None:
        raise ApiError(404, "not_found", f"Report {report_id} was not found.")
    filename = f"governance-report-{report.assessment_id}-v{report.version_number}.md"
    return Response(
        content=report.content_markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _require_named_actor(actor: str) -> None:
    if actor == "unspecified":
        raise ApiError(422, "actor_required", "Enter your name before recording this action.")


def _require_assessment(session: Session, assessment_id: int):
    assessment = get_assessment(session, assessment_id)
    if assessment is None:
        raise ApiError(404, "not_found", f"Assessment {assessment_id} was not found.")
    return assessment


def _require_task(session: Session, assessment_id: int):
    task = get_review_task(session, assessment_id)
    if task is None:
        raise ApiError(404, "not_found", f"Assessment {assessment_id} has no review task.")
    return task


def _call(action):
    try:
        return action()
    except WorkflowError as exc:
        raise ApiError(exc.status_code, exc.code, exc.message) from exc


def task_system_name(session: Session, ai_system_id: int) -> str:
    from ai_governance.db.inventory import AISystem

    system = session.get(AISystem, ai_system_id)
    return system.name if system is not None else "Unknown system"


def _task_record(task, system_name: str) -> ReviewTaskRecord:
    decision = None
    if task.decision is not None:
        decision = DecisionRecord(
            id=task.decision.id,
            assessment_id=task.decision.assessment_id,
            decision=task.decision.decision,
            reviewer_name=task.decision.reviewer_name,
            rationale=task.decision.rationale,
            decided_at=task.decision.decided_at.isoformat(),
        )
    return ReviewTaskRecord(
        id=task.id,
        assessment_id=task.assessment_id,
        ai_system_id=task.ai_system_id,
        system_name=system_name,
        status=task.status,
        created_at=task.created_at.isoformat(),
        decision=decision,
    )


def _evidence_record(evidence) -> EvidenceRecordModel:
    return EvidenceRecordModel(
        id=evidence.id,
        note=evidence.note,
        submitted_by=evidence.submitted_by,
        review_status=evidence.review_status,
        reviewed_by=evidence.reviewed_by,
        review_note=evidence.review_note,
    )


def _remediation_record(action) -> RemediationRecord:
    today = date.today()
    overdue = bool(
        action.due_on is not None
        and action.due_on < today
        and action.status in {"open", "in_progress"}
    )
    return RemediationRecord(
        id=action.id,
        assessment_id=action.assessment_id,
        finding_id=action.finding_id,
        title=action.title,
        description=action.description,
        owner=action.owner,
        status=action.status,
        due_on=action.due_on,
        overdue=overdue,
        evidence=[_evidence_record(item) for item in action.evidence],
    )


def _audit_record(event) -> AuditRecord:
    return AuditRecord(
        id=event.id,
        ai_system_id=event.ai_system_id,
        assessment_id=event.assessment_id,
        event_type=event.event_type,
        summary=event.summary,
        actor=event.actor,
        created_at=event.created_at.isoformat(),
    )


def _report_record(report) -> ReportRecord:
    return ReportRecord(
        id=report.id,
        assessment_id=report.assessment_id,
        version_number=report.version_number,
        content_sha256=report.content_sha256,
        generated_by=report.generated_by,
        created_at=report.created_at.isoformat(),
    )
