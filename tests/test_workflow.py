"""Review, remediation, audit history, reports, and reassessment."""

from datetime import date, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from ai_governance.api.app import create_app
from ai_governance.assessment.examples import cleared
from ai_governance.reporting.report import render_governance_report, report_sha256
from ai_governance.workflow.reasons import reassessment_reasons
from datetime import datetime, timezone

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


@pytest.fixture
def client(database_url: str):
    _truncate(database_url)
    app = create_app(database_url)
    with TestClient(app) as test_client:
        yield test_client
    _truncate(database_url)


def test_fact_change_requires_reassessment(client: TestClient) -> None:
    system_id, assessment_id = _screen(client)
    before = client.get(f"/api/ai-systems/{system_id}")
    assert before.json()["reassessment_required"] is False

    changed = cleared("Renamed checker", "Suggest spelling fixes.").model_dump(mode="json")
    updated = client.put(f"/api/ai-systems/{system_id}", json=changed, headers={"X-Actor": "Ada"})
    assert updated.status_code == 200
    body = updated.json()
    assert body["reassessment_required"] is True
    assert "facts changed" in " ".join(body["reassessment_reasons"]).lower()
    stored = client.get(f"/api/assessments/{assessment_id}")
    assert stored.json()["use_case"]["name"] == "Spelling checker"


def test_review_remediation_control_and_report_are_versioned(client: TestClient) -> None:
    system_id, assessment_id = _screen(client)
    missing_name = client.post(
        f"/api/assessments/{assessment_id}/review",
        json={"decision": "changes_requested", "rationale": "The facts are still unknown."},
    )
    assert missing_name.status_code == 422
    assert missing_name.json()["code"] == "actor_required"

    headers = {"X-Actor": "Ada"}
    decided = client.post(
        f"/api/assessments/{assessment_id}/review",
        json={"decision": "changes_requested", "rationale": "The facts are still unknown."},
        headers=headers,
    )
    assert decided.status_code == 201
    assert decided.json()["status"] == "decided"
    assert decided.json()["decision"]["reviewer_name"] == "Ada"
    repeat = client.post(
        f"/api/assessments/{assessment_id}/review",
        json={"decision": "not_accepted", "rationale": "A second decision."},
        headers=headers,
    )
    assert repeat.status_code == 409

    action = client.post(
        f"/api/assessments/{assessment_id}/remediation",
        json={
            "title": "Answer the screening questions",
            "description": "Record yes or no for each unanswered question.",
            "owner": "Case owner",
            "due_on": (date.today() - timedelta(days=1)).isoformat(),
        },
        headers=headers,
    )
    assert action.status_code == 201
    assert action.json()["overdue"] is True
    evidence = client.post(
        f"/api/remediation/{action.json()['id']}/evidence",
        json={"note": "The owner started the questionnaire."},
        headers=headers,
    )
    assert evidence.status_code == 201
    reviewed = client.post(
        f"/api/evidence/{evidence.json()['id']}/review",
        json={"review_status": "accepted", "review_note": "The note is enough to track."},
        headers={"X-Actor": "Mina"},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["review_status"] == "accepted"

    controls = client.get(f"/api/assessments/{assessment_id}/controls")
    assert controls.status_code == 200
    assert controls.json()
    control_id = controls.json()[0]["control_id"]
    saved = client.put(
        f"/api/assessments/{assessment_id}/controls/{control_id}",
        json={"status": "gap", "notes": "Not started."},
        headers=headers,
    )
    assert saved.status_code == 200
    assert saved.json()["status"] == "gap"

    first = client.post(f"/api/assessments/{assessment_id}/reports", headers=headers)
    second = client.post(f"/api/assessments/{assessment_id}/reports", headers={"X-Actor": "Mina"})
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["version_number"] == first.json()["version_number"] + 1
    assert first.json()["content_sha256"] != second.json()["content_sha256"]
    downloaded = client.get(f"/api/reports/{first.json()['id']}")
    assert downloaded.status_code == 200
    assert "does not certify legal compliance" in downloaded.text
    assert "Spelling checker" in downloaded.text
    again = client.get(f"/api/reports/{first.json()['id']}")
    assert again.text == downloaded.text

    audit = client.get("/api/audit", params={"ai_system_id": system_id})
    event_types = {item["event_type"] for item in audit.json()}
    assert {
        "system_registered",
        "assessment_created",
        "review_decision_recorded",
        "remediation_created",
        "evidence_submitted",
        "evidence_reviewed",
        "control_status_changed",
        "report_generated",
    } <= event_types
    queue = client.get("/api/review-tasks", params={"status": "open"})
    assert all(item["assessment_id"] != assessment_id for item in queue.json())


def test_reassessment_reasons_ignore_an_unscreened_system() -> None:
    assert reassessment_reasons(
        has_assessment=False,
        latest_record_id=None,
        current_record_id=1,
        latest_rule_version=None,
        current_rule_version="1",
        latest_content_sha256=None,
        current_content_sha256="abc",
    ) == []
    reasons = reassessment_reasons(
        has_assessment=True,
        latest_record_id=1,
        current_record_id=1,
        latest_rule_version="1",
        current_rule_version="2",
        latest_content_sha256="aaa",
        current_content_sha256="bbb",
    )
    assert any("rule set" in reason.lower() for reason in reasons)
    assert any("newer text" in reason.lower() for reason in reasons)


def test_report_digest_changes_when_the_body_changes() -> None:
    moment = datetime(2026, 10, 21, tzinfo=timezone.utc)
    common = dict(
        system_name="Checker",
        snapshot_version=1,
        purpose="Suggest spelling fixes.",
        assessment_id=1,
        assessment_status="needs_further_information",
        rule_set_version="1",
        celex="32024R1689",
        content_sha256=None,
        assessed_on=None,
        notice="Decision-support screening.",
        findings=[],
        controls=[],
        remediations=[],
        decision=None,
        generated_by="Ada",
        generated_at=moment,
    )
    first = render_governance_report(report_version=1, **common)
    second = render_governance_report(report_version=2, **common)
    assert report_sha256(first) != report_sha256(second)
    assert "does not certify legal compliance" in first


def _screen(client: TestClient) -> tuple[int, int]:
    created = client.post(
        "/api/ai-systems",
        json={"name": "Spelling checker"},
        headers={"X-Actor": "Ada"},
    )
    assert created.status_code == 201
    assessment = client.post(
        f"/api/ai-systems/{created.json()['id']}/assessments",
        json={},
        headers={"X-Actor": "Ada"},
    )
    assert assessment.status_code == 201
    return created.json()["id"], assessment.json()["id"]


def _truncate(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE ai_systems, regulations RESTART IDENTITY CASCADE"))
    engine.dispose()
