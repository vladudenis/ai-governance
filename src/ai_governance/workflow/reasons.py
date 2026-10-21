"""When a stored screening no longer matches the current facts or rules."""


def reassessment_reasons(
    *,
    has_assessment: bool,
    latest_record_id: int | None,
    current_record_id: int,
    latest_rule_version: str | None,
    current_rule_version: str,
    latest_content_sha256: str | None,
    current_content_sha256: str | None,
) -> list[str]:
    """Return why the latest screening should be run again.

    A system that has never been screened is not a reassessment. It is simply
    unscreened. A reason is returned only when a stored screening is stale.
    """
    if not has_assessment:
        return []
    reasons: list[str] = []
    if latest_record_id != current_record_id:
        reasons.append("The facts changed after the latest screening.")
    if latest_rule_version != current_rule_version:
        reasons.append("The rule set changed after the latest screening.")
    if (
        latest_content_sha256
        and current_content_sha256
        and latest_content_sha256 != current_content_sha256
    ):
        reasons.append("A newer text of the Act is loaded than the one linked to the latest screening.")
    return reasons
