"""Lightweight construction-aware query normalization."""

import re
from dataclasses import dataclass

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*", re.IGNORECASE)
IDENTIFIER_PATTERNS = (
    re.compile(r"\b[a-z]{1,3}[- ]\d{2,4}(?:\.\d+)?\b", re.IGNORECASE),
    re.compile(r"\b\d{2}\s+\d{2}\s+\d{2}\b"),
    re.compile(r"\broom\s+[a-z0-9-]+\b", re.IGNORECASE),
    re.compile(r"\b(?:rfi|submittal|rev(?:ision)?)\s*#?[-:]?\s*[a-z0-9-]+\b", re.IGNORECASE),
)
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "for",
    "from",
    "has",
    "in",
    "is",
    "it",
    "of",
    "on",
    "the",
    "this",
    "to",
    "what",
    "where",
    "which",
}


def canonical_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


@dataclass(frozen=True, slots=True)
class NormalizedQuery:
    text: str
    terms: tuple[str, ...]
    identifiers: tuple[str, ...]


class ConstructionQueryNormalizer:
    def normalize(self, text: str) -> NormalizedQuery:
        lowered = " ".join(text.lower().split())
        terms = tuple(
            dict.fromkeys(
                token.lower()
                for token in TOKEN_PATTERN.findall(lowered)
                if token.lower() not in STOP_WORDS and len(token) > 1
            )
        )
        identifiers = tuple(
            dict.fromkeys(
                canonical_identifier(match.group())
                for pattern in IDENTIFIER_PATTERNS
                for match in pattern.finditer(lowered)
            )
        )
        return NormalizedQuery(text=lowered, terms=terms, identifiers=identifiers)

    def identifiers_in(self, text: str) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(
                canonical_identifier(match.group())
                for pattern in IDENTIFIER_PATTERNS
                for match in pattern.finditer(text)
            )
        )
