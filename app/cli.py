"""Command-line entry point for Brunel development workflows."""

import argparse
import logging
from datetime import date
from pathlib import Path

from config import get_settings
from core.logging import configure_logging
from document_processing import DocumentIngestionService, DocumentType, IngestionError
from storage import JsonDocumentRepository


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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.logging)
    repository = JsonDocumentRepository(settings.data_directory / "ingested")
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
        logging.getLogger(__name__).error("document_ingestion_failed", extra={"reason": str(exc)})
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


if __name__ == "__main__":
    raise SystemExit(main())
