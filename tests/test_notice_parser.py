"""Branch-notice parsing and the separation of related legal works."""

import pytest

from ai_governance.ingestion.errors import (
    DocumentNotFound,
    IdentifierMismatch,
    MalformedDocument,
)
from ai_governance.ingestion.models import DocumentKind
from ai_governance.ingestion.notice import document_kind_for, parse_branch_notice
from tests.ingestion_samples import NOTICE_XML


def test_notice_keeps_original_text_apart_from_consolidations_and_amendments() -> None:
    notice = parse_branch_notice(NOTICE_XML.encode(), celex="32024R1689", language="ENG")

    assert notice.celex == "32024R1689"
    assert notice.document_kind is DocumentKind.original
    assert notice.resource_type == "REG"
    assert notice.language == "en"
    assert notice.eli == "http://data.europa.eu/eli/reg/2024/1689/oj"
    assert notice.document_date.isoformat() == "2024-06-13"
    assert notice.publication_date.isoformat() == "2024-07-12"
    assert notice.manifestation_uri.endswith("work.0006.02")
    assert notice.amends_celex == ["32013R0167"]
    assert notice.amended_by_celex == ["32026R1744"]
    assert notice.proposed_amendment_celex == ["52025PC0836"]
    assert notice.related_consolidated_celex == ["02024R1689-20260727"]
    assert "02013R0167-20260802" not in notice.related_consolidated_celex
    assert notice.related_consolidation_ids == ["2024R1689/20240712"]


def test_notice_rejects_a_different_celex() -> None:
    with pytest.raises(IdentifierMismatch):
        parse_branch_notice(NOTICE_XML.encode(), celex="32013R0167", language="ENG")


def test_notice_rejects_malformed_xml() -> None:
    with pytest.raises(MalformedDocument):
        parse_branch_notice(b"<NOTICE>", celex="32024R1689")


def test_missing_language_expression_is_not_found() -> None:
    without_expression = NOTICE_XML.replace("ENG", "FRA")
    with pytest.raises(DocumentNotFound):
        parse_branch_notice(without_expression.encode(), celex="32024R1689", language="ENG")


def test_document_kind_uses_celex_sector_and_resource_type() -> None:
    assert document_kind_for("32024R1689", "REG") is DocumentKind.original
    assert document_kind_for("02024R1689-20260727", "CONS_TEXT") is DocumentKind.consolidated
    assert document_kind_for("52025PC0836", "GUIDE") is DocumentKind.guidance
