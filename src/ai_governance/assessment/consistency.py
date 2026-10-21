"""Facts that cannot be true together.

These checks are about the record, not about whether a legal test is met.
A recruitment use recorded as "not an AI system" is a contradiction. A claimed
Article 6(3) derogation for a system that also profiles is a legal condition,
and the engine handles that in the high-risk rule rather than here.
"""

from ai_governance.assessment.facts import AnnexUse, UseCase, YesNo

_PRACTICE_FIELDS = (
    "subliminal_or_purposefully_manipulative",
    "exploits_vulnerabilities",
    "social_scoring",
    "criminal_risk_solely_from_profiling",
    "untargeted_facial_scraping",
    "emotion_inference_workplace_or_education",
    "biometric_categorisation_of_sensitive_attributes",
    "realtime_remote_biometric_public_law_enforcement",
    "safety_component_of_annex_i_product",
    "interacts_directly_with_people",
    "generates_synthetic_content",
    "deepfake",
    "is_general_purpose_ai_model",
)


def find_contradictions(use_case: UseCase) -> list[str]:
    """Return human-readable contradictions. An empty list means the record is usable."""
    messages: list[str] = []
    if use_case.is_ai_system.value is YesNo.no:
        if use_case.annex_iii_use.value not in {AnnexUse.none, AnnexUse.unknown}:
            messages.append(
                "The record says this is not an AI system and also records an Annex III use."
            )
        for field_name in _PRACTICE_FIELDS:
            answer = getattr(use_case, field_name)
            if answer.value is YesNo.yes:
                messages.append(
                    f"The record says this is not an AI system and also records {field_name} as yes."
                )
    if (
        use_case.article_6_3_derogation_claimed.value is YesNo.yes
        and use_case.annex_iii_use.value is AnnexUse.none
    ):
        messages.append(
            "An Article 6(3) derogation is claimed, but the recorded use is not an Annex III use."
        )
    return messages
