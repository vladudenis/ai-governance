"""CELLAR client retries, missing documents, and HTTP failures."""

import httpx
import pytest

from ai_governance.ingestion.cellar import CellarClient
from ai_governance.ingestion.errors import DocumentNotFound, RetrievalError


class QueueTransport(httpx.BaseTransport):
    """Return scripted responses, including transport failures."""

    def __init__(self, events: list[object]) -> None:
        self.events = list(events)
        self.calls = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if not self.events:
            raise AssertionError(f"unexpected request {request.url}")
        event = self.events.pop(0)
        if isinstance(event, Exception):
            raise event
        if isinstance(event, httpx.Response):
            return event
        status, body = event
        return httpx.Response(status, content=body)


def test_retries_a_server_error_then_returns_the_body() -> None:
    transport = QueueTransport([(503, b""), (200, b"notice")])
    slept: list[float] = []
    with CellarClient(transport=transport, attempts=3, sleep=slept.append) as client:
        retrieved = client.fetch_notice("32024R1689")

    assert retrieved.body == b"notice"
    assert transport.calls == 2
    assert slept == [0.25]


def test_exhausted_retries_raise_retrieval_error() -> None:
    transport = QueueTransport([httpx.ConnectError("offline")] * 3)
    with CellarClient(transport=transport, attempts=3, sleep=lambda _seconds: None) as client:
        with pytest.raises(RetrievalError):
            client.fetch_formex("32024R1689")
    assert transport.calls == 3


def test_not_found_is_not_retried() -> None:
    transport = QueueTransport([(404, b"missing")])
    with CellarClient(transport=transport, attempts=3, sleep=lambda _seconds: None) as client:
        with pytest.raises(DocumentNotFound):
            client.fetch_notice("32024R1689")
    assert transport.calls == 1


def test_client_error_is_not_retried() -> None:
    transport = QueueTransport([(406, b"not acceptable")])
    with CellarClient(transport=transport, attempts=3, sleep=lambda _seconds: None) as client:
        with pytest.raises(RetrievalError):
            client.fetch_formex("32024R1689")
    assert transport.calls == 1
