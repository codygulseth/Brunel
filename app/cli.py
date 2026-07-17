"""Command-line entry point for Brunel development workflows."""

import argparse
import logging
from datetime import date
from pathlib import Path

from config import get_settings
from config.settings import Settings
from core.logging import configure_logging
from document_processing import DocumentIngestionService, DocumentType, IngestionError
from rag import (
    CitationBuilder,
    CitedQuestionAnsweringService,
    ExtractiveAnswerProvider,
    LocalProjectRetriever,
    OpenAICompatibleClient,
    ProjectQuestion,
    RetrievalFilters,
    RetrievalQuery,
    StructuredModelAnswerProvider,
)
from rag.interfaces import GroundedAnswerProvider
from storage import JsonDocumentRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brunel", description="Brunel project tools")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Ingest a local PDF, TXT, or Markdown file")
    ingest.add_argument("--project-id", required=True, help="Project identifier")
    ingest.add_argument("--file", required=True, type=Path, help="Path to the source document")
    ingest.add_argument("--document-type", choices=[item.value for item in DocumentType])
    ingest.add_argument("--title")
    ingest.add_argument("--revision")
    ingest.add_argument("--revision-date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    ingest.add_argument("--sheet-number")
    ingest.add_argument("--specification-section")

    search = commands.add_parser("search", help="Search ingested project evidence")
    search.add_argument("--project-id", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int)
    _add_retrieval_filters(search)

    ask = commands.add_parser("ask", help="Ask a cited question about ingested project records")
    ask.add_argument("--project-id", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--top-k", type=int)
    return parser


def _add_retrieval_filters(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--document-type", choices=[item.value for item in DocumentType])
    parser.add_argument("--document-id")
    parser.add_argument("--page-number", type=int)
    parser.add_argument("--sheet-number")
    parser.add_argument("--specification-section")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.logging)
    repository = JsonDocumentRepository(settings.data_directory / "ingested")
    if args.command == "ingest":
        return _run_ingest(args, repository)
    if args.command == "search":
        return _run_search(args, repository, settings)
    if args.command == "ask":
        return _run_ask(args, repository, settings)
    raise AssertionError(f"Unhandled command: {args.command}")


def _run_ingest(args: argparse.Namespace, repository: JsonDocumentRepository) -> int:
    service = DocumentIngestionService(repository)
    try:
        result = service.ingest(
            project_id=args.project_id,
            file_path=args.file,
            document_type=DocumentType(args.document_type) if args.document_type else None,
            title=args.title,
            revision=args.revision,
            revision_date=args.revision_date,
            sheet_number=args.sheet_number,
            specification_section=args.specification_section,
        )
    except (IngestionError, ValueError, OSError) as exc:
        logger.error("document_ingestion_failed", extra={"reason": str(exc)})
        print(f"Ingestion failed: {exc}")
        return 1
    print(
        f"Ingested {result.document.original_filename}: "
        f"{result.page_count} page(s), {result.chunk_count} chunk(s)"
    )
    print(f"Document ID: {result.document.document_id}")
    print(f"Stored at: {result.storage_location}")
    for warning in result.warnings:
        print(f"Warning: {warning}")
    return 0


def _run_search(
    args: argparse.Namespace, repository: JsonDocumentRepository, settings: Settings
) -> int:
    top_k = args.top_k or settings.retrieval.top_k
    try:
        query = RetrievalQuery(
            project_id=args.project_id,
            text=args.query,
            limit=top_k,
            minimum_relevance=settings.retrieval.minimum_relevance,
            filters=RetrievalFilters(
                document_type=DocumentType(args.document_type) if args.document_type else None,
                document_id=args.document_id,
                page_number=args.page_number,
                sheet_number=args.sheet_number,
                specification_section=args.specification_section,
            ),
        )
    except ValueError as exc:
        print(f"Search failed: {exc}")
        return 1
    result = LocalProjectRetriever(repository).retrieve(query)
    print(f"Retrieved {len(result.evidence)} evidence chunk(s).")
    for index, item in enumerate(result.evidence, start=1):
        citation = item.chunk.citation
        location = f"page {citation.page_number}"
        if citation.sheet_number:
            location += f", sheet {citation.sheet_number}"
        if citation.specification_section:
            location += f", spec {citation.specification_section}"
        print(f"[{index}] score={item.relevance_score:.3f} {citation.document_name} ({location})")
        print(f"    {item.chunk.content.strip()}")
    return 0


def _run_ask(
    args: argparse.Namespace, repository: JsonDocumentRepository, settings: Settings
) -> int:
    try:
        provider = _answer_provider(settings)
        top_k = args.top_k or settings.retrieval.top_k
        service = CitedQuestionAnsweringService(
            LocalProjectRetriever(repository),
            provider,
            citation_builder=CitationBuilder(settings.retrieval.citation_excerpt_length),
            default_top_k=top_k,
            minimum_relevance=settings.retrieval.minimum_relevance,
            maximum_evidence_chunks=settings.retrieval.maximum_evidence_chunks,
        )
        answer = service.answer(ProjectQuestion(project_id=args.project_id, question=args.question))
    except (ValueError, OSError) as exc:
        print(f"Question failed: {exc}")
        return 1
    print(f"Answer: {answer.answer}")
    print(f"Status: {answer.status.value}")
    print(f"Evidence: {answer.evidence_assessment.level.value}")
    print(f"Sources retrieved: {answer.retrieval_metadata.get('sources_retrieved', 0)}")
    for index, citation in enumerate(answer.citations, start=1):
        location = f"page {citation.page_number}"
        if citation.sheet_number:
            location += f", sheet {citation.sheet_number}"
        if citation.specification_section:
            location += f", spec {citation.specification_section}"
        label = (
            f"{citation.document_title} [{citation.document_name}]"
            if citation.document_title
            else citation.document_name
        )
        print(f"[{index}] {label} ({location})")
        print(f"    {citation.excerpt}")
    for unresolved in answer.unresolved_questions:
        print(f"Unresolved: {unresolved}")
    return 0 if answer.status.value != "failed" else 1


def _answer_provider(settings: Settings) -> GroundedAnswerProvider:
    provider = settings.answers.provider.lower()
    if provider == "extractive":
        return ExtractiveAnswerProvider(
            settings.retrieval.maximum_evidence_chunks,
            settings.retrieval.citation_excerpt_length,
        )
    if provider == "openai_compatible":
        model = settings.models
        if not model.base_url or not model.model_name or not model.api_key:
            raise ValueError(
                "OpenAI-compatible answering requires BRUNEL_MODEL_BASE_URL, "
                "BRUNEL_MODEL_NAME, and BRUNEL_MODEL_API_KEY"
            )
        client = OpenAICompatibleClient(
            base_url=model.base_url,
            model=model.model_name,
            api_key=model.api_key,
            temperature=model.temperature,
        )
        return StructuredModelAnswerProvider(client, model.structured_output_retry_limit)
    raise ValueError(f"Unsupported answer provider: {settings.answers.provider}")


if __name__ == "__main__":
    raise SystemExit(main())
