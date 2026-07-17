"""Explainable, versioned construction change classification and significance."""

import re

from .models import (
    ChangeCategory,
    ClassificationSignal,
    EvidenceStrength,
    TokenDiff,
)

RULES: dict[ChangeCategory, tuple[str, ...]] = {
    ChangeCategory.PROCUREMENT: ("lead time", "delivery", "procurement"),
    ChangeCategory.SCHEDULE: (
        "milestone",
        "completion",
        "duration",
        "week",
        "day",
        "date",
        "curing",
    ),
    ChangeCategory.COST: ("cost", "allowance", "unit price", "credit", "deduct"),
    ChangeCategory.SAFETY: (
        "osha",
        "fall protection",
        "energized",
        "confined space",
        "life safety",
    ),
    ChangeCategory.TESTING: ("testing", "test", "inspection", "witness"),
    ChangeCategory.COMMISSIONING: ("commissioning", "startup", "functional performance"),
    ChangeCategory.RESPONSIBILITY: (
        "owner",
        "contractor",
        "subcontractor",
        "agency",
        "architect",
        "engineer",
    ),
    ChangeCategory.APPROVAL_STATUS: ("approved", "revise and resubmit", "rejected", "approval"),
    ChangeCategory.EQUIPMENT: ("equipment", "switchgear", "generator", "model", "nema"),
    ChangeCategory.MATERIAL: ("concrete", "steel", "copper", "aluminum", "material"),
    ChangeCategory.QUALITY: ("quality", "strength", "psi", "tolerance"),
    ChangeCategory.CONTRACT: ("contract", "shall", "must", "required", "prohibited"),
}


class ConstructionChangeClassifier:
    rules_version = "construction-rules-v1"

    def classify(
        self, old: str, new: str, diff: TokenDiff
    ) -> tuple[tuple[ChangeCategory, ...], tuple[ClassificationSignal, ...], str]:
        text = f"{old}\n{new}".casefold()
        hits: dict[ChangeCategory, list[str]] = {}
        for category, terms in RULES.items():
            matched = [
                term
                for term in terms
                if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text)
            ]
            if matched:
                hits[category] = matched
        if {"numeric_change", "quantity_change"}.intersection(diff.signals):
            hits.setdefault(ChangeCategory.QUANTITY, []).append("numeric value changed")
        signals = tuple(
            ClassificationSignal(
                rule_id=f"{self.rules_version}:{category.value}",
                category=category,
                supporting_text=", ".join(terms),
                strength=EvidenceStrength.STRONG if len(terms) > 1 else EvidenceStrength.MODERATE,
            )
            for category, terms in sorted(hits.items(), key=lambda item: item[0].value)
        )
        categories = tuple(signal.category for signal in signals) or (ChangeCategory.UNKNOWN,)
        explanation = "Flagged by deterministic rules: " + (
            "; ".join(f"{signal.category.value} ({signal.supporting_text})" for signal in signals)
            if signals
            else "no construction-specific rule matched"
        )
        return categories, signals, explanation
