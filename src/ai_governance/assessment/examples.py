"""Manually labelled use cases for the screening rules.

Each example states the status the engine should return. The labels are
decision-support expectations, not legal conclusions about the described systems.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from ai_governance.assessment.facts import (
    AnnexAnswer,
    AnnexUse,
    Answer,
    Basis,
    OperatorRole,
    RoleAnswer,
    TextFact,
    UseCase,
    YesNo,
)
from ai_governance.assessment.results import AssessmentStatus

SCREENED_ON = date(2026, 10, 21)


class LabelledExample(BaseModel):
    """One use case and the screening result a reviewer should see."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    use_case: UseCase
    expected_status: AssessmentStatus
    expected_categories: list[str]
    expected_citations: list[str] = []
    assessed_on: date | None = SCREENED_ON


def answered_yes(evidence: str) -> Answer:
    """A stated yes, with the words it came from."""
    return Answer(value=YesNo.yes, basis=Basis.stated, evidence=evidence)


def answered_no(evidence: str = "The source description does not describe this practice.") -> Answer:
    """A stated no."""
    return Answer(value=YesNo.no, basis=Basis.stated, evidence=evidence)


def annex_use(use: AnnexUse, evidence: str) -> AnnexAnswer:
    """A stated Annex III classification."""
    return AnnexAnswer(value=use, basis=Basis.stated, evidence=evidence)


def cleared(name: str, purpose: str, **overrides: object) -> UseCase:
    """A fully answered record that does not indicate a listed practice.

    Overrides replace individual facts. Callers use this so an example changes
    only the fact under test.
    """
    payload: dict[str, object] = {}
    for field_name, field in UseCase.model_fields.items():
        if field_name == "name":
            payload[field_name] = name
        elif field.annotation is Answer:
            payload[field_name] = answered_no()
        elif field.annotation is TextFact:
            payload[field_name] = TextFact(value=purpose, basis=Basis.stated, evidence=purpose)
        elif field.annotation is AnnexAnswer:
            payload[field_name] = annex_use(
                AnnexUse.none,
                "The described use is not one of the Annex III uses.",
            )
        elif field.annotation is RoleAnswer:
            payload[field_name] = RoleAnswer(
                value=OperatorRole.deployer,
                basis=Basis.stated,
                evidence="The organisation uses the system itself.",
            )
    payload["is_ai_system"] = answered_yes(
        "The description says the system infers outputs such as predictions or text from its input."
    )
    payload["used_in_the_union"] = answered_yes("The system is used by staff in the Union.")
    payload.update(overrides)
    return UseCase.model_validate(payload)


LABELLED_EXAMPLES: tuple[LabelledExample, ...] = (
    LabelledExample(
        name="Internal spelling checker",
        description="Suggests spelling fixes inside an editor. It does not score people or make a decision about them.",
        use_case=cleared(
            "Internal spelling checker",
            "Suggest spelling fixes in an internal editor.",
        ),
        expected_status=AssessmentStatus.no_indicated_prohibited_or_high_risk_practice,
        expected_categories=[],
    ),
    LabelledExample(
        name="Office spreadsheet",
        description="A workbook that totals columns with formulas.",
        use_case=UseCase(
            name="Office spreadsheet",
            is_ai_system=answered_no(
                "The workbook calculates totals with formulas and does not infer outputs."
            ),
        ),
        expected_status=AssessmentStatus.no_indicated_prohibited_or_high_risk_practice,
        expected_categories=[],
    ),
    LabelledExample(
        name="Unscreened assistant",
        description="A named system with no answered screening questions.",
        use_case=UseCase(name="Unscreened assistant"),
        expected_status=AssessmentStatus.needs_further_information,
        expected_categories=["information_gap"],
    ),
    LabelledExample(
        name="Recruitment filter",
        description="Ranks job applicants and filters applications.",
        use_case=cleared(
            "Recruitment filter",
            "Rank and filter job applications.",
            annex_iii_use=annex_use(
                AnnexUse.recruitment,
                "The system filters job applications and ranks candidates.",
            ),
        ),
        expected_status=AssessmentStatus.potentially_high_risk,
        expected_categories=["high_risk"],
        expected_citations=["Annex III(4)(a)", "Article 6(2)"],
    ),
    LabelledExample(
        name="Recruitment derogation",
        description="The provider claims an Article 6(3) derogation and says the system does not profile people.",
        use_case=cleared(
            "Recruitment derogation",
            "Prepare a checklist of missing application fields without selecting the candidate.",
            annex_iii_use=annex_use(AnnexUse.recruitment, "The tool reads job applications."),
            article_6_3_derogation_claimed=answered_yes(
                "The provider says the tool only performs a narrow procedural task."
            ),
            performs_profiling=answered_no("The description says the tool does not profile applicants."),
        ),
        expected_status=AssessmentStatus.requires_legal_review,
        expected_categories=["high_risk"],
        expected_citations=["Annex III(4)(a)", "Article 6(3)", "Article 6(4)"],
    ),
    LabelledExample(
        name="Workplace emotion inference",
        description="Infers employee emotions from video during the workday.",
        use_case=cleared(
            "Workplace emotion inference",
            "Infer employee emotions from workplace video.",
            emotion_inference_workplace_or_education=answered_yes(
                "The system infers emotions of employees at work."
            ),
            annex_iii_use=annex_use(
                AnnexUse.emotion_recognition,
                "The intended use is emotion recognition.",
            ),
        ),
        expected_status=AssessmentStatus.requires_legal_review,
        expected_categories=["high_risk", "prohibited_practice", "transparency"],
        expected_citations=["Article 5(1)(f)", "Annex III(1)(c)", "Article 50(3)"],
    ),
    LabelledExample(
        name="Customer chatbot",
        description="Answers customer questions in a website chat window.",
        use_case=cleared(
            "Customer chatbot",
            "Answer customer questions in a chat window.",
            interacts_directly_with_people=answered_yes(
                "Customers type questions and the system replies in the chat."
            ),
        ),
        expected_status=AssessmentStatus.requires_legal_review,
        expected_categories=["transparency"],
        expected_citations=["Article 50(1)"],
    ),
    LabelledExample(
        name="Doorway face check",
        description="Compares one face with that person's own badge photo.",
        use_case=cleared(
            "Doorway face check",
            "Confirm that the person at the door is the badge holder.",
            annex_iii_use=annex_use(
                AnnexUse.biometric_verification_only,
                "The only purpose is to confirm a specific person is the badge holder.",
            ),
        ),
        expected_status=AssessmentStatus.no_indicated_prohibited_or_high_risk_practice,
        expected_categories=[],
    ),
    LabelledExample(
        name="Card-fraud detector",
        description="Flags payment transactions that look like financial fraud.",
        use_case=cleared(
            "Card-fraud detector",
            "Detect financial fraud in card transactions.",
            annex_iii_use=annex_use(
                AnnexUse.credit_fraud_detection_only,
                "The system is used to detect financial fraud.",
            ),
        ),
        expected_status=AssessmentStatus.no_indicated_prohibited_or_high_risk_practice,
        expected_categories=[],
    ),
    LabelledExample(
        name="Military maintenance planner",
        description="The record says the system is used only for national defence.",
        use_case=cleared(
            "Military maintenance planner",
            "Plan maintenance of defence equipment.",
            exclusively_military_defence_or_national_security=answered_yes(
                "The description says the system is used exclusively for national defence."
            ),
        ),
        expected_status=AssessmentStatus.requires_legal_review,
        expected_categories=["scope"],
        expected_citations=["Article 2(3)"],
    ),
    LabelledExample(
        name="Machinery safety component",
        description="Both Article 6(1) conditions are recorded as yes. Article 6(1) applies from 2 August 2027.",
        use_case=cleared(
            "Machinery safety component",
            "Act as the safety component of a machine covered by listed product legislation.",
            safety_component_of_annex_i_product=answered_yes(
                "The system is the safety component of a product covered by Annex I legislation."
            ),
            third_party_conformity_required=answered_yes(
                "The product is required to undergo a third-party conformity assessment."
            ),
        ),
        expected_status=AssessmentStatus.potentially_high_risk,
        expected_categories=["high_risk"],
        expected_citations=["Article 6(1)(a)", "Article 6(1)(b)"],
    ),
)
