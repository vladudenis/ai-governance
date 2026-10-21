"""Parser checks against the Formex ZIP and branch notice downloaded for Milestone 2.

The files are produced by the CELLAR request and are gitignored. A checkout
without them skips these tests; the synthetic fixtures still run.
"""

from pathlib import Path

import pytest

from ai_governance.ingestion.formex import parse_formex_zip
from ai_governance.ingestion.models import DocumentKind, ProvisionKind, iter_provisions
from ai_governance.ingestion.notice import parse_branch_notice

ROOT = Path(__file__).resolve().parents[1]
FORMEX_ZIP = ROOT / "data" / "raw" / "32024R1689_eng_fmx4.bin"
BRANCH_NOTICE = ROOT / "data" / "raw" / "32024R1689_branch_notice.xml"


@pytest.mark.skipif(not FORMEX_ZIP.is_file(), reason="local Formex ZIP is not present")
def test_official_ai_act_formex_has_the_expected_structure() -> None:
    parsed = parse_formex_zip(FORMEX_ZIP.read_bytes(), celex="32024R1689", expected_language="EN")
    provisions = list(iter_provisions(parsed.provisions))

    assert parsed.oj_reference == "OJ L 2024/1689"
    assert parsed.document_date is not None
    assert parsed.document_date.isoformat() == "2024-06-13"
    assert sum(item.kind is ProvisionKind.article for item in provisions) == 113
    assert sum(item.kind is ProvisionKind.recital for item in provisions) == 180
    assert sum(item.kind is ProvisionKind.annex for item in provisions) == 13

    article_5 = next(item for item in provisions if item.citation == "Article 5")
    assert "Prohibited AI practices" in (article_5.heading or "")
    recital_1 = next(item for item in provisions if item.citation == "Recital 1")
    assert "internal market" in recital_1.text
    annex_iii = next(item for item in provisions if item.citation == "Annex III")
    assert annex_iii.heading is not None
    assert "High-risk" in annex_iii.heading
    nested = [item for item in provisions if item.citation == "Article 5(1)(h)(iii)"]
    assert len(nested) == 1
    assert nested[0].text


@pytest.mark.skipif(not BRANCH_NOTICE.is_file(), reason="local branch notice is not present")
def test_official_branch_notice_identifies_the_english_original() -> None:
    notice = parse_branch_notice(BRANCH_NOTICE.read_bytes(), celex="32024R1689", language="ENG")

    assert notice.document_kind is DocumentKind.original
    assert notice.resource_type == "REG"
    assert notice.language == "en"
    assert notice.eli == "http://data.europa.eu/eli/reg/2024/1689/oj"
    assert notice.cellar_uri is not None
    assert notice.cellar_uri.endswith("dc8116a1-3fe6-11ef-865a-01aa75ed71a1")
    assert notice.manifestation_uri.endswith(".0006.02")
    assert notice.document_date is not None
    assert notice.document_date.isoformat() == "2024-06-13"
    assert notice.publication_date is not None
    assert notice.publication_date.isoformat() == "2024-07-12"
    assert "02024R1689-20240712" in notice.related_consolidated_celex
    assert "02024R1689-20260727" in notice.related_consolidated_celex
    assert "02013R0167-20260802" not in notice.related_consolidated_celex
    assert "32026R1744" in notice.amended_by_celex
