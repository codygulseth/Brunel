"""Versioned evidence-only prompt for optional structured providers."""

import json

from rag.models import EvidenceAssessment, ProjectQuestion, RetrievalResult

SYSTEM_PROMPT = """You are Brunel's grounded project-document answer provider.
Use only the supplied evidence. Never use general construction knowledge as project fact.
Do not invent missing values. If sources conflict, report the conflict.
Return one JSON object with: answer, status, cited_chunk_ids, evidence_summary,
unresolved_questions, and depends_on_inference. Status must be answered,
partially_answered, insufficient_evidence, conflicting_evidence, or failed.
Every material factual claim must cite at least one supplied chunk ID.
Do not place fabricated quotations in the answer.
"""


def build_user_prompt(
    question: ProjectQuestion,
    retrieval: RetrievalResult,
    assessment: EvidenceAssessment,
) -> str:
    evidence = [
        {
            "chunk_id": item.chunk.id,
            "document": item.chunk.citation.document_name,
            "page": item.chunk.page_number,
            "sheet": item.chunk.citation.sheet_number,
            "specification_section": item.chunk.citation.specification_section,
            "content": item.chunk.content,
        }
        for item in retrieval.evidence
    ]
    return json.dumps(
        {
            "project_id": question.project_id,
            "question": question.question,
            "deterministic_evidence_assessment": assessment.model_dump(mode="json"),
            "evidence": evidence,
        },
        ensure_ascii=False,
    )
