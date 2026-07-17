"""Deterministic identifier, text, similarity, and movement-aware alignment."""

from difflib import SequenceMatcher

from .models import AlignmentResult, BlockMatch, ComparisonUnit, MatchMethod


class BlockAlignmentService:
    def __init__(
        self, similarity_threshold: float = 0.55, ambiguous_threshold: float = 0.08
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.ambiguous_threshold = ambiguous_threshold

    def align(
        self, old: tuple[ComparisonUnit, ...], new: tuple[ComparisonUnit, ...]
    ) -> AlignmentResult:
        available = set(range(len(new)))
        matches: list[BlockMatch] = []
        ambiguous: list[BlockMatch] = []
        removed: list[ComparisonUnit] = []
        for old_unit in old:
            candidates = [(i, self._score(old_unit, new[i])) for i in available]
            candidates.sort(key=lambda item: (-item[1][0], new[item[0]].order))
            if not candidates or candidates[0][1][0] < self.similarity_threshold:
                removed.append(old_unit)
                continue
            index, (score, method) = candidates[0]
            is_ambiguous = (
                len(candidates) > 1 and score - candidates[1][1][0] < self.ambiguous_threshold
            )
            match = BlockMatch(
                old_unit=old_unit,
                new_unit=new[index],
                method=method,
                score=round(score, 6),
                ambiguous=is_ambiguous,
            )
            (ambiguous if is_ambiguous else matches).append(match)
            available.remove(index)
        return AlignmentResult(
            matches=tuple(matches),
            added=tuple(new[i] for i in sorted(available)),
            removed=tuple(removed),
            ambiguous=tuple(ambiguous),
        )

    @staticmethod
    def _score(old: ComparisonUnit, new: ComparisonUnit) -> tuple[float, MatchMethod]:
        if old.identifier and old.identifier == new.identifier:
            ratio = SequenceMatcher(None, old.normalized_text, new.normalized_text).ratio()
            return max(0.82, ratio), MatchMethod.EXACT_IDENTIFIER
        if old.span.source_text == new.span.source_text:
            return 1.0, MatchMethod.EXACT_TEXT
        if old.normalized_text == new.normalized_text:
            return 0.99, MatchMethod.NORMALIZED_TEXT
        ratio = SequenceMatcher(None, old.normalized_text, new.normalized_text).ratio()
        return ratio, MatchMethod.SIMILARITY
