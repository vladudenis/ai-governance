"""Load three labelled example systems when the inventory is empty.

Run after the schema exists:

    .\\.venv\\Scripts\\python.exe -m ai_governance.seed

Inside Compose:

    docker compose run --rm api python -m ai_governance.seed
"""

import sys

from sqlalchemy import func, select

from ai_governance.assessment.engine import assess
from ai_governance.assessment.examples import LABELLED_EXAMPLES
from ai_governance.config import get_settings
from ai_governance.db.inventory import AISystem
from ai_governance.db.inventory_store import create_system, current_act_sha, save_assessment
from ai_governance.db.session import make_engine, make_session_factory
from ai_governance.db.workflow_store import add_remediation, generate_report, record_decision, record_event

EXAMPLE_NAMES = (
    "Internal spelling checker",
    "Recruitment filter",
    "Customer chatbot",
)
ACTOR = "example seed"


def seed_examples(session) -> int:
    """Insert the example systems. Return 0 when any system is already stored."""
    existing = session.scalar(select(func.count()).select_from(AISystem))
    if existing:
        return 0
    selected = [example for example in LABELLED_EXAMPLES if example.name in EXAMPLE_NAMES]
    content_sha = current_act_sha(session)
    created: list[tuple[str, int]] = []
    for example in selected:
        system = create_system(session, example.use_case)
        record_event(
            session,
            event_type="system_registered",
            summary=f"Registered {system.name}.",
            actor=ACTOR,
            ai_system_id=system.id,
        )
        assessment = save_assessment(
            session,
            system.records[-1],
            assess(example.use_case, content_sha256=content_sha, assessed_on=example.assessed_on),
        )
        record_event(
            session,
            event_type="assessment_created",
            summary=f"Stored screening {assessment.id} with status {assessment.status}.",
            actor=ACTOR,
            ai_system_id=system.id,
            assessment_id=assessment.id,
            details={"status": assessment.status},
        )
        created.append((example.name, assessment.id))
    by_name = dict(created)
    record_decision(
        session,
        by_name["Internal spelling checker"],
        decision="accepted_for_tracking",
        rationale="The answered facts do not indicate a prohibited practice or a high-risk route.",
        reviewer_name=ACTOR,
    )
    add_remediation(
        session,
        _assessment(session, by_name["Recruitment filter"]),
        title="Document the Annex III classification",
        description="Record whether Article 6(3) is claimed and whether the system profiles applicants.",
        owner="Case owner",
        due_on=None,
        finding_id=None,
        actor=ACTOR,
    )
    generate_report(session, _assessment(session, by_name["Internal spelling checker"]), ACTOR)
    return len(created)


def main() -> int:
    """Seed the database configured by DATABASE_URL."""
    engine = make_engine(get_settings().database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            created = seed_examples(session)
            session.commit()
    finally:
        engine.dispose()
    if created == 0:
        print("already seeded")
    else:
        print(f"seeded {created} systems")
    return 0


def _assessment(session, assessment_id: int):
    from ai_governance.db.inventory_store import get_assessment

    assessment = get_assessment(session, assessment_id)
    if assessment is None:
        raise RuntimeError(f"Example assessment {assessment_id} was not stored.")
    return assessment


if __name__ == "__main__":
    sys.exit(main())
