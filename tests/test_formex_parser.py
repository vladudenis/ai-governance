"""Formex parsing, including malformed documents and identifier checks."""

import pytest

from ai_governance.ingestion.errors import IdentifierMismatch, MalformedDocument
from ai_governance.ingestion.formex import parse_formex_zip
from ai_governance.ingestion.models import ProvisionKind, iter_provisions
from tests.ingestion_samples import ACT_XML, formex_zip


def _by_citation(parsed, citation: str):
    matches = [item for item in iter_provisions(parsed.provisions) if item.citation == citation]
    assert len(matches) == 1
    return matches[0]


def test_parser_extracts_structure_wording_and_notes() -> None:
    parsed = parse_formex_zip(formex_zip(), celex="32024R1689", expected_language="EN")

    assert parsed.oj_reference == "OJ L 2024/1689"
    assert parsed.language == "EN"
    assert parsed.formex_schema.endswith("formex-06.02.1-20231031.xd")
    assert "Sample title" in parsed.title
    assert parsed.unparsed_files == ["L_sample.toc.fmx.xml"]

    chapter = _by_citation(parsed, "Chapter I")
    assert chapter.heading == "GENERAL PROVISIONS"
    assert chapter.kind is ProvisionKind.chapter

    article = _by_citation(parsed, "Article 1")
    assert article.heading == "Subject matter"
    assert article.provision_id == "article/1"

    point = _by_citation(parsed, "Article 1(1)(h)(iii)")
    assert point.provision_id == "article/1/paragraph/1/subparagraph/1/point/h/point/iii"
    assert "nested point iii" in point.text

    subparagraph = next(
        item
        for item in iter_provisions(parsed.provisions)
        if item.kind is ProvisionKind.subparagraph and item.number == "2"
    )
    assert subparagraph.text == "Second subparagraph sample."
    assert subparagraph.citation == "Article 1(1)"

    recital = _by_citation(parsed, "Recital 1")
    assert "the Charter." in recital.text
    visa = _by_citation(parsed, "Visa 1")
    assert visa.text == "Having regard to the Treaty,"
    assert visa.notes == ["OJ C 1."]
    annex = _by_citation(parsed, "Annex III")
    assert annex.heading == "High-risk sample"
    assert _by_citation(parsed, "Annex III(1)").text.startswith("(1) First annex point")


def test_malformed_xml_is_rejected() -> None:
    broken = formex_zip(act="<ACT><TITLE>", annex=None)
    with pytest.raises(MalformedDocument):
        parse_formex_zip(broken, celex="32024R1689", expected_language="EN")


def test_non_zip_payload_is_rejected() -> None:
    with pytest.raises(MalformedDocument):
        parse_formex_zip(b"<ACT></ACT>", celex="32024R1689", expected_language="EN")


def test_dtd_payload_is_rejected() -> None:
    payload = formex_zip(act="<!DOCTYPE ACT [<!ENTITY x 'x'>]><ACT></ACT>", annex=None)
    with pytest.raises(MalformedDocument):
        parse_formex_zip(payload, celex="32024R1689", expected_language="EN")


def test_wrong_language_is_rejected() -> None:
    french = ACT_XML.replace("<LG.DOC>EN</LG.DOC>", "<LG.DOC>FR</LG.DOC>")
    with pytest.raises(IdentifierMismatch):
        parse_formex_zip(formex_zip(act=french, annex=None), celex="32024R1689", expected_language="EN")


def test_oj_number_must_match_celex() -> None:
    other_year = ACT_XML.replace("<YEAR>2024</YEAR>", "<YEAR>1999</YEAR>")
    with pytest.raises(IdentifierMismatch):
        parse_formex_zip(
            formex_zip(act=other_year, annex=None),
            celex="32024R1689",
            expected_language="EN",
        )
