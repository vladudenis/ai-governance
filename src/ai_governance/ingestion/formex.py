"""Parser for Official Journal Formex XML.

The Publications Office publishes the act as a ZIP of Formex 4 files. The act
body is an ``ACT`` document. Each annex is a separate ``ANNEX`` document.
Cover-page and table-of-contents files are kept in ``unparsed_files`` because
they repeat navigation metadata rather than the operative text.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date
from xml.etree import ElementTree as ET

from ai_governance.ingestion.errors import IdentifierMismatch, MalformedDocument
from ai_governance.ingestion.models import (
    LegalProvision,
    ProvisionKind,
    iter_provisions,
)
from ai_governance.ingestion.textutil import extract_text, point_number

PARSER_VERSION = "1"
_SCHEMA_ATTR = "{http://www.w3.org/2001/XMLSchema-instance}noNamespaceSchemaLocation"
_CELEX_ACT = re.compile(
    r"^[0-9](?P<year>\d{4})(?P<type>[A-Z])(?P<number>\d+)(?:-\d{8})?$"
)
_DIVISION_HEADING = re.compile(
    r"^(CHAPTER|SECTION|SUBSECTION)\s+([IVXLCDM]+|\d+)\b\s*(.*)$",
    re.IGNORECASE,
)
_ARTICLE_HEADING = re.compile(r"^Article\s+(\S+)$", re.IGNORECASE)
_ANNEX_HEADING = re.compile(r"^ANNEX\s+([IVXLCDM]+|\d+)\b\s*(.*)$", re.IGNORECASE)
_DIVISION_KIND = {
    "CHAPTER": ProvisionKind.chapter,
    "SECTION": ProvisionKind.section,
    "SUBSECTION": ProvisionKind.subsection,
}


@dataclass(frozen=True)
class ParsedFormex:
    """Structured act text taken from one Formex ZIP."""

    title: str
    formex_schema: str | None
    oj_reference: str | None
    document_date: date | None
    language: str
    provisions: list[LegalProvision]
    source_files: list[str]
    unparsed_files: list[str]


def parse_formex_zip(payload: bytes, *, celex: str, expected_language: str) -> ParsedFormex:
    """Parse a Formex ZIP and reject a document that is not the requested act."""
    archive = _open_zip(payload)
    provisions: list[LegalProvision] = []
    source_files: list[str] = []
    unparsed_files: list[str] = []
    schema: str | None = None
    title = ""
    oj_reference: str | None = None
    document_date: date | None = None
    languages: set[str] = set()
    saw_act = False

    for info in archive.infolist():
        if info.is_dir() or not info.filename.lower().endswith(".xml"):
            continue
        root = _parse_xml(archive.read(info), info.filename)
        if root.tag == "ACT":
            if saw_act:
                raise MalformedDocument("Formex ZIP contains more than one ACT file")
            saw_act = True
            act = _parse_act(root, info.filename)
            provisions.extend(act.provisions)
            title = act.title
            schema = act.formex_schema
            oj_reference = act.oj_reference
            document_date = act.document_date
            languages.add(act.language)
            source_files.append(info.filename)
        elif root.tag == "ANNEX":
            annex = _parse_annex(root, info.filename)
            provisions.append(annex.provision)
            languages.add(annex.language)
            source_files.append(info.filename)
        else:
            unparsed_files.append(info.filename)

    if not saw_act:
        raise MalformedDocument("Formex ZIP does not contain an ACT file")
    if languages != {expected_language}:
        found = ", ".join(sorted(languages)) or "none"
        raise IdentifierMismatch(
            f"Formex language is {found}; expected {expected_language} for CELEX {celex}"
        )
    _assert_oj_matches_celex(celex, oj_reference)
    _assert_unique_ids(provisions)
    return ParsedFormex(
        title=title,
        formex_schema=schema,
        oj_reference=oj_reference,
        document_date=document_date,
        language=expected_language,
        provisions=provisions,
        source_files=source_files,
        unparsed_files=unparsed_files,
    )


@dataclass(frozen=True)
class _ActParts:
    title: str
    formex_schema: str | None
    oj_reference: str | None
    document_date: date | None
    language: str
    provisions: list[LegalProvision]


def _parse_act(act: ET.Element, source_file: str) -> _ActParts:
    language, years, numbers, document_date = _bibliography(act, source_file)
    title_element = act.find("TITLE")
    if title_element is None:
        raise MalformedDocument(f"{source_file} is missing TITLE")
    title, _ = extract_text(title_element)
    provisions: list[LegalProvision] = [
        LegalProvision(
            provision_id="title",
            kind=ProvisionKind.title,
            citation="Title",
            text=title,
            source_file=source_file,
        )
    ]
    preamble = act.find("PREAMBLE")
    if preamble is not None:
        provisions.append(_parse_preamble(preamble, source_file))
    enacting = act.find("ENACTING.TERMS")
    if enacting is None:
        raise MalformedDocument(f"{source_file} is missing ENACTING.TERMS")
    provisions.extend(_parse_enacting(enacting, source_file))
    final = act.find("FINAL")
    if final is not None:
        closing, notes = extract_text(final)
        provisions.append(
            LegalProvision(
                provision_id="closing",
                kind=ProvisionKind.closing,
                citation="Closing",
                text=closing,
                notes=notes,
                source_file=source_file,
            )
        )
    xml_articles = [element for element in act.iter("ARTICLE")]
    parsed_articles = [
        item for item in iter_provisions(provisions) if item.kind is ProvisionKind.article
    ]
    if len(xml_articles) != len(parsed_articles):
        raise MalformedDocument(
            f"{source_file} has {len(xml_articles)} ARTICLE elements "
            f"and {len(parsed_articles)} were parsed"
        )
    xml_recitals = [element for element in act.iter("CONSID")]
    parsed_recitals = [
        item for item in iter_provisions(provisions) if item.kind is ProvisionKind.recital
    ]
    if len(xml_recitals) != len(parsed_recitals):
        raise MalformedDocument(
            f"{source_file} has {len(xml_recitals)} recitals and {len(parsed_recitals)} were parsed"
        )
    oj_reference = None
    if years and numbers:
        collection = (
            act.findtext("BIB.INSTANCE/DOCUMENT.REF/COLL")
            or act.findtext("BIB.INSTANCE/COLL")
            or "L"
        )
        oj_reference = f"OJ {collection} {years[0]}/{int(numbers[0])}"
    return _ActParts(
        title=title,
        formex_schema=act.attrib.get(_SCHEMA_ATTR),
        oj_reference=oj_reference,
        document_date=document_date,
        language=language,
        provisions=provisions,
    )


@dataclass(frozen=True)
class _AnnexParts:
    provision: LegalProvision
    language: str


def _parse_annex(annex: ET.Element, source_file: str) -> _AnnexParts:
    language, _, _, _ = _bibliography(annex, source_file)
    title_element = annex.find("TITLE")
    if title_element is None:
        raise MalformedDocument(f"{source_file} is missing TITLE")
    title, _ = extract_text(title_element)
    match = _ANNEX_HEADING.match(title)
    if match is None:
        raise MalformedDocument(f"Unrecognised annex heading in {source_file}: {title}")
    number = match.group(1)
    heading = match.group(2).strip() or None
    provision_id = f"annex/{number}"
    citation = f"Annex {number}"
    contents = annex.find("CONTENTS")
    text_source = contents if contents is not None else annex
    text, notes = extract_text(text_source)
    children = _parse_lists(text_source, provision_id, citation, source_file)
    return _AnnexParts(
        provision=LegalProvision(
            provision_id=provision_id,
            kind=ProvisionKind.annex,
            citation=citation,
            number=number,
            heading=heading,
            text=text,
            notes=notes,
            source_file=source_file,
            source_identifier=annex.attrib.get("IDENTIFIER"),
            children=children,
        ),
        language=language,
    )


def _parse_preamble(preamble: ET.Element, source_file: str) -> LegalProvision:
    children: list[LegalProvision] = []
    visa_number = 0

    def walk(element: ET.Element) -> None:
        nonlocal visa_number
        for child in list(element):
            if child.tag == "VISA":
                visa_number += 1
                text, notes = extract_text(child)
                children.append(
                    LegalProvision(
                        provision_id=f"visa/{visa_number}",
                        kind=ProvisionKind.visa,
                        citation=f"Visa {visa_number}",
                        number=str(visa_number),
                        text=text,
                        notes=notes,
                        source_file=source_file,
                    )
                )
            elif child.tag == "CONSID":
                children.append(_parse_recital(child, source_file))
            else:
                walk(child)

    walk(preamble)
    intro = preamble.find("PREAMBLE.INIT")
    text = extract_text(intro)[0] if intro is not None else "Preamble"
    return LegalProvision(
        provision_id="preamble",
        kind=ProvisionKind.preamble,
        citation="Preamble",
        text=text,
        source_file=source_file,
        children=children,
    )


def _parse_recital(recital: ET.Element, source_file: str) -> LegalProvision:
    number_element = recital.find(".//NO.P")
    if number_element is None:
        raise MalformedDocument(f"{source_file} has a recital without NO.P")
    number = point_number(extract_text(number_element)[0])
    if not number:
        raise MalformedDocument(f"{source_file} has a blank recital number")
    text, notes = extract_text(recital)
    return LegalProvision(
        provision_id=f"recital/{number}",
        kind=ProvisionKind.recital,
        citation=f"Recital {number}",
        number=number,
        text=text,
        notes=notes,
        source_file=source_file,
    )


def _parse_enacting(element: ET.Element, source_file: str) -> list[LegalProvision]:
    provisions: list[LegalProvision] = []
    for child in list(element):
        if child.tag == "DIVISION":
            provisions.append(_parse_division(child, source_file, None, None))
        elif child.tag == "ARTICLE":
            provisions.append(_parse_article(child, source_file))
        elif list(child):
            provisions.extend(_parse_enacting(child, source_file))
    return provisions


def _parse_division(
    division: ET.Element,
    source_file: str,
    parent_id: str | None,
    parent_citation: str | None,
) -> LegalProvision:
    title_element = division.find("TITLE")
    if title_element is None:
        raise MalformedDocument(f"{source_file} has a DIVISION without TITLE")
    title, _ = extract_text(title_element)
    match = _DIVISION_HEADING.match(title)
    if match is None:
        raise MalformedDocument(f"Unrecognised division heading in {source_file}: {title}")
    label = match.group(1).upper()
    number = match.group(2)
    heading = match.group(3).strip() or None
    kind = _DIVISION_KIND[label]
    if kind is ProvisionKind.chapter:
        provision_id = f"chapter/{number}"
        citation = f"Chapter {number}"
    elif kind is ProvisionKind.section:
        provision_id = f"{parent_id}/section/{number}" if parent_id else f"section/{number}"
        citation = f"{parent_citation}, Section {number}" if parent_citation else f"Section {number}"
    else:
        provision_id = (
            f"{parent_id}/subsection/{number}" if parent_id else f"subsection/{number}"
        )
        citation = (
            f"{parent_citation}, Subsection {number}" if parent_citation else f"Subsection {number}"
        )
    children: list[LegalProvision] = []
    for child in list(division):
        if child.tag == "DIVISION":
            children.append(_parse_division(child, source_file, provision_id, citation))
        elif child.tag == "ARTICLE":
            children.append(_parse_article(child, source_file))
    return LegalProvision(
        provision_id=provision_id,
        kind=kind,
        citation=citation,
        number=number,
        heading=heading,
        text=title,
        source_file=source_file,
        source_identifier=division.attrib.get("IDENTIFIER"),
        children=children,
    )


def _parse_article(article: ET.Element, source_file: str) -> LegalProvision:
    heading_element = article.find("TI.ART")
    if heading_element is None:
        raise MalformedDocument(f"{source_file} has an ARTICLE without TI.ART")
    heading_text, _ = extract_text(heading_element)
    match = _ARTICLE_HEADING.match(heading_text)
    if match is None:
        raise MalformedDocument(f"Unrecognised article heading in {source_file}: {heading_text}")
    number = match.group(1)
    subtitle = article.find("STI.ART")
    article_heading = extract_text(subtitle)[0] if subtitle is not None else ""
    provision_id = f"article/{number}"
    citation = f"Article {number}"
    text, notes = extract_text(article)
    # Direct paragraphs only. A PARAG nested in QUOT.S is quoted text from another
    # act being amended, and it stays inside the quoting provision's wording.
    paragraphs = article.findall("PARAG")
    children: list[LegalProvision] = []
    if paragraphs:
        for index, paragraph in enumerate(paragraphs, start=1):
            children.append(_parse_paragraph(paragraph, provision_id, citation, source_file, index))
    else:
        children.extend(_parse_lists(article, provision_id, citation, source_file))
    return LegalProvision(
        provision_id=provision_id,
        kind=ProvisionKind.article,
        citation=citation,
        number=number,
        heading=article_heading or None,
        text=text,
        notes=notes,
        source_file=source_file,
        source_identifier=article.attrib.get("IDENTIFIER"),
        children=children,
    )


def _parse_paragraph(
    paragraph: ET.Element,
    article_id: str,
    article_citation: str,
    source_file: str,
    index: int,
) -> LegalProvision:
    number_element = paragraph.find("NO.PARAG")
    if number_element is None:
        number = f"unnumbered-{index}"
        citation = article_citation
    else:
        number = point_number(extract_text(number_element)[0]) or f"unnumbered-{index}"
        citation = f"{article_citation}({number})"
    provision_id = f"{article_id}/paragraph/{number}"
    text, notes = extract_text(paragraph)
    alineas = paragraph.findall("ALINEA")
    children: list[LegalProvision] = []
    if len(alineas) > 1:
        for alinea_index, alinea in enumerate(alineas, start=1):
            sub_id = f"{provision_id}/subparagraph/{alinea_index}"
            sub_text, sub_notes = extract_text(alinea)
            children.append(
                LegalProvision(
                    provision_id=sub_id,
                    kind=ProvisionKind.subparagraph,
                    citation=citation,
                    number=str(alinea_index),
                    text=sub_text,
                    notes=sub_notes,
                    source_file=source_file,
                    children=_parse_lists(alinea, sub_id, citation, source_file),
                )
            )
    else:
        container = alineas[0] if alineas else paragraph
        children.extend(_parse_lists(container, provision_id, citation, source_file))
    return LegalProvision(
        provision_id=provision_id,
        kind=ProvisionKind.paragraph,
        citation=citation,
        number=number,
        text=text,
        notes=notes,
        source_file=source_file,
        source_identifier=paragraph.attrib.get("IDENTIFIER"),
        children=children,
    )


def _parse_lists(
    container: ET.Element,
    parent_id: str,
    parent_citation: str,
    source_file: str,
) -> list[LegalProvision]:
    """Parse lists owned by ``container``.

    A second list in the same container restarts its numbering in Formex.
    The extra ``list`` segment keeps those points distinct.
    """
    lists = _top_level_lists(container)
    points: list[LegalProvision] = []
    for list_index, list_element in enumerate(lists, start=1):
        list_parent = parent_id if len(lists) == 1 else f"{parent_id}/list/{list_index}"
        for index, item in enumerate(list_element.findall("ITEM"), start=1):
            points.append(_parse_item(item, list_parent, parent_citation, source_file, index))
    return points


def _parse_item(
    item: ET.Element,
    parent_id: str,
    parent_citation: str,
    source_file: str,
    index: int,
) -> LegalProvision:
    scope = item.find("NP")
    if scope is None:
        scope = item
    number_element = scope.find("NO.P")
    if number_element is None:
        number = f"unnumbered-{index}"
    else:
        number = point_number(extract_text(number_element)[0]) or f"unnumbered-{index}"
    provision_id = f"{parent_id}/point/{number}"
    citation = f"{parent_citation}({number})"
    text, notes = extract_text(scope)
    return LegalProvision(
        provision_id=provision_id,
        kind=ProvisionKind.point,
        citation=citation,
        number=number,
        text=text,
        notes=notes,
        source_file=source_file,
        children=_parse_lists(scope, provision_id, citation, source_file),
    )


def _top_level_lists(container: ET.Element) -> list[ET.Element]:
    found: list[ET.Element] = []

    def walk(element: ET.Element, inside_list: bool) -> None:
        for child in list(element):
            if child.tag == "LIST" and not inside_list:
                found.append(child)
                walk(child, True)
            else:
                walk(child, inside_list)

    walk(container, False)
    return found


def _bibliography(
    root: ET.Element,
    source_file: str,
) -> tuple[str, list[str], list[str], date | None]:
    bibliography = root.find("BIB.INSTANCE")
    if bibliography is None:
        raise MalformedDocument(f"{source_file} is missing BIB.INSTANCE")
    language = (bibliography.findtext("LG.DOC") or "").strip()
    if not language:
        raise MalformedDocument(f"{source_file} is missing LG.DOC")
    years: list[str] = []
    numbers: list[str] = []
    for number_element in bibliography.findall(".//NO.DOC"):
        year = (number_element.findtext("YEAR") or "").strip()
        number = (number_element.findtext("NO.CURRENT") or "").strip()
        if year:
            years.append(year)
        if number:
            numbers.append(number)
    if not years or not numbers:
        raise MalformedDocument(f"{source_file} is missing the OJ year or number")
    if len(set(years)) != 1 or len({int(number) for number in numbers}) != 1:
        raise MalformedDocument(f"{source_file} has conflicting OJ identifiers")
    raw_date = bibliography.find("DATE")
    document_date = None
    if raw_date is not None and raw_date.attrib.get("ISO"):
        document_date = _compact_date(raw_date.attrib["ISO"], source_file)
    return language, years, numbers, document_date


def _assert_oj_matches_celex(celex: str, oj_reference: str | None) -> None:
    match = _CELEX_ACT.match(celex)
    if match is None:
        raise IdentifierMismatch(f"CELEX {celex} is not a recognised act identifier")
    if oj_reference is None:
        raise IdentifierMismatch(f"Formex file for {celex} has no OJ reference")
    expected = f"{match.group('year')}/{int(match.group('number'))}"
    if not oj_reference.endswith(expected):
        raise IdentifierMismatch(
            f"Formex OJ reference {oj_reference} does not match CELEX {celex}"
        )


def _assert_unique_ids(provisions: list[LegalProvision]) -> None:
    seen: set[str] = set()
    for provision in iter_provisions(provisions):
        if provision.provision_id in seen:
            raise MalformedDocument(f"Duplicate provision id {provision.provision_id}")
        seen.add(provision.provision_id)


def _compact_date(value: str, source_file: str) -> date:
    if len(value) != 8 or not value.isdigit():
        raise MalformedDocument(f"{source_file} has an unreadable DATE ISO value {value}")
    return date(int(value[0:4]), int(value[4:6]), int(value[6:8]))


def _open_zip(payload: bytes) -> zipfile.ZipFile:
    if not payload.startswith(b"PK"):
        raise MalformedDocument("Formex response is not a ZIP archive")
    try:
        return zipfile.ZipFile(io.BytesIO(payload))
    except zipfile.BadZipFile as exc:
        raise MalformedDocument("Formex response is not a ZIP archive") from exc


def _parse_xml(payload: bytes, label: str) -> ET.Element:
    prefix = payload[:2000].upper()
    if b"<!DOCTYPE" in prefix or b"<!ENTITY" in prefix:
        raise MalformedDocument(f"{label} contains a DTD")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise MalformedDocument(f"{label} is not well-formed XML") from exc
