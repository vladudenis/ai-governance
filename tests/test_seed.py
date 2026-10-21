"""Example inventory seed."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url

from ai_governance.db.inventory import AISystem, Assessment
from ai_governance.db.session import make_session_factory
from ai_governance.db.workflow import GovernanceReport, RemediationAction, ReviewTask
from ai_governance.seed import seed_examples

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "postgresql+psycopg://ai_governance:change-me@127.0.0.1:5432/ai_governance"


@pytest.fixture(scope="module")
def database_url() -> str:
    admin_url = make_url(BASE_URL).set(database="postgres")
    test_url = make_url(BASE_URL).set(database="ai_governance_test").render_as_string(hide_password=False)
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


def test_seed_is_idempotent_and_covers_three_outcomes(database_url: str) -> None:
    engine = create_engine(database_url)
    factory = make_session_factory(engine)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE ai_systems RESTART IDENTITY CASCADE"))
    with factory() as session:
        created = seed_examples(session)
        session.commit()
        names = set(session.scalars(select(AISystem.name)))
        statuses = set(session.scalars(select(Assessment.status)))
        open_reviews = session.scalar(select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "open"))
        decided = session.scalar(select(func.count()).select_from(ReviewTask).where(ReviewTask.status == "decided"))
        remediations = session.scalar(select(func.count()).select_from(RemediationAction))
        reports = session.scalar(select(func.count()).select_from(GovernanceReport))
        second = seed_examples(session)
    engine.dispose()

    assert created == 3
    assert second == 0
    assert names == {"Internal spelling checker", "Recruitment filter", "Customer chatbot"}
    assert "potentially_high_risk" in statuses
    assert "requires_legal_review" in statuses
    assert "no_indicated_prohibited_or_high_risk_practice" in statuses
    assert open_reviews == 2
    assert decided == 1
    assert remediations == 1
    assert reports == 1
