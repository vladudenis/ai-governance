"""Read and write AI systems and assessments.

Functions flush and do not commit. The caller owns the transaction.
"""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ai_governance.assessment.facts import AnnexAnswer, Answer, RoleAnswer, TextFact, UseCase
from ai_governance.assessment.results import AssessmentResult, Finding, LegalReference
from ai_governance.db.inventory import (
    AISystem,
    Assessment,
    AssessmentFinding,
    UseCaseAnswer,
    UseCaseRecord,
)
from ai_governance.db.models import Regulation, RegulatoryVersion

_FACT_FIELDS = {
    name: field.annotation
    for name, field in UseCase.model_fields.items()
    if name != "name"
}


def create_system(session: Session, use_case: UseCase, recorded_at: datetime | None = None) -> AISystem:
    """Insert a system and its first fact snapshot."""
    moment = recorded_at or datetime.now(timezone.utc)
    system = AISystem(name=use_case.name, created_at=moment, updated_at=moment)
    session.add(system)
    session.flush()
    _append_record(session, system, use_case, moment)
    session.flush()
    return system


def replace_facts(session: Session, system: AISystem, use_case: UseCase, recorded_at: datetime | None = None) -> UseCaseRecord:
    """Append a new snapshot. Earlier snapshots and their assessments stay."""
    moment = recorded_at or datetime.now(timezone.utc)
    system.name = use_case.name
    system.updated_at = moment
    record = _append_record(session, system, use_case, moment)
    session.flush()
    return record


def get_system(session: Session, system_id: int) -> AISystem | None:
    """Load one system with its snapshots and assessments."""
    return session.scalar(
        select(AISystem)
        .where(AISystem.id == system_id)
        .options(
            selectinload(AISystem.records).selectinload(UseCaseRecord.answers),
            selectinload(AISystem.assessments),
        )
    )


def list_systems(session: Session, name_query: str | None, limit: int, offset: int) -> list[AISystem]:
    """Return systems ordered by id, optionally filtered by name."""
    statement = (
        select(AISystem)
        .options(
            selectinload(AISystem.records),
            selectinload(AISystem.assessments),
        )
        .order_by(AISystem.id)
        .limit(limit)
        .offset(offset)
    )
    if name_query:
        escaped = name_query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        statement = statement.where(AISystem.name.ilike(f"%{escaped}%", escape="\\"))
    return list(session.scalars(statement))


def current_record(system: AISystem) -> UseCaseRecord:
    """Return the newest snapshot. A system is always created with one."""
    return system.records[-1]


def record_to_use_case(record: UseCaseRecord) -> UseCase:
    """Rebuild the validated record the rules engine accepts."""
    payload: dict[str, object] = {"name": record.name}
    for answer in record.answers:
        payload[answer.field_name] = {
            "value": answer.value,
            "basis": answer.basis,
            "evidence": answer.evidence,
        }
    return UseCase.model_validate(payload)


def current_act_sha(session: Session, celex: str = "32024R1689", language: str = "en") -> str | None:
    """Return the current imported ZIP digest, when that version is loaded."""
    return session.scalar(
        select(RegulatoryVersion.content_sha256)
        .join(Regulation, RegulatoryVersion.regulation_id == Regulation.id)
        .where(
            Regulation.celex == celex,
            RegulatoryVersion.language == language,
            RegulatoryVersion.status == "current",
        )
    )


def save_assessment(session: Session, record: UseCaseRecord, result: AssessmentResult) -> Assessment:
    """Persist an engine result against the snapshot that produced it."""
    assessment = Assessment(
        ai_system_id=record.ai_system_id,
        use_case_record=record,
        rule_set_version=result.rule_set_version,
        celex=result.celex,
        content_sha256=result.content_sha256,
        assessed_on=result.assessed_on,
        status=result.status.value,
        notice=result.notice,
        categories=list(result.categories),
        information_gaps=list(result.information_gaps),
        contradictions=list(result.contradictions),
        created_at=datetime.now(timezone.utc),
    )
    session.add(assessment)
    session.flush()
    position = 0
    for bucket, items in (("finding", result.findings), ("check", result.checks)):
        for item in items:
            assessment.findings.append(_finding_row(assessment.id, position, bucket, item))
            position += 1
    session.flush()
    from ai_governance.db.workflow_store import open_review_task

    open_review_task(session, assessment)
    return assessment


def get_assessment(session: Session, assessment_id: int) -> Assessment | None:
    """Load one assessment with its findings and the snapshot it used."""
    return session.scalar(
        select(Assessment)
        .where(Assessment.id == assessment_id)
        .options(
            selectinload(Assessment.findings),
            selectinload(Assessment.use_case_record).selectinload(UseCaseRecord.answers),
        )
    )


def list_assessments(session: Session, system_id: int) -> list[Assessment]:
    """Return assessments for one system, oldest first."""
    return list(
        session.scalars(
            select(Assessment)
            .where(Assessment.ai_system_id == system_id)
            .options(selectinload(Assessment.use_case_record))
            .order_by(Assessment.id)
        )
    )


def finding_from_row(row: AssessmentFinding) -> Finding:
    """Restore a finding model from a stored row."""
    application = row.application_reference
    return Finding(
        rule_id=row.rule_id,
        rule_version=row.rule_version,
        category=row.category,
        outcome=row.outcome,
        explanation=row.explanation,
        conditions=list(row.conditions),
        facts=list(row.facts),
        missing_facts=list(row.missing_facts),
        legal_references=[LegalReference.model_validate(item) for item in row.legal_references],
        control_ids=list(row.control_ids),
        applicable_from=row.applicable_from,
        application_reference=LegalReference.model_validate(application) if application else None,
        application_reached=row.application_reached,
    )


def _append_record(session: Session, system: AISystem, use_case: UseCase, moment: datetime) -> UseCaseRecord:
    record = UseCaseRecord(
        version_number=len(system.records) + 1,
        name=use_case.name,
        recorded_at=moment,
    )
    system.records.append(record)
    session.flush()
    for field_name in _FACT_FIELDS:
        record.answers.append(_answer_row(record.id, field_name, getattr(use_case, field_name)))
    return record


def _answer_row(record_id: int, field_name: str, fact: Answer | TextFact | AnnexAnswer | RoleAnswer) -> UseCaseAnswer:
    return UseCaseAnswer(
        use_case_record_id=record_id,
        field_name=field_name,
        value=_stored_value(fact),
        basis=fact.basis.value,
        evidence=fact.evidence,
    )


def _stored_value(fact: Answer | TextFact | AnnexAnswer | RoleAnswer) -> str | None:
    value = fact.value
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str):
        if not value.strip():
            return None
        return value
    return str(value)


def _finding_row(assessment_id: int, position: int, bucket: str, item: Finding) -> AssessmentFinding:
    application = item.application_reference.model_dump() if item.application_reference else None
    return AssessmentFinding(
        assessment_id=assessment_id,
        position=position,
        bucket=bucket,
        rule_id=item.rule_id,
        rule_version=item.rule_version,
        category=item.category.value,
        outcome=item.outcome.value,
        explanation=item.explanation,
        conditions=list(item.conditions),
        facts=list(item.facts),
        missing_facts=list(item.missing_facts),
        legal_references=[reference.model_dump() for reference in item.legal_references],
        control_ids=list(item.control_ids),
        applicable_from=item.applicable_from,
        application_reference=application,
        application_reached=item.application_reached,
    )
