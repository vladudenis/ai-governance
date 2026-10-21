"""Form values for the dashboard, kept separate from Streamlit widgets.

A yes or no answer is recorded as stated by the person using the form, and it
needs evidence. Unknown stays unknown and carries no evidence. The screening
result is decision support, not a compliance score.
"""

from dataclasses import dataclass

from ai_governance.assessment.facts import AnnexUse, OperatorRole, UseCase

STATUS_LABELS = {
    "requires_legal_review": "Requires legal review",
    "potentially_high_risk": "Potentially high-risk",
    "needs_further_information": "Needs further information",
    "no_indicated_prohibited_or_high_risk_practice": "No indicated prohibited or high-risk practice",
}

STATUS_NOTES = {
    "requires_legal_review": "A person needs to apply the statutory conditions. This is not a prohibition decision.",
    "potentially_high_risk": "The recorded use matches a high-risk route in the rule set. This is not a completed classification.",
    "needs_further_information": "The screening cannot be completed until the missing facts are answered.",
    "no_indicated_prohibited_or_high_risk_practice": "The answered facts do not match a prohibited practice or a high-risk route in this rule set.",
}

OUTCOME_LABELS = {
    "not_indicated": "Not indicated",
    "needs_further_information": "Needs further information",
    "requires_legal_review": "Requires legal review",
    "potentially_high_risk": "Potentially high-risk",
}

YES_NO_OPTIONS = (
    ("unknown", "Not yet answered"),
    ("yes", "Yes"),
    ("no", "No"),
)

ROLE_OPTIONS = (
    ("unknown", "Not yet answered"),
    ("provider", "Provider"),
    ("deployer", "Deployer"),
    ("provider_and_deployer", "Provider and deployer"),
    ("other", "Other"),
)

ANNEX_OPTIONS = (
    ("unknown", "Not yet answered"),
    ("none", "None of the listed Annex III uses"),
    ("remote_biometric_identification", "Remote biometric identification"),
    ("biometric_verification_only", "Biometric verification of one person only"),
    ("biometric_categorisation", "Biometric categorisation"),
    ("emotion_recognition", "Emotion recognition"),
    ("critical_infrastructure_safety", "Critical-infrastructure safety component"),
    ("education_access", "Education or training access"),
    ("education_evaluation", "Evaluating learning outcomes"),
    ("education_level", "Assessing level of education"),
    ("student_proctoring", "Monitoring students during tests"),
    ("recruitment", "Recruitment or candidate selection"),
    ("worker_management", "Worker management or monitoring"),
    ("public_benefits", "Essential public benefits"),
    ("credit_scoring", "Creditworthiness or credit score"),
    ("credit_fraud_detection_only", "Financial-fraud detection only"),
    ("insurance_pricing", "Life or health insurance pricing"),
    ("emergency_dispatch", "Emergency call dispatch"),
    ("law_enforcement", "Law enforcement"),
    ("migration_asylum_border", "Migration, asylum, or border control"),
    ("justice_assistance", "Assisting a judicial authority"),
    ("election_influence", "Influencing an election or referendum"),
)

YES_NO_FIELDS = (
    ("is_ai_system", "Is this an AI system?"),
    ("used_in_the_union", "Is the system or its output used in the Union?"),
    ("exclusively_military_defence_or_national_security", "Used exclusively for military, defence, or national security?"),
    ("solely_scientific_research", "Developed solely for scientific research?"),
    ("purely_personal_non_professional", "Used only in a personal, non-professional activity?"),
    ("subliminal_or_purposefully_manipulative", "Subliminal, purposefully manipulative, or deceptive techniques?"),
    ("exploits_vulnerabilities", "Exploits vulnerabilities due to age, disability, or social or economic situation?"),
    ("social_scoring", "Social scoring over time?"),
    ("criminal_risk_solely_from_profiling", "Predicts criminal offending solely from profiling?"),
    ("untargeted_facial_scraping", "Builds a facial-recognition database by untargeted scraping?"),
    ("emotion_inference_workplace_or_education", "Infers emotions in the workplace or in education?"),
    ("biometric_categorisation_of_sensitive_attributes", "Infers sensitive attributes from biometric data?"),
    ("realtime_remote_biometric_public_law_enforcement", "Real-time remote biometric identification in public for law enforcement?"),
    ("safety_component_of_annex_i_product", "Safety component of a product, or a product, covered by Annex I?"),
    ("third_party_conformity_required", "Does that product require a third-party conformity assessment?"),
    ("performs_profiling", "Does the system profile natural persons?"),
    ("article_6_3_derogation_claimed", "Is an Article 6(3) derogation claimed?"),
    ("interacts_directly_with_people", "Intended to interact directly with people?"),
    ("generates_synthetic_content", "Generates synthetic audio, image, video, or text?"),
    ("deepfake", "Generates or manipulates a deep fake?"),
    ("is_general_purpose_ai_model", "Is this a general-purpose AI model?"),
    ("systemic_risk_classified", "Classified as a general-purpose model with systemic risk?"),
)

IDENTITY_FIELDS = YES_NO_FIELDS[:2]
SCOPE_FIELDS = YES_NO_FIELDS[2:5]
PROHIBITED_FIELDS = YES_NO_FIELDS[5:13]
CLASSIFICATION_FIELDS = YES_NO_FIELDS[13:17]
TRANSPARENCY_FIELDS = YES_NO_FIELDS[17:]

FIELD_LABELS = {field_name: label for field_name, label in YES_NO_FIELDS}
FIELD_LABELS["operator_role"] = "Who operates it?"
FIELD_LABELS["annex_iii_use"] = "Annex III use"
FIELD_LABELS["intended_purpose"] = "Intended purpose"


def fact_label(field_name: str) -> str:
    """The question shown in the form for a stored field name."""
    return FIELD_LABELS.get(field_name, field_name.replace("_", " "))


NOTICE = (
    "Decision-support screening against Regulation (EU) 2024/1689. "
    "It is not a legal determination, a prohibition decision, or a compliance certificate."
)


@dataclass(frozen=True)
class DraftAnswer:
    """One form answer before it is validated."""

    value: str = "unknown"
    evidence: str = ""


def blank_answers() -> dict[str, DraftAnswer]:
    """Every screening question starts unanswered."""
    answers = {field_name: DraftAnswer() for field_name, _label in YES_NO_FIELDS}
    answers["operator_role"] = DraftAnswer()
    answers["annex_iii_use"] = DraftAnswer()
    return answers


def answers_from_use_case(use_case: dict) -> dict[str, DraftAnswer]:
    """Copy a stored snapshot into form answers."""
    answers = blank_answers()
    for field_name in answers:
        stored = use_case.get(field_name) or {}
        answers[field_name] = DraftAnswer(
            value=str(stored.get("value") or "unknown"),
            evidence=stored.get("evidence") or "",
        )
    return answers


def build_use_case(name: str, purpose: str, answers: dict[str, DraftAnswer]) -> tuple[dict | None, list[str]]:
    """Return an API payload, or the reasons the form cannot be saved."""
    errors: list[str] = []
    cleaned = name.strip()
    if not cleaned:
        errors.append("Enter a name for the system.")
    payload: dict[str, object] = {"name": cleaned or "pending"}
    payload["intended_purpose"] = _text_fact(purpose)
    payload["operator_role"] = _choice_fact("operator_role", answers, OperatorRole, errors)
    payload["annex_iii_use"] = _choice_fact("annex_iii_use", answers, AnnexUse, errors)
    for field_name, label in YES_NO_FIELDS:
        payload[field_name] = _yes_no_fact(label, answers.get(field_name, DraftAnswer()), errors)
    if errors:
        return None, errors
    UseCase.model_validate(payload)
    return payload, []


def status_label(status: str | None) -> str:
    """Human label for an assessment status. Missing means not screened."""
    if status is None:
        return "Not screened"
    return STATUS_LABELS.get(status, status)


def _text_fact(purpose: str) -> dict[str, str | None]:
    text = purpose.strip()
    if not text:
        return {"value": None, "basis": "unknown", "evidence": None}
    return {"value": text, "basis": "stated", "evidence": text}


def _yes_no_fact(label: str, answer: DraftAnswer, errors: list[str]) -> dict[str, str | None]:
    if answer.value == "unknown":
        return {"value": "unknown", "basis": "unknown", "evidence": None}
    evidence = answer.evidence.strip()
    if answer.value not in {"yes", "no"}:
        errors.append(f"{label} has an unsupported answer.")
        return {"value": "unknown", "basis": "unknown", "evidence": None}
    if not evidence:
        errors.append(f"Add evidence for “{label}”")
        return {"value": answer.value, "basis": "stated", "evidence": None}
    return {"value": answer.value, "basis": "stated", "evidence": evidence}


def _choice_fact(field_name: str, answers: dict[str, DraftAnswer], enum_type: type, errors: list[str]) -> dict[str, str | None]:
    answer = answers.get(field_name, DraftAnswer())
    allowed = {item.value for item in enum_type}
    if answer.value not in allowed:
        errors.append(f"{field_name} has an unsupported answer.")
        return {"value": "unknown", "basis": "unknown", "evidence": None}
    if answer.value == "unknown":
        return {"value": "unknown", "basis": "unknown", "evidence": None}
    evidence = answer.evidence.strip()
    if not evidence:
        errors.append(f"Add evidence for {field_name.replace('_', ' ')}.")
        return {"value": answer.value, "basis": "stated", "evidence": None}
    return {"value": answer.value, "basis": "stated", "evidence": evidence}
