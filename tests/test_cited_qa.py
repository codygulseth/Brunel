from pathlib import Path

import pytest

from app.cli import main as cli_main
from config import get_settings
from document_processing import DocumentIngestionService, DocumentType
from rag import (
    AnswerStatus,
    CitedQuestionAnsweringService,
    EvidenceLevel,
    ExtractiveAnswerProvider,
    LocalProjectRetriever,
    ProjectQuestion,
    RetrievalFilters,
    RetrievalQuery,
    StructuredModelAnswerProvider,
)
from rag.assessment import EvidenceAssessor
from rag.errors import InvalidStructuredOutputError
from storage import JsonDocumentRepository


@pytest.fixture
def knowledge_base(tmp_path: Path):
    repository = JsonDocumentRepository(tmp_path / "ingested")
    ingestion = DocumentIngestionService(repository)

    def add(
        filename: str,
        content: str,
        *,
        project: str = "project-alpha",
        document_type: DocumentType = DocumentType.SPECIFICATION,
        title: str | None = None,
        sheet: str | None = None,
        section: str | None = None,
        revision: str | None = None,
    ):
        path = tmp_path / filename
        path.write_text(content, encoding="utf-8")
        return ingestion.ingest(
            project_id=project,
            file_path=path,
            document_type=document_type,
            title=title,
            sheet_number=sheet,
            specification_section=section,
            revision=revision,
        )

    records = {
        "concrete": add(
            "concrete-spec.txt",
            "Generator pad concrete shall have a minimum compressive strength of 4,000 psi at 28 days.",
            title="Synthetic Cast-in-Place Concrete",
            section="03 30 00",
        ),
        "room": add(
            "room-finish.txt",
            "Room 105 shall have a finished ceiling height of 10 feet.",
            document_type=DocumentType.DRAWING,
            title="Synthetic Room Finish Plan",
            sheet="A-201",
        ),
        "electrical": add(
            "electrical-equipment.txt",
            "Electrical equipment submittals shall comply with Specification Section 26 05 00. "
            "Switchgear Submittal SUB-042 status: Approved.",
            title="Synthetic Electrical Requirements",
            section="26 05 00",
        ),
        "fire_r1": add(
            "fire-rating-r1.txt",
            "The electrical room wall shall have a 1 hour fire rating.",
            title="Synthetic Life Safety Revision 1",
            revision="1",
        ),
        "fire_r2": add(
            "fire-rating-r2.txt",
            "The electrical room wall shall have a 2 hour fire rating.",
            title="Synthetic Life Safety Revision 2",
            revision="2",
        ),
        "duplicate": add(
            "concrete-spec-copy.txt",
            "Generator pad concrete shall have a minimum compressive strength of 4,000 psi at 28 days.",
            title="Synthetic Duplicate",
            section="03 30 00",
        ),
        "unrelated": add(
            "unrelated-project.txt",
            "Generator pad concrete shall have a minimum compressive strength of 9,000 psi.",
            project="project-beta",
            title="Unrelated Project Specification",
        ),
    }
    return repository, records, tmp_path


@pytest.fixture
def retriever(knowledge_base):
    return LocalProjectRetriever(knowledge_base[0])


def test_project_scoped_retrieval_and_no_cross_project_leakage(retriever):
    result = retriever.retrieve(
        RetrievalQuery(project_id="project-alpha", text="generator pad concrete strength")
    )

    assert result.evidence
    assert all(item.chunk.project_id == "project-alpha" for item in result.evidence)
    assert all("9,000 psi" not in item.chunk.content for item in result.evidence)


def test_relevant_chunk_ranks_first(retriever):
    result = retriever.retrieve(
        RetrievalQuery(project_id="project-alpha", text="generator pad concrete strength")
    )
    assert "4,000 psi" in result.evidence[0].chunk.content


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("A-201", "Room 105"),
        ("26 05 00", "Electrical equipment"),
        ("Room 105 ceiling height", "10 feet"),
        ("SUB-042", "Approved"),
    ],
)
def test_exact_construction_identifier_searches(retriever, query, expected):
    result = retriever.retrieve(RetrievalQuery(project_id="project-alpha", text=query))
    assert result.evidence
    assert expected in result.evidence[0].chunk.content
    assert result.evidence[0].matched_identifiers


def test_metadata_filters(retriever, knowledge_base):
    document_id = knowledge_base[1]["room"].document.document_id
    result = retriever.retrieve(
        RetrievalQuery(
            project_id="project-alpha",
            text="ceiling height",
            filters=RetrievalFilters(
                document_type=DocumentType.DRAWING,
                document_id=document_id,
                page_number=1,
                sheet_number="A-201",
            ),
        )
    )
    assert len(result.evidence) == 1
    assert result.evidence[0].chunk.citation.sheet_number == "A-201"

    specification = retriever.retrieve(
        RetrievalQuery(
            project_id="project-alpha",
            text="electrical equipment",
            filters=RetrievalFilters(specification_section="26 05 00"),
        )
    )
    assert len(specification.evidence) == 1
    assert specification.evidence[0].chunk.citation.specification_section == "26 05 00"


def test_empty_retrieval_result(retriever):
    result = retriever.retrieve(
        RetrievalQuery(project_id="project-alpha", text="zoological habitat requirement")
    )
    assert result.evidence == ()


def test_duplicate_evidence_is_removed(retriever):
    result = retriever.retrieve(
        RetrievalQuery(project_id="project-alpha", text="generator pad concrete strength")
    )
    assert result.duplicates_removed == 1
    assert sum("4,000 psi" in item.chunk.content for item in result.evidence) == 1


def test_citation_metadata_and_exact_excerpt(retriever):
    service = CitedQuestionAnsweringService(retriever, ExtractiveAnswerProvider())
    answer = service.answer(
        ProjectQuestion(
            project_id="project-alpha",
            question="What concrete strength is required for the generator pad?",
        )
    )

    assert answer.status == AnswerStatus.ANSWERED
    citation = answer.citations[0]
    assert citation.document_name == "concrete-spec.txt"
    assert citation.page_number == 1
    assert citation.specification_section == "03 30 00"
    evidence = retriever.retrieve(
        RetrievalQuery(project_id="project-alpha", text="generator pad concrete strength")
    )
    source_chunk = next(
        item.chunk for item in evidence.evidence if item.chunk.id == citation.chunk_id
    )
    assert citation.excerpt in source_chunk.content


def test_insufficient_evidence_response(retriever):
    service = CitedQuestionAnsweringService(retriever, ExtractiveAnswerProvider())
    answer = service.answer(
        ProjectQuestion(project_id="project-alpha", question="What is the roofing warranty?")
    )
    assert answer.status == AnswerStatus.INSUFFICIENT_EVIDENCE
    assert answer.citations == ()
    assert answer.answer == "The provided project documents do not establish this."


def test_partial_answer(retriever):
    service = CitedQuestionAnsweringService(retriever, ExtractiveAnswerProvider())
    answer = service.answer(
        ProjectQuestion(
            project_id="project-alpha",
            question="What is the generator pad concrete strength and curing procedure?",
        )
    )
    assert answer.status == AnswerStatus.PARTIALLY_ANSWERED
    assert answer.citations
    assert answer.unresolved_questions


def test_conflicting_evidence_is_presented(retriever):
    service = CitedQuestionAnsweringService(retriever, ExtractiveAnswerProvider())
    answer = service.answer(
        ProjectQuestion(
            project_id="project-alpha",
            question="What fire rating is required for the electrical room wall?",
        )
    )
    assert answer.status == AnswerStatus.CONFLICTING_EVIDENCE
    assert answer.evidence_assessment.level == EvidenceLevel.CONFLICTING
    assert "1 hour" in answer.answer and "2 hour" in answer.answer
    assert len(answer.citations) >= 2


class FailingProvider:
    def generate(self, question, retrieval, assessment):
        raise RuntimeError("synthetic provider failure")


def test_provider_failure_fails_safely(retriever):
    answer = CitedQuestionAnsweringService(retriever, FailingProvider()).answer(
        ProjectQuestion(project_id="project-alpha", question="What is the Room 105 ceiling height?")
    )
    assert answer.status == AnswerStatus.FAILED
    assert answer.citations == ()
    assert "validated" in answer.answer


class InvalidClient:
    def __init__(self):
        self.calls = 0

    def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        self.calls += 1
        return "not valid structured output"


def test_invalid_structured_output_retries_then_raises(retriever):
    retrieval = retriever.retrieve(
        RetrievalQuery(project_id="project-alpha", text="Room 105 ceiling height")
    )
    assessment = EvidenceAssessor().assess(retrieval)
    client = InvalidClient()
    provider = StructuredModelAnswerProvider(client, retry_limit=1)

    with pytest.raises(InvalidStructuredOutputError):
        provider.generate(
            ProjectQuestion(project_id="project-alpha", question="Room 105 ceiling height?"),
            retrieval,
            assessment,
        )
    assert client.calls == 2


def test_invalid_structured_output_returns_failed_answer(retriever):
    provider = StructuredModelAnswerProvider(InvalidClient(), retry_limit=0)
    answer = CitedQuestionAnsweringService(retriever, provider).answer(
        ProjectQuestion(project_id="project-alpha", question="What is the Room 105 ceiling height?")
    )
    assert answer.status == AnswerStatus.FAILED
    assert answer.citations == ()


def test_deterministic_retrieval(retriever):
    query = RetrievalQuery(project_id="project-alpha", text="electrical equipment submittals")
    first = retriever.retrieve(query)
    second = retriever.retrieve(query)
    assert [item.chunk.id for item in first.evidence] == [item.chunk.id for item in second.evidence]
    assert [item.relevance_score for item in first.evidence] == [
        item.relevance_score for item in second.evidence
    ]


def test_qa_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("BRUNEL_RETRIEVAL_TOP_K", "7")
    monkeypatch.setenv("BRUNEL_MINIMUM_RELEVANCE", "0.2")
    monkeypatch.setenv("BRUNEL_CITATION_EXCERPT_LENGTH", "180")
    monkeypatch.setenv("BRUNEL_MAXIMUM_EVIDENCE_CHUNKS", "6")
    monkeypatch.setenv("BRUNEL_ANSWER_PROVIDER", "extractive")
    get_settings.cache_clear()
    settings = get_settings()
    get_settings.cache_clear()

    assert settings.retrieval.top_k == 7
    assert settings.retrieval.minimum_relevance == 0.2
    assert settings.retrieval.citation_excerpt_length == 180
    assert settings.retrieval.maximum_evidence_chunks == 6
    assert settings.answers.provider == "extractive"


def test_cli_search_and_ask(knowledge_base, monkeypatch, capsys):
    repository = knowledge_base[0]
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(repository.root.parent))
    get_settings.cache_clear()

    search_code = cli_main(
        [
            "search",
            "--project-id",
            "project-alpha",
            "--query",
            "Room 105 ceiling height",
            "--top-k",
            "3",
        ]
    )
    search_output = capsys.readouterr().out
    ask_code = cli_main(
        [
            "ask",
            "--project-id",
            "project-alpha",
            "--question",
            "What is the Room 105 ceiling height?",
        ]
    )
    ask_output = capsys.readouterr().out
    get_settings.cache_clear()

    assert search_code == 0 and "Room 105" in search_output and "score=" in search_output
    assert ask_code == 0
    assert "Status: answered" in ask_output
    assert "room-finish.txt" in ask_output
    assert "10 feet" in ask_output
