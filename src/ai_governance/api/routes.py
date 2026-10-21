"""HTTP routes for systems, assessments, and legal provisions."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_governance.api.deps import get_actor, get_session
from ai_governance.api.errors import ApiError
from ai_governance.api.schemas import (
    AISystemDetail,
    AISystemSummary,
    AssessmentCreate,
    AssessmentDetail,
    AssessmentSummary,
    ProvisionDetail,
    ProvisionList,
    ProvisionSummary,
)
from ai_governance.assessment.engine import assess
from ai_governance.assessment.facts import UseCase
from ai_governance.db.inventory import AISystem, Assessment
from ai_governance.db.inventory_store import (
    create_system,
    current_act_sha,
    current_record,
    finding_from_row,
    get_assessment,
    get_system,
    list_assessments,
    list_systems,
    record_to_use_case,
    replace_facts,
    save_assessment,
)
from ai_governance.db.models import LegalProvision, Regulation, RegulatoryVersion
from ai_governance.db.workflow_store import record_event, system_reassessment_reasons

router = APIRouter(prefix="/api")


@router.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report that the process is serving requests."""
    return {"status": "ok"}


@router.post("/ai-systems", response_model=AISystemDetail, status_code=201, tags=["ai-systems"])
def create_ai_system(
    body: UseCase,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> AISystemDetail:
    """Register a system and store the first validated fact snapshot."""
    system = create_system(session, body)
    record_event(
        session,
        event_type="system_registered",
        summary=f"Registered {system.name}.",
        actor=actor,
        ai_system_id=system.id,
    )
    return _system_detail(session, system)


@router.get("/ai-systems", response_model=list[AISystemSummary], tags=["ai-systems"])
def list_ai_systems(
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> list[AISystemSummary]:
    """List registered systems. ``q`` matches the current name."""
    return [_system_summary(session, system) for system in list_systems(session, q, limit, offset)]


@router.get("/ai-systems/{system_id}", response_model=AISystemDetail, tags=["ai-systems"])
def read_ai_system(system_id: int, session: Session = Depends(get_session)) -> AISystemDetail:
    """Return the current snapshot of one system."""
    return _system_detail(session, _require_system(session, system_id))


@router.put("/ai-systems/{system_id}", response_model=AISystemDetail, tags=["ai-systems"])
def update_ai_system(
    system_id: int,
    body: UseCase,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> AISystemDetail:
    """Store a new fact snapshot. Older snapshots and assessments stay in place."""
    system = _require_system(session, system_id)
    record = replace_facts(session, system, body)
    record_event(
        session,
        event_type="facts_updated",
        summary=f"Saved fact snapshot {record.version_number} for {system.name}.",
        actor=actor,
        ai_system_id=system.id,
        details={"version_number": record.version_number},
    )
    return _system_detail(session, system)


@router.post(
    "/ai-systems/{system_id}/assessments",
    response_model=AssessmentDetail,
    status_code=201,
    tags=["assessments"],
)
def create_assessment(
    system_id: int,
    body: AssessmentCreate,
    session: Session = Depends(get_session),
    actor: str = Depends(get_actor),
) -> AssessmentDetail:
    """Run the rules engine on the current snapshot and store the result."""
    system = _require_system(session, system_id)
    record = current_record(system)
    use_case = record_to_use_case(record)
    result = assess(
        use_case,
        content_sha256=current_act_sha(session),
        assessed_on=body.assessed_on,
    )
    assessment = save_assessment(session, record, result)
    record_event(
        session,
        event_type="assessment_created",
        summary=f"Stored screening {assessment.id} with status {assessment.status}.",
        actor=actor,
        ai_system_id=system.id,
        assessment_id=assessment.id,
        details={"status": assessment.status, "rule_set_version": assessment.rule_set_version},
    )
    return _assessment_detail(assessment, use_case)


@router.get(
    "/ai-systems/{system_id}/assessments",
    response_model=list[AssessmentSummary],
    tags=["assessments"],
)
def read_system_assessments(system_id: int, session: Session = Depends(get_session)) -> list[AssessmentSummary]:
    """List stored screenings for one system, oldest first."""
    _require_system(session, system_id)
    return [_assessment_summary(item) for item in list_assessments(session, system_id)]


@router.get("/assessments/{assessment_id}", response_model=AssessmentDetail, tags=["assessments"])
def read_assessment(assessment_id: int, session: Session = Depends(get_session)) -> AssessmentDetail:
    """Return one stored screening and the snapshot it used."""
    assessment = get_assessment(session, assessment_id)
    if assessment is None:
        raise ApiError(404, "not_found", f"Assessment {assessment_id} was not found.")
    return _assessment_detail(assessment, record_to_use_case(assessment.use_case_record))


@router.get("/legal-provisions", response_model=ProvisionList, tags=["legal-provisions"])
def list_legal_provisions(
    celex: str = Query(default="32024R1689", min_length=5, max_length=64),
    provision_key: str | None = Query(default=None, max_length=128),
    citation: str | None = Query(default=None, max_length=128),
    kind: str | None = Query(default=None, max_length=32),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> ProvisionList:
    """List provisions from the current version of an imported act."""
    statement = _current_provisions(celex)
    if provision_key is not None:
        statement = statement.where(LegalProvision.provision_key == provision_key)
    if citation is not None:
        statement = statement.where(LegalProvision.citation == citation)
    if kind is not None:
        statement = statement.where(LegalProvision.kind == kind)
    rows = session.execute(
        statement.order_by(LegalProvision.id).limit(limit).offset(offset)
    ).all()
    return ProvisionList(
        items=[_provision_summary(provision, act_celex, digest) for provision, act_celex, digest in rows],
        limit=limit,
        offset=offset,
    )


@router.get("/legal-provisions/{provision_id}", response_model=ProvisionDetail, tags=["legal-provisions"])
def read_legal_provision(provision_id: int, session: Session = Depends(get_session)) -> ProvisionDetail:
    """Return one stored provision, including superseded versions."""
    row = session.execute(
        select(LegalProvision, Regulation.celex, RegulatoryVersion.content_sha256)
        .join(RegulatoryVersion, LegalProvision.regulatory_version_id == RegulatoryVersion.id)
        .join(Regulation, RegulatoryVersion.regulation_id == Regulation.id)
        .where(LegalProvision.id == provision_id)
    ).one_or_none()
    if row is None:
        raise ApiError(404, "not_found", f"Legal provision {provision_id} was not found.")
    provision, act_celex, digest = row
    summary = _provision_summary(provision, act_celex, digest)
    return ProvisionDetail(
        **summary.model_dump(),
        text=provision.provision_text,
        source_file=provision.source_file,
    )


def _require_system(session: Session, system_id: int) -> AISystem:
    system = get_system(session, system_id)
    if system is None:
        raise ApiError(404, "not_found", f"AI system {system_id} was not found.")
    return system


def _system_summary(session: Session, system: AISystem) -> AISystemSummary:
    record = current_record(system)
    latest = system.assessments[-1].status if system.assessments else None
    reasons = system_reassessment_reasons(session, system)
    return AISystemSummary(
        id=system.id,
        name=system.name,
        version_number=record.version_number,
        created_at=system.created_at,
        updated_at=system.updated_at,
        latest_assessment_status=latest,
        reassessment_required=bool(reasons),
        reassessment_reasons=reasons,
    )


def _system_detail(session: Session, system: AISystem) -> AISystemDetail:
    summary = _system_summary(session, system)
    return AISystemDetail(
        **summary.model_dump(),
        use_case=record_to_use_case(current_record(system)),
    )


def _assessment_summary(assessment: Assessment) -> AssessmentSummary:
    return AssessmentSummary(
        id=assessment.id,
        ai_system_id=assessment.ai_system_id,
        use_case_record_id=assessment.use_case_record_id,
        use_case_version=assessment.use_case_record.version_number,
        rule_set_version=assessment.rule_set_version,
        status=assessment.status,
        celex=assessment.celex,
        content_sha256=assessment.content_sha256,
        assessed_on=assessment.assessed_on,
        created_at=assessment.created_at,
    )


def _assessment_detail(assessment: Assessment, use_case: UseCase) -> AssessmentDetail:
    findings = [finding_from_row(row) for row in assessment.findings if row.bucket == "finding"]
    checks = [finding_from_row(row) for row in assessment.findings if row.bucket == "check"]
    summary = _assessment_summary(assessment)
    return AssessmentDetail(
        **summary.model_dump(),
        notice=assessment.notice,
        categories=list(assessment.categories),
        information_gaps=list(assessment.information_gaps),
        contradictions=list(assessment.contradictions),
        use_case=use_case,
        findings=findings,
        checks=checks,
    )


def _current_provisions(celex: str):
    return (
        select(LegalProvision, Regulation.celex, RegulatoryVersion.content_sha256)
        .join(RegulatoryVersion, LegalProvision.regulatory_version_id == RegulatoryVersion.id)
        .join(Regulation, RegulatoryVersion.regulation_id == Regulation.id)
        .where(
            Regulation.celex == celex,
            RegulatoryVersion.language == "en",
            RegulatoryVersion.status == "current",
        )
    )


def _provision_summary(provision: LegalProvision, celex: str, digest: str) -> ProvisionSummary:
    return ProvisionSummary(
        id=provision.id,
        celex=celex,
        content_sha256=digest,
        provision_key=provision.provision_key,
        citation=provision.citation,
        kind=provision.kind,
        heading=provision.heading,
    )
