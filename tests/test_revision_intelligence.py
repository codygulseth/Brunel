from pathlib import Path

import pytest

from app.cli import main as cli_main
from config import get_settings
from document_processing import DocumentIngestionService, DocumentType
from revision_intelligence.alignment import BlockAlignmentService
from revision_intelligence.differ import TokenDiffer
from revision_intelligence.errors import CrossProjectComparisonError, DocumentsNotComparableError
from revision_intelligence.lineage import RevisionLineageService
from revision_intelligence.models import ChangeCategory, ChangeType, ComparisonRequest
from revision_intelligence.normalization import ContentNormalizer
from revision_intelligence.qa import ComparisonQuestionAnsweringService
from revision_intelligence.rendering import MarkdownComparisonRenderer
from revision_intelligence.repository import JsonComparisonRepository
from revision_intelligence.service import RevisionComparisonService
from storage import JsonDocumentRepository


@pytest.fixture
def revision_project(tmp_path: Path):
    documents = JsonDocumentRepository(tmp_path / "ingested")
    comparisons = JsonComparisonRepository(tmp_path / "revision-intelligence")
    ingestion = DocumentIngestionService(documents)
    old_path = tmp_path / "concrete-rev-1.txt"
    new_path = tmp_path / "concrete-rev-2.txt"
    old_path.write_text(
        "1.1 Generator pad concrete shall be 3,000 psi.\n"
        "1.2 Contractor is responsible for testing.\n"
        "1.3 Provide two equipment pads with a seven-day curing period.",
        encoding="utf-8",
    )
    new_path.write_text(
        "1.1 Generator pad concrete shall be 4,000 psi.\n"
        "1.2 Independent testing agency is responsible for testing.\n"
        "1.3 Provide three equipment pads with a fourteen-day curing period.\n"
        "1.4 Testing report shall be submitted before startup.",
        encoding="utf-8",
    )
    kwargs = dict(
        project_id="demo-project",
        document_type=DocumentType.SPECIFICATION,
        document_family_id="concrete-spec",
        title="Concrete Specification",
        specification_section="03 30 00",
    )
    old = ingestion.ingest(file_path=old_path, revision="1", revision_sequence=1, **kwargs)
    new = ingestion.ingest(
        file_path=new_path,
        revision="2",
        revision_sequence=2,
        supersedes_document_id=old.document.document_id,
        **kwargs,
    )
    return documents, comparisons, old, new, tmp_path


def test_lineage_orders_explicit_revisions(revision_project):
    documents, _, old, new, _ = revision_project
    lineage = RevisionLineageService().build(
        (documents.get(new.document.document_id), documents.get(old.document.document_id))
    )
    assert [item.document.revision for item in lineage.revisions] == ["1", "2"]
    assert not lineage.inferred


def test_cross_project_rejected(revision_project, tmp_path):
    documents, _, old, _, _ = revision_project
    path = tmp_path / "other.txt"
    path.write_text("Concrete shall be 3,000 psi.", encoding="utf-8")
    other = DocumentIngestionService(documents).ingest(project_id="other", file_path=path)
    with pytest.raises(CrossProjectComparisonError):
        RevisionLineageService().assess(
            documents.get(old.document.document_id), documents.get(other.document.document_id)
        )


def test_normalization_preserves_exact_source_span(revision_project):
    documents, _, old, _, _ = revision_project
    units = ContentNormalizer().normalize(documents.get(old.document.document_id))
    assert units[0].identifier == "1.1"
    assert units[0].span.source_text in documents.get(old.document.document_id).chunks[0].content
    assert "3,000 psi" in units[0].span.source_text


def test_alignment_and_token_diff_detect_numeric_responsibility_changes(revision_project):
    documents, _, old, new, _ = revision_project
    norm = ContentNormalizer()
    alignment = BlockAlignmentService().align(
        norm.normalize(documents.get(old.document.document_id)),
        norm.normalize(documents.get(new.document.document_id)),
    )
    assert len(alignment.matches) == 3 and len(alignment.added) == 1
    kind, diff = TokenDiffer().diff(
        alignment.matches[0].old_unit.span.source_text,
        alignment.matches[0].new_unit.span.source_text,
    )
    assert kind == ChangeType.MODIFIED and "numeric_change" in diff.signals


def test_end_to_end_comparison_citations_persistence_and_markdown(revision_project):
    documents, comparisons, old, new, _ = revision_project
    result = RevisionComparisonService(documents, comparisons).compare(
        ComparisonRequest(
            project_id="demo-project",
            old_document_id=old.document.document_id,
            new_document_id=new.document.document_id,
        )
    )
    assert result.summary.modified == 3 and result.summary.added == 1
    numeric = next(
        item for item in result.changes if "3,000 psi" in (item.evidence.old_excerpt or "")
    )
    assert ChangeCategory.QUANTITY in numeric.categories
    assert numeric.evidence.old_citation.document_id == old.document.document_id
    assert numeric.evidence.new_citation.document_id == new.document.document_id
    assert comparisons.get(result.id) == result
    assert not RevisionComparisonService(documents, comparisons).is_stale(result)
    markdown = MarkdownComparisonRenderer().render(result)
    assert "## Priority review" in markdown and "3,000 psi" in markdown and "4,000 psi" in markdown


def test_stable_comparison_ids_and_project_scoped_qa(revision_project):
    documents, comparisons, old, new, _ = revision_project
    request = ComparisonRequest(
        project_id="demo-project",
        old_document_id=old.document.document_id,
        new_document_id=new.document.document_id,
    )
    service = RevisionComparisonService(documents, comparisons)
    assert service.compare(request).id == service.compare(request).id
    answer = ComparisonQuestionAnsweringService(comparisons).answer(
        "demo-project", "Did concrete strength change?"
    )
    assert answer.sufficient and answer.evidence[0].old_citation and answer.evidence[0].new_citation
    assert (
        not ComparisonQuestionAnsweringService(comparisons)
        .answer("other", "concrete strength changed")
        .sufficient
    )


class FailingRevisionProvider:
    name = "synthetic-failing-provider"

    def summarize(self, changes):
        raise RuntimeError("synthetic provider outage")


def test_optional_revision_provider_failure_preserves_deterministic_result(revision_project):
    documents, comparisons, old, new, _ = revision_project
    result = RevisionComparisonService(
        documents,
        comparisons,
        analysis_provider=FailingRevisionProvider(),
    ).compare(
        ComparisonRequest(
            project_id="demo-project",
            old_document_id=old.document.document_id,
            new_document_id=new.document.document_id,
            use_model=True,
        )
    )

    assert result.summary.total_changes == 4
    assert result.provider_metadata["failed"] is True
    assert result.provider_metadata["deterministic"] is True
    assert any("failed safely" in warning for warning in result.warnings)


def test_unrelated_requires_force(revision_project, tmp_path):
    documents, comparisons, old, _, _ = revision_project
    path = tmp_path / "minutes.txt"
    path.write_text("Owner meeting agenda and attendees.", encoding="utf-8")
    unrelated = DocumentIngestionService(documents).ingest(
        project_id="demo-project",
        file_path=path,
        document_type=DocumentType.MEETING_MINUTES,
        title="Weekly Meeting",
    )
    service = RevisionComparisonService(documents, comparisons)
    with pytest.raises(DocumentsNotComparableError):
        service.compare(
            ComparisonRequest(
                project_id="demo-project",
                old_document_id=old.document.document_id,
                new_document_id=unrelated.document.document_id,
            )
        )
    forced = service.compare(
        ComparisonRequest(
            project_id="demo-project",
            old_document_id=old.document.document_id,
            new_document_id=unrelated.document.document_id,
            force=True,
        )
    )
    assert forced.comparability.forced and forced.warnings


def test_cli_compare_list_show_and_revision_qa(revision_project, monkeypatch, capsys):
    _, _, old, new, tmp_path = revision_project
    monkeypatch.setenv("BRUNEL_DATA_DIRECTORY", str(tmp_path))
    get_settings.cache_clear()
    output = tmp_path / "reports" / "comparison.md"
    assert (
        cli_main(
            [
                "compare",
                "--project-id",
                "demo-project",
                "--old-document-id",
                old.document.document_id,
                "--new-document-id",
                new.document.document_id,
                "--output",
                str(output),
            ]
        )
        == 0
    )
    text = capsys.readouterr().out
    comparison_id = text.split("Comparison ID: ")[1].strip()
    assert output.is_file()
    assert cli_main(["comparison-list", "--project-id", "demo-project"]) == 0
    assert (
        cli_main(
            ["comparison-show", "--project-id", "demo-project", "--comparison-id", comparison_id]
        )
        == 0
    )
    assert (
        cli_main(
            [
                "ask",
                "--project-id",
                "demo-project",
                "--question",
                "What changed in concrete strength?",
            ]
        )
        == 0
    )
    assert "Old source:" in capsys.readouterr().out
    get_settings.cache_clear()
