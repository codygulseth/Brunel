"""Inspectable token-aware deterministic difference detection."""

import re
from difflib import SequenceMatcher

from .models import ChangeType, TokenDiff

_TOKEN = re.compile(
    r"\d+(?:[,.]\d+)*(?:\s*(?:psi|weeks?|days?|hours?|minutes?|v|a|°f|ft|in))?|[A-Za-z]+(?:[-'][A-Za-z0-9]+)*|\S",
    re.I,
)


class TokenDiffer:
    def diff(self, old: str, new: str) -> tuple[ChangeType, TokenDiff]:
        if old == new:
            return ChangeType.UNCHANGED, TokenDiff()
        if " ".join(old.split()).casefold() == " ".join(new.split()).casefold():
            return ChangeType.FORMATTING_ONLY, TokenDiff(signals=("formatting_only",))
        old_tokens, new_tokens = _TOKEN.findall(old), _TOKEN.findall(new)
        added: list[str] = []
        removed: list[str] = []
        replacements: list[tuple[str, str]] = []
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, old_tokens, new_tokens).get_opcodes():
            if tag in {"delete", "replace"}:
                removed.extend(old_tokens[i1:i2])
            if tag in {"insert", "replace"}:
                added.extend(new_tokens[j1:j2])
            if tag == "replace":
                replacements.append((" ".join(old_tokens[i1:i2]), " ".join(new_tokens[j1:j2])))
        joined = f"{' '.join(removed)} -> {' '.join(added)}".casefold()
        number_words = {
            "zero",
            "one",
            "two",
            "three",
            "four",
            "five",
            "six",
            "seven",
            "eight",
            "nine",
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
            "twenty",
            "thirty",
            "sixty",
        }
        changed_words = {token.casefold() for token in (*removed, *added)}
        signals = tuple(
            signal
            for signal, present in {
                "numeric_change": bool(re.search(r"\d", joined)),
                "quantity_change": bool(number_words.intersection(changed_words)),
                "requirement_strength_change": any(
                    x in joined for x in ("shall", "must", "may", "required", "prohibited")
                ),
                "negation_change": any(x in joined for x in (" no ", "not", "none")),
                "responsibility_change": any(
                    x in joined
                    for x in (
                        "owner",
                        "contractor",
                        "subcontractor",
                        "agency",
                        "architect",
                        "engineer",
                    )
                ),
                "approval_status_change": any(
                    x in joined for x in ("approved", "revise", "resubmit", "rejected")
                ),
            }.items()
            if present
        )
        return ChangeType.MODIFIED, TokenDiff(
            added=tuple(added),
            removed=tuple(removed),
            replacements=tuple(replacements),
            signals=signals,
        )
