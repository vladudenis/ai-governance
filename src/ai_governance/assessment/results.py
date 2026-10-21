"""What one run of the rules engine returns.

The status is a decision-support label. It is not a determination that a
practice is prohibited, that a system is high-risk in law, or that a system
complies with Regulation (EU) 2024/1689.
"""

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class AssessmentStatus(str, Enum):
    """Strictest label for the whole record."""

    requires_legal_review = "requires_legal_review"
    potentially_high_risk = "potentially_high_risk"
    needs_further_information = "needs_further_information"
    no_indicated_prohibited_or_high_risk_practice = "no_indicated_prohibited_or_high_risk_practice"


class Outcome(str, Enum):
    """Result of one rule."""

    not_indicated = "not_indicated"
    needs_further_information = "needs_further_information"
    requires_legal_review = "requires_legal_review"
    potentially_high_risk = "potentially_high_risk"


class Category(str, Enum):
    """Topic of a finding. A record can carry more than one."""

    consistency = "consistency"
    scope = "scope"
    prohibited_practice = "prohibited_practice"
    high_risk = "high_risk"
    transparency = "transparency"
    general_purpose_model = "general_purpose_model"
    information_gap = "information_gap"


class LegalReference(BaseModel):
    """A provision in a specific imported act."""

    model_config = ConfigDict(extra="forbid")

    celex: str
    provision_key: str
    citation: str


class Finding(BaseModel):
    """One rule result, including the facts and provisions that produced it."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_version: str
    category: Category
    outcome: Outcome
    explanation: str
    conditions: list[str]
    facts: list[str]
    missing_facts: list[str] = Field(default_factory=list)
    legal_references: list[LegalReference]
    control_ids: list[str] = Field(default_factory=list)
    applicable_from: date | None = None
    application_reference: LegalReference | None = None
    application_reached: bool | None = None


class AssessmentResult(BaseModel):
    """The rule set version and every check from one evaluation."""

    model_config = ConfigDict(extra="forbid")

    notice: str
    rule_set_version: str
    celex: str
    content_sha256: str | None = None
    assessed_on: date | None = None
    status: AssessmentStatus
    categories: list[str]
    findings: list[Finding]
    checks: list[Finding]
    information_gaps: list[str]
    contradictions: list[str]
