"""Parser for a CELLAR branch notice.

The notice is metadata. It identifies the work, the English expression, and the
Formex manifestation. Consolidated texts and later amendments are recorded as
links so they are not treated as the text of the requested CELEX.
"""

from collections.abc import Iterable
from datetime import date
from xml.etree import ElementTree as ET

from pydantic import BaseModel, Field

from ai_governance.ingestion.errors import (
    DocumentNotFound,
    IdentifierMismatch,
    MalformedDocument,
)
from ai_governance.ingestion.models import DocumentKind

_GUIDANCE_TYPES = {"GUIDE", "GUIDELINE", "SUM"}


class BranchNotice(BaseModel):
    """Identifiers taken from one branch notice."""

    celex: str
    document_kind: DocumentKind
    resource_type: str | None
    notice_title: str | None
    eli: str | None
    cellar_uri: str | None
    document_date: date | None
    publication_date: date | None
    expression_language: str
    language: str
    expression_uri: str
    manifestation_uri: str
    amends_celex: list[str] = Field(default_factory=list)
    amended_by_celex: list[str] = Field(default_factory=list)
    proposed_amendment_celex: list[str] = Field(default_factory=list)
    related_consolidated_celex: list[str] = Field(default_factory=list)
    related_consolidation_ids: list[str] = Field(default_factory=list)


def parse_branch_notice(payload: bytes, *, celex: str, language: str = "ENG") -> BranchNotice:
    """Read a branch notice and require it to describe ``celex`` in ``language``."""
    root = _parse_notice(payload)
    if root.tag != "NOTICE":
        raise MalformedDocument("Branch notice root is not NOTICE")
    work = root.find("WORK")
    if work is None:
        raise MalformedDocument("Branch notice has no WORK element")

    notice_celex = _direct_value(work, "ID_CELEX") or _direct_value(work, "RESOURCE_LEGAL_ID_CELEX")
    if notice_celex is None:
        raise MalformedDocument("Branch notice has no CELEX identifier")
    if notice_celex != celex:
        raise IdentifierMismatch(f"Branch notice CELEX is {notice_celex}; requested {celex}")

    resource_type = _resource_type(work)
    expression = _english_expression(root, celex, language)
    manifestation_uri = _formex_manifestation(root, expression.findtext("URI/VALUE") or "")
    consolidated_prefix = "0" + celex[1:]
    natural_number = celex[1:]

    return BranchNotice(
        celex=celex,
        document_kind=document_kind_for(celex, resource_type),
        resource_type=resource_type,
        notice_title=_direct_value(work, "TITLE"),
        eli=_direct_value(work, "ELI") or _direct_value(work, "RESOURCE_LEGAL_ELI"),
        cellar_uri=_cellar_uri(work),
        document_date=_direct_date(work, "WORK_DATE_DOCUMENT"),
        publication_date=_direct_date(work, "DATE_PUBLICATION"),
        expression_language=language.lower(),
        language="en" if language == "ENG" else language.lower(),
        expression_uri=expression.findtext("URI/VALUE") or "",
        manifestation_uri=manifestation_uri,
        amends_celex=_linked_celex(work, "RESOURCE_LEGAL_AMENDS_RESOURCE_LEGAL", exclude={celex}),
        amended_by_celex=_linked_celex(work, "RESOURCE_LEGAL_AMENDED_BY_RESOURCE_LEGAL", exclude={celex}),
        proposed_amendment_celex=_linked_celex(
            work,
            "RESOURCE_LEGAL_AMENDMENT_PROPOSED_BY_RESOURCE_LEGAL",
            exclude={celex},
        ),
        related_consolidated_celex=_consolidated_celex(work, consolidated_prefix),
        related_consolidation_ids=_consolidation_ids(work, natural_number),
    )


def document_kind_for(celex: str, resource_type: str | None) -> DocumentKind:
    """Classify a work from its CELEX sector and CELLAR resource type."""
    if celex.startswith("0") or resource_type == "CONS_TEXT":
        return DocumentKind.consolidated
    if resource_type in _GUIDANCE_TYPES:
        return DocumentKind.guidance
    return DocumentKind.original


def _english_expression(root: ET.Element, celex: str, language: str) -> ET.Element:
    matches: list[ET.Element] = []
    for expression in root.findall("EXPRESSION"):
        expression_language = expression.findtext("EXPRESSION_USES_LANGUAGE/IDENTIFIER")
        belongs = {
            (uri.findtext("IDENTIFIER") or "")
            for uri in expression.findall("EXPRESSION_BELONGS_TO_WORK/SAMEAS/URI")
        }
        if expression_language == language and celex in belongs:
            matches.append(expression)
    if not matches:
        raise DocumentNotFound(f"No {language} expression for CELEX {celex}")
    if len(matches) > 1:
        raise IdentifierMismatch(f"Multiple {language} expressions for CELEX {celex}")
    return matches[0]


def _formex_manifestation(root: ET.Element, expression_uri: str) -> str:
    matches: list[str] = []
    for manifestation in root.findall("MANIFESTATION"):
        kind = manifestation.attrib.get("manifestation-type") or manifestation.findtext(
            "MANIFESTATION_TYPE/VALUE"
        )
        manifests = manifestation.findtext("MANIFESTATION_MANIFESTS_EXPRESSION/URI/VALUE")
        uri = manifestation.findtext("URI/VALUE")
        if kind == "fmx4" and manifests == expression_uri and uri:
            matches.append(uri)
    unique = list(dict.fromkeys(matches))
    if not unique:
        raise DocumentNotFound(f"No Formex manifestation for {expression_uri}")
    if len(unique) > 1:
        raise IdentifierMismatch(f"Multiple Formex manifestations for {expression_uri}")
    return unique[0]


def _linked_celex(work: ET.Element, tag: str, *, exclude: set[str]) -> list[str]:
    found: list[str] = []
    for child in list(work):
        if child.tag != tag:
            continue
        found.extend(_celex_identifiers(child))
    return _unique(identifier for identifier in found if identifier not in exclude)


def _consolidated_celex(work: ET.Element, prefix: str) -> list[str]:
    found: list[str] = []
    for child in list(work):
        if "CONSOLIDATED" not in child.tag:
            continue
        found.extend(
            identifier for identifier in _celex_identifiers(child) if identifier.startswith(prefix)
        )
    return _unique(found)


def _consolidation_ids(work: ET.Element, natural_number: str) -> list[str]:
    found: list[str] = []
    for child in list(work):
        if "CONSOLIDATED" not in child.tag:
            continue
        for uri in child.findall("SAMEAS/URI"):
            if uri.findtext("TYPE") != "consolidation":
                continue
            identifier = (uri.findtext("IDENTIFIER") or "").strip()
            if identifier and natural_number in identifier:
                found.append(identifier)
    return _unique(found)


def _celex_identifiers(element: ET.Element) -> list[str]:
    found: list[str] = []
    for uri in element.findall("SAMEAS/URI"):
        if uri.findtext("TYPE") == "celex" and uri.findtext("IDENTIFIER"):
            found.append(uri.findtext("IDENTIFIER").strip())
    embedded = element.find("EMBEDDED_NOTICE/WORK")
    if embedded is not None:
        for child in list(embedded):
            if child.tag in {"ID_CELEX", "RESOURCE_LEGAL_ID_CELEX"}:
                value = child.findtext("VALUE")
                if value:
                    found.append(value.strip())
    return found


def _resource_type(work: ET.Element) -> str | None:
    for child in list(work):
        if child.tag == "WORK_HAS_RESOURCE-TYPE":
            return child.findtext("URI/IDENTIFIER") or child.findtext("IDENTIFIER")
    return None


def _cellar_uri(work: ET.Element) -> str | None:
    for child in list(work):
        if child.tag == "URI" and child.findtext("TYPE") == "cellar":
            return child.findtext("VALUE")
    return None


def _direct_value(work: ET.Element, tag: str) -> str | None:
    for child in list(work):
        if child.tag == tag:
            value = child.findtext("VALUE")
            if value:
                return value.strip()
    return None


def _direct_date(work: ET.Element, tag: str) -> date | None:
    raw = _direct_value(work, tag)
    if raw is None:
        return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError as exc:
        raise MalformedDocument(f"Unreadable {tag} value {raw}") from exc


def _parse_notice(payload: bytes) -> ET.Element:
    if b"<!DOCTYPE" in payload[:2000].upper() or b"<!ENTITY" in payload[:2000].upper():
        raise MalformedDocument("Branch notice contains a DTD")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise MalformedDocument("Branch notice is not well-formed XML") from exc


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(values))
