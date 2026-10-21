"""Print the labelled screening examples.

Run from the repository root:

    .\\.venv\\Scripts\\python.exe -m ai_governance.assessment
"""

from ai_governance.assessment.catalog import RULE_SET_VERSION
from ai_governance.assessment.engine import assess
from ai_governance.assessment.examples import LABELLED_EXAMPLES


def main() -> int:
    """Evaluate the labelled examples and print the decision-support status."""
    print(f"rule set {RULE_SET_VERSION}")
    for example in LABELLED_EXAMPLES:
        result = assess(example.use_case, assessed_on=example.assessed_on)
        citations = sorted(
            {
                reference.citation
                for finding in result.findings
                for reference in finding.legal_references
            }
        )
        print(f"{example.name}: {result.status.value}")
        print(f"  categories: {', '.join(result.categories) or 'none'}")
        if citations:
            print(f"  citations: {', '.join(citations)}")
        if result.information_gaps:
            print(f"  gaps: {', '.join(result.information_gaps)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
