"""Request and response models for the first API."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from ai_governance.assessment.facts import UseCase
from ai_governance.assessment.results import Finding


class AISystemSummary(BaseModel):
    """A system as it appears in a list."""

    model_config = ConfigDict(extra="forbid")

    id: int
    name: str
    version_number: int
    created_at: datetime
    updated_at: datetime
    latest_assessment_status: str | None
    reassessment_required: bool = False
    reassessment_reasons: list[str] = Field(default_factory=list)


class AISystemDetail(AISystemSummary):
    """A system plus the facts of its current snapshot."""

    use_case: UseCase


class AssessmentCreate(BaseModel):
    """Options for one screening run. The facts come from the current snapshot."""

    model_config = ConfigDict(extra="forbid")

    assessed_on: date | None = None


class AssessmentSummary(BaseModel):
    """An assessment without its findings."""

    model_config = ConfigDict(extra="forbid")

    id: int
    ai_system_id: int
    use_case_record_id: int
    use_case_version: int
    rule_set_version: str
    status: str
    celex: str
    content_sha256: str | None
    assessed_on: date | None
    created_at: datetime


class AssessmentDetail(AssessmentSummary):
    """The stored engine result, including the snapshot it used."""

    notice: str
    categories: list[str]
    information_gaps: list[str]
    contradictions: list[str]
    use_case: UseCase
    findings: list[Finding]
    checks: list[Finding]


class ProvisionSummary(BaseModel):
    """A legal provision without its full wording."""

    model_config = ConfigDict(extra="forbid")

    id: int
    celex: str
    content_sha256: str
    provision_key: str
    citation: str
    kind: str
    heading: str | None


class ProvisionDetail(ProvisionSummary):
    """A legal provision and the wording stored for the current version."""

    text: str
    source_file: str


class ProvisionList(BaseModel):
    """One page of provisions from the current version of an act."""

    model_config = ConfigDict(extra="forbid")

    items: list[ProvisionSummary]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
