"""Load the current local regulatory JSON into PostgreSQL.

Run after Alembic has created the schema:

    .\\.venv\\Scripts\\python.exe -m alembic upgrade head
    .\\.venv\\Scripts\\python.exe -m ai_governance.db.load_regulatory
"""

import argparse
import sys
from pathlib import Path

from sqlalchemy import func, select

from ai_governance.config import get_settings
from ai_governance.db.integrity import RegulatoryIntegrityError, assert_document_stored
from ai_governance.db.models import LegalProvision
from ai_governance.db.regulatory_import import import_regulatory_document
from ai_governance.db.session import make_engine, make_session_factory
from ai_governance.ingestion.store import RegulatoryStore


def main(argv: list[str] | None = None) -> int:
    """Import the current stored document for one CELEX and check it."""
    parser = argparse.ArgumentParser(description="Load a stored regulatory JSON file into PostgreSQL.")
    parser.add_argument("--celex", default="32024R1689")
    parser.add_argument("--language", default="en")
    args = parser.parse_args(argv)

    settings = get_settings()
    store = RegulatoryStore(Path(settings.data_dir) / "regulatory")
    try:
        document = store.load_current(args.celex, args.language)
    except ValueError as exc:
        print(f"Load failed: {exc}", file=sys.stderr)
        print("Import the act from CELLAR before loading the database.", file=sys.stderr)
        return 1

    engine = make_engine(settings.database_url)
    factory = make_session_factory(engine)
    try:
        with factory() as session:
            result = import_regulatory_document(session, document)
            assert_document_stored(session, document, expect_current=True)
            provision_count = session.scalar(
                select(func.count())
                .select_from(LegalProvision)
                .where(LegalProvision.regulatory_version_id == result.regulatory_version_id)
            )
            session.commit()
    except RegulatoryIntegrityError as exc:
        print(f"Integrity check failed: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(f"CELEX {document.celex}")
    print(f"created: {'yes' if result.created else 'no, already stored'}")
    print(f"regulation id: {result.regulation_id}")
    print(f"version id: {result.regulatory_version_id}")
    print(f"provisions: {provision_count}")
    print(f"version: {result.content_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
