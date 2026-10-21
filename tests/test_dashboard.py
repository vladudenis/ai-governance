"""Dashboard form payload and API client behaviour."""

import httpx

from frontend.client import ApiClient, ApiError
from frontend.forms import (
    DraftAnswer,
    answers_from_use_case,
    blank_answers,
    build_use_case,
    fact_label,
    status_label,
)


def test_unanswered_form_is_a_valid_unknown_snapshot() -> None:
    payload, errors = build_use_case("Spelling checker", "", blank_answers())

    assert errors == []
    assert payload is not None
    assert payload["name"] == "Spelling checker"
    assert payload["intended_purpose"]["basis"] == "unknown"
    assert payload["is_ai_system"] == {"value": "unknown", "basis": "unknown", "evidence": None}
    assert payload["annex_iii_use"]["value"] == "unknown"


def test_yes_without_evidence_is_rejected() -> None:
    answers = blank_answers()
    answers["is_ai_system"] = DraftAnswer("yes", "  ")

    payload, errors = build_use_case("Checker", "Suggest spelling fixes.", answers)

    assert payload is None
    assert any("evidence" in error.lower() for error in errors)


def test_answered_fields_round_trip_through_a_stored_snapshot() -> None:
    answers = blank_answers()
    answers["is_ai_system"] = DraftAnswer("yes", "It infers spelling fixes from the text.")
    answers["annex_iii_use"] = DraftAnswer("recruitment", "It filters job applications.")
    payload, errors = build_use_case("Recruitment filter", "Rank candidates.", answers)
    assert errors == []
    assert payload is not None

    restored = answers_from_use_case(payload)
    again, again_errors = build_use_case(payload["name"], payload["intended_purpose"]["value"], restored)

    assert again_errors == []
    assert again == payload


def test_status_labels_do_not_call_a_result_compliant() -> None:
    assert status_label(None) == "Not screened"
    assert "compliant" not in status_label("no_indicated_prohibited_or_high_risk_practice").lower()
    assert status_label("potentially_high_risk") == "Potentially high-risk"
    assert fact_label("annex_iii_use") == "Annex III use"


def test_client_reads_a_not_found_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ai-systems/9":
            return httpx.Response(404, json={"code": "not_found", "message": "AI system 9 was not found."})
        return httpx.Response(200, json=[])

    client = ApiClient("http://dashboard.test", transport=httpx.MockTransport(handler))
    try:
        assert client.list_systems("spell") == []
        try:
            client.get_system(9)
        except ApiError as exc:
            assert exc.status_code == 404
            assert exc.message == "AI system 9 was not found."
        else:
            raise AssertionError("missing system should fail")
    finally:
        client.close()
