from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from pypdf import PdfWriter
from reportlab.pdfgen import canvas

from app.cli import main as cli_main
from document_processing import (
    ChunkingSettings,
    CitationReference,
    DeterministicTextChunker,
    DocumentIngestionService,
    DocumentType,
    EmptyDocumentError,
    SourceFileNotFoundError,
    UnsupportedFileTypeError,
)
from storage import JsonDocumentRepository


@pytest.fixture
def repository(tmp_path: Path) -> JsonDocumentRepository:
    return JsonDocumentRepository(tmp_path / "ingested")


@pytest.fixture
def service(repository: JsonDocumentRepository) -> DocumentIngestionService:
    return DocumentIngestionService(
        repository,
        chunker=DeterministicTextChunker(ChunkingSettings(chunk_size=80, overlap=15)),
        clock=lambda: datetime(2026, 7, 16, 12, 0, tzinfo=UTC),
    )


@pytest.fixture
def synthetic_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic_project_record.pdf"
    pdf = canvas.Canvas(str(path))
    pdf.drawString(72, 720, "Synthetic Page One - electrical coordination notes")
    pdf.showPage()
    pdf.drawString(72, 720, "Synthetic Page Two - commissioning readiness notes")
    pdf.showPage()
    pdf.showPage()  # intentionally image/text-free to verify warning behavior
    pdf.save()
    return path


def test_txt_ingestion(service: DocumentIngestionService, tmp_path: Path):
    source = tmp_path / "meeting_notes.txt"
    source.write_text("Synthetic coordination notes for testing only.", encoding="utf-8")

    result = service.ingest(project_id="demo-project", file_path=source)

    assert result.page_count == 1
    assert result.chunk_count == 1
    assert result.document.original_filename == source.name
    assert result.document.document_type == DocumentType.UNKNOWN
    assert result.document.title is None


def test_markdown_ingestion_retains_explicit_heading(
    service: DocumentIngestionService, repository: JsonDocumentRepository, tmp_path: Path
):
    source = tmp_path / "synthetic_submittal.md"
    source.write_text("# Synthetic Submittal Log\n\nNo real project data.", encoding="utf-8")

    result = service.ingest(
        project_id="demo-project",
        file_path=source,
        document_type=DocumentType.SUBMITTAL,
        revision="A",
        revision_date=date(2026, 7, 1),
        specification_section="26 05 00",
    )
    stored = repository.get(result.document.document_id)

    assert stored is not None
    assert stored.document.title == "Synthetic Submittal Log"
    assert stored.document.revision == "A"
    assert stored.document.revision_date == date(2026, 7, 1)
    assert stored.chunks[0].citation.specification_section == "26 05 00"


def test_pdf_extracts_page_by_page_and_warns_for_empty_page(
    service: DocumentIngestionService, repository: JsonDocumentRepository, synthetic_pdf: Path
):
    result = service.ingest(project_id="demo-project", file_path=synthetic_pdf)
    stored = repository.get(result.document.document_id)

    assert stored is not None
    assert result.page_count == 3
    assert "Page One" in stored.pages[0].content
    assert "Page Two" in stored.pages[1].content
    assert stored.pages[2].content == ""
    assert any("image-only" in warning for warning in result.warnings)


def test_chunk_ids_are_stable_for_unchanged_content(
    service: DocumentIngestionService, repository: JsonDocumentRepository, tmp_path: Path
):
    source = tmp_path / "stable.txt"
    source.write_text("stable content " * 40, encoding="utf-8")

    first = service.ingest(project_id="demo-project", file_path=source)
    first_record = repository.get(first.document.document_id)
    second = service.ingest(project_id="demo-project", file_path=source)
    second_record = repository.get(second.document.document_id)

    assert first.document.document_id == second.document.document_id
    assert first_record is not None and second_record is not None
    assert [chunk.id for chunk in first_record.chunks] == [
        chunk.id for chunk in second_record.chunks
    ]


def test_chunks_never_cross_pdf_page_boundaries(
    service: DocumentIngestionService, repository: JsonDocumentRepository, synthetic_pdf: Path
):
    result = service.ingest(project_id="demo-project", file_path=synthetic_pdf)
    stored = repository.get(result.document.document_id)

    assert stored is not None
    assert {chunk.page_number for chunk in stored.chunks} == {1, 2}
    for chunk in stored.chunks:
        if chunk.page_number == 1:
            assert "Page Two" not in chunk.content
        if chunk.page_number == 2:
            assert "Page One" not in chunk.content


def test_explicit_construction_metadata_and_citation_are_retained(
    service: DocumentIngestionService, repository: JsonDocumentRepository, tmp_path: Path
):
    source = tmp_path / "drawing-notes.txt"
    source.write_text("Synthetic drawing notes.", encoding="utf-8")
    result = service.ingest(
        project_id="project-42",
        file_path=source,
        document_type=DocumentType.DRAWING,
        title="Synthetic Electrical Plan",
        revision="2",
        sheet_number="E-101",
        parent_document_id="doc_parent",
    )
    stored = repository.get(result.document.document_id)

    assert stored is not None
    assert stored.document.project_id == "project-42"
    assert stored.document.sheet_number == "E-101"
    assert stored.document.parent_document_id == "doc_parent"
    assert stored.chunks[0].citation.document_name == source.name
    assert stored.chunks[0].citation.sheet_number == "E-101"
    assert stored.chunks[0].citation.source_location.endswith("#page=1")


def test_unsupported_file_type(service: DocumentIngestionService, tmp_path: Path):
    source = tmp_path / "unsupported.csv"
    source.write_text("not,supported", encoding="utf-8")
    with pytest.raises(UnsupportedFileTypeError, match="Unsupported file type"):
        service.ingest(project_id="demo-project", file_path=source)


def test_missing_file(service: DocumentIngestionService, tmp_path: Path):
    with pytest.raises(SourceFileNotFoundError, match="does not exist"):
        service.ingest(project_id="demo-project", file_path=tmp_path / "missing.pdf")


def test_empty_text_document(service: DocumentIngestionService, tmp_path: Path):
    source = tmp_path / "empty.txt"
    source.write_text("   \n", encoding="utf-8")
    with pytest.raises(EmptyDocumentError, match="No extractable text"):
        service.ingest(project_id="demo-project", file_path=source)


def test_zero_page_pdf_records_warning_without_inventing_page(
    service: DocumentIngestionService, tmp_path: Path
):
    source = tmp_path / "zero-pages.pdf"
    with source.open("wb") as output:
        PdfWriter().write(output)

    result = service.ingest(project_id="demo-project", file_path=source)

    assert result.page_count == 0
    assert result.chunk_count == 0
    assert result.warnings == ("PDF contains no pages",)


def test_storage_round_trip(service: DocumentIngestionService, repository, tmp_path: Path):
    source = tmp_path / "round-trip.txt"
    source.write_text("Synthetic storage round trip.", encoding="utf-8")
    result = service.ingest(project_id="demo-project", file_path=source)

    restored = repository.get(result.document.document_id)

    assert restored is not None
    assert restored.document == result.document
    assert restored.chunks[0].citation.chunk_id == restored.chunks[0].id


def test_citation_reference_validation():
    citation = CitationReference(
        document_id="doc_123",
        document_name="synthetic.pdf",
        page_number=7,
        sheet_number="M-201",
        specification_section=None,
        chunk_id="chk_123",
        source_location="C:/synthetic.pdf#page=7",
    )
    assert citation.page_number == 7
    assert citation.sheet_number == "M-201"


def test_cli_ingests_and_prints_summary(tmp_path: Path, monkeypatch, capsys):
    source = tmp_path / "cli.txt"
    source.write_text("Synthetic CLI content.", encoding="utf-8")
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(tmp_path / "cli-data"))
    from config import get_settings

    get_settings.cache_clear()
    exit_code = cli_main(["ingest", "--project-id", "demo-project", "--file", str(source)])
    get_settings.cache_clear()

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "1 page(s), 1 chunk(s)" in output
    assert "Document ID: doc_" in output
