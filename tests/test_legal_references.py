"""Every rule citation points at the imported EU AI Act text."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

from ai_governance.assessment.catalog import CONTROLS_BY_ID, reference_problems
from ai_governance.assessment.engine import assess
from ai_governance.assessment.examples import LABELLED_EXAMPLES
from ai_governance.db.models import LegalProvision, Regulation, RegulatoryVersion
from ai_governance.db.session import make_session_factory
from ai_governance.ingestion.models import iter_provisions
from ai_governance.ingestion.store import RegulatoryStore

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "regulatory" / "index.json"
BASE_URL = "postgresql+psycopg://ai_governance:change-me@127.0.0.1:5432/ai_governance"


def test_an_empty_act_index_is_reported() -> None:
    problems = reference_problems({})
    assert problems
    assert any("article/5/paragraph/1/subparagraph/1/point/a" in problem for problem in problems)


def test_rule_citations_match_the_postgres_act() -> None:
    index = _postgres_citations()
    assert reference_problems(index) == []


@pytest.mark.skipif(not CATALOG.is_file(), reason="local regulatory catalog is not present")
def test_rule_citations_match_the_stored_json() -> None:
    document = RegulatoryStore(ROOT / "data" / "regulatory").load_current("32024R1689")
    index = {provision.provision_id: provision.citation for provision in iter_provisions(document.provisions)}
    assert reference_problems(index) == []
    postgres_index = _postgres_citations()
    for key, citation in index.items():
        if key in postgres_index:
            assert postgres_index[key] == citation


def test_findings_only_name_controls_from_the_catalog() -> None:
    for example in LABELLED_EXAMPLES:
        result = assess(example.use_case, assessed_on=example.assessed_on)
        for item in (*result.findings, *result.checks):
            assert item.rule_version == "1"
            for control_id in item.control_ids:
                assert control_id in CONTROLS_BY_ID


def _postgres_citations() -> dict[str, str]:
    engine = create_engine(make_url(BASE_URL))
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            rows = session.execute(
                select(LegalProvision.provision_key, LegalProvision.citation)
                .join(RegulatoryVersion, LegalProvision.regulatory_version_id == RegulatoryVersion.id)
                .join(Regulation, RegulatoryVersion.regulation_id == Regulation.id)
                .where(Regulation.celex == "32024R1689", RegulatoryVersion.status == "current")
            ).all()
    finally:
        engine.dispose()
    return {key: citation for key, citation in rows}
