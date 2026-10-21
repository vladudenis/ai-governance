"""Inventory and assessment tables.

A use-case record is immutable. Updating a system inserts the next record, and
an assessment points at the record it evaluated. Regulatory text stays in the
tables from Milestone 3. Provision keys on a finding are text, so an assessment
can be stored before that provision row is loaded.
"""

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_governance.assessment.results import AssessmentStatus, Category, Outcome
from ai_governance.db.base import Base

ANSWER_BASES = ("stated", "inferred", "unknown")
ASSESSMENT_STATUSES = tuple(status.value for status in AssessmentStatus)
FINDING_OUTCOMES = tuple(outcome.value for outcome in Outcome)
FINDING_CATEGORIES = tuple(category.value for category in Category)
FINDING_BUCKETS = ("finding", "check")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class AISystem(Base):
    """One registered AI use case."""

    __tablename__ = "ai_systems"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    records: Mapped[list["UseCaseRecord"]] = relationship(
        back_populates="ai_system",
        order_by="UseCaseRecord.version_number",
        cascade="all, delete-orphan",
    )
    assessments: Mapped[list["Assessment"]] = relationship(
        back_populates="ai_system",
        order_by="Assessment.id",
        cascade="all, delete-orphan",
    )


class UseCaseRecord(Base):
    """One immutable snapshot of validated facts."""

    __tablename__ = "use_case_records"
    __table_args__ = (
        UniqueConstraint("ai_system_id", "version_number", name="uq_use_case_records_system_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ai_system_id: Mapped[int] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ai_system: Mapped[AISystem] = relationship(back_populates="records")
    answers: Mapped[list["UseCaseAnswer"]] = relationship(
        back_populates="use_case_record",
        order_by="UseCaseAnswer.field_name",
        cascade="all, delete-orphan",
    )
    assessments: Mapped[list["Assessment"]] = relationship(back_populates="use_case_record")


class UseCaseAnswer(Base):
    """One field of a use-case snapshot."""

    __tablename__ = "use_case_answers"
    __table_args__ = (
        UniqueConstraint("use_case_record_id", "field_name", name="uq_use_case_answers_record_field"),
        CheckConstraint(_allowed("basis", ANSWER_BASES), name="basis"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    use_case_record_id: Mapped[int] = mapped_column(
        ForeignKey("use_case_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field_name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[str | None] = mapped_column(Text)
    basis: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)

    use_case_record: Mapped[UseCaseRecord] = relationship(back_populates="answers")


class Assessment(Base):
    """One rules-engine run against one use-case snapshot."""

    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint(_allowed("status", ASSESSMENT_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ai_system_id: Mapped[int] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    use_case_record_id: Mapped[int] = mapped_column(
        ForeignKey("use_case_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_set_version: Mapped[str] = mapped_column(String(32), nullable=False)
    celex: Mapped[str] = mapped_column(String(64), nullable=False)
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    assessed_on: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    notice: Mapped[str] = mapped_column(Text, nullable=False)
    categories: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    information_gaps: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    contradictions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    ai_system: Mapped[AISystem] = relationship(back_populates="assessments")
    use_case_record: Mapped[UseCaseRecord] = relationship(back_populates="assessments")
    findings: Mapped[list["AssessmentFinding"]] = relationship(
        back_populates="assessment",
        order_by="AssessmentFinding.position",
        cascade="all, delete-orphan",
    )


class AssessmentFinding(Base):
    """One stored rule result, either a finding or a not-indicated check."""

    __tablename__ = "assessment_findings"
    __table_args__ = (
        UniqueConstraint("assessment_id", "position", name="uq_assessment_findings_assessment_position"),
        UniqueConstraint("assessment_id", "bucket", "rule_id", name="uq_assessment_findings_assessment_bucket_rule"),
        CheckConstraint(_allowed("outcome", FINDING_OUTCOMES), name="outcome"),
        CheckConstraint(_allowed("category", FINDING_CATEGORIES), name="category"),
        CheckConstraint(_allowed("bucket", FINDING_BUCKETS), name="bucket"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    bucket: Mapped[str] = mapped_column(String(16), nullable=False)
    rule_id: Mapped[str] = mapped_column(String(64), nullable=False)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    outcome: Mapped[str] = mapped_column(String(64), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    conditions: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    facts: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    missing_facts: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    legal_references: Mapped[list[dict[str, str]]] = mapped_column(JSONB, nullable=False)
    control_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    applicable_from: Mapped[date | None] = mapped_column(Date)
    application_reference: Mapped[dict[str, str] | None] = mapped_column(JSONB)
    application_reached: Mapped[bool | None] = mapped_column(Boolean)

    assessment: Mapped[Assessment] = relationship(back_populates="findings")
