"""Import one CELEX work from CELLAR into the local regulatory store."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from ai_governance.config import Settings, get_settings
from ai_governance.ingestion.cellar import CellarClient
from ai_governance.ingestion.errors import IdentifierMismatch
from ai_governance.ingestion.formex import PARSER_VERSION, parse_formex_zip
from ai_governance.ingestion.models import ImportResult, RegulatoryVersion
from ai_governance.ingestion.notice import parse_branch_notice
from ai_governance.ingestion.store import RegulatoryStore

_LANGUAGE = {
    "eng": {"notice": "ENG", "formex": "EN", "path": "en"},
}


def import_celex(
    celex: str,
    *,
    language: str = "eng",
    client: CellarClient | None = None,
    store: RegulatoryStore | None = None,
    settings: Settings | None = None,
    retrieved_at: datetime | None = None,
) -> ImportResult:
    """Retrieve, verify, parse, and store one linguistic version of a work.

    Repeating the call with the same Formex bytes does not create a second
    catalog row. A different payload is stored beside the previous one.
    """
    language_codes = _LANGUAGE.get(language.lower())
    if language_codes is None:
        raise ValueError("This milestone retrieves the English expression only (language='eng')")

    settings = settings or get_settings()
    owns_client = client is None
    client = client or CellarClient(settings.cellar_base_url)
    store = store or RegulatoryStore(_store_root(settings))
    moment = retrieved_at or datetime.now(timezone.utc)

    try:
        notice_object = client.fetch_notice(celex, language=language.lower())
        notice = parse_branch_notice(
            notice_object.body,
            celex=celex,
            language=language_codes["notice"],
        )
        formex_object = client.fetch_formex(celex, language=language.lower())
        _assert_resolved_manifestation(formex_object.url, notice.manifestation_uri)
        parsed = parse_formex_zip(
            formex_object.body,
            celex=celex,
            expected_language=language_codes["formex"],
        )
    finally:
        if owns_client:
            client.close()

    if (
        notice.document_date is not None
        and parsed.document_date is not None
        and notice.document_date != parsed.document_date
    ):
        raise IdentifierMismatch(
            f"Notice date {notice.document_date.isoformat()} does not match "
            f"Formex date {parsed.document_date.isoformat()} for {celex}"
        )

    document = RegulatoryVersion(
        celex=celex,
        language=language_codes["path"],
        expression_language=notice.expression_language,
        document_kind=notice.document_kind,
        resource_type=notice.resource_type,
        title=parsed.title or notice.notice_title or celex,
        notice_title=notice.notice_title,
        eli=notice.eli,
        cellar_uri=notice.cellar_uri,
        source_url=f"{client.base_url}/{celex}",
        manifestation_uri=notice.manifestation_uri,
        resolved_url=formex_object.url,
        oj_reference=parsed.oj_reference,
        document_date=notice.document_date or parsed.document_date,
        publication_date=notice.publication_date,
        formex_schema=parsed.formex_schema,
        content_sha256=hashlib.sha256(formex_object.body).hexdigest(),
        parser_version=PARSER_VERSION,
        retrieved_at=moment,
        amends_celex=notice.amends_celex,
        amended_by_celex=notice.amended_by_celex,
        proposed_amendment_celex=notice.proposed_amendment_celex,
        related_consolidated_celex=notice.related_consolidated_celex,
        related_consolidation_ids=notice.related_consolidation_ids,
        provisions=parsed.provisions,
        source_files=parsed.source_files,
        unparsed_files=parsed.unparsed_files,
    )
    return store.import_document(document, formex_object.body)


def _store_root(settings: Settings) -> Path:
    return Path(settings.data_dir) / "regulatory"


def _assert_resolved_manifestation(resolved_url: str, manifestation_uri: str) -> None:
    """When CELLAR redirects to a cellar URI, require the Formex manifestation."""
    if "/resource/cellar/" not in resolved_url:
        return
    marker = manifestation_uri.rstrip("/").split("/")[-1]
    if marker not in resolved_url:
        raise IdentifierMismatch(
            f"Formex response URL {resolved_url} does not match manifestation {manifestation_uri}"
        )
