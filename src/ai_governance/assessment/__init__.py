"""Deterministic EU AI Act screening.

The engine applies versioned rules to a validated use-case record. It does not
call a model, and it does not decide that a practice is prohibited or that a
system is legally high-risk.
"""

from ai_governance.assessment.engine import assess
from ai_governance.assessment.facts import UseCase
from ai_governance.assessment.results import AssessmentResult

__all__ = ["AssessmentResult", "UseCase", "assess"]
