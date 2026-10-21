"""PostgreSQL schema, migrations, and regulatory import integrity."""

import os
from datetime import date, datetime, timezone
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from ai_governance.db.base import Base
from ai_governance.db.integrity import assert_document_stored
from ai_governance.db.models import LegalProvision, RegulatoryVersion
from ai_governance.db.regulatory_import import import_regulatory_document
from ai_governance.db.session import make_session_factory
from ai_governance.ingestion.models import (
    DocumentKind,
    LegalProvision as ParsedProvision,
    ProvisionKind,
    RegulatoryVersion as ParsedDocument,
)
from ai_governance.ingestion.store import RegulatoryStore

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "data" / "regulatory" / "index.json"
BASE_URL = os.environ.get(
    "AI_GOVERNANCE_TEST_DATABASE_URL",
    "postgresql+psycopg://ai_governance:change-me@127.0.0.1:5432/ai_governance",
)


def _sample(digest: str, wording: str = "harmonised rules") -> ParsedDocument:
    return ParsedDocument(
        celex="32024R1689",
        language="en",
        expression_language="eng",
        document_kind=DocumentKind.original,
        resource_type="REG",
        title="Sample title",
        notice_title="ARTIFICIAL INTELLIGENCE ACT",
        eli="http://data.europa.eu/eli/reg/2024/1689/oj",
        cellar_uri="http://publications.europa.eu/resource/cellar/work",
        source_url="http://publications.europa.eu/resource/celex/32024R1689",
        manifestation_uri="http://publications.europa.eu/resource/cellar/work.0006.02",
        resolved_url="http://publications.europa.eu/resource/cellar/work.0006.02/zip",
        oj_reference="OJ L 2024/1689",
        document_date=date(2024, 6, 13),
        publication_date=date(2024, 7, 12),
        formex_schema="formex-test",
        content_sha256=digest,
        parser_version="1",
        retrieved_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
        amends_celex=["32013R0167"],
        amended_by_celex=["32026R1744"],
        related_consolidated_celex=["02024R1689-20260727"],
        related_consolidation_ids=["2024R1689/20240712"],
        provisions=[
            ParsedProvision(
                provision_id="article/1",
                kind=ProvisionKind.article,
                citation="Article 1",
                number="1",
                heading="Subject matter",
                text=wording,
                notes=["OJ C 1."],
                source_file="act.xml",
                children=[
                    ParsedProvision(
                        provision_id="article/1/paragraph/1",
                        kind=ProvisionKind.paragraph,
                        citation="Article 1(1)",
                        number="1",
                        text="paragraph text",
                        source_file="act.xml",
                    )
                ],
            )
        ],
        source_files=["act.xml"],
        unparsed_files=["toc.xml"],
    )


@pytest.fixture(scope="module")
def database_url() -> str:
    """Create a throwaway database and apply the Alembic migration."""
    admin_url = make_url(BASE_URL).set(database="postgres")
    test_url = make_url(BASE_URL).set(database="ai_governance_test").render_as_string(
        hide_password=False
    )
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = 'ai_governance_test'")
            ).scalar()
            if exists is None:
                connection.execute(text("CREATE DATABASE ai_governance_test"))
    except Exception as exc:
        pytest.fail(f"PostgreSQL is not available: {exc}")
    finally:
        admin.dispose()

    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_url)
    command.upgrade(config, "head")
    return test_url


@pytest.fixture
def session(database_url: str):
    engine = create_engine(database_url)
    factory = make_session_factory(engine)
    with factory() as db_session:
        yield db_session
        db_session.rollback()
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE regulations RESTART IDENTITY CASCADE"))
    engine.dispose()


def test_migration_matches_the_models(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        diff = compare_metadata(context, Base.metadata)
    engine.dispose()
    assert diff == []


def test_repeat_import_does_not_duplicate_rows(session) -> None:
    document = _sample("a" * 64)
    first = import_regulatory_document(session, document)
    second = import_regulatory_document(session, document)
    session.flush()

    assert first.created is True
    assert second.created is False
    assert second.regulatory_version_id == first.regulatory_version_id
    assert_document_stored(session, document)
    assert session.query(RegulatoryVersion).count() == 1
    assert session.query(LegalProvision).count() == 2


def test_new_digest_keeps_the_previous_provisions(session) -> None:
    original = _sample("a" * 64, "harmonised rules")
    changed = _sample("b" * 64, "changed rules")
    first = import_regulatory_document(session, original)
    second = import_regulatory_document(session, changed)

    assert first.created is True
    assert second.created is True
    assert_document_stored(session, original, expect_current=False)
    assert_document_stored(session, changed, expect_current=True)
    assert session.query(RegulatoryVersion).count() == 2
    assert session.query(LegalProvision).count() == 4

    reimported = import_regulatory_document(session, original)
    assert reimported.created is False
    assert reimported.regulatory_version_id == first.regulatory_version_id
    assert_document_stored(session, original, expect_current=False)
    assert session.query(LegalProvision).count() == 4


def test_a_provision_cannot_point_at_another_versions_parent(session) -> None:
    first = import_regulatory_document(session, _sample("a" * 64))
    second = import_regulatory_document(session, _sample("b" * 64, "changed rules"))
    parent = session.query(LegalProvision).filter_by(regulatory_version_id=first.regulatory_version_id).first()
    assert parent is not None
    session.add(
        LegalProvision(
            regulatory_version_id=second.regulatory_version_id,
            parent_id=parent.id,
            provision_key="article/9",
            kind="article",
            citation="Article 9",
            provision_text="does not belong here",
            source_file="act.xml",
            position=0,
        )
    )
    with pytest.raises(IntegrityError):
        session.flush()
    session.rollback()


@pytest.mark.skipif(not CATALOG.is_file(), reason="local regulatory catalog is not present")
def test_official_ai_act_round_trip(session) -> None:
    document = RegulatoryStore(ROOT / "data" / "regulatory").load_current("32024R1689")
    result = import_regulatory_document(session, document)
    repeated = import_regulatory_document(session, document)

    assert result.created is True
    assert repeated.created is False
    assert_document_stored(session, document)
    articles = session.query(LegalProvision).filter_by(kind="article").count()
    recitals = session.query(LegalProvision).filter_by(kind="recital").count()
    annexes = session.query(LegalProvision).filter_by(kind="annex").count()
    assert articles == 113
    assert recitals == 180
    assert annexes == 13
    stored_article = session.query(LegalProvision).filter_by(provision_key="article/5").one()
    assert stored_article.heading is not None
    assert "Prohibited AI practices" in stored_article.heading
