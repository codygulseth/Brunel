"""Operational answers distinguish team workflow records from source evidence."""

import re
from pydantic import BaseModel, ConfigDict

from .models import ProjectChange
from .repository import JsonChangeWorkflowRepository


class OperationalAnswer(BaseModel):
    model_config = ConfigDict(frozen=True)
    answer: str
    records: tuple[ProjectChange, ...] = ()
    evidence_type: str = "project_team_record"
    sufficient: bool = False


class OperationalQuestionService:
    def __init__(self, repository: JsonChangeWorkflowRepository) -> None:
        self.repository = repository

    def answer(self, project_id: str, question: str) -> OperationalAnswer:
        terms = {x for x in re.findall(r"[a-z0-9]+", question.casefold()) if len(x) > 2}
        ranked = []
        for item in self.repository.list_changes(project_id):
            assignment = next((a for a in reversed(item.assignments) if a.active), None)
            text = " ".join(
                (
                    item.title,
                    item.description,
                    item.status.value,
                    item.disposition.value,
                    assignment.assignee.display_name if assignment else "",
                    item.resolution_summary or "",
                    " ".join(link.reference for link in item.links),
                )
            ).casefold()
            score = len(terms.intersection(re.findall(r"[a-z0-9]+", text)))
            if score:
                ranked.append((score, item))
        ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
        if not ranked:
            return OperationalAnswer(answer="The project change register does not establish this.")
        item = ranked[0][1]
        assignment = next((a for a in reversed(item.assignments) if a.active), None)
        answer = f"The project team record lists '{item.title}' as {item.status.value}"
        if assignment:
            answer += f", assigned to {assignment.assignee.display_name}"
        answer += f". Disposition: {item.disposition.value}. Source comparison: {item.evidence.comparison_id}. Cost and schedule impacts are not confirmed unless explicitly dispositioned by a reviewer."
        return OperationalAnswer(answer=answer, records=(item,), sufficient=True)
