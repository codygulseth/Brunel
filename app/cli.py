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
from app.change_cli import COMMANDS as CHANGE_COMMANDS, register_change_commands, run_change_command
from app.rfi_cli import COMMANDS as RFI_COMMANDS, register_rfi_commands, run_rfi_command
from app.submittal_cli import (
    COMMANDS as SUBMITTAL_COMMANDS,
    register_submittal_commands,
    run_submittal_command,
)
from change_workflow.qa import OperationalQuestionService
from change_workflow.repository import JsonChangeWorkflowRepository
from revision_intelligence.alignment import BlockAlignmentService
from revision_intelligence.errors import RevisionIntelligenceError
from revision_intelligence.lineage import RevisionLineageService
from revision_intelligence.models import ChangeReviewStatus, ComparisonRequest
from revision_intelligence.rendering import MarkdownComparisonRenderer
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.qa import ComparisonQuestionAnsweringService
from revision_intelligence.service import RevisionComparisonService
from rfi.qa import RFIQuestionService
from rfi.repository import JsonRFIRepository
from submittal.qa import SubmittalQuestionService
from submittal.repository import JsonSubmittalRepository

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="brunel", description="Brunel project tools")
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="Ingest a local PDF, TXT, or Markdown file")
    ingest.add_argument("--project-id", required=True, help="Project identifier")
    ingest.add_argument("--file", required=True, type=Path, help="Path to the source document")
    ingest.add_argument("--document-type", choices=[item.value for item in DocumentType])
    ingest.add_argument("--title")
    ingest.add_argument("--document-family-id")
    ingest.add_argument("--document-number")
    ingest.add_argument("--discipline")
    ingest.add_argument("--revision")
    ingest.add_argument("--revision-sequence", type=int)
    ingest.add_argument("--revision-date", type=date.fromisoformat, metavar="YYYY-MM-DD")
    ingest.add_argument("--sheet-number")
    ingest.add_argument("--specification-section")
    ingest.add_argument("--supersedes-document-id")

    search = commands.add_parser("search", help="Search ingested project evidence")
    search.add_argument("--project-id", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--top-k", type=int)
    _add_retrieval_filters(search)

    ask = commands.add_parser("ask", help="Ask a cited question about ingested project records")
    ask.add_argument("--project-id", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--top-k", type=int)

    compare = commands.add_parser("compare", help="Compare two ingested document revisions")
    compare.add_argument("--project-id", required=True)
    compare.add_argument("--old-document-id", required=True)
    compare.add_argument("--new-document-id", required=True)
    compare.add_argument("--output", type=Path)
    compare.add_argument("--format", choices=("json", "markdown"), default="markdown")
    compare.add_argument("--include-formatting", action="store_true")
    compare.add_argument("--force", action="store_true")
    compare.add_argument("--use-model", action="store_true")
    compare.add_argument("--no-model", action="store_true")

    revisions = commands.add_parser("revisions", help="List known revisions")
    revisions.add_argument("--project-id", required=True)
    revisions.add_argument("--document-family-id", required=True)

    comparison_list = commands.add_parser("comparison-list", help="List saved comparisons")
    comparison_list.add_argument("--project-id", required=True)
    comparison_show = commands.add_parser("comparison-show", help="Show a saved comparison")
    comparison_show.add_argument("--project-id", required=True)
    comparison_show.add_argument("--comparison-id", required=True)
    review = commands.add_parser("comparison-review", help="Update a finding review state")
    review.add_argument("--project-id", required=True)
    review.add_argument("--comparison-id", required=True)
    review.add_argument("--change-id", required=True)
    review.add_argument(
        "--status", choices=[item.value for item in ChangeReviewStatus], required=True
    )
    review.add_argument("--note")
    register_change_commands(commands)
    register_rfi_commands(commands)
    register_submittal_commands(commands)
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
    comparison_repository = JsonComparisonRepository(
        settings.data_directory / "revision-intelligence"
    )
    workflow_repository = JsonChangeWorkflowRepository(settings.data_directory / "change-workflow")
    if args.command in CHANGE_COMMANDS:
        return run_change_command(args, settings)
    if args.command in RFI_COMMANDS:
        return run_rfi_command(args, settings)
    if args.command in SUBMITTAL_COMMANDS:
        return run_submittal_command(args, settings)
    if args.command == "ingest":
        return _run_ingest(args, repository)
    if args.command == "search":
        return _run_search(args, repository, settings)
    if args.command == "ask":
        return _run_ask(args, repository, settings, comparison_repository, workflow_repository)
    if args.command == "compare":
        return _run_compare(args, repository, comparison_repository, settings)
    if args.command == "revisions":
        return _run_revisions(args, repository)
    if args.command == "comparison-list":
        return _run_comparison_list(args, comparison_repository)
    if args.command == "comparison-show":
        return _run_comparison_show(args, comparison_repository)
    if args.command == "comparison-review":
        return _run_comparison_review(args, comparison_repository)
    raise AssertionError(f"Unhandled command: {args.command}")


def _run_ingest(args: argparse.Namespace, repository: JsonDocumentRepository) -> int:
    service = DocumentIngestionService(repository)
    try:
        result = service.ingest(
            project_id=args.project_id,
            file_path=args.file,
            document_type=DocumentType(args.document_type) if args.document_type else None,
            document_family_id=args.document_family_id,
            document_number=args.document_number,
            discipline=args.discipline,
            title=args.title,
            revision=args.revision,
            revision_sequence=args.revision_sequence,
            revision_date=args.revision_date,
            sheet_number=args.sheet_number,
            specification_section=args.specification_section,
            supersedes_document_id=args.supersedes_document_id,
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
    args: argparse.Namespace,
    repository: JsonDocumentRepository,
    settings: Settings,
    comparisons: JsonComparisonRepository | None = None,
    workflow: JsonChangeWorkflowRepository | None = None,
) -> int:
    submittal_terms = (
        "submittal",
        "shop drawing",
        "product data",
        "approved package",
        "procurement release",
        "released for procurement",
    )
    if any(term in args.question.casefold() for term in submittal_terms):
        submittal_answer = SubmittalQuestionService(
            JsonSubmittalRepository(settings.data_directory / "submittals")
        ).answer(args.project_id, args.question)
        if submittal_answer.sufficient:
            print(f"Answer: {submittal_answer.answer}")
            print("Status: answered")
            print("Evidence type: cited specification, project record, and official response")
            for submittal_citation in submittal_answer.citations:
                print(
                    f"Source: {submittal_citation.citation.document_name} "
                    f"(page {submittal_citation.citation.page_number}, "
                    f"chunk {submittal_citation.citation.chunk_id})"
                )
            return 0
    rfi_terms = ("rfi", "request for information", "architect answered", "engineer confirm")
    if any(term in args.question.casefold() for term in rfi_terms):
        rfi_answer = RFIQuestionService(JsonRFIRepository(settings.data_directory / "rfi")).answer(
            args.project_id, args.question
        )
        if rfi_answer.sufficient:
            print(f"Answer: {rfi_answer.answer}")
            print("Status: answered")
            print("Evidence type: RFI record with source-document/official-response distinctions")
            for rfi_citation in rfi_answer.citations:
                print(
                    f"Source: {rfi_citation.citation.document_name} "
                    f"(page {rfi_citation.citation.page_number}, "
                    f"chunk {rfi_citation.citation.chunk_id})"
                )
            return 0
    operational_terms = (
        "assigned",
        "reviewing",
        "overdue",
        "unreviewed",
        "resolved",
        "disposition",
        "requires an rfi",
        "needs information",
        "project change",
    )
    if workflow is not None and any(term in args.question.casefold() for term in operational_terms):
        operational = OperationalQuestionService(workflow).answer(args.project_id, args.question)
        if operational.sufficient:
            record = operational.records[0]
            print(f"Answer: {operational.answer}")
            print("Status: answered")
            print("Evidence type: project_team_record")
            print(f"Project change: {record.id}")
            print(f"Source comparison: {record.evidence.comparison_id}")
            for label, operational_citation in (
                ("Old source", record.evidence.old_citation),
                ("New source", record.evidence.new_citation),
            ):
                if operational_citation:
                    print(
                        f"{label}: {operational_citation.document_name} (page {operational_citation.page_number}, chunk {operational_citation.chunk_id})"
                    )
            return 0
    if comparisons is not None and any(
        term in args.question.casefold() for term in ("changed", "change", "revision", "updated")
    ):
        comparison_answer = ComparisonQuestionAnsweringService(comparisons).answer(
            args.project_id, args.question
        )
        if comparison_answer.sufficient:
            print(f"Answer: {comparison_answer.answer}")
            print("Status: answered")
            print(f"Comparison: {comparison_answer.comparison_id}")
            evidence = comparison_answer.evidence[0]
            for label, source_citation, excerpt in (
                ("Old", evidence.old_citation, evidence.old_excerpt),
                ("New", evidence.new_citation, evidence.new_excerpt),
            ):
                if source_citation and excerpt:
                    print(
                        f"{label} source: {source_citation.document_name} (page {source_citation.page_number}, chunk {source_citation.chunk_id})"
                    )
                    print(f"    {excerpt}")
            return 0
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


def _run_compare(
    args: argparse.Namespace,
    documents: JsonDocumentRepository,
    comparisons: JsonComparisonRepository,
    settings: Settings,
) -> int:
    if args.use_model and not args.no_model:
        print(
            "Warning: model-assisted comparison is not configured; deterministic analysis was used."
        )
    service = RevisionComparisonService(
        documents,
        comparisons,
        aligner=BlockAlignmentService(
            settings.revisions.alignment_similarity_threshold,
            settings.revisions.ambiguous_match_threshold,
        ),
    )
    try:
        result = service.compare(
            ComparisonRequest(
                project_id=args.project_id,
                old_document_id=args.old_document_id,
                new_document_id=args.new_document_id,
                force=args.force,
                include_formatting=args.include_formatting,
                use_model=args.use_model and not args.no_model,
            )
        )
    except (RevisionIntelligenceError, ValueError, OSError) as exc:
        print(f"Comparison failed: {exc}")
        return 1
    rendered = (
        result.model_dump_json(indent=2)
        if args.format == "json"
        else MarkdownComparisonRenderer().render(result)
    )
    if args.output:
        try:
            target = args.output.expanduser().resolve()
            workspace_root = Path.cwd().resolve()
            if target != workspace_root and workspace_root not in target.parents:
                raise ValueError("Report output must stay within the current workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(rendered, encoding="utf-8")
            print(f"Report written: {target}")
        except (OSError, ValueError) as exc:
            print(f"Report writing failed: {exc}")
            return 1
    else:
        print(rendered)
    print(f"Comparison ID: {result.id}")
    return 0


def _run_revisions(args: argparse.Namespace, repository: JsonDocumentRepository) -> int:
    documents = tuple(
        item
        for item in repository.list_by_project(args.project_id)
        if item.document.document_family_id == args.document_family_id
    )
    if not documents:
        print("No revisions found.")
        return 1
    lineage = RevisionLineageService().build(documents)
    for item in lineage.revisions:
        doc = item.document
        print(
            f"{doc.revision_sequence if doc.revision_sequence is not None else '-'}\t{doc.document_id}\t{doc.revision or 'unknown'}\t{doc.revision_date or 'unknown'}\t{doc.status or 'unknown'}"
        )
    return 0


def _run_comparison_list(args: argparse.Namespace, repository: JsonComparisonRepository) -> int:
    items = repository.list_by_project(args.project_id)
    for item in items:
        print(
            f"{item.id}\t{item.old_document.document_id} -> {item.new_document.document_id}\t{item.status.value}"
        )
    return 0


def _run_comparison_show(args: argparse.Namespace, repository: JsonComparisonRepository) -> int:
    item = repository.get(args.comparison_id)
    if item is None or item.project_id != args.project_id:
        print("Comparison not found in requested project.")
        return 1
    print(MarkdownComparisonRenderer().render(item))
    return 0


def _run_comparison_review(args: argparse.Namespace, repository: JsonComparisonRepository) -> int:
    item = repository.get(args.comparison_id)
    if item is None or item.project_id != args.project_id:
        print("Comparison not found in requested project.")
        return 1
    found = False
    updated = []
    for change in item.changes:
        if change.id == args.change_id:
            change = change.model_copy(
                update={
                    "review_status": ChangeReviewStatus(args.status),
                    "reviewer_note": args.note,
                }
            )
            found = True
        updated.append(change)
    if not found:
        print("Change not found.")
        return 1
    repository.save(item.model_copy(update={"changes": tuple(updated)}))
    print(f"Updated {args.change_id} to {args.status}.")
    return 0


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
