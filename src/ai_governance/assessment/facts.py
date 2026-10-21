"""Validated facts about one AI use case.

Each answer is yes, no, or unknown. A yes or no must say whether it was stated
in the description or inferred, and it must carry evidence from that
description. Unknown means the fact was not established. The assessment engine
reads only this record. It does not read the free-text evidence as an
instruction.
"""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Basis(str, Enum):
    """How a recorded value was obtained."""

    stated = "stated"
    inferred = "inferred"
    unknown = "unknown"


class YesNo(str, Enum):
    """A closed answer the rules can test."""

    yes = "yes"
    no = "no"
    unknown = "unknown"


class AnnexUse(str, Enum):
    """Intended use, limited to the Annex III list this rule set screens.

    ``none`` means the description was screened and is not one of those uses.
    ``unknown`` means the use has not been established. Two values record
    exceptions written in Annex III rather than a listed high-risk use.
    """

    unknown = "unknown"
    none = "none"
    remote_biometric_identification = "remote_biometric_identification"
    biometric_verification_only = "biometric_verification_only"
    biometric_categorisation = "biometric_categorisation"
    emotion_recognition = "emotion_recognition"
    critical_infrastructure_safety = "critical_infrastructure_safety"
    education_access = "education_access"
    education_evaluation = "education_evaluation"
    education_level = "education_level"
    student_proctoring = "student_proctoring"
    recruitment = "recruitment"
    worker_management = "worker_management"
    public_benefits = "public_benefits"
    credit_scoring = "credit_scoring"
    credit_fraud_detection_only = "credit_fraud_detection_only"
    insurance_pricing = "insurance_pricing"
    emergency_dispatch = "emergency_dispatch"
    law_enforcement = "law_enforcement"
    migration_asylum_border = "migration_asylum_border"
    justice_assistance = "justice_assistance"
    election_influence = "election_influence"


class OperatorRole(str, Enum):
    """Role used to point at provider or deployer obligations."""

    unknown = "unknown"
    provider = "provider"
    deployer = "deployer"
    provider_and_deployer = "provider_and_deployer"
    other = "other"


def _check_evidence(*, unknown: bool, basis: Basis, evidence: str | None) -> None:
    if unknown:
        if basis is not Basis.unknown:
            raise ValueError("An unknown value cannot be stated or inferred.")
        if evidence not in (None, ""):
            raise ValueError("An unknown value cannot include evidence.")
        return
    if basis is Basis.unknown:
        raise ValueError("A recorded value needs a stated or inferred basis.")
    if evidence is None or not evidence.strip():
        raise ValueError("A recorded value needs evidence from the description.")


class Answer(BaseModel):
    """Yes, no, or unknown, with the basis and the supporting words."""

    model_config = ConfigDict(extra="forbid")

    value: YesNo = YesNo.unknown
    basis: Basis = Basis.unknown
    evidence: str | None = None

    @model_validator(mode="after")
    def evidence_matches_the_value(self) -> "Answer":
        _check_evidence(unknown=self.value is YesNo.unknown, basis=self.basis, evidence=self.evidence)
        return self


class TextFact(BaseModel):
    """A short text fact. Empty means it has not been established."""

    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    basis: Basis = Basis.unknown
    evidence: str | None = None

    @model_validator(mode="after")
    def evidence_matches_the_value(self) -> "TextFact":
        unknown = self.value is None or not self.value.strip()
        _check_evidence(unknown=unknown, basis=self.basis, evidence=self.evidence)
        return self


class AnnexAnswer(BaseModel):
    """The intended Annex III use, or an explicit none or unknown."""

    model_config = ConfigDict(extra="forbid")

    value: AnnexUse = AnnexUse.unknown
    basis: Basis = Basis.unknown
    evidence: str | None = None

    @model_validator(mode="after")
    def evidence_matches_the_value(self) -> "AnnexAnswer":
        _check_evidence(
            unknown=self.value is AnnexUse.unknown,
            basis=self.basis,
            evidence=self.evidence,
        )
        return self


class RoleAnswer(BaseModel):
    """Who operates the system, where that has been established."""

    model_config = ConfigDict(extra="forbid")

    value: OperatorRole = OperatorRole.unknown
    basis: Basis = Basis.unknown
    evidence: str | None = None

    @model_validator(mode="after")
    def evidence_matches_the_value(self) -> "RoleAnswer":
        _check_evidence(
            unknown=self.value is OperatorRole.unknown,
            basis=self.basis,
            evidence=self.evidence,
        )
        return self


class UseCase(BaseModel):
    """Facts the rules are allowed to use.

    Fields default to unknown. A cleared screening sets each relevant field
    to yes or no with evidence. Extra fields are rejected so a caller cannot
    smuggle a conclusion in under another name.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    intended_purpose: TextFact = Field(default_factory=TextFact)
    operator_role: RoleAnswer = Field(default_factory=RoleAnswer)
    is_ai_system: Answer = Field(default_factory=Answer)
    used_in_the_union: Answer = Field(default_factory=Answer)
    exclusively_military_defence_or_national_security: Answer = Field(default_factory=Answer)
    solely_scientific_research: Answer = Field(default_factory=Answer)
    purely_personal_non_professional: Answer = Field(default_factory=Answer)
    subliminal_or_purposefully_manipulative: Answer = Field(default_factory=Answer)
    exploits_vulnerabilities: Answer = Field(default_factory=Answer)
    social_scoring: Answer = Field(default_factory=Answer)
    criminal_risk_solely_from_profiling: Answer = Field(default_factory=Answer)
    untargeted_facial_scraping: Answer = Field(default_factory=Answer)
    emotion_inference_workplace_or_education: Answer = Field(default_factory=Answer)
    biometric_categorisation_of_sensitive_attributes: Answer = Field(default_factory=Answer)
    realtime_remote_biometric_public_law_enforcement: Answer = Field(default_factory=Answer)
    annex_iii_use: AnnexAnswer = Field(default_factory=AnnexAnswer)
    safety_component_of_annex_i_product: Answer = Field(default_factory=Answer)
    third_party_conformity_required: Answer = Field(default_factory=Answer)
    performs_profiling: Answer = Field(default_factory=Answer)
    article_6_3_derogation_claimed: Answer = Field(default_factory=Answer)
    interacts_directly_with_people: Answer = Field(default_factory=Answer)
    generates_synthetic_content: Answer = Field(default_factory=Answer)
    deepfake: Answer = Field(default_factory=Answer)
    is_general_purpose_ai_model: Answer = Field(default_factory=Answer)
    systemic_risk_classified: Answer = Field(default_factory=Answer)
