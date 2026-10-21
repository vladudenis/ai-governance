"""Import the EU AI Act, or another CELEX work, from CELLAR.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m ai_governance.ingestion
"""

import argparse
import sys
from pathlib import Path

from ai_governance.config import get_settings
from ai_governance.ingestion.errors import IngestionError
from ai_governance.ingestion.models import ProvisionKind, count_provisions
from ai_governance.ingestion.service import import_celex
from ai_governance.ingestion.store import RegulatoryStore


def main(argv: list[str] | None = None) -> int:
    """Download one English CELEX work and print a short structural summary."""
    parser = argparse.ArgumentParser(description="Import an official EU act from CELLAR Formex.")
    parser.add_argument("--celex", default="32024R1689", help="CELEX identifier to retrieve")
    args = parser.parse_args(argv)
    try:
        result = import_celex(args.celex)
    except (IngestionError, ValueError) as exc:
        print(f"Import failed: {exc}", file=sys.stderr)
        return 1

    store = RegulatoryStore(Path(get_settings().data_dir) / "regulatory")
    document = store.load(result.version)
    print(f"CELEX {document.celex}")
    print(f"language: {document.language}")
    print(f"document kind: {document.document_kind.value}")
    print(f"resource type: {document.resource_type}")
    print(f"created: {'yes' if result.created else 'no, already stored'}")
    print(f"OJ reference: {document.oj_reference}")
    print(f"document date: {document.document_date}")
    print(f"publication date: {document.publication_date}")
    print(f"articles: {count_provisions(document.provisions, ProvisionKind.article)}")
    print(f"recitals: {count_provisions(document.provisions, ProvisionKind.recital)}")
    print(f"annexes: {count_provisions(document.provisions, ProvisionKind.annex)}")
    print(f"amended by: {', '.join(document.amended_by_celex) or 'none recorded'}")
    print(f"consolidated versions: {', '.join(document.related_consolidated_celex) or 'none recorded'}")
    print(f"version: {document.content_sha256}")
    print(f"stored: {store.root / result.version.relative_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
