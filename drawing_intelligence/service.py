# ruff: noqa: F403, F405
"""Drawing-set ingestion, validation, review, search, OCR, graph, and comparison services."""

from datetime import UTC, date, datetime
from hashlib import sha256
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from document_processing import DocumentIngestionService, DocumentType
from storage import JsonDocumentRepository
from .extraction import (
    citation,
    classify,
    extract_keynotes,
    extract_references,
    full_region,
    parse_index,
    sheet_metadata,
)
from .models import *  # noqa: F403, F405
from .ocr import DisabledOCRProvider, OCRProvider, run_ocr
from .rendering import NullPageRenderer, PageRenderer
from .repository import JsonDrawingRepository
from .templates import TitleBlockTemplateRegistry


class DrawingIntelligenceService:
    def __init__(
        self,
        documents: JsonDocumentRepository,
        repository: JsonDrawingRepository,
        *,
        renderer: PageRenderer | None = None,
        ocr_provider: OCRProvider | None = None,
    ):
        self.documents = documents
        self.repository = repository
        self.renderer = renderer or NullPageRenderer()
        self.ocr_provider = ocr_provider or DisabledOCRProvider()

    def ingest(
        self,
        *,
        project_id: str,
        file_path: Path,
        set_title: str | None = None,
        revision_label: str | None = None,
        revision_sequence: int | None = None,
        issue_date: date | None = None,
        issue_purpose: str | None = None,
        predecessor_revision_id: str | None = None,
        title_block_template_id: str | None = None,
        created_by: str = "system",
    ) -> DrawingAnalysis:
        if file_path.suffix.casefold() != ".pdf":
            raise ValueError("drawing sets must be PDF files")
        family = f"drawings_{sha256((project_id + '\0' + (set_title or file_path.stem)).encode()).hexdigest()[:16]}"
        ingested = DocumentIngestionService(self.documents).ingest(
            project_id=project_id,
            file_path=file_path,
            document_type=DocumentType.DRAWING,
            document_family_id=family,
            title=set_title,
            revision=revision_label,
            revision_sequence=revision_sequence,
            issue_date=issue_date,
        )
        revision_id = f"drev_{ingested.document.document_id[4:]}"
        prior = (
            self.repository.get_analysis(project_id, predecessor_revision_id)
            if predecessor_revision_id
            else None
        )
        template, template_method, template_review = TitleBlockTemplateRegistry().select(
            title_block_template_id
        )
        sheets = []
        regions = []
        index_entries = []
        render_warnings = []
        aggregate = self.documents.get(ingested.document.document_id)
        assert aggregate is not None
        for page in aggregate.pages:
            rendered = self.renderer.render(
                file_path, page.page_number, ingested.document.content_hash
            )
            if rendered.warning:
                render_warnings.append(f"Page {page.page_number}: {rendered.warning}")
            region = full_region(
                project_id,
                ingested.document.document_id,
                revision_id,
                page.page_number,
                max(1, rendered.width),
                max(1, rendered.height),
                rendered.reference,
                page.content,
            )
            regions.append(region)
            index_entries.extend(parse_index(page.content, region))
            number, title, revision = sheet_metadata(page.content)
            if not number:
                continue
            discipline, prefix, _ = classify(number)
            stable = f"sheet_{sha256((project_id + '\0' + number).encode()).hexdigest()[:20]}"
            sheet_revision_id = f"srev_{sha256((revision_id + '\0' + str(page.page_number)).encode()).hexdigest()[:20]}"
            readable = DrawingReadabilityAssessment(
                page_number=page.page_number,
                status=ReadabilityStatus.VECTOR_TEXT_READABLE
                if len(page.content.strip()) >= 20
                else ReadabilityStatus.OCR_RECOMMENDED,
                native_text_characters=len(page.content.strip()),
                native_vector_text_present=bool(page.content.strip()),
                ocr_recommended=len(page.content.strip()) < 20,
                warnings=("Native text is limited; controlled OCR may be requested",)
                if len(page.content.strip()) < 20
                else (),
            )
            sheets.append(
                DrawingSheet(
                    stable_sheet_id=stable,
                    sheet_revision_id=sheet_revision_id,
                    project_id=project_id,
                    drawing_set_revision_id=revision_id,
                    source_document_id=ingested.document.document_id,
                    source_page_number=page.page_number,
                    sheet_number=number,
                    original_sheet_prefix=prefix,
                    sheet_title=title,
                    discipline=discipline,
                    revision=revision,
                    issue_date=issue_date,
                    issue_purpose=issue_purpose,
                    content_hash=sha256(page.content.encode()).hexdigest(),
                    render_reference=rendered.reference,
                    readability=readable,
                    warnings=(rendered.warning,) if rendered.warning else (),
                )
            )
        sheet_by_page = {s.source_page_number: s for s in sheets}
        refs = []
        keynotes = []
        for page, region in zip(aggregate.pages, regions):
            sheet = sheet_by_page.get(page.page_number)
            if sheet:
                refs.extend(
                    extract_references(project_id, revision_id, sheet, page.content, region)
                )
                keynotes.extend(extract_keynotes(sheet, page.content, region))
        by_number = {s.sheet_number: s for s in sheets if s.sheet_number}
        refs = [
            r.model_copy(
                update={
                    "resolved": r.target_sheet_number in by_number,
                    "target_sheet_revision_id": by_number[r.target_sheet_number].sheet_revision_id
                    if r.target_sheet_number in by_number
                    else None,
                }
            )
            for r in refs
        ]
        index = (
            DrawingIndex(
                id=f"index_{uuid4().hex}",
                drawing_set_revision_id=revision_id,
                entries=tuple(index_entries),
                source_pages=tuple(sorted({e.citation.page_number for e in index_entries})),
            )
            if index_entries
            else None
        )
        issues = self._validate(revision_id, sheets, index, refs, regions)
        now = datetime.now(UTC)
        revision = DrawingSetRevision(
            drawing_set_id=family,
            revision_id=revision_id,
            project_id=project_id,
            source_document_id=ingested.document.document_id,
            set_title=set_title,
            issue_purpose=issue_purpose,
            issue_date=issue_date,
            revision_label=revision_label,
            revision_sequence=revision_sequence,
            discipline_coverage=tuple(sorted({s.discipline for s in sheets}, key=str)),
            file_content_hash=ingested.document.content_hash,
            total_page_count=ingested.page_count,
            identified_sheet_count=len(sheets),
            unidentified_page_count=ingested.page_count - len(sheets),
            drawing_index_present=index is not None,
            supersedes_revision_id=predecessor_revision_id,
            created_at=now,
            created_by=created_by,
            warnings=tuple(render_warnings),
        )
        analysis = DrawingAnalysis(
            revision=revision,
            sheets=tuple(sheets),
            index=index,
            references=tuple(refs),
            regions=tuple(regions),
            validation=DrawingSetValidationResult(
                revision_id=revision_id, issues=issues, created_at=now
            ),
            graph=DrawingReferenceGraph(
                revision_id=revision_id,
                node_ids=tuple(s.sheet_revision_id for s in sheets),
                edges=tuple(refs),
            ),
            keynotes=tuple(keynotes),
            title_block_template=template,
            title_block_detection_method=template_method,
            title_block_human_review_required=template_review,
        )
        self.repository.save_analysis(analysis)
        self._event(
            project_id,
            "drawing_set_analysis_completed",
            revision_id,
            created_by,
            f"Analyzed {len(sheets)} sheets",
        )
        for issue in issues:
            self._event(project_id, issue.status.value, revision_id, "system", issue.message)
        if prior:
            self.compare(project_id, prior.revision.revision_id, revision_id)
        return analysis

    def _validate(
        self,
        revision_id: str,
        sheets: list[DrawingSheet],
        index: DrawingIndex | None,
        refs: list[DrawingReference],
        regions: list[VisualRegion],
    ) -> tuple[DrawingSetIssue, ...]:
        issues = []
        groups = {}
        for s in sheets:
            groups.setdefault(s.sheet_number, []).append(s)
        for number, values in groups.items():
            if len(values) > 1:
                issues.append(
                    DrawingSetIssue(
                        id=f"issue_{uuid4().hex}",
                        status=PresenceStatus.DUPLICATE_SHEET,
                        message=f"Duplicate sheet number {number}",
                        affected_sheet_revision_ids=tuple(s.sheet_revision_id for s in values),
                        citations=tuple(
                            citation(
                                regions[s.source_page_number - 1],
                                s.sheet_revision_id,
                                s.sheet_number,
                                s.sheet_title,
                            )
                            for s in values
                        ),
                        evidence_strength=1,
                    )
                )
        present = set(groups)
        indexed = {e.sheet_number: e for e in index.entries} if index else {}
        for number, e in indexed.items():
            if number not in present:
                issues.append(
                    DrawingSetIssue(
                        id=f"issue_{uuid4().hex}",
                        status=PresenceStatus.MISSING_SHEET,
                        message=f"Indexed sheet {number} is missing",
                        citations=(e.citation,),
                        evidence_strength=1,
                    )
                )
        for s in sheets:
            if index and s.sheet_number not in indexed:
                issues.append(
                    DrawingSetIssue(
                        id=f"issue_{uuid4().hex}",
                        status=PresenceStatus.UNINDEXED_SHEET,
                        message=f"Sheet {s.sheet_number} is not in the drawing index",
                        affected_sheet_revision_ids=(s.sheet_revision_id,),
                        evidence_strength=0.9,
                    )
                )
            elif (
                index
                and s.sheet_number in indexed
                and indexed[s.sheet_number].sheet_title
                and s.sheet_title
                and indexed[s.sheet_number].sheet_title.casefold() != s.sheet_title.casefold()
            ):
                issues.append(
                    DrawingSetIssue(
                        id=f"issue_{uuid4().hex}",
                        status=PresenceStatus.TITLE_MISMATCH,
                        message=f"Title block and index disagree for {s.sheet_number}",
                        affected_sheet_revision_ids=(s.sheet_revision_id,),
                        citations=(
                            indexed[s.sheet_number].citation,
                            citation(
                                regions[s.source_page_number - 1],
                                s.sheet_revision_id,
                                s.sheet_number,
                                s.sheet_title,
                            ),
                        ),
                        evidence_strength=1,
                    )
                )
        for r in refs:
            if not r.resolved:
                issues.append(
                    DrawingSetIssue(
                        id=f"issue_{uuid4().hex}",
                        status=PresenceStatus.MISSING_SHEET,
                        message=f"Reference points to missing sheet {r.target_sheet_number}",
                        affected_sheet_revision_ids=(r.source_sheet_revision_id,),
                        citations=(r.citation,),
                        evidence_strength=0.9,
                    )
                )
        return tuple(issues)

    def review_metadata(
        self,
        project_id: str,
        sheet_revision_id: str,
        updates: dict[str, str | None],
        reviewer_id: str,
    ) -> DrawingSheet:
        analysis = self._find_sheet(project_id, sheet_revision_id)
        sheet = next(s for s in analysis.sheets if s.sheet_revision_id == sheet_revision_id)
        allowed = {"sheet_number", "sheet_title", "revision", "discipline"}
        unknown = set(updates) - allowed
        if unknown:
            raise ValueError(f"unsupported metadata fields: {sorted(unknown)}")
        values = dict(updates)
        if "discipline" in values and values["discipline"] is not None:
            values["discipline"] = DrawingDiscipline(values["discipline"])
        values["human_confirmed_fields"] = tuple(
            sorted(set(sheet.human_confirmed_fields) | set(updates))
        )
        updated = sheet.model_copy(update=values)
        self.repository.replace_after_review(
            analysis.model_copy(
                update={
                    "sheets": tuple(
                        updated if s.sheet_revision_id == sheet_revision_id else s
                        for s in analysis.sheets
                    )
                }
            )
        )
        self._event(
            project_id,
            "sheet_metadata_reviewed",
            sheet_revision_id,
            reviewer_id,
            "Metadata reviewed",
        )
        return updated

    def request_ocr(self, project_id: str, sheet_revision_id: str) -> OCRResult:
        self._find_sheet(project_id, sheet_revision_id)
        result = run_ocr(self.ocr_provider, project_id, sheet_revision_id)
        self.repository.save_ocr(result)
        self._event(
            project_id,
            "ocr_completed" if result.successful else "ocr_failed",
            sheet_revision_id,
            "system",
            "OCR result stored separately from native text",
        )
        return result

    def search(
        self,
        project_id: str,
        query: str,
        *,
        revision_id: str | None = None,
        discipline: DrawingDiscipline | None = None,
    ) -> tuple[DrawingSheet, ...]:
        needle = query.casefold()
        found = []
        for a in self.repository.list_analyses(project_id):
            if revision_id and a.revision.revision_id != revision_id:
                continue
            page_text = {r.page_number: (r.text_span or "") for r in a.regions}
            for s in a.sheets:
                if discipline and s.discipline != discipline:
                    continue
                refs = " ".join(
                    r.exact_text
                    for r in a.references
                    if r.source_sheet_revision_id == s.sheet_revision_id
                )
                if (
                    needle
                    in f"{s.sheet_number} {s.sheet_title} {s.discipline} {page_text.get(s.source_page_number, '')} {refs}".casefold()
                ):
                    found.append(s)
        return tuple(found)

    def compare(
        self, project_id: str, old_revision_id: str, new_revision_id: str
    ) -> DrawingSetComparison:
        old = self.repository.get_analysis(project_id, old_revision_id)
        new = self.repository.get_analysis(project_id, new_revision_id)
        if not old or not new:
            raise ValueError("drawing revision not found in requested project")
        om = {s.sheet_number: s for s in old.sheets}
        nm = {s.sheet_number: s for s in new.sheets}
        changes = []
        sheet_changes = []
        lineage = []
        for number in sorted(set(om) | set(nm)):
            o = om.get(number)
            n = nm.get(number)
            local = []
            if not o:
                local.append(
                    DrawingSetChange(
                        change_type="sheet_added",
                        sheet_number=number,
                        summary=f"Sheet {number} added",
                        new_citation=self._sheet_cite(new, n),
                    )
                )
            elif not n:
                local.append(
                    DrawingSetChange(
                        change_type="sheet_removed",
                        sheet_number=number,
                        summary=f"Sheet {number} removed",
                        old_citation=self._sheet_cite(old, o),
                    )
                )
            else:
                if o.sheet_title != n.sheet_title:
                    local.append(
                        DrawingSetChange(
                            change_type="sheet_retitled",
                            sheet_number=number,
                            summary=f"Sheet title changed from {o.sheet_title} to {n.sheet_title}",
                            old_citation=self._sheet_cite(old, o),
                            new_citation=self._sheet_cite(new, n),
                        )
                    )
                if o.content_hash != n.content_hash:
                    local.append(
                        DrawingSetChange(
                            change_type="content_changed",
                            sheet_number=number,
                            summary="Native text or unparsed visual content changed; graphical meaning was not interpreted",
                            old_citation=self._sheet_cite(old, o),
                            new_citation=self._sheet_cite(new, n),
                            human_visual_review_required=True,
                        )
                    )
            changes.extend(local)
            sheet_changes.append(
                DrawingSheetComparison(
                    old_sheet_revision_id=o.sheet_revision_id if o else None,
                    new_sheet_revision_id=n.sheet_revision_id if n else None,
                    sheet_number=number,
                    changes=tuple(local),
                    native_text_changed=bool(o and n and o.content_hash != n.content_hash),
                    visual_or_unparsed_change=any(c.human_visual_review_required for c in local),
                )
            )
            if o and n:
                lineage.append(
                    SheetLineage(
                        old_sheet_revision_id=o.sheet_revision_id,
                        new_sheet_revision_id=n.sheet_revision_id,
                        relationship="unchanged" if o.content_hash == n.content_hash else "revised",
                        evidence_strength=1.0,
                    )
                )
        removed = [sheet for number, sheet in om.items() if number not in nm]
        added = [sheet for number, sheet in nm.items() if number not in om]
        for old_sheet in removed:
            candidates = [
                (
                    SequenceMatcher(
                        None,
                        (old_sheet.sheet_title or "").casefold(),
                        (new_sheet.sheet_title or "").casefold(),
                    ).ratio(),
                    new_sheet,
                )
                for new_sheet in added
                if new_sheet.discipline == old_sheet.discipline
            ]
            if candidates:
                score, candidate = max(candidates, key=lambda item: item[0])
                if score >= 0.55:
                    relationship = "renumbered" if score >= 0.8 else "ambiguous_lineage"
                    lineage.append(
                        SheetLineage(
                            old_sheet_revision_id=old_sheet.sheet_revision_id,
                            new_sheet_revision_id=candidate.sheet_revision_id,
                            relationship=relationship,
                            evidence_strength=round(score, 3),
                            human_review_required=True,
                        )
                    )
                    changes.append(
                        DrawingSetChange(
                            change_type="sheet_renumbered" if score >= 0.8 else "ambiguous",
                            sheet_number=candidate.sheet_number,
                            summary=(
                                f"Possible lineage from {old_sheet.sheet_number} to "
                                f"{candidate.sheet_number}; human confirmation required"
                            ),
                            old_citation=self._sheet_cite(old, old_sheet),
                            new_citation=self._sheet_cite(new, candidate),
                        )
                    )
        result = DrawingSetComparison(
            id=f"dcomp_{uuid4().hex}",
            project_id=project_id,
            old_revision_id=old_revision_id,
            new_revision_id=new_revision_id,
            created_at=datetime.now(UTC),
            changes=tuple(changes),
            sheet_comparisons=tuple(sheet_changes),
            lineage=tuple(lineage),
            warnings=("Visual-only changes are not interpreted and require human review",),
        )
        self.repository.save_comparison(result)
        self._event(
            project_id,
            "drawing_set_comparison_created",
            result.id,
            "system",
            f"Compared {old_revision_id} to {new_revision_id}",
        )
        return result

    def _sheet_cite(
        self, a: DrawingAnalysis, s: DrawingSheet | None
    ) -> VisualRegionCitation | None:
        if not s:
            return None
        return citation(
            next(r for r in a.regions if r.page_number == s.source_page_number),
            s.sheet_revision_id,
            s.sheet_number,
            s.sheet_title,
        )

    def _find_sheet(self, project_id: str, sheet_id: str) -> DrawingAnalysis:
        for a in self.repository.list_analyses(project_id):
            if any(s.sheet_revision_id == sheet_id for s in a.sheets):
                return a
        raise ValueError("drawing sheet not found in requested project")

    def _event(
        self, project_id: str, event_type: str, subject_id: str, actor: str, summary: str
    ) -> None:
        now = datetime.now(UTC)
        self.repository.append_audit(
            AuditEvent(
                id=f"audit_{uuid4().hex}",
                project_id=project_id,
                event_type=event_type,
                subject_id=subject_id,
                actor_id=actor,
                created_at=now,
            )
        )
        self.repository.append_notification(
            NotificationRequest(
                id=f"notify_{uuid4().hex}",
                project_id=project_id,
                event_type=event_type,
                subject_id=subject_id,
                created_at=now,
                summary=summary,
            )
        )
