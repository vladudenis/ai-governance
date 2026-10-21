"""Review, remediation, controls, audit events, and stored reports.

An assessment keeps the screening it was given. A later fact change or a newer
rule set does not rewrite that row. The review task, decision, and report
versions point at that assessment.
"""

from datetime import date, datetime

from sqlalchemy import (
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

from ai_governance.db.base import Base

REVIEW_STATUSES = ("open", "decided")
DECISIONS = (
    "accepted_for_tracking",
    "accepted_with_conditions",
    "changes_requested",
    "not_accepted",
)
REMEDIATION_STATUSES = ("open", "in_progress", "done", "cancelled")
EVIDENCE_STATUSES = ("submitted", "accepted", "not_accepted")
CONTROL_STATUSES = ("not_started", "in_place", "gap", "not_applicable")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class ReviewTask(Base):
    """One governance review for one stored screening."""

    __tablename__ = "review_tasks"
    __table_args__ = (
        UniqueConstraint("assessment_id", name="uq_review_tasks_assessment"),
        CheckConstraint(_allowed("status", REVIEW_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
    )
    ai_system_id: Mapped[int] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    decision: Mapped["ReviewerDecision | None"] = relationship(
        back_populates="review_task",
        cascade="all, delete-orphan",
        uselist=False,
    )


class ReviewerDecision(Base):
    """The reviewer's recorded decision. It is not a legal approval."""

    __tablename__ = "reviewer_decisions"
    __table_args__ = (
        UniqueConstraint("review_task_id", name="uq_reviewer_decisions_task"),
        CheckConstraint(_allowed("decision", DECISIONS), name="decision"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_task_id: Mapped[int] = mapped_column(
        ForeignKey("review_tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    review_task: Mapped[ReviewTask] = relationship(back_populates="decision")


class RemediationAction(Base):
    """Work assigned from a screening."""

    __tablename__ = "remediation_actions"
    __table_args__ = (
        CheckConstraint(_allowed("status", REMEDIATION_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ai_system_id: Mapped[int] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    finding_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessment_findings.id", ondelete="SET NULL"),
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    owner: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    evidence: Mapped[list["EvidenceRecord"]] = relationship(
        back_populates="remediation_action",
        cascade="all, delete-orphan",
        order_by="EvidenceRecord.id",
    )


class EvidenceRecord(Base):
    """A note submitted against a remediation action, and its review."""

    __tablename__ = "evidence_records"
    __table_args__ = (
        CheckConstraint(_allowed("review_status", EVIDENCE_STATUSES), name="review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    remediation_action_id: Mapped[int] = mapped_column(
        ForeignKey("remediation_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_by: Mapped[str] = mapped_column(String(200), nullable=False)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(200))
    review_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    remediation_action: Mapped[RemediationAction] = relationship(back_populates="evidence")


class ControlAssessment(Base):
    """Status of one catalog control for one screening."""

    __tablename__ = "control_assessments"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "control_id",
            name="uq_control_assessments_assessment_control",
        ),
        CheckConstraint(_allowed("status", CONTROL_STATUSES), name="status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    control_id: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditEvent(Base):
    """One recorded change to a system, screening, control, decision, or report."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ai_system_id: Mapped[int | None] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        index=True,
    )
    assessment_id: Mapped[int | None] = mapped_column(
        ForeignKey("assessments.id", ondelete="SET NULL"),
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    actor: Mapped[str] = mapped_column(String(200), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GovernanceReport(Base):
    """One stored markdown report. A later generation is a new version."""

    __tablename__ = "governance_reports"
    __table_args__ = (
        UniqueConstraint(
            "assessment_id",
            "version_number",
            name="uq_governance_reports_assessment_version",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assessment_id: Mapped[int] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    ai_system_id: Mapped[int] = mapped_column(
        ForeignKey("ai_systems.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content_markdown: Mapped[str] = mapped_column(Text, nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
