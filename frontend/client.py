"""HTTP client for the governance API.

The dashboard uses this instead of opening the database itself.
"""

import httpx


class ApiError(Exception):
    """A response the dashboard should show to the user."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        super().__init__(message)


class ApiClient:
    """Calls the FastAPI routes used by the inventory and screening pages."""

    def __init__(
        self,
        base_url: str,
        transport: httpx.BaseTransport | None = None,
        actor: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._actor = actor.strip() if actor and actor.strip() else None
        self._client = httpx.Client(base_url=self.base_url, transport=transport, timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def list_systems(self, name_query: str | None = None) -> list[dict]:
        params = {"limit": 200}
        if name_query:
            params["q"] = name_query
        return self._request("GET", "/api/ai-systems", params=params)

    def get_system(self, system_id: int) -> dict:
        return self._request("GET", f"/api/ai-systems/{system_id}")

    def create_system(self, payload: dict) -> dict:
        return self._request("POST", "/api/ai-systems", json=payload)

    def update_system(self, system_id: int, payload: dict) -> dict:
        return self._request("PUT", f"/api/ai-systems/{system_id}", json=payload)

    def list_assessments(self, system_id: int) -> list[dict]:
        return self._request("GET", f"/api/ai-systems/{system_id}/assessments")

    def create_assessment(self, system_id: int, assessed_on: str | None) -> dict:
        body = {} if assessed_on is None else {"assessed_on": assessed_on}
        return self._request("POST", f"/api/ai-systems/{system_id}/assessments", json=body)

    def get_assessment(self, assessment_id: int) -> dict:
        return self._request("GET", f"/api/assessments/{assessment_id}")

    def list_review_tasks(self, status: str = "open") -> list[dict]:
        return self._request("GET", "/api/review-tasks", params={"status": status})

    def get_review(self, assessment_id: int) -> dict:
        return self._request("GET", f"/api/assessments/{assessment_id}/review")

    def record_decision(self, assessment_id: int, decision: str, rationale: str) -> dict:
        return self._request(
            "POST",
            f"/api/assessments/{assessment_id}/review",
            json={"decision": decision, "rationale": rationale},
        )

    def list_remediation(self, assessment_id: int) -> list[dict]:
        return self._request("GET", f"/api/assessments/{assessment_id}/remediation")

    def create_remediation(self, assessment_id: int, title: str, description: str, owner: str) -> dict:
        return self._request(
            "POST",
            f"/api/assessments/{assessment_id}/remediation",
            json={"title": title, "description": description, "owner": owner},
        )

    def list_controls(self, assessment_id: int) -> list[dict]:
        return self._request("GET", f"/api/assessments/{assessment_id}/controls")

    def save_control(self, assessment_id: int, control_id: str, status: str, notes: str) -> dict:
        return self._request(
            "PUT",
            f"/api/assessments/{assessment_id}/controls/{control_id}",
            json={"status": status, "notes": notes or None},
        )

    def list_audit(self, ai_system_id: int | None = None) -> list[dict]:
        params = {} if ai_system_id is None else {"ai_system_id": ai_system_id}
        return self._request("GET", "/api/audit", params=params)

    def create_report(self, assessment_id: int) -> dict:
        return self._request("POST", f"/api/assessments/{assessment_id}/reports")

    def download_report(self, report_id: int) -> str:
        try:
            response = self._client.request("GET", f"/api/reports/{report_id}", headers=self._headers())
        except httpx.HTTPError as exc:
            raise ApiError(0, "unavailable", f"The API at {self.base_url} is not reachable.") from exc
        if response.status_code >= 400:
            code, message = _error_body(response)
            raise ApiError(response.status_code, code, message)
        return response.text

    def find_provision(self, provision_key: str) -> dict | None:
        page = self._request(
            "GET",
            "/api/legal-provisions",
            params={"provision_key": provision_key, "limit": 1},
        )
        items = page["items"]
        if not items:
            return None
        return self._request("GET", f"/api/legal-provisions/{items[0]['id']}")

    def _headers(self) -> dict[str, str]:
        if not self._actor:
            return {}
        return {"X-Actor": self._actor}

    def _request(self, method: str, path: str, **kwargs: object) -> dict | list:
        headers = dict(kwargs.pop("headers", {}) or {})
        headers.update(self._headers())
        try:
            response = self._client.request(method, path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ApiError(0, "unavailable", f"The API at {self.base_url} is not reachable.") from exc
        if response.status_code >= 400:
            body = _error_body(response)
            raise ApiError(response.status_code, body[0], body[1])
        return response.json()


def _error_body(response: httpx.Response) -> tuple[str, str]:
    try:
        payload = response.json()
    except ValueError:
        return "http_error", response.text or "The request failed."
    if isinstance(payload, dict) and "message" in payload:
        return str(payload.get("code") or "http_error"), str(payload["message"])
    return "http_error", "The request failed."
