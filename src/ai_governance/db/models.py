"""Minimum schema for versioned regulatory text.

AI-system inventory, assessments, controls, and the review workflow are later
milestones. Their tables are added with the feature that writes them, so this
schema does not contain unused placeholders.

A legal work is one row in ``regulations``. Each Formex import is a
``regulatory_versions`` row identified by the ZIP digest. Provisions point at
that version. An older version is marked superseded and its provisions stay,
so a later assessment can still cite the text it used.
"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ai_governance.db.base import Base
from ai_governance.ingestion.models import DocumentKind, ProvisionKind

DOCUMENT_KINDS = tuple(kind.value for kind in DocumentKind)
PROVISION_KINDS = tuple(kind.value for kind in ProvisionKind)
VERSION_STATUSES = ("current", "superseded")
RELATIONSHIP_TYPES = (
    "amends",
    "amended_by",
    "proposed_amendment",
    "consolidated_version",
    "consolidation_identifier",
)
FILE_ROLES = ("source", "unparsed")


def _allowed(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class Regulation(Base):
    """One legal work, identified by its CELEX number."""

    __tablename__ = "regulations"
    __table_args__ = (
        CheckConstraint(
            _allowed("document_kind", DOCUMENT_KINDS),
            name="document_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    celex: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    document_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    resource_type: Mapped[str | None] = mapped_column(String(64))
    eli: Mapped[str | None] = mapped_column(Text)
    cellar_uri: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    versions: Mapped[list["RegulatoryVersion"]] = relationship(back_populates="regulation")


class RegulatoryVersion(Base):
    """One imported manifestation of a regulation."""

    __tablename__ = "regulatory_versions"
    __table_args__ = (
        UniqueConstraint(
            "regulation_id",
            "language",
            "content_sha256",
            name="uq_regulatory_versions_regulation_language_sha",
        ),
        CheckConstraint(_allowed("status", VERSION_STATUSES), name="status"),
        Index(
            "uq_regulatory_versions_one_current",
            "regulation_id",
            "language",
            unique=True,
            postgresql_where=text("status = 'current'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regulation_id: Mapped[int] = mapped_column(
        ForeignKey("regulations.id", ondelete="CASCADE"),
        nullable=False,
    )
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    expression_language: Mapped[str] = mapped_column(String(16), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    parser_version: Mapped[str] = mapped_column(String(32), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    notice_title: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    manifestation_uri: Mapped[str | None] = mapped_column(Text)
    resolved_url: Mapped[str | None] = mapped_column(Text)
    oj_reference: Mapped[str | None] = mapped_column(String(64))
    document_date: Mapped[date | None] = mapped_column(Date)
    publication_date: Mapped[date | None] = mapped_column(Date)
    formex_schema: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    regulation: Mapped[Regulation] = relationship(back_populates="versions")
    provisions: Mapped[list["LegalProvision"]] = relationship(back_populates="regulatory_version")


class LegalProvision(Base):
    """One structural unit belonging to exactly one regulatory version."""

    __tablename__ = "legal_provisions"
    __table_args__ = (
        UniqueConstraint(
            "regulatory_version_id",
            "provision_key",
            name="uq_legal_provisions_version_key",
        ),
        UniqueConstraint(
            "regulatory_version_id",
            "id",
            name="uq_legal_provisions_version_row",
        ),
        ForeignKeyConstraint(
            ["regulatory_version_id", "parent_id"],
            ["legal_provisions.regulatory_version_id", "legal_provisions.id"],
            name="fk_legal_provisions_parent_same_version",
        ),
        CheckConstraint(_allowed("kind", PROVISION_KINDS), name="kind"),
        Index("ix_legal_provisions_version_kind", "regulatory_version_id", "kind"),
        Index("ix_legal_provisions_version_citation", "regulatory_version_id", "citation"),
        Index("ix_legal_provisions_parent_id", "parent_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regulatory_version_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    parent_id: Mapped[int | None] = mapped_column(Integer)
    provision_key: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    citation: Mapped[str] = mapped_column(String(128), nullable=False)
    number: Mapped[str | None] = mapped_column(String(64))
    heading: Mapped[str | None] = mapped_column(Text)
    provision_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(128))
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    regulatory_version: Mapped[RegulatoryVersion] = relationship(back_populates="provisions")
    notes: Mapped[list["ProvisionNote"]] = relationship(back_populates="provision")


class ProvisionNote(Base):
    """Footnote text kept off the sentence it is attached to."""

    __tablename__ = "provision_notes"
    __table_args__ = (
        UniqueConstraint(
            "legal_provision_id",
            "position",
            name="uq_provision_notes_provision_position",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_provision_id: Mapped[int] = mapped_column(
        ForeignKey("legal_provisions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    note_text: Mapped[str] = mapped_column(Text, nullable=False)

    provision: Mapped[LegalProvision] = relationship(back_populates="notes")


class RegulatoryRelationship(Base):
    """A link from an imported version to another work that is not its text.

    The target may not be loaded yet, so the identifier is stored as text
    rather than a foreign key.
    """

    __tablename__ = "regulatory_relationships"
    __table_args__ = (
        UniqueConstraint(
            "regulatory_version_id",
            "relationship_type",
            "target_identifier",
            name="uq_regulatory_relationships_version_type_target",
        ),
        CheckConstraint(
            _allowed("relationship_type", RELATIONSHIP_TYPES),
            name="relationship_type",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regulatory_version_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_identifier: Mapped[str] = mapped_column(String(128), nullable=False)


class VersionFile(Base):
    """Formex file name that was parsed, or kept aside as non-operative."""

    __tablename__ = "version_files"
    __table_args__ = (
        UniqueConstraint(
            "regulatory_version_id",
            "role",
            "filename",
            name="uq_version_files_version_role_filename",
        ),
        CheckConstraint(_allowed("role", FILE_ROLES), name="role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    regulatory_version_id: Mapped[int] = mapped_column(
        ForeignKey("regulatory_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)


# Importing these modules registers their tables on the shared metadata.
from ai_governance.db import inventory as inventory_models  # noqa: E402, F401
from ai_governance.db import workflow as workflow_models  # noqa: E402, F401
