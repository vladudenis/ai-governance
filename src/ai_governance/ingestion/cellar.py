"""CELLAR content-negotiation client.

Official retrieval, verified against the Publications Office documentation and
a live request for CELEX 32024R1689:

- Branch notice: ``GET http://publications.europa.eu/resource/celex/{CELEX}``
  with ``Accept: application/xml;notice=branch`` and ``Accept-Language: eng``.
- Formex 4 ZIP: the same URL with ``Accept: application/zip;mtype=fmx4``.

Those headers are specified in the CELLAR dissemination interface and in
EUR-Lex "Data extraction using web services", section 3.4.5. The client
follows the redirect to the English Formex manifestation. It does not scrape
the EUR-Lex HTML view.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass

import httpx

from ai_governance.ingestion.errors import DocumentNotFound, RetrievalError

logger = logging.getLogger(__name__)

NOTICE_ACCEPT = "application/xml;notice=branch"
FORMEX_ACCEPT = "application/zip;mtype=fmx4"
USER_AGENT = "ai-governance-ingestion/0.1 (local educational import)"
_RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class RetrievedObject:
    """Bytes returned by one CELLAR request."""

    body: bytes
    url: str
    content_type: str | None


class CellarClient:
    """Small client for the documented CELEX content-negotiation URL."""

    def __init__(
        self,
        base_url: str = "http://publications.europa.eu/resource/celex",
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 90.0,
        attempts: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        max_bytes: int = 52_428_800,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.attempts = attempts
        self._sleep = sleep
        self.max_bytes = max_bytes
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "CellarClient":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def fetch_notice(self, celex: str, *, language: str = "eng") -> RetrievedObject:
        """Download the branch notice for one work."""
        return self._get(self._url(celex), NOTICE_ACCEPT, language)

    def fetch_formex(self, celex: str, *, language: str = "eng") -> RetrievedObject:
        """Download the Formex 4 ZIP for one linguistic version."""
        return self._get(self._url(celex), FORMEX_ACCEPT, language)

    def _url(self, celex: str) -> str:
        return f"{self.base_url}/{celex}"

    def _get(self, url: str, accept: str, language: str) -> RetrievedObject:
        headers = {
            "Accept": accept,
            "Accept-Language": language,
            "Accept-Max-Cs-Size": str(self.max_bytes),
        }
        last_error: Exception | None = None
        for attempt in range(1, self.attempts + 1):
            try:
                response = self._client.get(url, headers=headers)
            except httpx.TransportError as exc:
                last_error = exc
                logger.warning("CELLAR request failed (%s/%s): %s", attempt, self.attempts, exc)
            else:
                if response.status_code == 404:
                    raise DocumentNotFound(f"CELLAR has no document for {url}")
                if response.status_code in _RETRY_STATUSES:
                    last_error = RetrievalError(f"CELLAR returned HTTP {response.status_code} for {url}")
                    logger.warning(
                        "CELLAR HTTP %s (%s/%s) for %s",
                        response.status_code,
                        attempt,
                        self.attempts,
                        url,
                    )
                elif response.status_code >= 400:
                    raise RetrievalError(f"CELLAR returned HTTP {response.status_code} for {url}")
                else:
                    body = response.content
                    if len(body) > self.max_bytes:
                        raise RetrievalError(f"CELLAR response for {url} exceeds {self.max_bytes} bytes")
                    return RetrievedObject(
                        body=body,
                        url=str(response.url),
                        content_type=response.headers.get("content-type"),
                    )
            if attempt < self.attempts:
                self._sleep(0.25 * attempt)
        raise RetrievalError(f"CELLAR request failed after {self.attempts} attempts: {url}") from last_error
