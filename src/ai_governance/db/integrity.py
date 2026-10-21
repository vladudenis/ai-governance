"""Compare a stored regulatory version with the parsed document it came from."""

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


class RegulatoryIntegrityError(Exception):
    """The database rows do not match the parsed document."""


def assert_document_stored(
    session: Session,
    document: ParsedDocument,
    *,
    expect_current: bool = True,
) -> RegulatoryVersion:
    """Raise if the database copy of ``document`` differs from the parse."""
    regulation = session.scalar(select(Regulation).where(Regulation.celex == document.celex))
    if regulation is None:
        raise RegulatoryIntegrityError(f"CELEX {document.celex} is not in regulations")
    version = session.scalar(
        select(RegulatoryVersion).where(
            RegulatoryVersion.regulation_id == regulation.id,
            RegulatoryVersion.content_sha256 == document.content_sha256,
            RegulatoryVersion.language == document.language,
        )
    )
    if version is None:
        raise RegulatoryIntegrityError(f"Version {document.content_sha256} is not stored")

    expected_status = "current" if expect_current else "superseded"
    if version.status != expected_status:
        raise RegulatoryIntegrityError(
            f"Version status is {version.status}; expected {expected_status}"
        )
    _assert_equal("document kind", regulation.document_kind, document.document_kind.value)
    _assert_equal("title", version.title, document.title)
    _assert_equal("ELI", regulation.eli, document.eli)
    _assert_equal("OJ reference", version.oj_reference, document.oj_reference)
    _assert_equal("document date", version.document_date, document.document_date)
    _assert_equal("publication date", version.publication_date, document.publication_date)

    stored = _stored_snapshot(session, version.id)
    parsed = _parsed_snapshot(document.provisions)
    if stored != parsed:
        missing = sorted(set(parsed) - set(stored))
        extra = sorted(set(stored) - set(parsed))
        changed = sorted(key for key in parsed.keys() & stored.keys() if parsed[key] != stored[key])
        detail = changed[0] if changed else ""
        if detail:
            detail = f" First changed key: {detail}."
        raise RegulatoryIntegrityError(
            f"Provision tree differs. missing={missing[:5]} extra={extra[:5]}.{detail}"
        )

    stored_links = _links(session, version.id)
    parsed_links = _parsed_links(document)
    if stored_links != parsed_links:
        raise RegulatoryIntegrityError("Relationship links do not match the parsed document")

    stored_files = _files(session, version.id)
    parsed_files = {
        ("source", filename) for filename in document.source_files
    } | {("unparsed", filename) for filename in document.unparsed_files}
    if stored_files != parsed_files:
        raise RegulatoryIntegrityError("Version file list does not match the parsed document")
    return version


def _stored_snapshot(session: Session, version_id: int) -> dict[str, tuple[object, ...]]:
    provisions = session.scalars(
        select(LegalProvision).where(LegalProvision.regulatory_version_id == version_id)
    ).all()
    keys_by_id = {row.id: row.provision_key for row in provisions}
    note_rows = session.scalars(
        select(ProvisionNote)
        .join(LegalProvision)
        .where(LegalProvision.regulatory_version_id == version_id)
        .order_by(ProvisionNote.legal_provision_id, ProvisionNote.position)
    ).all()
    notes_by_provision: dict[int, list[str]] = {}
    for note in note_rows:
        notes_by_provision.setdefault(note.legal_provision_id, []).append(note.note_text)
    snapshot: dict[str, tuple[object, ...]] = {}
    for row in provisions:
        parent_key = None if row.parent_id is None else keys_by_id[row.parent_id]
        snapshot[row.provision_key] = (
            parent_key,
            row.position,
            row.kind,
            row.citation,
            row.number,
            row.heading,
            row.provision_text,
            tuple(notes_by_provision.get(row.id, [])),
            row.source_file,
            row.source_identifier,
        )
    return snapshot


def _parsed_snapshot(
    provisions: list[ParsedProvision],
    parent_key: str | None = None,
) -> dict[str, tuple[object, ...]]:
    snapshot: dict[str, tuple[object, ...]] = {}
    for position, provision in enumerate(provisions):
        snapshot[provision.provision_id] = (
            parent_key,
            position,
            provision.kind.value,
            provision.citation,
            provision.number,
            provision.heading,
            provision.text,
            tuple(provision.notes),
            provision.source_file,
            provision.source_identifier,
        )
        snapshot.update(_parsed_snapshot(provision.children, provision.provision_id))
    return snapshot


def _links(session: Session, version_id: int) -> set[tuple[str, str]]:
    rows = session.scalars(
        select(RegulatoryRelationship).where(
            RegulatoryRelationship.regulatory_version_id == version_id
        )
    ).all()
    return {(row.relationship_type, row.target_identifier) for row in rows}


def _parsed_links(document: ParsedDocument) -> set[tuple[str, str]]:
    groups = {
        "amends": document.amends_celex,
        "amended_by": document.amended_by_celex,
        "proposed_amendment": document.proposed_amendment_celex,
        "consolidated_version": document.related_consolidated_celex,
        "consolidation_identifier": document.related_consolidation_ids,
    }
    return {
        (relationship_type, identifier)
        for relationship_type, identifiers in groups.items()
        for identifier in identifiers
    }


def _files(session: Session, version_id: int) -> set[tuple[str, str]]:
    rows = session.scalars(
        select(VersionFile).where(VersionFile.regulatory_version_id == version_id)
    ).all()
    return {(row.role, row.filename) for row in rows}


def _assert_equal(label: str, stored: object, expected: object) -> None:
    if stored != expected:
        raise RegulatoryIntegrityError(f"{label} is {stored!r}; parsed document has {expected!r}")
