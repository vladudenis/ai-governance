"""Evaluate a validated use case against the versioned AI Act rules.

The same record always produces the same result. Text in the evidence fields
is stored for a reviewer and is not interpreted.
"""

from datetime import date

from ai_governance.assessment.catalog import (
    ANNEX_BY_USE,
    ARTICLE_113,
    ARTICLE_113_A,
    ARTICLE_113_B,
    ARTICLE_113_C,
    ARTICLE_3_3,
    ARTICLE_3_4,
    ARTICLE_3_12,
    ARTICLE_50_3,
    ARTICLE_6_1_A,
    ARTICLE_6_1_B,
    ARTICLE_6_1_APPLICATION,
    ARTICLE_6_2,
    ARTICLE_6_3,
    ARTICLE_6_3_PROFILING,
    CELEX,
    GENERAL_APPLICATION,
    GPAI_APPLICATION,
    NOTICE,
    PROHIBITED,
    RULE_SET_VERSION,
    RULE_VERSION,
    SCOPE_EXCLUSIONS,
    TRANSPARENCY,
    AnnexRule,
    Indicator,
)
from ai_governance.assessment.consistency import find_contradictions
from ai_governance.assessment.facts import AnnexUse, Answer, Basis, UseCase, YesNo
from ai_governance.assessment.results import (
    AssessmentResult,
    AssessmentStatus,
    Category,
    Finding,
    Outcome,
)


def assess(
    use_case: UseCase,
    *,
    content_sha256: str | None = None,
    assessed_on: date | None = None,
) -> AssessmentResult:
    """Screen ``use_case`` and record the rule-set version on the result."""
    contradictions = find_contradictions(use_case)
    if contradictions:
        finding = _finding(
            rule_id="R-CONSISTENCY",
            category=Category.consistency,
            outcome=Outcome.requires_legal_review,
            explanation=(
                "The record contains facts that cannot be used together, so the other rules "
                "were not applied. Correct the record before screening it."
            ),
            conditions=("Contradictory facts are absent.",),
            facts=contradictions,
            references=[],
            control_ids=["CTRL-SCOPE"],
            applicable_from=None,
            application_reference=None,
            assessed_on=assessed_on,
        )
        return _result(
            use_case_sha=content_sha256,
            assessed_on=assessed_on,
            findings=[finding],
            checks=[],
            contradictions=contradictions,
        )

    if use_case.is_ai_system.value is YesNo.no:
        check = _finding(
            rule_id="R-SCOPE-NOT-AI",
            category=Category.scope,
            outcome=Outcome.not_indicated,
            explanation=(
                "The record says this is not an AI system within Article 3(1). The prohibited-practice, "
                "high-risk, transparency, and general-purpose rules were not applied. A reviewer should "
                "confirm that characterisation."
            ),
            conditions=("is_ai_system is no.",),
            facts=[_fact("is_ai_system", use_case.is_ai_system)],
            references=[_ref("article/3/point/1", "Article 3(1)")],
            control_ids=["CTRL-SCOPE"],
            applicable_from=date(2025, 2, 2),
            application_reference=ARTICLE_113_A.as_model(),
            assessed_on=assessed_on,
        )
        return _result(
            use_case_sha=content_sha256,
            assessed_on=assessed_on,
            findings=[],
            checks=[check],
            contradictions=[],
        )

    findings: list[Finding] = []
    checks: list[Finding] = []
    _split_indicators(use_case, PROHIBITED, findings, checks, assessed_on, screening_id="R-ART5-SCREENING")
    _split_indicators(
        use_case,
        TRANSPARENCY,
        findings,
        checks,
        assessed_on,
        screening_id="R-ART50-SCREENING",
    )
    _split_indicators(
        use_case,
        SCOPE_EXCLUSIONS,
        findings,
        checks,
        assessed_on,
        screening_id="R-SCOPE-SCREENING",
    )
    _append_union_nexus(use_case, findings, checks, assessed_on)
    _append_purpose_and_role(use_case, findings, assessed_on)
    _append_annex(use_case, findings, checks, assessed_on)
    _append_article_6_1(use_case, findings, checks, assessed_on)
    _append_article_50_3(use_case, findings, checks, assessed_on)
    _append_gpai(use_case, findings, checks, assessed_on)
    return _result(
        use_case_sha=content_sha256,
        assessed_on=assessed_on,
        findings=findings,
        checks=checks,
        contradictions=[],
    )


def _split_indicators(
    use_case: UseCase,
    indicators: tuple[Indicator, ...],
    findings: list[Finding],
    checks: list[Finding],
    assessed_on: date | None,
    screening_id: str,
) -> None:
    unknown: list[Indicator] = []
    for indicator in indicators:
        answer = getattr(use_case, indicator.field)
        if answer.value is YesNo.unknown:
            unknown.append(indicator)
            continue
        outcome = Outcome.not_indicated
        explanation = f"The record answers {indicator.field} as no, so this rule is not indicated."
        if answer.value is YesNo.yes:
            outcome = _stated_outcome(indicator.positive_outcome, answer)
            explanation = indicator.explanation
            if answer.basis is Basis.inferred:
                explanation += " The triggering answer was inferred, so it is not treated as an established fact."
        item = _from_indicator(indicator, outcome, explanation, [_fact(indicator.field, answer)], [], assessed_on)
        if outcome is Outcome.not_indicated:
            checks.append(item)
        else:
            findings.append(item)
    if unknown:
        findings.append(_unknown_group(screening_id, unknown, assessed_on))


def _append_union_nexus(
    use_case: UseCase,
    findings: list[Finding],
    checks: list[Finding],
    assessed_on: date | None,
) -> None:
    answer = use_case.used_in_the_union
    if answer.value is YesNo.unknown:
        findings.append(
            _gap(
                "R-SCOPE-UNION",
                "used_in_the_union",
                "It is not established whether the system is placed on the Union market, put into service in the Union, or has output used in the Union.",
                [_ref("article/2/paragraph/1", "Article 2(1)")],
                assessed_on,
                date(2025, 2, 2),
                _ref("article/113/point/a", "Article 113(a)"),
            )
        )
        return
    if answer.value is YesNo.no:
        findings.append(
            _finding(
                rule_id="R-SCOPE-UNION",
                category=Category.scope,
                outcome=_stated_outcome(Outcome.requires_legal_review, answer),
                explanation=(
                    "The record says the system and its output are not used in the Union. Article 2(1) "
                    "defines several ways the Regulation reaches providers, deployers, and output used in "
                    "the Union. That characterisation needs legal review before the Act is treated as inapplicable."
                ),
                conditions=("used_in_the_union is no.",),
                facts=[_fact("used_in_the_union", answer)],
                references=[_ref("article/2/paragraph/1", "Article 2(1)")],
                control_ids=["CTRL-SCOPE"],
                applicable_from=date(2025, 2, 2),
                application_reference=ARTICLE_113_A.as_model(),
                assessed_on=assessed_on,
            )
        )
        return
    checks.append(
        _finding(
            rule_id="R-SCOPE-UNION",
            category=Category.scope,
            outcome=Outcome.not_indicated,
            explanation="The record says the system or its output is used in the Union, so an Article 2(1) exclusion is not indicated.",
            conditions=("used_in_the_union is yes.",),
            facts=[_fact("used_in_the_union", answer)],
            references=[_ref("article/2/paragraph/1", "Article 2(1)")],
            control_ids=["CTRL-SCOPE"],
            applicable_from=date(2025, 2, 2),
            application_reference=ARTICLE_113_A.as_model(),
            assessed_on=assessed_on,
        )
    )


def _append_purpose_and_role(use_case: UseCase, findings: list[Finding], assessed_on: date | None) -> None:
    purpose = use_case.intended_purpose
    if purpose.value is None or not purpose.value.strip():
        findings.append(
            _gap(
                "R-PURPOSE",
                "intended_purpose",
                "The intended purpose is missing. Article 6 classification depends on the use the system is intended for.",
                [ARTICLE_3_12.as_model()],
                assessed_on,
                date(2025, 2, 2),
                ARTICLE_113_A.as_model(),
            )
        )
    if use_case.operator_role.value.value == "unknown":
        findings.append(
            _gap(
                "R-ROLE",
                "operator_role",
                "The provider or deployer role is missing. Several duties differ between those roles.",
                [ARTICLE_3_3.as_model(), ARTICLE_3_4.as_model()],
                assessed_on,
                date(2025, 2, 2),
                ARTICLE_113_A.as_model(),
            )
        )


def _append_annex(
    use_case: UseCase,
    findings: list[Finding],
    checks: list[Finding],
    assessed_on: date | None,
) -> None:
    recorded = use_case.annex_iii_use
    if recorded.value is AnnexUse.unknown:
        findings.append(
            _gap(
                "R-ANNEX-III",
                "annex_iii_use",
                "The intended use has not been matched to Annex III, so the engine cannot say that no listed high-risk use is indicated.",
                [_ref("annex/III", "Annex III"), ARTICLE_6_2.as_model()],
                assessed_on,
                GENERAL_APPLICATION,
                ARTICLE_113.as_model(),
            )
        )
        return
    if recorded.value is AnnexUse.none:
        checks.append(
            _finding(
                rule_id="R-ANNEX-III",
                category=Category.high_risk,
                outcome=Outcome.not_indicated,
                explanation=(
                    "The recorded use is not an Annex III use in this rule set. Using AI does not by itself "
                    "indicate a high-risk system under Article 6(2)."
                ),
                conditions=("annex_iii_use is none.",),
                facts=[_annex_fact(use_case)],
                references=[_ref("annex/III", "Annex III"), ARTICLE_6_2.as_model()],
                control_ids=["CTRL-ART6-CLASSIFICATION"],
                applicable_from=GENERAL_APPLICATION,
                application_reference=ARTICLE_113.as_model(),
                assessed_on=assessed_on,
            )
        )
        return

    rule = ANNEX_BY_USE[recorded.value]
    if not rule.listed:
        checks.append(_annex_check(rule, use_case, assessed_on))
        return

    outcome = Outcome.requires_legal_review if rule.permission_qualified else Outcome.potentially_high_risk
    explanation = rule.explanation + " " + _derogation_sentence(use_case)
    missing: list[str] = []
    if use_case.performs_profiling.value is YesNo.unknown:
        missing.append("performs_profiling")
    if use_case.article_6_3_derogation_claimed.value is YesNo.unknown:
        missing.append("article_6_3_derogation_claimed")
    if use_case.article_6_3_derogation_claimed.value is YesNo.yes and use_case.performs_profiling.value is YesNo.no:
        outcome = Outcome.requires_legal_review
    outcome = _stated_outcome(outcome, recorded)
    if recorded.basis is Basis.inferred and "inferred" not in explanation:
        explanation += " The Annex III use was inferred, so it is not treated as an established fact."
    findings.append(
        _finding(
            rule_id=rule.rule_id,
            category=Category.high_risk,
            outcome=outcome,
            explanation=explanation,
            conditions=(
                f"annex_iii_use is {recorded.value.value}.",
                "Article 6(2) classifies Annex III systems as high-risk unless Article 6(3) applies.",
                "Article 6(3) does not remove that classification where the system profiles natural persons.",
            ),
            facts=[_annex_fact(use_case), _fact("performs_profiling", use_case.performs_profiling), _fact("article_6_3_derogation_claimed", use_case.article_6_3_derogation_claimed)],
            missing_facts=missing,
            references=_annex_references(rule, use_case),
            control_ids=_annex_controls(use_case),
            applicable_from=GENERAL_APPLICATION,
            application_reference=ARTICLE_113.as_model(),
            assessed_on=assessed_on,
        )
    )


def _append_article_6_1(
    use_case: UseCase,
    findings: list[Finding],
    checks: list[Finding],
    assessed_on: date | None,
) -> None:
    safety = use_case.safety_component_of_annex_i_product
    conformity = use_case.third_party_conformity_required
    facts = [_fact("safety_component_of_annex_i_product", safety), _fact("third_party_conformity_required", conformity)]
    references = [ARTICLE_6_1_A.as_model(), ARTICLE_6_1_B.as_model(), _ref("annex/I", "Annex I")]
    if safety.value is YesNo.no:
        checks.append(
            _finding(
                rule_id="R-ART6-1",
                category=Category.high_risk,
                outcome=Outcome.not_indicated,
                explanation="Article 6(1) needs both a safety-component or product condition and a third-party conformity assessment. The first condition is recorded as no.",
                conditions=("safety_component_of_annex_i_product is no.",),
                facts=facts,
                references=references,
                control_ids=["CTRL-ART6-CLASSIFICATION"],
                applicable_from=ARTICLE_6_1_APPLICATION,
                application_reference=ARTICLE_113_C.as_model(),
                assessed_on=assessed_on,
            )
        )
        return
    if safety.value is YesNo.unknown or conformity.value is YesNo.unknown:
        missing = []
        if safety.value is YesNo.unknown:
            missing.append("safety_component_of_annex_i_product")
        if conformity.value is YesNo.unknown:
            missing.append("third_party_conformity_required")
        findings.append(
            _finding(
                rule_id="R-ART6-1",
                category=Category.information_gap,
                outcome=Outcome.needs_further_information,
                explanation="Article 6(1) classifies a system as high-risk only where both of its conditions are met. At least one condition is unanswered, so this route is not indicated and is not ruled out.",
                conditions=("Both Article 6(1) conditions are answered.",),
                facts=facts,
                missing_facts=missing,
                references=references,
                control_ids=["CTRL-ART6-CLASSIFICATION"],
                applicable_from=ARTICLE_6_1_APPLICATION,
                application_reference=ARTICLE_113_C.as_model(),
                assessed_on=assessed_on,
            )
        )
        return
    if conformity.value is YesNo.no:
        checks.append(
            _finding(
                rule_id="R-ART6-1",
                category=Category.high_risk,
                outcome=Outcome.not_indicated,
                explanation="The safety-component condition is recorded as yes, and the third-party conformity condition is recorded as no. Article 6(1) requires both.",
                conditions=("third_party_conformity_required is no.",),
                facts=facts,
                references=references,
                control_ids=["CTRL-ART6-CLASSIFICATION"],
                applicable_from=ARTICLE_6_1_APPLICATION,
                application_reference=ARTICLE_113_C.as_model(),
                assessed_on=assessed_on,
            )
        )
        return
    outcome = Outcome.potentially_high_risk
    if safety.basis is Basis.inferred or conformity.basis is Basis.inferred:
        outcome = Outcome.requires_legal_review
    findings.append(
        _finding(
            rule_id="R-ART6-1",
            category=Category.high_risk,
            outcome=outcome,
            explanation=(
                "Both Article 6(1) conditions are recorded as yes: the system is an Annex I product or its "
                "safety component, and that product requires a third-party conformity assessment. This is a "
                "potential high-risk classification, not a completed conformity assessment. Article 6(1) applies from 2 August 2027."
                + (
                    " At least one triggering answer was inferred, so it is not treated as an established fact."
                    if safety.basis is Basis.inferred or conformity.basis is Basis.inferred
                    else ""
                )
            ),
            conditions=("safety_component_of_annex_i_product is yes.", "third_party_conformity_required is yes."),
            facts=facts,
            references=references,
            control_ids=["CTRL-ART6-CLASSIFICATION", "CTRL-HIGH-RISK-OBLIGATIONS"],
            applicable_from=ARTICLE_6_1_APPLICATION,
            application_reference=ARTICLE_113_C.as_model(),
            assessed_on=assessed_on,
        )
    )


def _append_article_50_3(
    use_case: UseCase,
    findings: list[Finding],
    checks: list[Finding],
    assessed_on: date | None,
) -> None:
    emotion = use_case.emotion_inference_workplace_or_education.value is YesNo.yes
    sensitive = use_case.biometric_categorisation_of_sensitive_attributes.value is YesNo.yes
    annex_match = use_case.annex_iii_use.value in {AnnexUse.emotion_recognition, AnnexUse.biometric_categorisation}
    if emotion or sensitive or annex_match:
        findings.append(
            _finding(
                rule_id="R-ART50-3",
                category=Category.transparency,
                outcome=Outcome.requires_legal_review,
                explanation=(
                    "Article 50(3) tells deployers of an emotion-recognition system or a biometric "
                    "categorisation system to inform the people exposed to it. The recorded facts match "
                    "that subject. The engine does not decide who the deployer is or whether an exception applies."
                ),
                conditions=("An emotion-recognition or biometric-categorisation use is recorded as yes.",),
                facts=[
                    _fact("emotion_inference_workplace_or_education", use_case.emotion_inference_workplace_or_education),
                    _fact("biometric_categorisation_of_sensitive_attributes", use_case.biometric_categorisation_of_sensitive_attributes),
                    _annex_fact(use_case),
                ],
                references=[ARTICLE_50_3.as_model()],
                control_ids=["CTRL-TRANSPARENCY"],
                applicable_from=GENERAL_APPLICATION,
                application_reference=ARTICLE_113.as_model(),
                assessed_on=assessed_on,
            )
        )
        return
    relevant_unknown = (
        use_case.emotion_inference_workplace_or_education.value is YesNo.unknown
        or use_case.biometric_categorisation_of_sensitive_attributes.value is YesNo.unknown
        or use_case.annex_iii_use.value is AnnexUse.unknown
    )
    if relevant_unknown:
        return
    checks.append(
        _finding(
            rule_id="R-ART50-3",
            category=Category.transparency,
            outcome=Outcome.not_indicated,
            explanation="The record does not describe an emotion-recognition or biometric-categorisation system, so Article 50(3) is not indicated.",
            conditions=("Emotion recognition and biometric categorisation are no.",),
            facts=[_annex_fact(use_case)],
            references=[ARTICLE_50_3.as_model()],
            control_ids=["CTRL-TRANSPARENCY"],
            applicable_from=GENERAL_APPLICATION,
            application_reference=ARTICLE_113.as_model(),
            assessed_on=assessed_on,
        )
    )


def _append_gpai(
    use_case: UseCase,
    findings: list[Finding],
    checks: list[Finding],
    assessed_on: date | None,
) -> None:
    model = use_case.is_general_purpose_ai_model
    systemic = use_case.systemic_risk_classified
    if model.value is YesNo.unknown:
        findings.append(
            _gap(
                "R-GPAI",
                "is_general_purpose_ai_model",
                "It is not established whether this is a general-purpose AI model. Articles 51 and 53 cannot be screened without that fact.",
                [_ref("article/51", "Article 51"), _ref("article/53", "Article 53")],
                assessed_on,
                GPAI_APPLICATION,
                ARTICLE_113_B.as_model(),
            )
        )
        return
    if model.value is YesNo.no:
        checks.append(
            _finding(
                rule_id="R-GPAI",
                category=Category.general_purpose_model,
                outcome=Outcome.not_indicated,
                explanation="The record says this is not a general-purpose AI model, so Articles 51, 53, and 55 are not indicated.",
                conditions=("is_general_purpose_ai_model is no.",),
                facts=[_fact("is_general_purpose_ai_model", model)],
                references=[_ref("article/53", "Article 53")],
                control_ids=["CTRL-GPAI"],
                applicable_from=GPAI_APPLICATION,
                application_reference=ARTICLE_113_B.as_model(),
                assessed_on=assessed_on,
            )
        )
        return
    missing = ["systemic_risk_classified"] if systemic.value is YesNo.unknown else []
    references = [_ref("article/53", "Article 53")]
    if systemic.value is YesNo.yes:
        references.extend([_ref("article/51", "Article 51"), _ref("article/55", "Article 55")])
    explanation = (
        "The record says this is a general-purpose AI model. Article 53 duties may apply to its provider. "
        "Article 51 is the classification rule for systemic risk, and Article 55 adds duties where that classification applies."
    )
    if systemic.value is YesNo.unknown:
        explanation += " Whether the model has systemic risk is unanswered."
    findings.append(
        _finding(
            rule_id="R-GPAI",
            category=Category.general_purpose_model,
            outcome=_stated_outcome(Outcome.requires_legal_review, model),
            explanation=explanation,
            conditions=("is_general_purpose_ai_model is yes.",),
            facts=[_fact("is_general_purpose_ai_model", model), _fact("systemic_risk_classified", systemic)],
            missing_facts=missing,
            references=references,
            control_ids=["CTRL-GPAI"],
            applicable_from=GPAI_APPLICATION,
            application_reference=ARTICLE_113_B.as_model(),
            assessed_on=assessed_on,
        )
    )


def _derogation_sentence(use_case: UseCase) -> str:
    claimed = use_case.article_6_3_derogation_claimed.value
    profiling = use_case.performs_profiling.value
    if claimed is YesNo.yes and profiling is YesNo.yes:
        return (
            "A derogation under Article 6(3) is claimed, and profiling of natural persons is also recorded. "
            "The last subparagraph of Article 6(3) says an Annex III system that profiles natural persons "
            "shall always be considered high-risk, so the derogation is not available on these facts."
        )
    if claimed is YesNo.yes and profiling is YesNo.no:
        return (
            "A derogation under Article 6(3) is claimed, and profiling is recorded as no. The derogation "
            "also requires that the system does not pose a significant risk of harm and that one of the "
            "conditions in Article 6(3) is met. Article 6(4) requires the provider to document that "
            "assessment. This engine does not accept the derogation."
        )
    if claimed is YesNo.yes:
        return "A derogation under Article 6(3) is claimed, but profiling has not been answered. Article 6(3) excludes the derogation where the system profiles natural persons."
    if claimed is YesNo.no:
        return "No Article 6(3) derogation is claimed."
    return "It is not recorded whether the provider claims an Article 6(3) derogation."


def _annex_references(rule: AnnexRule, use_case: UseCase) -> list:
    references = [rule.ref.as_model(), ARTICLE_6_2.as_model(), ARTICLE_6_3.as_model()]
    if use_case.performs_profiling.value is YesNo.yes or use_case.article_6_3_derogation_claimed.value is YesNo.yes:
        references.append(ARTICLE_6_3_PROFILING.as_model())
    if use_case.article_6_3_derogation_claimed.value is YesNo.yes:
        references.append(_ref("article/6/paragraph/4", "Article 6(4)"))
    return references


def _annex_controls(use_case: UseCase) -> list[str]:
    controls = ["CTRL-ART6-CLASSIFICATION", "CTRL-HIGH-RISK-OBLIGATIONS"]
    if use_case.article_6_3_derogation_claimed.value is YesNo.yes:
        controls.append("CTRL-ART6-DEROGATION-RECORD")
    return controls


def _annex_check(rule: AnnexRule, use_case: UseCase, assessed_on: date | None) -> Finding:
    return _finding(
        rule_id=rule.rule_id,
        category=Category.high_risk,
        outcome=Outcome.not_indicated,
        explanation=rule.explanation,
        conditions=(f"annex_iii_use is {rule.use.value}.",),
        facts=[_annex_fact(use_case)],
        references=[rule.ref.as_model()],
        control_ids=["CTRL-ART6-CLASSIFICATION"],
        applicable_from=GENERAL_APPLICATION,
        application_reference=ARTICLE_113.as_model(),
        assessed_on=assessed_on,
    )


def _unknown_group(rule_id: str, indicators: list[Indicator], assessed_on: date | None) -> Finding:
    first = indicators[0]
    return _finding(
        rule_id=rule_id,
        category=Category.information_gap,
        outcome=Outcome.needs_further_information,
        explanation=(
            "These questions are unanswered, so the engine cannot treat the corresponding "
            "practices as absent."
        ),
        conditions=tuple(indicator.conditions[0].replace(" is yes.", " is answered.") for indicator in indicators),
        facts=[],
        missing_facts=[indicator.field for indicator in indicators],
        references=[indicator.ref.as_model() for indicator in indicators],
        control_ids=list(dict.fromkeys(control_id for indicator in indicators for control_id in indicator.control_ids)),
        applicable_from=first.applicable_from,
        application_reference=first.application_reference.as_model(),
        assessed_on=assessed_on,
    )


def _gap(
    rule_id: str,
    field_name: str,
    explanation: str,
    references: list,
    assessed_on: date | None,
    applicable_from: date,
    application_reference,
) -> Finding:
    return _finding(
        rule_id=rule_id,
        category=Category.information_gap,
        outcome=Outcome.needs_further_information,
        explanation=explanation,
        conditions=(f"{field_name} is answered.",),
        facts=[],
        missing_facts=[field_name],
        references=references,
        control_ids=["CTRL-SCOPE"],
        applicable_from=applicable_from,
        application_reference=application_reference,
        assessed_on=assessed_on,
    )


def _from_indicator(
    indicator: Indicator,
    outcome: Outcome,
    explanation: str,
    facts: list[str],
    missing: list[str],
    assessed_on: date | None,
) -> Finding:
    return _finding(
        rule_id=indicator.rule_id,
        category=indicator.category,
        outcome=outcome,
        explanation=explanation,
        conditions=indicator.conditions,
        facts=facts,
        missing_facts=missing,
        references=[indicator.ref.as_model()],
        control_ids=list(indicator.control_ids),
        applicable_from=indicator.applicable_from,
        application_reference=indicator.application_reference.as_model(),
        assessed_on=assessed_on,
    )


def _finding(
    *,
    rule_id: str,
    category: Category,
    outcome: Outcome,
    explanation: str,
    conditions: tuple[str, ...] | list[str],
    facts: list[str],
    references: list,
    control_ids: list[str],
    applicable_from: date | None,
    application_reference,
    assessed_on: date | None,
    missing_facts: list[str] | None = None,
) -> Finding:
    reached = None
    if assessed_on is not None and applicable_from is not None:
        reached = assessed_on >= applicable_from
    return Finding(
        rule_id=rule_id,
        rule_version=RULE_VERSION,
        category=category,
        outcome=outcome,
        explanation=explanation,
        conditions=list(conditions),
        facts=facts,
        missing_facts=missing_facts or [],
        legal_references=list(references),
        control_ids=control_ids,
        applicable_from=applicable_from,
        application_reference=application_reference,
        application_reached=reached,
    )


def _result(
    *,
    use_case_sha: str | None,
    assessed_on: date | None,
    findings: list[Finding],
    checks: list[Finding],
    contradictions: list[str],
) -> AssessmentResult:
    ordered_findings = sorted(findings, key=lambda item: item.rule_id)
    ordered_checks = sorted(checks, key=lambda item: item.rule_id)
    gaps: list[str] = []
    for finding in ordered_findings:
        for field_name in finding.missing_facts:
            if field_name not in gaps:
                gaps.append(field_name)
    categories = sorted({finding.category.value for finding in ordered_findings})
    return AssessmentResult(
        notice=NOTICE,
        rule_set_version=RULE_SET_VERSION,
        celex=CELEX,
        content_sha256=use_case_sha,
        assessed_on=assessed_on,
        status=_status(ordered_findings, contradictions),
        categories=categories,
        findings=ordered_findings,
        checks=ordered_checks,
        information_gaps=gaps,
        contradictions=contradictions,
    )


def _status(findings: list[Finding], contradictions: list[str]) -> AssessmentStatus:
    if contradictions or any(finding.outcome is Outcome.requires_legal_review for finding in findings):
        return AssessmentStatus.requires_legal_review
    if any(finding.outcome is Outcome.potentially_high_risk for finding in findings):
        return AssessmentStatus.potentially_high_risk
    if any(finding.outcome is Outcome.needs_further_information for finding in findings):
        return AssessmentStatus.needs_further_information
    return AssessmentStatus.no_indicated_prohibited_or_high_risk_practice


def _stated_outcome(outcome: Outcome, answer: Answer | object) -> Outcome:
    basis = getattr(answer, "basis", None)
    if basis is Basis.inferred and outcome is not Outcome.not_indicated:
        return Outcome.requires_legal_review
    return outcome


def _fact(field_name: str, answer: Answer) -> str:
    return f"{field_name}={answer.value.value} ({answer.basis.value})"


def _annex_fact(use_case: UseCase) -> str:
    recorded = use_case.annex_iii_use
    return f"annex_iii_use={recorded.value.value} ({recorded.basis.value})"


def _ref(provision_key: str, citation: str):
    from ai_governance.assessment.results import LegalReference

    return LegalReference(celex=CELEX, provision_key=provision_key, citation=citation)
