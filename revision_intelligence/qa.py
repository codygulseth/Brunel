"""Project-scoped retrieval over saved findings while retaining both source revisions."""

import re
from pydantic import BaseModel, ConfigDict

from .interfaces import ComparisonRepository
from .models import ChangeEvidence, DocumentChange


class ComparisonAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    comparison_id: str | None = None
    findings: tuple[DocumentChange, ...] = ()
    evidence: tuple[ChangeEvidence, ...] = ()
    sufficient: bool = False


class ComparisonQuestionAnsweringService:
    def __init__(self, repository: ComparisonRepository) -> None:
        self.repository = repository

    def answer(self, project_id: str, question: str) -> ComparisonAnswer:
        terms = {term for term in re.findall(r"[a-z0-9]+", question.casefold()) if len(term) > 2}
        scored: list[tuple[int, str, DocumentChange]] = []
        for comparison in self.repository.list_by_project(project_id):
            for change in comparison.changes:
                searchable = " ".join(
                    filter(
                        None,
                        (
                            change.title,
                            change.evidence.old_excerpt,
                            change.evidence.new_excerpt,
                            " ".join(category.value for category in change.categories),
                        ),
                    )
                ).casefold()
                score = len(terms.intersection(re.findall(r"[a-z0-9]+", searchable)))
                if score:
                    scored.append((score, comparison.id, change))
        scored.sort(key=lambda item: (-item[0], item[2].id))
        if not scored:
            return ComparisonAnswer(answer="The saved revision comparisons do not establish this.")
        _, comparison_id, change = scored[0]
        old_text = change.evidence.old_excerpt or "[content added in new revision]"
        new_text = change.evidence.new_excerpt or "[content removed from new revision]"
        return ComparisonAnswer(
            answer=f"Brunel detected a {change.change_type.value} finding. Old: {old_text} New: {new_text}",
            comparison_id=comparison_id,
            findings=(change,),
            evidence=(change.evidence,),
            sufficient=True,
        )
