"""Records produced by a regulatory import.

A version is identified by the SHA-256 digest of the official Formex ZIP.
Later assessments should cite that digest. A newer import of different bytes
adds a version and leaves the previous file in place.
"""

from datetime import date, datetime
from enum import Enum
from typing import Iterator

from pydantic import BaseModel, Field


class DocumentKind(str, Enum):
    """Role of a retrieved work.

    An amending regulation is stored as its own ``original`` instrument.
    The link to the act it changes is ``amends_celex`` on that instrument and
    ``amended_by_celex`` on the act that was changed. ``amendment`` is reserved
    for a future explicit classification of an instrument that has no
    free-standing rules of its own.
    """

    original = "original"
    amendment = "amendment"
    consolidated = "consolidated"
    guidance = "guidance"


class ProvisionKind(str, Enum):
    """Structural unit extracted from Formex."""

    title = "title"
    preamble = "preamble"
    visa = "visa"
    recital = "recital"
    chapter = "chapter"
    section = "section"
    subsection = "subsection"
    article = "article"
    paragraph = "paragraph"
    subparagraph = "subparagraph"
    point = "point"
    annex = "annex"
    closing = "closing"


class LegalProvision(BaseModel):
    """One structural unit of a legal act, with its original wording."""

    provision_id: str
    kind: ProvisionKind
    citation: str
    number: str | None = None
    heading: str | None = None
    text: str
    notes: list[str] = Field(default_factory=list)
    source_file: str
    source_identifier: str | None = None
    children: list["LegalProvision"] = Field(default_factory=list)


class RegulatoryVersion(BaseModel):
    """One imported manifestation of a legal work."""

    celex: str
    language: str
    expression_language: str
    document_kind: DocumentKind
    resource_type: str | None
    title: str
    notice_title: str | None
    eli: str | None
    cellar_uri: str | None
    source_url: str
    manifestation_uri: str | None
    resolved_url: str | None
    oj_reference: str | None
    document_date: date | None
    publication_date: date | None
    formex_schema: str | None
    content_sha256: str
    parser_version: str
    retrieved_at: datetime
    amends_celex: list[str] = Field(default_factory=list)
    amended_by_celex: list[str] = Field(default_factory=list)
    proposed_amendment_celex: list[str] = Field(default_factory=list)
    related_consolidated_celex: list[str] = Field(default_factory=list)
    related_consolidation_ids: list[str] = Field(default_factory=list)
    provisions: list[LegalProvision]
    source_files: list[str] = Field(default_factory=list)
    unparsed_files: list[str] = Field(default_factory=list)


class StoredVersion(BaseModel):
    """Catalog row for one content-addressed import."""

    celex: str
    language: str
    document_kind: DocumentKind
    content_sha256: str
    retrieved_at: datetime
    relative_path: str
    superseded: bool = False
    title: str
    manifestation_uri: str | None = None


class ImportResult(BaseModel):
    """Outcome of an import attempt."""

    created: bool
    version: StoredVersion


class Catalog(BaseModel):
    """Index of imported versions. Payloads live in separate JSON files."""

    versions: list[StoredVersion] = Field(default_factory=list)


def iter_provisions(provisions: list[LegalProvision]) -> Iterator[LegalProvision]:
    """Yield each provision, parent before children."""
    pending = list(provisions)
    # Recursion is clearer, and the AI Act tree is shallow.
    for provision in pending:
        yield provision
        yield from iter_provisions(provision.children)


def count_provisions(provisions: list[LegalProvision], kind: ProvisionKind) -> int:
    """Count provisions of one kind anywhere in the tree."""
    return sum(1 for provision in iter_provisions(provisions) if provision.kind is kind)
