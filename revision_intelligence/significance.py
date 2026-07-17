"""Explainable significance assessment separate from classification confidence."""

from .models import (
    ChangeCategory,
    ChangeSeverity,
    ChangeType,
    EvidenceStrength,
    SignificanceAssessment,
    TokenDiff,
)


class ChangeSignificanceAssessor:
    """Conservative assessment: severity does not imply factual impact certainty."""

    def assess(
        self,
        *,
        change_type: ChangeType,
        categories: tuple[ChangeCategory, ...],
        diff: TokenDiff,
        ambiguous: bool,
    ) -> SignificanceAssessment:
        high_categories = {
            ChangeCategory.SAFETY,
            ChangeCategory.RESPONSIBILITY,
            ChangeCategory.APPROVAL_STATUS,
        }
        if change_type == ChangeType.FORMATTING_ONLY:
            severity = ChangeSeverity.INFORMATIONAL
        elif high_categories.intersection(categories):
            severity = ChangeSeverity.HIGH
        elif diff.signals or categories != (ChangeCategory.UNKNOWN,):
            severity = ChangeSeverity.MEDIUM
        else:
            severity = ChangeSeverity.LOW
        return SignificanceAssessment(
            severity=severity,
            evidence_strength=EvidenceStrength.WEAK if ambiguous else EvidenceStrength.STRONG,
            explanation=(
                "Potential significance is based on construction-sensitive categories or token "
                "changes; project impact remains unconfirmed and requires human review."
            ),
        )
