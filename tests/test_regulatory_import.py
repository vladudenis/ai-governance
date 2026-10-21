"""Idempotent imports, version tracking, and the full retrieval flow."""

from datetime import datetime, timezone

import httpx
import pytest

from ai_governance.ingestion.cellar import CellarClient
from ai_governance.ingestion.errors import IdentifierMismatch
from ai_governance.ingestion.service import import_celex
from ai_governance.ingestion.store import RegulatoryStore
from tests.ingestion_samples import ACT_XML, NOTICE_XML, formex_zip

MANIFESTATION = "work.0006.02"
RETRIEVED_AT = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)


class RouteTransport(httpx.BaseTransport):
    """Serve a branch notice and a Formex redirect without leaving the test."""

    def __init__(self, package: bytes, *, redirect_to: str = MANIFESTATION) -> None:
        self.package = package
        self.redirect_to = redirect_to
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        accept = request.headers.get("accept", "")
        if "notice=branch" in accept:
            return httpx.Response(200, content=NOTICE_XML.encode())
        if str(request.url).endswith("/zip"):
            return httpx.Response(200, content=self.package, headers={"content-type": "application/zip"})
        location = f"http://publications.europa.eu/resource/cellar/{self.redirect_to}/zip"
        return httpx.Response(302, headers={"location": location})


def test_repeat_import_does_not_create_a_second_record(tmp_path) -> None:
    package = formex_zip()
    store = RegulatoryStore(tmp_path)
    transport = RouteTransport(package)
    client = CellarClient(transport=transport, sleep=lambda _seconds: None)

    first = import_celex(
        "32024R1689",
        client=client,
        store=store,
        retrieved_at=RETRIEVED_AT,
    )
    second = import_celex(
        "32024R1689",
        client=client,
        store=store,
        retrieved_at=RETRIEVED_AT,
    )

    assert first.created is True
    assert second.created is False
    assert first.version.content_sha256 == second.version.content_sha256
    catalog = store._read_catalog()
    assert len(catalog.versions) == 1
    json_files = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.json")}
    assert json_files == {"index.json", first.version.relative_path}
    stored = store.load(first.version)
    assert stored.celex == "32024R1689"
    assert stored.language == "en"
    assert stored.document_kind.value == "original"
    assert stored.amended_by_celex == ["32026R1744"]
    assert "02013R0167-20260802" not in stored.related_consolidated_celex
    client.close()


def test_changed_payload_keeps_the_previous_version(tmp_path) -> None:
    store = RegulatoryStore(tmp_path)
    original = formex_zip()
    changed_act = ACT_XML.replace("harmonised rules;", "changed rules;")
    changed = formex_zip(act=changed_act)
    first_client = CellarClient(transport=RouteTransport(original), sleep=lambda _seconds: None)
    second_client = CellarClient(transport=RouteTransport(changed), sleep=lambda _seconds: None)

    first = import_celex("32024R1689", client=first_client, store=store, retrieved_at=RETRIEVED_AT)
    second = import_celex("32024R1689", client=second_client, store=store, retrieved_at=RETRIEVED_AT)

    catalog = store._read_catalog()
    assert first.created is True
    assert second.created is True
    assert len(catalog.versions) == 2
    previous = next(version for version in catalog.versions if version.content_sha256 == first.version.content_sha256)
    current = next(version for version in catalog.versions if version.content_sha256 == second.version.content_sha256)
    assert previous.superseded is True
    assert current.superseded is False
    assert (tmp_path / previous.relative_path).is_file()
    assert (tmp_path / current.relative_path).is_file()
    assert "harmonised rules" in store.load(previous).model_dump_json()
    assert "changed rules" in store.load(current).model_dump_json()
    assert store.load_current("32024R1689").content_sha256 == second.version.content_sha256
    first_client.close()
    second_client.close()


def test_wrong_manifestation_is_not_stored(tmp_path) -> None:
    store = RegulatoryStore(tmp_path)
    client = CellarClient(
        transport=RouteTransport(formex_zip(), redirect_to="work.9999.01"),
        sleep=lambda _seconds: None,
    )
    with pytest.raises(IdentifierMismatch):
        import_celex("32024R1689", client=client, store=store, retrieved_at=RETRIEVED_AT)
    assert store._read_catalog().versions == []
    client.close()
