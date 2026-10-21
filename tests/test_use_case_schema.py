"""Validation of the use-case record the rules are allowed to read."""

import pytest
from pydantic import ValidationError

from ai_governance.assessment.facts import Answer, Basis, UseCase, YesNo


def test_yes_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Answer(value=YesNo.yes, basis=Basis.stated)


def test_unknown_with_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Answer(value=YesNo.unknown, basis=Basis.unknown, evidence="The description is silent.")


def test_unknown_marked_stated_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Answer(value=YesNo.unknown, basis=Basis.stated, evidence="A sentence.")


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        UseCase.model_validate({"name": "Widget", "high_risk": True})
