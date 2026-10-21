"""Versioned screening rules and the controls they point at.

Conditions, explanations, and legal references live here so a test can check
every reference against the imported AI Act. Changing a rule's meaning requires
a new ``RULE_SET_VERSION``. The engine copies that version onto each result.
"""

from dataclasses import dataclass
from datetime import date

from ai_governance.assessment.facts import AnnexUse
from ai_governance.assessment.results import Category, LegalReference, Outcome

RULE_SET_VERSION = "1"
RULE_VERSION = "1"
CELEX = "32024R1689"

NOTICE = (
    "Decision-support screening against Regulation (EU) 2024/1689. "
    "It is not a legal determination, a prohibition decision, or a compliance certificate."
)

CHAPTER_I_AND_II = date(2025, 2, 2)
GPAI_APPLICATION = date(2025, 8, 2)
GENERAL_APPLICATION = date(2026, 8, 2)
ARTICLE_6_1_APPLICATION = date(2027, 8, 2)


@dataclass(frozen=True)
class Ref:
    """One provision key and the citation stored for that key."""

    provision_key: str
    citation: str

    def as_model(self) -> LegalReference:
        return LegalReference(celex=CELEX, provision_key=self.provision_key, citation=self.citation)


ARTICLE_113 = Ref("article/113", "Article 113")
ARTICLE_113_A = Ref("article/113/point/a", "Article 113(a)")
ARTICLE_113_B = Ref("article/113/point/b", "Article 113(b)")
ARTICLE_113_C = Ref("article/113/point/c", "Article 113(c)")


@dataclass(frozen=True)
class Control:
    """A follow-up topic mapped to provisions. It is not evidence the control exists."""

    control_id: str
    title: str
    summary: str
    references: tuple[Ref, ...]


CONTROLS: tuple[Control, ...] = (
    Control(
        control_id="CTRL-SCOPE",
        title="Confirm whether the Regulation applies",
        summary="Review the recorded role, Union nexus, and any claimed exclusion before treating the Act as inapplicable.",
        references=(
            Ref("article/2/paragraph/1", "Article 2(1)"),
            Ref("article/2/paragraph/3", "Article 2(3)"),
            Ref("article/2/paragraph/6", "Article 2(6)"),
            Ref("article/2/paragraph/10", "Article 2(10)"),
            Ref("article/3/point/1", "Article 3(1)"),
        ),
    ),
    Control(
        control_id="CTRL-ART5-REVIEW",
        title="Review a possible prohibited practice",
        summary="Compare the use with the conditions and exceptions in the cited Article 5 point before any deployment decision.",
        references=(Ref("article/5", "Article 5"),),
    ),
    Control(
        control_id="CTRL-ART6-CLASSIFICATION",
        title="Document the high-risk classification",
        summary="Record which Article 6 route and which Annex III point were considered.",
        references=(
            Ref("article/6", "Article 6"),
            Ref("annex/I", "Annex I"),
            Ref("annex/III", "Annex III"),
        ),
    ),
    Control(
        control_id="CTRL-ART6-DEROGATION-RECORD",
        title="Document an Article 6(3) derogation",
        summary="Article 6(4) requires the provider to document a conclusion that an Annex III system is not high-risk, and Article 49(2) requires registration.",
        references=(
            Ref("article/6/paragraph/3", "Article 6(3)"),
            Ref("article/6/paragraph/4", "Article 6(4)"),
            Ref("article/49", "Article 49"),
        ),
    ),
    Control(
        control_id="CTRL-HIGH-RISK-OBLIGATIONS",
        title="Screen provider and deployer obligations for a high-risk system",
        summary="Where a high-risk classification is confirmed, Chapter III obligations such as risk management, human oversight, and provider duties need their own assessment.",
        references=(
            Ref("article/9", "Article 9"),
            Ref("article/14", "Article 14"),
            Ref("article/16", "Article 16"),
        ),
    ),
    Control(
        control_id="CTRL-TRANSPARENCY",
        title="Review transparency duties",
        summary="Check the Article 50 duties for the provider or deployer, including the exceptions written in that article.",
        references=(Ref("article/50", "Article 50"),),
    ),
    Control(
        control_id="CTRL-GPAI",
        title="Review general-purpose model duties",
        summary="Distinguish the Article 53 duties from the additional duties for a model with systemic risk.",
        references=(
            Ref("article/51", "Article 51"),
            Ref("article/53", "Article 53"),
            Ref("article/55", "Article 55"),
        ),
    ),
)

CONTROLS_BY_ID = {control.control_id: control for control in CONTROLS}


@dataclass(frozen=True)
class Indicator:
    """A yes/no/unknown field that maps to one provision."""

    rule_id: str
    field: str
    category: Category
    positive_outcome: Outcome
    ref: Ref
    explanation: str
    control_ids: tuple[str, ...]
    applicable_from: date
    application_reference: Ref
    conditions: tuple[str, ...]


PROHIBITED: tuple[Indicator, ...] = (
    Indicator(
        rule_id="R-ART5-1-A",
        field="subliminal_or_purposefully_manipulative",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/a", "Article 5(1)(a)"),
        explanation=(
            "Article 5(1)(a) concerns subliminal, purposefully manipulative, or deceptive techniques "
            "with a specified objective or effect. A yes answer only shows that the description matches "
            "that subject. It does not establish the objective, the effect, or that the practice is prohibited."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("subliminal_or_purposefully_manipulative is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-B",
        field="exploits_vulnerabilities",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/b", "Article 5(1)(b)"),
        explanation=(
            "Article 5(1)(b) concerns exploiting vulnerabilities due to age, disability, or a specific "
            "social or economic situation, with a specified objective or effect. The engine does not decide "
            "whether that objective or effect is present."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("exploits_vulnerabilities is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-C",
        field="social_scoring",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/c", "Article 5(1)(c)"),
        explanation=(
            "Article 5(1)(c) concerns social scoring over time that leads to detrimental treatment of the "
            "kinds listed in that point. A matching description needs legal review of those conditions."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("social_scoring is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-D",
        field="criminal_risk_solely_from_profiling",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/d", "Article 5(1)(d)"),
        explanation=(
            "Article 5(1)(d) concerns criminal-offence risk assessment based solely on profiling or "
            "personality traits. The point also states an exception. The engine does not apply that exception."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("criminal_risk_solely_from_profiling is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-E",
        field="untargeted_facial_scraping",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/e", "Article 5(1)(e)"),
        explanation=(
            "Article 5(1)(e) concerns creating or expanding facial-recognition databases by untargeted "
            "scraping of facial images from the internet or CCTV footage."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("untargeted_facial_scraping is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-F",
        field="emotion_inference_workplace_or_education",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/f", "Article 5(1)(f)"),
        explanation=(
            "Article 5(1)(f) concerns inferring emotions in the workplace or in education institutions. "
            "The point states an exception. The engine does not decide whether the exception applies."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("emotion_inference_workplace_or_education is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-G",
        field="biometric_categorisation_of_sensitive_attributes",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/g", "Article 5(1)(g)"),
        explanation=(
            "Article 5(1)(g) concerns biometric categorisation that deduces or infers sensitive attributes "
            "listed in that point. The point states exceptions. The engine does not apply them."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("biometric_categorisation_of_sensitive_attributes is yes.",),
    ),
    Indicator(
        rule_id="R-ART5-1-H",
        field="realtime_remote_biometric_public_law_enforcement",
        category=Category.prohibited_practice,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/5/paragraph/1/subparagraph/1/point/h", "Article 5(1)(h)"),
        explanation=(
            "Article 5(1)(h) concerns real-time remote biometric identification in publicly accessible "
            "spaces for law enforcement, unless one of the objectives in that point applies and the later "
            "conditions in Article 5 are met. The engine does not decide those conditions."
        ),
        control_ids=("CTRL-ART5-REVIEW",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("realtime_remote_biometric_public_law_enforcement is yes.",),
    ),
)

TRANSPARENCY: tuple[Indicator, ...] = (
    Indicator(
        rule_id="R-ART50-1",
        field="interacts_directly_with_people",
        category=Category.transparency,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/50/paragraph/1", "Article 50(1)"),
        explanation=(
            "Article 50(1) requires providers of systems intended to interact directly with natural persons "
            "to design them so people are informed that they are interacting with an AI system, unless that "
            "is obvious. The engine does not decide the exception."
        ),
        control_ids=("CTRL-TRANSPARENCY",),
        applicable_from=GENERAL_APPLICATION,
        application_reference=ARTICLE_113,
        conditions=("interacts_directly_with_people is yes.",),
    ),
    Indicator(
        rule_id="R-ART50-2",
        field="generates_synthetic_content",
        category=Category.transparency,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/50/paragraph/2", "Article 50(2)"),
        explanation=(
            "Article 50(2) concerns marking synthetic audio, image, video, or text as artificially generated "
            "or manipulated. The paragraph states limits. The engine does not decide those limits."
        ),
        control_ids=("CTRL-TRANSPARENCY",),
        applicable_from=GENERAL_APPLICATION,
        application_reference=ARTICLE_113,
        conditions=("generates_synthetic_content is yes.",),
    ),
    Indicator(
        rule_id="R-ART50-4",
        field="deepfake",
        category=Category.transparency,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/50/paragraph/4", "Article 50(4)"),
        explanation=(
            "Article 50(4) concerns deployer disclosure for a deep fake, and a separate disclosure for "
            "certain generated text. The paragraph states exceptions. The engine does not apply them."
        ),
        control_ids=("CTRL-TRANSPARENCY",),
        applicable_from=GENERAL_APPLICATION,
        application_reference=ARTICLE_113,
        conditions=("deepfake is yes.",),
    ),
)

SCOPE_EXCLUSIONS: tuple[Indicator, ...] = (
    Indicator(
        rule_id="R-SCOPE-MILITARY",
        field="exclusively_military_defence_or_national_security",
        category=Category.scope,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/2/paragraph/3", "Article 2(3)"),
        explanation=(
            "Article 2(3) sets out exclusions for military, defence, and national security uses. "
            "The exclusion depends on the limits written in that paragraph. A yes answer is not a decision "
            "that the Regulation does not apply."
        ),
        control_ids=("CTRL-SCOPE",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("exclusively_military_defence_or_national_security is yes.",),
    ),
    Indicator(
        rule_id="R-SCOPE-RESEARCH",
        field="solely_scientific_research",
        category=Category.scope,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/2/paragraph/6", "Article 2(6)"),
        explanation=(
            "Article 2(6) excludes systems or models developed and put into service for the sole purpose "
            "of scientific research and development. The engine does not decide whether that sole purpose is met."
        ),
        control_ids=("CTRL-SCOPE",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("solely_scientific_research is yes.",),
    ),
    Indicator(
        rule_id="R-SCOPE-PERSONAL",
        field="purely_personal_non_professional",
        category=Category.scope,
        positive_outcome=Outcome.requires_legal_review,
        ref=Ref("article/2/paragraph/10", "Article 2(10)"),
        explanation=(
            "Article 2(10) says the Regulation does not apply to obligations of deployers who are natural "
            "persons using systems in a purely personal non-professional activity. It is not a general "
            "exemption for the system or its provider."
        ),
        control_ids=("CTRL-SCOPE",),
        applicable_from=CHAPTER_I_AND_II,
        application_reference=ARTICLE_113_A,
        conditions=("purely_personal_non_professional is yes.",),
    ),
)


@dataclass(frozen=True)
class AnnexRule:
    """One Annex III use, or an exception written in that annex."""

    use: AnnexUse
    rule_id: str
    ref: Ref
    listed: bool
    permission_qualified: bool
    explanation: str


ANNEX_RULES: tuple[AnnexRule, ...] = (
    AnnexRule(
        AnnexUse.remote_biometric_identification,
        "R-ANNEX-III-1-A",
        Ref("annex/III/point/1/point/a", "Annex III(1)(a)"),
        True,
        True,
        "Annex III(1)(a) lists remote biometric identification. Point 1 applies in so far as the use is permitted under relevant Union or national law. Article 6(2) then classifies a listed system as high-risk, subject to Article 6(3).",
    ),
    AnnexRule(
        AnnexUse.biometric_verification_only,
        "R-ANNEX-III-1-A-EXCEPTION",
        Ref("annex/III/point/1/point/a", "Annex III(1)(a)"),
        False,
        False,
        "Annex III(1)(a) says remote biometric identification does not include biometric verification whose sole purpose is to confirm that a specific person is who they claim to be. The recorded use is that exception, so this rule does not indicate a high-risk Annex III use.",
    ),
    AnnexRule(
        AnnexUse.biometric_categorisation,
        "R-ANNEX-III-1-B",
        Ref("annex/III/point/1/point/b", "Annex III(1)(b)"),
        True,
        True,
        "Annex III(1)(b) lists biometric categorisation based on sensitive or protected attributes. Point 1 applies in so far as the use is permitted. Article 5(1)(g) may also apply and is screened separately.",
    ),
    AnnexRule(
        AnnexUse.emotion_recognition,
        "R-ANNEX-III-1-C",
        Ref("annex/III/point/1/point/c", "Annex III(1)(c)"),
        True,
        True,
        "Annex III(1)(c) lists emotion recognition. Point 1 applies in so far as the use is permitted. Emotion inference in the workplace or education is screened separately under Article 5(1)(f).",
    ),
    AnnexRule(
        AnnexUse.critical_infrastructure_safety,
        "R-ANNEX-III-2",
        Ref("annex/III/point/2", "Annex III(2)"),
        True,
        False,
        "Annex III(2) lists AI systems intended as safety components in the management and operation of critical digital infrastructure, road traffic, or the supply of water, gas, heating, or electricity.",
    ),
    AnnexRule(
        AnnexUse.education_access,
        "R-ANNEX-III-3-A",
        Ref("annex/III/point/3/point/a", "Annex III(3)(a)"),
        True,
        False,
        "Annex III(3)(a) lists systems intended to determine access or admission, or to assign people, to educational or vocational training institutions.",
    ),
    AnnexRule(
        AnnexUse.education_evaluation,
        "R-ANNEX-III-3-B",
        Ref("annex/III/point/3/point/b", "Annex III(3)(b)"),
        True,
        False,
        "Annex III(3)(b) lists systems intended to evaluate learning outcomes, including where those outcomes steer learning.",
    ),
    AnnexRule(
        AnnexUse.education_level,
        "R-ANNEX-III-3-C",
        Ref("annex/III/point/3/point/c", "Annex III(3)(c)"),
        True,
        False,
        "Annex III(3)(c) lists systems intended to assess the appropriate level of education a person will receive or be able to access.",
    ),
    AnnexRule(
        AnnexUse.student_proctoring,
        "R-ANNEX-III-3-D",
        Ref("annex/III/point/3/point/d", "Annex III(3)(d)"),
        True,
        False,
        "Annex III(3)(d) lists systems intended to monitor and detect prohibited behaviour of students during tests.",
    ),
    AnnexRule(
        AnnexUse.recruitment,
        "R-ANNEX-III-4-A",
        Ref("annex/III/point/4/point/a", "Annex III(4)(a)"),
        True,
        False,
        "Annex III(4)(a) lists systems intended for recruitment or selection of natural persons, including targeted job advertisements, filtering applications, and evaluating candidates.",
    ),
    AnnexRule(
        AnnexUse.worker_management,
        "R-ANNEX-III-4-B",
        Ref("annex/III/point/4/point/b", "Annex III(4)(b)"),
        True,
        False,
        "Annex III(4)(b) lists systems intended for decisions on work relationships, task allocation from individual traits, or monitoring and evaluation of workers.",
    ),
    AnnexRule(
        AnnexUse.public_benefits,
        "R-ANNEX-III-5-A",
        Ref("annex/III/point/5/point/a", "Annex III(5)(a)"),
        True,
        False,
        "Annex III(5)(a) lists systems used by or for public authorities to evaluate eligibility for essential public assistance benefits and services, or to grant, reduce, revoke, or reclaim them.",
    ),
    AnnexRule(
        AnnexUse.credit_scoring,
        "R-ANNEX-III-5-B",
        Ref("annex/III/point/5/point/b", "Annex III(5)(b)"),
        True,
        False,
        "Annex III(5)(b) lists systems intended to evaluate creditworthiness or establish a credit score, with an exception for detecting financial fraud. This value is the listed use, not that exception.",
    ),
    AnnexRule(
        AnnexUse.credit_fraud_detection_only,
        "R-ANNEX-III-5-B-EXCEPTION",
        Ref("annex/III/point/5/point/b", "Annex III(5)(b)"),
        False,
        False,
        "Annex III(5)(b) excepts AI systems used to detect financial fraud. The recorded use is that exception, so this rule does not indicate the credit-scoring high-risk use. A reviewer still has to confirm that fraud detection is the purpose.",
    ),
    AnnexRule(
        AnnexUse.insurance_pricing,
        "R-ANNEX-III-5-C",
        Ref("annex/III/point/5/point/c", "Annex III(5)(c)"),
        True,
        False,
        "Annex III(5)(c) lists risk assessment and pricing for natural persons in life and health insurance.",
    ),
    AnnexRule(
        AnnexUse.emergency_dispatch,
        "R-ANNEX-III-5-D",
        Ref("annex/III/point/5/point/d", "Annex III(5)(d)"),
        True,
        False,
        "Annex III(5)(d) lists systems intended to evaluate and classify emergency calls or to dispatch or prioritise emergency first response.",
    ),
    AnnexRule(
        AnnexUse.law_enforcement,
        "R-ANNEX-III-6",
        Ref("annex/III/point/6", "Annex III(6)"),
        True,
        True,
        "Annex III(6) lists specified law-enforcement uses in so far as they are permitted under relevant Union or national law. The recorded area is that point. The particular lettered use still needs review, as does Article 5 where a prohibition may apply.",
    ),
    AnnexRule(
        AnnexUse.migration_asylum_border,
        "R-ANNEX-III-7",
        Ref("annex/III/point/7", "Annex III(7)"),
        True,
        True,
        "Annex III(7) lists specified migration, asylum, and border-control uses in so far as they are permitted under relevant Union or national law. The particular lettered use still needs review.",
    ),
    AnnexRule(
        AnnexUse.justice_assistance,
        "R-ANNEX-III-8-A",
        Ref("annex/III/point/8/point/a", "Annex III(8)(a)"),
        True,
        False,
        "Annex III(8)(a) lists systems intended to assist a judicial authority in researching and interpreting facts and the law and in applying the law to facts, or to be used in a similar way in alternative dispute resolution.",
    ),
    AnnexRule(
        AnnexUse.election_influence,
        "R-ANNEX-III-8-B",
        Ref("annex/III/point/8/point/b", "Annex III(8)(b)"),
        True,
        False,
        "Annex III(8)(b) lists systems intended to influence the outcome of an election or referendum or voting behaviour. The point also states what it does not include.",
    ),
)

ANNEX_BY_USE = {rule.use: rule for rule in ANNEX_RULES}

ARTICLE_6_2 = Ref("article/6/paragraph/2", "Article 6(2)")
ARTICLE_6_3 = Ref("article/6/paragraph/3", "Article 6(3)")
ARTICLE_6_3_PROFILING = Ref("article/6/paragraph/3/subparagraph/3", "Article 6(3)")
ARTICLE_6_1_A = Ref("article/6/paragraph/1/point/a", "Article 6(1)(a)")
ARTICLE_6_1_B = Ref("article/6/paragraph/1/point/b", "Article 6(1)(b)")
ARTICLE_50_3 = Ref("article/50/paragraph/3", "Article 50(3)")
ARTICLE_3_3 = Ref("article/3/point/3", "Article 3(3)")
ARTICLE_3_4 = Ref("article/3/point/4", "Article 3(4)")
ARTICLE_3_12 = Ref("article/3/point/12", "Article 3(12)")


def reference_problems(stored_citations: dict[str, str]) -> list[str]:
    """Return citation mismatches between this catalog and an imported act."""
    problems: list[str] = []
    seen: set[tuple[str, str]] = set()
    for ref in _every_reference():
        pair = (ref.provision_key, ref.citation)
        if pair in seen:
            continue
        seen.add(pair)
        stored = stored_citations.get(ref.provision_key)
        if stored is None:
            problems.append(f"{ref.provision_key} is not in the stored act")
        elif stored != ref.citation:
            problems.append(
                f"{ref.provision_key} is cited as {ref.citation!r} here and {stored!r} in the stored act"
            )
    return problems


def _every_reference() -> list[Ref]:
    refs: list[Ref] = [
        ARTICLE_113,
        ARTICLE_113_A,
        ARTICLE_113_B,
        ARTICLE_113_C,
        ARTICLE_6_2,
        ARTICLE_6_3,
        ARTICLE_6_3_PROFILING,
        ARTICLE_6_1_A,
        ARTICLE_6_1_B,
        ARTICLE_50_3,
        ARTICLE_3_3,
        ARTICLE_3_4,
        ARTICLE_3_12,
    ]
    for control in CONTROLS:
        refs.extend(control.references)
    for indicator in (*PROHIBITED, *TRANSPARENCY, *SCOPE_EXCLUSIONS):
        refs.append(indicator.ref)
        refs.append(indicator.application_reference)
    for rule in ANNEX_RULES:
        refs.append(rule.ref)
    return refs
