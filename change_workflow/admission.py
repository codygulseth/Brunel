"""Versioned deterministic material-finding admission rules."""

from revision_intelligence.models import ChangeCategory, ChangeSeverity, ChangeType, DocumentChange

from .models import AdmissionDecision


class ChangeAdmissionService:
    def __init__(self, policy_version: str = "change-admission-v1") -> None:
        self.policy_version = policy_version

    def evaluate(self, finding: DocumentChange, *, manual: bool = False) -> AdmissionDecision:
        reasons: list[str] = []
        if manual:
            reasons.append("manual_promotion")
        if finding.change_type == ChangeType.FORMATTING_ONLY and not manual:
            return AdmissionDecision(
                finding_id=finding.id,
                admitted=False,
                reasons=("formatting_only_excluded",),
                policy_version=self.policy_version,
            )
        if finding.severity in {ChangeSeverity.CRITICAL, ChangeSeverity.HIGH}:
            reasons.append("high_significance")
        if finding.review_required:
            reasons.append("human_review_required")
        for signal in finding.evidence.diff.signals:
            if signal in {
                "numeric_change",
                "quantity_change",
                "responsibility_change",
                "approval_status_change",
                "requirement_strength_change",
                "negation_change",
            }:
                reasons.append(signal)
        material = {
            ChangeCategory.SCHEDULE,
            ChangeCategory.PROCUREMENT,
            ChangeCategory.SAFETY,
            ChangeCategory.CODE,
            ChangeCategory.TESTING,
            ChangeCategory.INSPECTION,
            ChangeCategory.EQUIPMENT,
            ChangeCategory.MATERIAL,
            ChangeCategory.QUANTITY,
            ChangeCategory.DIMENSION,
            ChangeCategory.RESPONSIBILITY,
            ChangeCategory.APPROVAL_STATUS,
        }
        reasons.extend(f"category:{item.value}" for item in finding.categories if item in material)
        return AdmissionDecision(
            finding_id=finding.id,
            admitted=bool(reasons),
            reasons=tuple(dict.fromkeys(reasons)) or ("below_materiality_threshold",),
            policy_version=self.policy_version,
        )
