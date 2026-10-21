"""Load a parsed regulatory document into PostgreSQL.

The same content digest is inserted once. A different digest for the same
CELEX and language is inserted as the current version, and the previous
current row is marked superseded. Provision rows of the older version remain.
"""

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_governance.db.models import (
    LegalProvision,
    ProvisionNote,
    Regulation,
    RegulatoryRelationship,
    RegulatoryVersion,
    VersionFile,
)
from ai_governance.ingestion.models import LegalProvision as ParsedProvision
from ai_governance.ingestion.models import RegulatoryVersion as ParsedDocument


@dataclass(frozen=True)
class DatabaseImportResult:
    """Outcome of writing one parsed document."""

    created: bool
    regulation_id: int
    regulatory_version_id: int
    content_sha256: str


def import_regulatory_document(session: Session, document: ParsedDocument) -> DatabaseImportResult:
    """Insert ``document`` unless this digest is already stored for its work.

    The caller commits. A failure before commit leaves the transaction unwritten.
    """
    regulation = _regulation_for(session, document)
    existing = session.scalar(
        select(RegulatoryVersion).where(
            RegulatoryVersion.regulation_id == regulation.id,
            RegulatoryVersion.language == document.language,
            RegulatoryVersion.content_sha256 == document.content_sha256,
        )
    )
    if existing is not None:
        return DatabaseImportResult(
            created=False,
            regulation_id=regulation.id,
            regulatory_version_id=existing.id,
            content_sha256=existing.content_sha256,
        )

    now = datetime.now(timezone.utc)
    current_rows = session.scalars(
        select(RegulatoryVersion).where(
            RegulatoryVersion.regulation_id == regulation.id,
            RegulatoryVersion.language == document.language,
            RegulatoryVersion.status == "current",
        )
    ).all()
    for current in current_rows:
        current.status = "superseded"
    session.flush()

    version = RegulatoryVersion(
        regulation_id=regulation.id,
        language=document.language,
        expression_language=document.expression_language,
        content_sha256=document.content_sha256,
        parser_version=document.parser_version,
        title=document.title,
        notice_title=document.notice_title,
        source_url=document.source_url,
        manifestation_uri=document.manifestation_uri,
        resolved_url=document.resolved_url,
        oj_reference=document.oj_reference,
        document_date=document.document_date,
        publication_date=document.publication_date,
        formex_schema=document.formex_schema,
        status="current",
        retrieved_at=document.retrieved_at,
        created_at=now,
    )
    session.add(version)
    session.flush()
    for position, provision in enumerate(document.provisions):
        _insert_provision(session, version.id, provision, None, position)
    _insert_relationships(session, version.id, document)
    _insert_files(session, version.id, "source", document.source_files)
    _insert_files(session, version.id, "unparsed", document.unparsed_files)
    regulation.updated_at = now
    session.flush()
    return DatabaseImportResult(
        created=True,
        regulation_id=regulation.id,
        regulatory_version_id=version.id,
        content_sha256=version.content_sha256,
    )


def _regulation_for(session: Session, document: ParsedDocument) -> Regulation:
    regulation = session.scalar(select(Regulation).where(Regulation.celex == document.celex))
    now = datetime.now(timezone.utc)
    if regulation is None:
        regulation = Regulation(
            celex=document.celex,
            document_kind=document.document_kind.value,
            resource_type=document.resource_type,
            eli=document.eli,
            cellar_uri=document.cellar_uri,
            created_at=now,
            updated_at=now,
        )
        session.add(regulation)
        session.flush()
        return regulation

    if regulation.document_kind != document.document_kind.value:
        raise ValueError(
            f"CELEX {document.celex} is stored as {regulation.document_kind} "
            f"and the import says {document.document_kind.value}"
        )
    _same_or_fill(regulation, "resource_type", document.resource_type)
    _same_or_fill(regulation, "eli", document.eli)
    _same_or_fill(regulation, "cellar_uri", document.cellar_uri)
    return regulation


def _same_or_fill(regulation: Regulation, field_name: str, incoming: str | None) -> None:
    if incoming is None:
        return
    current = getattr(regulation, field_name)
    if current is None:
        setattr(regulation, field_name, incoming)
        return
    if current != incoming:
        raise ValueError(
            f"CELEX {regulation.celex} already has {field_name} {current}; import has {incoming}"
        )


def _insert_provision(
    session: Session,
    version_id: int,
    provision: ParsedProvision,
    parent_id: int | None,
    position: int,
) -> None:
    row = LegalProvision(
        regulatory_version_id=version_id,
        parent_id=parent_id,
        provision_key=provision.provision_id,
        kind=provision.kind.value,
        citation=provision.citation,
        number=provision.number,
        heading=provision.heading,
        provision_text=provision.text,
        source_file=provision.source_file,
        source_identifier=provision.source_identifier,
        position=position,
    )
    session.add(row)
    session.flush()
    for note_position, note in enumerate(provision.notes):
        session.add(
            ProvisionNote(
                legal_provision_id=row.id,
                position=note_position,
                note_text=note,
            )
        )
    for child_position, child in enumerate(provision.children):
        _insert_provision(session, version_id, child, row.id, child_position)


def _insert_relationships(session: Session, version_id: int, document: ParsedDocument) -> None:
    groups = {
        "amends": document.amends_celex,
        "amended_by": document.amended_by_celex,
        "proposed_amendment": document.proposed_amendment_celex,
        "consolidated_version": document.related_consolidated_celex,
        "consolidation_identifier": document.related_consolidation_ids,
    }
    seen: set[tuple[str, str]] = set()
    for relationship_type, identifiers in groups.items():
        for identifier in identifiers:
            key = (relationship_type, identifier)
            if key in seen:
                continue
            seen.add(key)
            session.add(
                RegulatoryRelationship(
                    regulatory_version_id=version_id,
                    relationship_type=relationship_type,
                    target_identifier=identifier,
                )
            )


def _insert_files(session: Session, version_id: int, role: str, filenames: list[str]) -> None:
    for position, filename in enumerate(filenames):
        session.add(
            VersionFile(
                regulatory_version_id=version_id,
                role=role,
                filename=filename,
                position=position,
            )
        )
