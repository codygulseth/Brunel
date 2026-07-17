"""Deterministic attachment ingestion, extraction, evidence mapping, and comparison."""

import mimetypes
import re
import shutil
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from change_workflow.models import (
    ActorReference,
    NotificationRequest,
    NotificationType,
    ReviewerReference,
)
from change_workflow.notifications import NotificationOutboxService
from change_workflow.repository import JsonChangeWorkflowRepository
from document_processing import DocumentIngestionService, DocumentType, IngestionError
from document_processing.models import IngestedDocument
from revision_intelligence.models import EvidenceStrength
from storage import JsonDocumentRepository

from .attachment_models import (
    AttachmentClassification,
    AttachmentConflict,
    AttachmentDuplicateAssessment,
    AttachmentEvidenceReference,
    AttachmentExtractionResult,
    AttachmentIdentity,
    AttachmentIngestionResult,
    AttachmentMismatchAssessment,
    AttachmentQualityIssue,
    AttachmentReadabilityAssessment,
    AttachmentReference,
    AttachmentRevision,
    AttachmentRole,
    AttachmentSetChange,
    AttachmentSupersession,
    AttachmentTechnicalAttribute,
    AttachmentType,
    ComplianceMappingReview,
    ConflictStatus,
    DeviationStatus,
    DuplicateStatus,
    ExtractionStatus,
    HumanConfirmationStatus,
    MissingAttachmentIssue,
    PackageAttachmentStalenessAssessment,
    PackageAttachmentStalenessStatus,
    PackageAttachmentSummary,
    PackageChangeType,
    PackageEvidenceSet,
    PackageRevisionComparison,
    PossibleDeviation,
    ProposedComplianceMapping,
    ReadabilityStatus,
    SubmittalAttachment,
    SupersessionStatus,
)
from .attachment_repository import JsonAttachmentIntelligenceRepository
from .errors import (
    AttachmentIngestionError,
    AttachmentSecurityError,
    AttachmentUnsupportedError,
    SubmittalNotFoundError,
    SubmittalValidationError,
)
from .models import (
    CompletenessIssue,
    CompletenessSeverity,
    CompletenessStatus,
    MatrixStatus,
    PackageReviewStatus,
    StalenessStatus,
    SubmittalAuditEvent,
    SubmittalCompletenessAssessment,
    SubmittalPackage,
    SubmittalRequirement,
    SubmittalStalenessAssessment,
    SubmittalType,
)
from .repository import JsonSubmittalRepository
from .service import SubmittalService


CONTENT_EXTENSIONS = {".pdf", ".txt", ".md", ".markdown"}
METADATA_EXTENSIONS = {
    ".docx",
    ".xlsx",
    ".csv",
    ".png",
    ".jpg",
    ".jpeg",
    ".tif",
    ".tiff",
    ".dwg",
    ".rvt",
    ".zip",
}
BLOCKED_EXTENSIONS = {".exe", ".dll", ".bat", ".cmd", ".ps1", ".js", ".msi", ".com"}

TYPE_PATTERNS: tuple[tuple[AttachmentType, tuple[str, ...]], ...] = (
    (AttachmentType.COVER_SHEET, ("cover sheet", "submittal transmittal")),
    (AttachmentType.PRODUCT_DATA, ("product data", "catalog data", "technical data")),
    (AttachmentType.SHOP_DRAWING, ("shop drawing", "shop drawings")),
    (AttachmentType.CALCULATION, ("calculation", "short-circuit study", "engineering calc")),
    (AttachmentType.TEST_REPORT, ("test report", "factory test", "test results")),
    (AttachmentType.WARRANTY, ("warranty", "warranties")),
    (
        AttachmentType.INSTALLATION_INSTRUCTION,
        ("installation instruction", "installation manual", "installing"),
    ),
    (AttachmentType.CERTIFICATE, ("certificate", "certification")),
    (AttachmentType.COORDINATION_DRAWING, ("coordination drawing",)),
    (AttachmentType.OPERATION_AND_MAINTENANCE, ("operation and maintenance", "o&m")),
    (AttachmentType.SUBSTITUTION_REQUEST, ("substitution request",)),
    (AttachmentType.MARKUP, ("review markup", "markup")),
)

ATTRIBUTE_PATTERNS: tuple[tuple[str, re.Pattern[str], str | None], ...] = (
    (
        "voltage",
        re.compile(r"\b(\d{2,4}(?:Y/\d{2,4})?\s*V(?:AC|DC)?)\b", re.I),
        "V",
    ),
    ("current", re.compile(r"\b(\d+(?:\.\d+)?)\s*(A|amp(?:s|eres)?)\b", re.I), "A"),
    (
        "short_circuit_rating",
        re.compile(r"\b(\d+(?:\.\d+)?)\s*kA(?:IC|ICR)?\b", re.I),
        "kA",
    ),
    ("nema_rating", re.compile(r"\bNEMA\s+(\d+[A-Z]?)\b", re.I), None),
    ("ip_rating", re.compile(r"\bIP\s*(\d{2})\b", re.I), None),
    (
        "warranty_duration",
        re.compile(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s*[- ]?year\s+warranty\b",
            re.I,
        ),
        "years",
    ),
    (
        "dimensions",
        re.compile(
            r"\b(\d+(?:\.\d+)?)\s*(?:in(?:ches)?|\")\s*[xX]\s*(\d+(?:\.\d+)?)\s*(?:in(?:ches)?|\")",
            re.I,
        ),
        "in",
    ),
    (
        "material",
        re.compile(r"\b(copper|aluminum|stainless steel|painted steel)\s+bus\b", re.I),
        None,
    ),
    ("frequency", re.compile(r"\b(50|60)\s*Hz\b", re.I), "Hz"),
    ("phase", re.compile(r"\b(single|three|1|3)[ -]?phase\b", re.I), None),
    (
        "lead_time",
        re.compile(r"\b(\d+)\s*(?:calendar )?(?:weeks?|days?)\s+lead time\b", re.I),
        None,
    ),
)

TYPE_TO_SUBMITTAL = {
    AttachmentType.PRODUCT_DATA: SubmittalType.PRODUCT_DATA,
    AttachmentType.SHOP_DRAWING: SubmittalType.SHOP_DRAWING,
    AttachmentType.CALCULATION: SubmittalType.CALCULATION,
    AttachmentType.TEST_REPORT: SubmittalType.TEST_REPORT,
    AttachmentType.CERTIFICATE: SubmittalType.CERTIFICATE,
    AttachmentType.WARRANTY: SubmittalType.WARRANTY,
    AttachmentType.INSTALLATION_INSTRUCTION: SubmittalType.INSTALLATION_INSTRUCTION,
    AttachmentType.OPERATION_AND_MAINTENANCE: SubmittalType.OPERATION_AND_MAINTENANCE,
    AttachmentType.COORDINATION_DRAWING: SubmittalType.COORDINATION_DRAWING,
    AttachmentType.DELEGATED_DESIGN: SubmittalType.DELEGATED_DESIGN,
    AttachmentType.SUBSTITUTION_REQUEST: SubmittalType.SUBSTITUTION_REQUEST,
}

SUBMITTAL_TO_ATTACHMENT = {value: key for key, value in TYPE_TO_SUBMITTAL.items()}


class AttachmentFileStore(Protocol):
    def store(
        self,
        project_id: str,
        attachment_id: str,
        attachment_revision_id: str,
        source: Path,
    ) -> Path: ...


class LocalAttachmentFileStore:
    """Immutable local binary store; paths never cross API serialization."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def store(
        self,
        project_id: str,
        attachment_id: str,
        attachment_revision_id: str,
        source: Path,
    ) -> Path:
        target = (
            self.root
            / _safe_id(project_id)
            / _safe_id(attachment_id)
            / _safe_id(attachment_revision_id)
            / source.name
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            temporary = target.with_suffix(target.suffix + ".tmp")
            shutil.copyfile(source, temporary)
            temporary.replace(target)
        return target


class AttachmentIngestionService:
    def __init__(
        self,
        attachments: JsonAttachmentIntelligenceRepository,
        submittals: JsonSubmittalRepository,
        documents: JsonDocumentRepository,
        file_store: AttachmentFileStore,
        changes: JsonChangeWorkflowRepository | None = None,
        *,
        maximum_file_size: int = 50 * 1024 * 1024,
        allowed_input_root: Path | None = None,
        extraction_policy_version: str = "attachment-extractor-v1",
        mapping_policy_version: str = "deterministic-cited-mapping-v1",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.attachments = attachments
        self.submittals = submittals
        self.documents = documents
        self.file_store = file_store
        self.changes = changes
        self.maximum_file_size = maximum_file_size
        self.allowed_input_root = (allowed_input_root or Path.cwd()).resolve()
        self.extraction_policy_version = extraction_policy_version
        self.mapping_policy_version = mapping_policy_version
        self.clock = clock or (lambda: datetime.now(UTC))
        self.analysis = PackageAttachmentAnalysisService(
            attachments,
            submittals,
            changes,
            extraction_policy_version=extraction_policy_version,
            mapping_policy_version=mapping_policy_version,
            clock=self.clock,
        )

    def ingest(
        self,
        project_id: str,
        package_id: str,
        file_path: Path,
        actor: ActorReference,
        *,
        package_revision: int | None = None,
        attachment_id: str | None = None,
        declared_type: AttachmentType | None = None,
        role: AttachmentRole = AttachmentRole.UNKNOWN,
        display_name: str | None = None,
        revision_label: str | None = None,
        supersedes_attachment_revision_id: str | None = None,
    ) -> AttachmentIngestionResult:
        package = SubmittalService(self.submittals).get_package(project_id, package_id)
        revision_number = package_revision or package.current_revision
        if not any(item.revision == revision_number for item in package.revisions):
            raise SubmittalNotFoundError("Package revision not found")
        source = self._validate_file(file_path)
        content = source.read_bytes()
        content_hash = sha256(content).hexdigest()
        logical_id = attachment_id or self._attachment_id(project_id, package_id, source.name)
        existing = self.attachments.get_attachment(project_id, logical_id)
        if existing and existing.package_id != package_id:
            raise SubmittalValidationError("Attachment belongs to another package")
        revision_id = f"attrev_{sha256(f'{logical_id}\0{revision_number}\0{content_hash}'.encode()).hexdigest()[:24]}"
        if existing:
            prior_same = next((item for item in existing.revisions if item.id == revision_id), None)
            if prior_same:
                extraction = (
                    self.attachments.get_extraction(project_id, prior_same.extraction_result_id)
                    if prior_same.extraction_result_id
                    else None
                )
                evidence_set = self.analysis.latest_evidence_set(
                    project_id, package_id, revision_number
                )
                return AttachmentIngestionResult(
                    attachment=existing,
                    revision=prior_same,
                    extraction=extraction,
                    duplicate=self._duplicate(project_id, package_id, logical_id, content_hash),
                    evidence_set_id=evidence_set.id if evidence_set else None,
                    warnings=("Idempotent attachment revision reused.",),
                )
        stored = self.file_store.store(project_id, logical_id, revision_id, source)
        prior_revision = existing.revisions[-1] if existing else None
        source_document: IngestedDocument | None = None
        ingestion_warning: str | None = None
        if source.suffix.casefold() in CONTENT_EXTENSIONS:
            try:
                result = DocumentIngestionService(self.documents).ingest(
                    project_id=project_id,
                    file_path=stored,
                    document_type=DocumentType.SUBMITTAL,
                    document_family_id=logical_id,
                    title=display_name or source.stem,
                    revision=revision_label or str(len(existing.revisions) + 1 if existing else 1),
                    revision_sequence=len(existing.revisions) + 1 if existing else 1,
                    parent_document_id=prior_revision.source_document_id
                    if prior_revision
                    else None,
                )
                source_document = self.documents.get(result.document.document_id)
            except IngestionError as exc:
                ingestion_warning = f"Content extraction failed safely: {type(exc).__name__}."
        readability = AttachmentContentExtractor.readability(
            source, source_document, ingestion_warning
        )
        classification = AttachmentContentExtractor.classify(
            source.name, source_document, declared_type
        )
        extraction = AttachmentContentExtractor.extract(
            project_id,
            package_id,
            revision_number,
            logical_id,
            revision_id,
            content_hash,
            source_document,
            readability,
            classification,
            self.clock(),
            configuration_version=self.extraction_policy_version,
        )
        self.attachments.save_extraction(extraction)
        duplicate = self._duplicate(project_id, package_id, logical_id, content_hash)
        supersession = self._supersession(
            prior_revision, revision_id, source.name, supersedes_attachment_revision_id
        )
        revision = AttachmentRevision(
            id=revision_id,
            attachment_id=logical_id,
            project_id=project_id,
            package_id=package_id,
            package_revision=revision_number,
            source_document_id=source_document.document.document_id if source_document else None,
            original_filename=source.name,
            display_name=display_name or source.name,
            mime_type=mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            file_extension=source.suffix.casefold(),
            file_size=len(content),
            content_hash=content_hash,
            storage_reference=str(stored),
            user_declared_type=declared_type,
            inferred_type=classification.inferred_type,
            role=role,
            revision_label=revision_label,
            uploaded_at=self.clock(),
            uploaded_by=actor,
            page_count=readability.page_count,
            extraction_status=extraction.extraction_status,
            readability_status=readability.status,
            extraction_result_id=extraction.id,
            supersedes_attachment_revision_id=(
                supersedes_attachment_revision_id
                or (prior_revision.id if supersession and prior_revision else None)
            ),
        )
        revisions: tuple[AttachmentRevision, ...] = ()
        if existing:
            revisions = tuple(
                item.model_copy(
                    update={
                        "active": False,
                        "superseded_by_attachment_revision_id": revision.id,
                    }
                )
                if item.id == (revision.supersedes_attachment_revision_id or "")
                else item
                for item in existing.revisions
            )
        now = self.clock()
        attachment = SubmittalAttachment(
            id=logical_id,
            project_id=project_id,
            package_id=package_id,
            display_name=display_name or source.name,
            active_revision_id=revision.id,
            revisions=revisions + (revision,),
            version=(existing.version + 1 if existing else 1),
            created_at=existing.created_at if existing else now,
            updated_at=now,
        )
        self.attachments.save_attachment(
            attachment, expected_version=existing.version if existing else None
        )
        mismatches = self.analysis.detect_mismatches(project_id, package, extraction)
        self._audit(project_id, logical_id, actor, "attachment_registered", None, revision.id)
        self._audit(project_id, logical_id, actor, "attachment_file_stored", None, content_hash)
        self._audit(project_id, logical_id, actor, "attachment_revision_created", None, revision.id)
        self._audit(
            project_id,
            logical_id,
            actor,
            "attachment_extracted",
            None,
            extraction.id,
        )
        self._audit(
            project_id,
            logical_id,
            actor,
            "attachment_classified",
            declared_type.value if declared_type else None,
            classification.inferred_type.value,
        )
        self._audit(
            project_id,
            logical_id,
            actor,
            "readability_assessed",
            None,
            readability.status.value,
        )
        if duplicate.status != DuplicateStatus.UNIQUE:
            self._audit(
                project_id, logical_id, actor, "duplicate_detected", None, duplicate.status.value
            )
        if supersession:
            self._audit(
                project_id,
                logical_id,
                actor,
                "supersession_confirmed"
                if supersession.user_confirmed
                else "supersession_suggested",
                supersession.prior_attachment_revision_id,
                supersession.new_attachment_revision_id,
            )
        for mismatch in mismatches:
            self._audit(
                project_id, logical_id, actor, "mismatch_detected", None, mismatch.mismatch_type
            )
        evidence_set = self.analysis.analyze_package(
            project_id, package_id, actor, package_revision=revision_number
        )
        warnings = tuple(value for value in (ingestion_warning,) if value)
        return AttachmentIngestionResult(
            attachment=attachment,
            revision=revision,
            extraction=extraction,
            duplicate=duplicate,
            mismatches=mismatches,
            supersession=supersession,
            evidence_set_id=evidence_set.id,
            warnings=warnings,
        )

    def _validate_file(self, file_path: Path) -> Path:
        if file_path.name != Path(file_path.name).name or ".." in file_path.parts:
            raise AttachmentSecurityError("Unsafe attachment filename")
        source = file_path.expanduser().resolve()
        if source != self.allowed_input_root and self.allowed_input_root not in source.parents:
            raise AttachmentSecurityError("Attachment path must stay within the allowed input root")
        if not source.is_file():
            raise AttachmentIngestionError("Attachment file does not exist")
        extension = source.suffix.casefold()
        if extension in BLOCKED_EXTENSIONS:
            raise AttachmentSecurityError("Executable attachment types are prohibited")
        if extension not in CONTENT_EXTENSIONS | METADATA_EXTENSIONS:
            raise AttachmentUnsupportedError("Attachment extension is not allowed")
        if source.stat().st_size > self.maximum_file_size:
            raise AttachmentSecurityError("Attachment exceeds configured file-size limit")
        return source

    @staticmethod
    def _attachment_id(project_id: str, package_id: str, filename: str) -> str:
        logical = re.sub(r"[^a-z0-9]+", "-", Path(filename).stem.casefold()).strip("-")
        identity = sha256(f"{project_id}\0{package_id}\0{logical}".encode()).hexdigest()[:24]
        return f"att_{identity}"

    def _duplicate(
        self, project_id: str, package_id: str, attachment_id: str, content_hash: str
    ) -> AttachmentDuplicateAssessment:
        same_identity = self.attachments.get_attachment(project_id, attachment_id)
        if same_identity and any(
            revision.content_hash == content_hash for revision in same_identity.revisions
        ):
            return AttachmentDuplicateAssessment(
                status=DuplicateStatus.REUSED_ATTACHMENT,
                matching_attachment_ids=(attachment_id,),
                explanation="Identical content is reused under the same logical attachment lineage.",
                content_hashes=(content_hash,),
                page_overlap=1.0,
            )
        matches = tuple(
            attachment
            for attachment in self.attachments.list_attachments(project_id, package_id)
            if attachment.id != attachment_id
            and any(revision.content_hash == content_hash for revision in attachment.revisions)
        )
        if matches:
            return AttachmentDuplicateAssessment(
                status=DuplicateStatus.EXACT_DUPLICATE,
                matching_attachment_ids=tuple(item.id for item in matches),
                explanation="Identical SHA-256 content exists under another attachment identity.",
                content_hashes=(content_hash,),
                page_overlap=1.0,
            )
        current = next(
            (
                item
                for item in reversed(self.attachments.list_extractions(project_id, attachment_id))
                if item.source_content_hash == content_hash
            ),
            None,
        )
        if current:
            current_terms = _extraction_terms(current)
            candidates: list[tuple[float, str, str]] = []
            for other in self.attachments.list_extractions(project_id):
                if other.package_id != package_id or other.attachment_id == attachment_id:
                    continue
                other_terms = _extraction_terms(other)
                union = current_terms | other_terms
                overlap = len(current_terms & other_terms) / len(union) if union else 0.0
                if overlap >= 0.5:
                    candidates.append((overlap, other.attachment_id, other.source_content_hash))
            if candidates:
                candidates.sort(reverse=True)
                best = candidates[0][0]
                return AttachmentDuplicateAssessment(
                    status=DuplicateStatus.PROBABLE_DUPLICATE
                    if best >= 0.85
                    else DuplicateStatus.PARTIAL_DUPLICATE,
                    matching_attachment_ids=tuple(item[1] for item in candidates),
                    method="deterministic_token_jaccard",
                    explanation=(
                        "Submitted text substantially overlaps another package attachment; "
                        "human review is required before exclusion."
                    ),
                    content_hashes=(content_hash,) + tuple(item[2] for item in candidates),
                    page_overlap=best,
                )
        return AttachmentDuplicateAssessment(
            status=DuplicateStatus.UNIQUE,
            explanation="No exact package attachment content hash matched.",
            content_hashes=(content_hash,),
        )

    @staticmethod
    def _supersession(
        prior: AttachmentRevision | None,
        revision_id: str,
        filename: str,
        declared_prior: str | None,
    ) -> AttachmentSupersession | None:
        if not prior:
            return None
        confirmed = bool(declared_prior)
        return AttachmentSupersession(
            prior_attachment_revision_id=declared_prior or prior.id,
            new_attachment_revision_id=revision_id,
            status=SupersessionStatus.CONFIRMED if confirmed else SupersessionStatus.PROBABLE,
            signals=(
                "user_declared_supersession" if confirmed else "same logical attachment identity",
                f"filename:{filename}",
                "changed_content_hash",
            ),
            user_confirmed=confirmed,
            human_review_required=not confirmed,
        )

    def _audit(
        self,
        project_id: str,
        entity_id: str,
        actor: ActorReference,
        event_type: str,
        previous: str | None,
        new: str | None,
    ) -> None:
        self.submittals.append_audit(
            SubmittalAuditEvent(
                id=f"subaudit_{uuid4().hex}",
                project_id=project_id,
                entity_type="submittal_attachment",
                entity_id=entity_id,
                event_type=event_type,
                actor=actor,
                timestamp=self.clock(),
                previous_state=previous,
                new_state=new,
            )
        )


class AttachmentContentExtractor:
    @staticmethod
    def readability(
        source: Path,
        document: IngestedDocument | None,
        ingestion_warning: str | None,
    ) -> AttachmentReadabilityAssessment:
        if source.suffix.casefold() not in CONTENT_EXTENSIONS:
            return AttachmentReadabilityAssessment(
                status=ReadabilityStatus.UNSUPPORTED,
                explanation="Metadata preserved; content extraction is unavailable for this format.",
                issues=(
                    AttachmentQualityIssue(
                        code="unsupported_format",
                        message="Content was not inspected; the file remains unresolved evidence.",
                    ),
                ),
                may_support_compliance_mapping=False,
            )
        if document is None:
            return AttachmentReadabilityAssessment(
                status=ReadabilityStatus.CORRUPT,
                explanation=ingestion_warning or "The attachment could not be extracted.",
                issues=(
                    AttachmentQualityIssue(
                        code="extraction_failed",
                        message="Attachment content could not be inspected.",
                        severity="blocking",
                    ),
                ),
                may_support_compliance_mapping=False,
            )
        empty = tuple(page.page_number for page in document.pages if not page.content.strip())
        warned = tuple(page.page_number for page in document.pages if page.extraction_warnings)
        readable = len(document.pages) - len(empty)
        issues = tuple(
            AttachmentQualityIssue(
                code="page_unavailable",
                page_number=page,
                message="No extractable page text; the page may be image-only.",
            )
            for page in empty
        )
        status = (
            ReadabilityStatus.UNREADABLE
            if document.pages and readable == 0
            else ReadabilityStatus.PARTIALLY_READABLE
            if empty
            else ReadabilityStatus.READABLE_WITH_WARNINGS
            if warned
            else ReadabilityStatus.READABLE
        )
        return AttachmentReadabilityAssessment(
            status=status,
            page_count=len(document.pages),
            pages_successfully_extracted=readable,
            pages_with_warnings=warned,
            pages_unavailable=empty,
            issues=issues,
            explanation=(
                "All pages contain extractable text."
                if status == ReadabilityStatus.READABLE
                else "Attachment extraction requires human review; unavailable pages do not support mapping."
            ),
            may_support_compliance_mapping=readable > 0,
        )

    @staticmethod
    def classify(
        filename: str,
        document: IngestedDocument | None,
        declared: AttachmentType | None,
    ) -> AttachmentClassification:
        text = filename.casefold() + " " + _document_text(document).casefold()[:10_000]
        scores: list[tuple[int, AttachmentType, tuple[str, ...]]] = []
        for attachment_type, terms in TYPE_PATTERNS:
            signals = tuple(term for term in terms if term in text)
            if signals:
                scores.append((len(signals), attachment_type, signals))
        scores.sort(key=lambda item: (-item[0], item[1].value))
        inferred = scores[0][1] if scores else AttachmentType.UNKNOWN
        signals = scores[0][2] if scores else ()
        alternates = tuple(item[1] for item in scores[1:3])
        strength = "strong" if len(signals) > 1 else "moderate" if signals else "insufficient"
        return AttachmentClassification(
            user_declared_type=declared,
            inferred_type=inferred,
            strength=strength,
            supporting_signals=signals,
            alternate_types=alternates,
            disagreement=bool(
                declared and inferred != AttachmentType.UNKNOWN and declared != inferred
            ),
            human_review_required=True,
        )

    @classmethod
    def extract(
        cls,
        project_id: str,
        package_id: str,
        package_revision: int,
        attachment_id: str,
        attachment_revision_id: str,
        content_hash: str,
        document: IngestedDocument | None,
        readability: AttachmentReadabilityAssessment,
        classification: AttachmentClassification,
        extracted_at: datetime,
        *,
        configuration_version: str = "attachment-extractor-v1",
    ) -> AttachmentExtractionResult:
        evidence = cls._evidence(
            attachment_id, attachment_revision_id, package_id, package_revision, document
        )
        identities = cls._identities(evidence)
        attributes = cls._attributes(evidence)
        references = cls._references(evidence)
        status = (
            ExtractionStatus.UNAVAILABLE
            if readability.status == ReadabilityStatus.UNSUPPORTED
            else ExtractionStatus.FAILED
            if not readability.may_support_compliance_mapping
            else ExtractionStatus.COMPLETE_WITH_WARNINGS
            if readability.status != ReadabilityStatus.READABLE
            else ExtractionStatus.COMPLETE
        )
        identity = sha256(
            f"{attachment_revision_id}\0{content_hash}\0{configuration_version}".encode()
        ).hexdigest()[:24]
        return AttachmentExtractionResult(
            id=f"attext_{identity}",
            project_id=project_id,
            package_id=package_id,
            package_revision=package_revision,
            attachment_id=attachment_id,
            attachment_revision_id=attachment_revision_id,
            source_document_id=document.document.document_id if document else None,
            source_content_hash=content_hash,
            extracted_at=extracted_at,
            extraction_status=status,
            readability=readability,
            classification=classification,
            identities=identities,
            technical_attributes=attributes,
            references=references,
            warnings=tuple(issue.message for issue in readability.issues),
            configuration_version=configuration_version,
        )

    @staticmethod
    def _evidence(
        attachment_id: str,
        revision_id: str,
        package_id: str,
        package_revision: int,
        document: IngestedDocument | None,
    ) -> tuple[AttachmentEvidenceReference, ...]:
        if document is None:
            return ()
        return tuple(
            AttachmentEvidenceReference(
                attachment_id=attachment_id,
                attachment_revision_id=revision_id,
                package_id=package_id,
                package_revision=package_revision,
                citation=chunk.citation,
                excerpt=chunk.content.strip(),
            )
            for chunk in document.chunks
            if chunk.content.strip()
        )

    @staticmethod
    def _identities(
        evidence: tuple[AttachmentEvidenceReference, ...],
    ) -> tuple[AttachmentIdentity, ...]:
        results = []
        for item in evidence:
            text = item.excerpt
            manufacturer = _first_group(r"(?im)^\s*manufacturer\s*:\s*([^\r\n]+)", text)
            product = _first_group(r"(?im)^\s*product(?: name)?\s*:\s*([^\r\n]+)", text)
            models = tuple(
                dict.fromkeys(
                    re.findall(
                        r"(?im)\b(?:model|catalog)(?:\s+(?:number|no\.?))?\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{2,})",
                        text,
                    )
                )
            )
            if manufacturer or product or models:
                results.append(
                    AttachmentIdentity(
                        manufacturer=manufacturer,
                        product_name=product,
                        model_number=models[0] if models else None,
                        evidence=(item,),
                        strength=EvidenceStrength.STRONG
                        if manufacturer and (product or models)
                        else EvidenceStrength.MODERATE,
                        candidate_alternatives=models[1:],
                    )
                )
        return tuple(results)

    @staticmethod
    def _attributes(
        evidence: tuple[AttachmentEvidenceReference, ...],
    ) -> tuple[AttachmentTechnicalAttribute, ...]:
        results = []
        seen: set[tuple[str, str, str]] = set()
        for item in evidence:
            for name, pattern, unit in ATTRIBUTE_PATTERNS:
                for match in pattern.finditer(item.excerpt):
                    value = (
                        " x ".join(match.groups()[:2]) if name == "dimensions" else match.group(1)
                    )
                    key = (name, value.casefold(), item.citation.chunk_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        AttachmentTechnicalAttribute(
                            id=f"attr_{sha256(f'{item.attachment_revision_id}\0{name}\0{value}\0{item.citation.chunk_id}'.encode()).hexdigest()[:20]}",
                            name=name,
                            value=value,
                            unit=unit,
                            normalized_value=_normalize_value(name, value),
                            table_or_paragraph_context=item.excerpt[:500],
                            evidence=item,
                            strength=EvidenceStrength.STRONG,
                        )
                    )
        return tuple(results)

    @staticmethod
    def _references(
        evidence: tuple[AttachmentEvidenceReference, ...],
    ) -> tuple[AttachmentReference, ...]:
        patterns = (
            ("specification_section", r"\b(?:Section\s+)?(\d{2}\s\d{2}\s\d{2})\b"),
            ("drawing_sheet", r"\b([A-Z]{1,3}-\d{2,4}(?:\.\d+)?)\b"),
            ("equipment_tag", r"\b((?:MSB|SWGR|AHU|PMP|GEN)-?\d{1,4})\b"),
            ("room", r"\bRoom\s+([A-Z0-9-]+)\b"),
            ("rfi", r"\b(RFI[- ]?\d+)\b"),
            ("standard", r"\b(UL\s*\d+|IEEE\s*[A-Z0-9.-]+|NFPA\s*\d+)\b"),
        )
        results = []
        seen: set[tuple[str, str, str]] = set()
        for item in evidence:
            for reference_type, pattern in patterns:
                for value in re.findall(pattern, item.excerpt, re.I):
                    key = (reference_type, value.casefold(), item.citation.chunk_id)
                    if key not in seen:
                        seen.add(key)
                        results.append(
                            AttachmentReference(
                                reference_type=reference_type, value=value, evidence=item
                            )
                        )
        return tuple(results)


class PackageAttachmentAnalysisService:
    def __init__(
        self,
        attachments: JsonAttachmentIntelligenceRepository,
        submittals: JsonSubmittalRepository,
        changes: JsonChangeWorkflowRepository | None = None,
        *,
        extraction_policy_version: str = "attachment-extractor-v1",
        mapping_policy_version: str = "deterministic-cited-mapping-v1",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.attachments = attachments
        self.submittals = submittals
        self.changes = changes
        self.extraction_policy_version = extraction_policy_version
        self.mapping_policy_version = mapping_policy_version
        self.clock = clock or (lambda: datetime.now(UTC))

    def analyze_package(
        self,
        project_id: str,
        package_id: str,
        actor: ActorReference,
        *,
        package_revision: int | None = None,
    ) -> PackageEvidenceSet:
        package = SubmittalService(self.submittals).get_package(project_id, package_id)
        revision_number = package_revision or package.current_revision
        revisions = self._active_revisions(project_id, package_id, revision_number)
        extractions = tuple(
            extraction
            for revision in revisions
            if revision.extraction_result_id
            and (
                extraction := self.attachments.get_extraction(
                    project_id, revision.extraction_result_id
                )
            )
        )
        requirements = tuple(
            requirement
            for item_id in package.register_item_ids
            for requirement in SubmittalService(self.submittals)
            .get_register(project_id, item_id)
            .requirements
        )
        missing = self._missing(requirements, extractions)
        conflicts = self._conflicts(package_id, revision_number, extractions)
        mismatches = tuple(
            mismatch
            for extraction in extractions
            for mismatch in self.detect_mismatches(project_id, package, extraction)
        )
        deviations = self._deviations(package, requirements, extractions)
        mappings = tuple(
            self._mapping(package, revision_number, requirement, extractions, conflicts, deviations)
            for requirement in requirements
        )
        for mapping in mappings:
            existing = self.attachments.get_mapping(project_id, mapping.id)
            self.attachments.save_mapping(existing or mapping)
        identity = self._evidence_hash(
            revisions,
            requirements,
            extraction_policy=self.extraction_policy_version,
            mapping_policy=self.mapping_policy_version,
        )
        prior = self.latest_evidence_set(project_id, package_id, revision_number)
        existing_evidence = self.attachments.get_evidence_set(
            project_id, f"evidence_{identity[:24]}"
        )
        if existing_evidence is not None:
            return existing_evidence
        evidence_set = PackageEvidenceSet(
            id=f"evidence_{identity[:24]}",
            project_id=project_id,
            package_id=package_id,
            package_revision=revision_number,
            attachment_revision_ids=tuple(item.id for item in revisions),
            attachment_content_hashes=tuple(item.content_hash for item in revisions),
            extraction_result_ids=tuple(item.id for item in extractions),
            requirement_ids=tuple(item.id for item in requirements),
            requirement_set_version=sha256(
                "\0".join(item.id + item.description for item in requirements).encode()
            ).hexdigest()[:16],
            mapping_policy_version=self.mapping_policy_version,
            extraction_policy_version=self.extraction_policy_version,
            created_at=self.clock(),
            evidence_set_hash=identity,
            readability_summary=self._readability_summary(extractions),
            missing_attachments=missing,
            conflicts=conflicts,
            mismatches=mismatches,
            possible_deviations=deviations,
            compliance_mappings=tuple(
                self.attachments.get_mapping(project_id, item.id) or item for item in mappings
            ),
            human_review_complete=bool(mappings)
            and all(
                (
                    self.attachments.get_mapping(project_id, item.id) or item
                ).human_confirmation_status
                in {HumanConfirmationStatus.CONFIRMED, HumanConfirmationStatus.MODIFIED}
                for item in mappings
            ),
            supersedes_evidence_set_id=(
                prior.id if prior and prior.evidence_set_hash != identity else None
            ),
        )
        self.attachments.save_evidence_set(evidence_set)
        self._apply_completeness(package, evidence_set, actor)
        for event_type, records in (
            ("missing_attachment_identified", evidence_set.missing_attachments),
            ("attachment_conflict_identified", evidence_set.conflicts),
            ("possible_deviation_identified", evidence_set.possible_deviations),
            ("compliance_mapping_proposed", evidence_set.compliance_mappings),
        ):
            for record in records:
                self._audit(
                    project_id,
                    package_id,
                    actor,
                    event_type,
                    None,
                    getattr(record, "id", getattr(record, "requirement_id", None)),
                )
        if missing or conflicts or mismatches or deviations:
            self._notify_findings(package, evidence_set)
        if prior and prior.evidence_set_hash != evidence_set.evidence_set_hash:
            self._mark_stale(package, prior, evidence_set, actor)
        self._audit(
            project_id,
            package_id,
            actor,
            "package_evidence_set_created",
            prior.evidence_set_hash if prior else None,
            evidence_set.evidence_set_hash,
        )
        return evidence_set

    def generate_mappings(
        self, project_id: str, package_id: str, actor: ActorReference
    ) -> tuple[ProposedComplianceMapping, ...]:
        return self.analyze_package(project_id, package_id, actor).compliance_mappings

    def review_mapping(
        self,
        project_id: str,
        package_id: str,
        requirement_id: str,
        reviewer: ReviewerReference,
        actor: ActorReference,
        *,
        confirmation: HumanConfirmationStatus,
        status: MatrixStatus | None = None,
        note: str | None = None,
        added_evidence: tuple[AttachmentEvidenceReference, ...] = (),
        removed_evidence_ids: tuple[str, ...] = (),
    ) -> ProposedComplianceMapping:
        package = SubmittalService(self.submittals).get_package(project_id, package_id)
        mapping_id = self._mapping_id(package_id, package.current_revision, requirement_id)
        mapping = self.attachments.get_mapping(project_id, mapping_id)
        if mapping is None:
            raise SubmittalNotFoundError("Proposed compliance mapping not found")
        if confirmation == HumanConfirmationStatus.MODIFIED and status is None:
            raise SubmittalValidationError("Modified mapping requires a confirmed status")
        if confirmation == HumanConfirmationStatus.CONFIRMED:
            status = mapping.proposed_status
        if confirmation in {
            HumanConfirmationStatus.REJECTED,
            HumanConfirmationStatus.NEEDS_INFORMATION,
        }:
            status = None
        review = ComplianceMappingReview(
            id=f"mapreview_{uuid4().hex}",
            reviewer=reviewer,
            confirmation_status=confirmation,
            confirmed_status=status,
            note=note,
            added_evidence=added_evidence,
            removed_evidence_ids=removed_evidence_ids,
            reviewed_at=self.clock(),
        )
        removed = set(removed_evidence_ids)
        evidence = (
            tuple(
                item
                for item in mapping.supporting_evidence
                if f"{item.attachment_revision_id}:{item.citation.chunk_id}" not in removed
            )
            + added_evidence
        )
        updated = mapping.model_copy(
            update={
                "human_confirmation_status": confirmation,
                "confirmed_status": status,
                "supporting_evidence": tuple(dict.fromkeys(evidence)),
                "reviews": mapping.reviews + (review,),
            }
        )
        self.attachments.save_mapping(updated)
        self._audit(
            project_id,
            package_id,
            actor,
            "compliance_mapping_reviewed",
            mapping.human_confirmation_status.value,
            confirmation.value,
        )
        return updated

    def latest_evidence_set(
        self, project_id: str, package_id: str, package_revision: int | None = None
    ) -> PackageEvidenceSet | None:
        items = self.attachments.list_evidence_sets(project_id, package_id, package_revision)
        return items[-1] if items else None

    def summary(self, project_id: str, package_id: str) -> PackageAttachmentSummary:
        package = SubmittalService(self.submittals).get_package(project_id, package_id)
        evidence = self.latest_evidence_set(project_id, package_id, package.current_revision)
        revisions = self._active_revisions(project_id, package_id, package.current_revision)
        extractions = tuple(
            item
            for revision in revisions
            if revision.extraction_result_id
            and (item := self.attachments.get_extraction(project_id, revision.extraction_result_id))
        )
        return PackageAttachmentSummary(
            project_id=project_id,
            package_id=package_id,
            package_revision=package.current_revision,
            attachment_count=len(self.attachments.list_attachments(project_id, package_id)),
            active_revision_count=len(revisions),
            readable_count=sum(
                item.readability.may_support_compliance_mapping for item in extractions
            ),
            unsupported_count=sum(
                item.readability.status == ReadabilityStatus.UNSUPPORTED for item in extractions
            ),
            duplicate_count=sum(
                self._is_duplicate(project_id, package_id, revision) for revision in revisions
            ),
            missing_count=len(evidence.missing_attachments) if evidence else 0,
            mismatch_count=len(evidence.mismatches) if evidence else 0,
            conflict_count=len(evidence.conflicts) if evidence else 0,
            deviation_count=len(evidence.possible_deviations) if evidence else 0,
            unreviewed_mapping_count=sum(
                mapping.human_confirmation_status == HumanConfirmationStatus.UNREVIEWED
                for mapping in evidence.compliance_mappings
            )
            if evidence
            else 0,
            evidence_set_id=evidence.id if evidence else None,
            evidence_set_hash=evidence.evidence_set_hash if evidence else None,
        )

    def detect_mismatches(
        self,
        project_id: str,
        package: SubmittalPackage,
        extraction: AttachmentExtractionResult,
    ) -> tuple[AttachmentMismatchAssessment, ...]:
        sections = {
            item.specification_section
            for item_id in package.register_item_ids
            if (item := SubmittalService(self.submittals).get_register(project_id, item_id))
        }
        mismatches = []
        for reference in extraction.references:
            if (
                reference.reference_type == "specification_section"
                and reference.value not in sections
            ):
                mismatches.append(
                    AttachmentMismatchAssessment(
                        mismatch_type="specification_section_mismatch",
                        package_evidence=f"Package register sections: {', '.join(sorted(sections))}",
                        attachment_evidence=reference.evidence,
                        severity="warning",
                    )
                )
        package_product = package.revisions[-1].product
        if package_product and package_product.model_number:
            for identity in extraction.identities:
                if identity.model_number and identity.model_number != package_product.model_number:
                    mismatches.append(
                        AttachmentMismatchAssessment(
                            mismatch_type="package_model_mismatch",
                            package_evidence=f"Package product model: {package_product.model_number}",
                            attachment_evidence=identity.evidence[0] if identity.evidence else None,
                            severity="warning",
                            strength=EvidenceStrength.STRONG,
                        )
                    )
        return tuple(mismatches)

    def check_staleness(
        self, project_id: str, package_id: str, actor: ActorReference
    ) -> PackageAttachmentStalenessAssessment:
        package = SubmittalService(self.submittals).get_package(project_id, package_id)
        sets = self.attachments.list_evidence_sets(project_id, package_id, package.current_revision)
        status = (
            PackageAttachmentStalenessStatus.POTENTIALLY_STALE
            if len(sets) > 1 and sets[-1].evidence_set_hash != sets[-2].evidence_set_hash
            else PackageAttachmentStalenessStatus.CURRENT
        )
        assessment = PackageAttachmentStalenessAssessment(
            id=f"attstale_{sha256(f'{package_id}\0{sets[-1].evidence_set_hash if sets else "none"}\0{status.value}'.encode()).hexdigest()[:24]}",
            project_id=project_id,
            package_id=package_id,
            package_revision=package.current_revision,
            status=status,
            reasons=(
                ("Package evidence set changed and requires renewed human review.",)
                if status != PackageAttachmentStalenessStatus.CURRENT
                else ("Latest attachment evidence set matches the recorded review basis.",)
            ),
            previous_evidence_set_hash=sets[-2].evidence_set_hash if len(sets) > 1 else None,
            current_evidence_set_hash=sets[-1].evidence_set_hash if sets else None,
            assessed_by=actor,
            assessed_at=self.clock(),
            human_review_required=status != PackageAttachmentStalenessStatus.CURRENT,
        )
        existing = self.attachments.list_staleness(project_id, package_id)
        if not any(item.id == assessment.id for item in existing):
            self.attachments.save_staleness(assessment)
        return assessment

    def acknowledge_staleness(
        self,
        project_id: str,
        package_id: str,
        actor: ActorReference,
    ) -> PackageAttachmentStalenessAssessment:
        existing = self.attachments.list_staleness(project_id, package_id)
        if not existing:
            raise SubmittalNotFoundError("No attachment staleness assessment exists")
        latest = existing[-1]
        acknowledged = latest.model_copy(
            update={
                "id": f"attstale_{uuid4().hex}",
                "acknowledged_by": actor,
                "acknowledged_at": self.clock(),
            }
        )
        self.attachments.save_staleness(acknowledged)
        self._audit(
            project_id, package_id, actor, "attachment_staleness_acknowledged", None, latest.id
        )
        return acknowledged

    def _active_revisions(
        self, project_id: str, package_id: str, package_revision: int
    ) -> tuple[AttachmentRevision, ...]:
        return tuple(
            revision
            for attachment in self.attachments.list_attachments(project_id, package_id)
            for revision in attachment.revisions
            if revision.package_revision == package_revision and revision.active
        )

    @staticmethod
    def _missing(
        requirements: Sequence[SubmittalRequirement],
        extractions: Sequence[AttachmentExtractionResult],
    ) -> tuple[MissingAttachmentIssue, ...]:
        present = {
            TYPE_TO_SUBMITTAL.get(extraction.classification.inferred_type)
            for extraction in extractions
            if extraction.readability.may_support_compliance_mapping
        }
        return tuple(
            MissingAttachmentIssue(
                requirement_id=requirement.id,
                missing_type=SUBMITTAL_TO_ATTACHMENT.get(
                    requirement.submittal_type, AttachmentType.UNKNOWN
                ),
                requirement_evidence=requirement.evidence[0],
                package_evidence_state="No readable classified attachment supports this required document type.",
                blocking=requirement.submittal_type
                in {
                    SubmittalType.PRODUCT_DATA,
                    SubmittalType.SHOP_DRAWING,
                    SubmittalType.CALCULATION,
                    SubmittalType.TEST_REPORT,
                },
                suggested_action="Add a readable attachment and regenerate proposed mappings.",
            )
            for requirement in requirements
            if requirement.submittal_type not in present
            and requirement.submittal_type in SUBMITTAL_TO_ATTACHMENT
        )

    @staticmethod
    def _conflicts(
        package_id: str,
        package_revision: int,
        extractions: tuple[AttachmentExtractionResult, ...],
    ) -> tuple[AttachmentConflict, ...]:
        grouped: dict[str, dict[str, list[AttachmentEvidenceReference]]] = {}
        for extraction in extractions:
            for identity in extraction.identities:
                if identity.model_number and identity.evidence:
                    grouped.setdefault("model_number", {}).setdefault(
                        identity.model_number, []
                    ).extend(identity.evidence)
            for attribute in extraction.technical_attributes:
                grouped.setdefault(attribute.name, {}).setdefault(attribute.value, []).append(
                    attribute.evidence
                )
        conflicts = []
        for subject, values in grouped.items():
            if len(values) <= 1:
                continue
            evidence = tuple(item for group in values.values() for item in group)
            conflict_id = sha256(
                f"{package_id}\0{package_revision}\0{subject}\0{'|'.join(sorted(values))}".encode()
            ).hexdigest()[:24]
            conflicts.append(
                AttachmentConflict(
                    id=f"conflict_{conflict_id}",
                    package_id=package_id,
                    package_revision=package_revision,
                    conflict_type="cross_attachment_value_conflict",
                    subject=subject,
                    values=tuple(values),
                    evidence=evidence,
                    status=ConflictStatus.CONTEXT_MAY_DIFFER,
                    explanation="Different submitted values were extracted; configuration context requires human review.",
                )
            )
        return tuple(conflicts)

    @staticmethod
    def _deviations(
        package: SubmittalPackage,
        requirements: Sequence[SubmittalRequirement],
        extractions: Sequence[AttachmentExtractionResult],
    ) -> tuple[PossibleDeviation, ...]:
        submitted: dict[str, list[AttachmentTechnicalAttribute]] = {}
        for extraction in extractions:
            for attribute in extraction.technical_attributes:
                submitted.setdefault(attribute.name, []).append(attribute)
        deviations = []
        for requirement in requirements:
            expected = _specified_attributes(requirement.description)
            for name, expected_value in expected.items():
                for attribute in submitted.get(name, []):
                    if _comparable(attribute.value) == _comparable(expected_value):
                        continue
                    disclosed = any(
                        name.replace("_", " ") in value.casefold()
                        or attribute.value.casefold() in value.casefold()
                        for value in package.revisions[-1].deviations
                    )
                    identity = sha256(
                        f"{requirement.id}\0{name}\0{expected_value}\0{attribute.value}".encode()
                    ).hexdigest()[:24]
                    deviations.append(
                        PossibleDeviation(
                            id=f"deviation_{identity}",
                            requirement_id=requirement.id,
                            attribute_name=name,
                            specified_value=expected_value,
                            submitted_value=attribute.value,
                            specification_evidence=requirement.evidence[0],
                            attachment_evidence=attribute.evidence,
                            status=DeviationStatus.DISCLOSED_DEVIATION
                            if disclosed
                            else DeviationStatus.POSSIBLE_UNDOCUMENTED_DEVIATION,
                            disclosed=disclosed,
                            explanation="Submitted text differs from the cited requirement; acceptability and equivalency are not determined.",
                        )
                    )
        return tuple(deviations)

    def _mapping(
        self,
        package: SubmittalPackage,
        revision_number: int,
        requirement: SubmittalRequirement,
        extractions: Sequence[AttachmentExtractionResult],
        conflicts: Sequence[AttachmentConflict],
        deviations: Sequence[PossibleDeviation],
    ) -> ProposedComplianceMapping:
        type_evidence = tuple(
            evidence
            for extraction in extractions
            if TYPE_TO_SUBMITTAL.get(extraction.classification.inferred_type)
            == requirement.submittal_type
            and extraction.readability.may_support_compliance_mapping
            for evidence in _extraction_evidence(extraction)
        )
        terms = {
            token
            for token in re.findall(r"[a-z0-9]+", requirement.description.casefold())
            if len(token) > 2
        }
        lexical = tuple(
            evidence
            for extraction in extractions
            for evidence in _extraction_evidence(extraction)
            if len(terms & set(re.findall(r"[a-z0-9]+", evidence.excerpt.casefold()))) >= 2
        )
        evidence = tuple(dict.fromkeys(type_evidence + lexical))
        related_deviations = tuple(
            item for item in deviations if item.requirement_id == requirement.id
        )
        related_conflicts = tuple(
            item
            for item in conflicts
            if any(evidence_item in evidence for evidence_item in item.evidence)
        )
        if related_conflicts:
            status = MatrixStatus.UNCLEAR
            explanation = "Conflicting submitted evidence requires human interpretation."
            strength = "conflicting"
        elif related_deviations:
            status = (
                MatrixStatus.DEVIATION_DISCLOSED
                if all(item.disclosed for item in related_deviations)
                else MatrixStatus.PARTIALLY_ADDRESSED
            )
            explanation = "Submitted evidence differs from the cited requirement; Brunel flags a possible deviation only."
            strength = "moderate"
        elif type_evidence:
            status = MatrixStatus.ADDRESSED
            explanation = "A readable attachment of the required type provides cited content; technical compliance is not determined."
            strength = "strong"
        elif evidence:
            status = MatrixStatus.PARTIALLY_ADDRESSED
            explanation = "Related attachment text was found, but the required document type or full evidence is unclear."
            strength = "weak"
        else:
            status = MatrixStatus.NOT_ADDRESSED
            explanation = (
                "No readable submitted attachment evidence was mapped to this requirement."
            )
            strength = "insufficient"
        return ProposedComplianceMapping(
            id=self._mapping_id(package.id, revision_number, requirement.id),
            project_id=package.project_id,
            package_id=package.id,
            package_revision=revision_number,
            requirement_id=requirement.id,
            specification_section=requirement.specification_section,
            specification_evidence=requirement.evidence[0],
            proposed_status=status,
            proposed_explanation=explanation,
            supporting_evidence=evidence,
            missing_evidence=() if evidence else (requirement.submittal_type.value,),
            conflicting_evidence_ids=tuple(item.id for item in related_conflicts),
            possible_deviation_ids=tuple(item.id for item in related_deviations),
            evidence_strength=strength,
        )

    @staticmethod
    def _mapping_id(package_id: str, revision: int, requirement_id: str) -> str:
        return f"mapping_{sha256(f'{package_id}\0{revision}\0{requirement_id}'.encode()).hexdigest()[:24]}"

    @staticmethod
    def _evidence_hash(
        revisions: Sequence[AttachmentRevision],
        requirements: Sequence[SubmittalRequirement],
        *,
        extraction_policy: str,
        mapping_policy: str,
    ) -> str:
        payload = "\0".join(
            tuple(
                f"{item.id}:{item.content_hash}:{item.extraction_result_id}" for item in revisions
            )
            + tuple(f"{item.id}:{item.description}" for item in requirements)
            + (extraction_policy, mapping_policy)
        )
        return sha256(payload.encode()).hexdigest()

    @staticmethod
    def _readability_summary(
        extractions: Sequence[AttachmentExtractionResult],
    ) -> dict[str, int]:
        summary: dict[str, int] = {}
        for extraction in extractions:
            key = extraction.readability.status.value
            summary[key] = summary.get(key, 0) + 1
        return summary

    def _apply_completeness(
        self, package: SubmittalPackage, evidence_set: PackageEvidenceSet, actor: ActorReference
    ) -> None:
        issues = tuple(
            CompletenessIssue(
                code=f"missing_actual_attachment_{item.missing_type.value}",
                severity=CompletenessSeverity.BLOCKING
                if item.blocking
                else CompletenessSeverity.WARNING,
                message=item.package_evidence_state,
                requirement_id=item.requirement_id,
                citation=item.requirement_evidence,
                blocks_routing=item.blocking,
                recommended_action=item.suggested_action,
            )
            for item in evidence_set.missing_attachments
        )
        issues += tuple(
            CompletenessIssue(
                code="unreadable_actual_attachment",
                severity=CompletenessSeverity.BLOCKING,
                message="An attachment is unreadable or unsupported and cannot satisfy a requirement.",
                blocks_routing=True,
                recommended_action="Provide a readable supported attachment or record a human disposition.",
            )
            for status, count in evidence_set.readability_summary.items()
            if status in {"unreadable", "unsupported", "corrupt"} and count
        )
        status = (
            CompletenessStatus.BLOCKED
            if any(item.blocks_routing for item in issues)
            else CompletenessStatus.COMPLETE_WITH_WARNINGS
            if issues or evidence_set.conflicts or evidence_set.possible_deviations
            else CompletenessStatus.COMPLETE
        )
        assessment = SubmittalCompletenessAssessment(
            id=f"complete_{uuid4().hex}",
            package_id=package.id,
            package_revision=evidence_set.package_revision,
            status=status,
            issues=issues,
            performed_by=actor,
            performed_at=self.clock(),
            technical_compliance_determined=False,
        )
        current = self.submittals.get_package(package.project_id, package.id)
        if current is None:
            raise SubmittalNotFoundError("Submittal package not found")
        updated = current.model_copy(
            update={
                "version": current.version + 1,
                "updated_at": self.clock(),
                "completeness_assessments": current.completeness_assessments + (assessment,),
            }
        )
        self.submittals.save_package(updated, expected_version=current.version)

    def _mark_stale(
        self,
        package: SubmittalPackage,
        prior: PackageEvidenceSet,
        current: PackageEvidenceSet,
        actor: ActorReference,
    ) -> None:
        latest = self.submittals.get_package(package.project_id, package.id)
        if latest is None:
            return
        was_reviewed = latest.internal_review_status in {
            PackageReviewStatus.APPROVED_FOR_SUBMISSION,
            PackageReviewStatus.ISSUED,
            PackageReviewStatus.RESPONSE_RECEIVED,
        } or any(
            revision.revision == current.package_revision and revision.internally_approved
            for revision in latest.revisions
        )
        if not was_reviewed:
            return
        reason = "Attachment evidence set changed after internal review; renewed human review is required."
        stale = SubmittalStalenessAssessment(
            id=f"stale_{uuid4().hex}",
            status=StalenessStatus.POTENTIALLY_STALE,
            reasons=(reason,),
            source_references=(prior.evidence_set_hash, current.evidence_set_hash),
            assessed_by=actor,
            assessed_at=self.clock(),
        )
        updated = latest.model_copy(
            update={
                "version": latest.version + 1,
                "updated_at": self.clock(),
                "internal_review_status": PackageReviewStatus.DRAFT,
                "staleness_assessments": latest.staleness_assessments + (stale,),
            }
        )
        self.submittals.save_package(updated, expected_version=latest.version)
        assessment = PackageAttachmentStalenessAssessment(
            id=f"attstale_{uuid4().hex}",
            project_id=latest.project_id,
            package_id=latest.id,
            package_revision=current.package_revision,
            status=PackageAttachmentStalenessStatus.RE_REVIEW_REQUIRED,
            reasons=(reason,),
            previous_evidence_set_hash=prior.evidence_set_hash,
            current_evidence_set_hash=current.evidence_set_hash,
            assessed_by=actor,
            assessed_at=self.clock(),
        )
        self.attachments.save_staleness(assessment)
        self._notify(updated, reason)
        self._audit(
            latest.project_id,
            latest.id,
            actor,
            "package_marked_stale",
            prior.evidence_set_hash,
            current.evidence_set_hash,
        )

    def _notify(self, package: SubmittalPackage, summary: str) -> None:
        if self.changes is None:
            return
        reviewer = next(
            (
                item.internal_reviewer
                for item_id in package.register_item_ids
                if (item := self.submittals.get_register(package.project_id, item_id))
                and item.internal_reviewer
            ),
            None,
        )
        if reviewer is None:
            return
        NotificationOutboxService(self.changes).queue(
            NotificationRequest(
                id="pending",
                project_id=package.project_id,
                change_id=package.id,
                event_id=f"{package.id}:{package.version}:attachment-stale",
                recipient=reviewer,
                notification_type=NotificationType.STATUS_CHANGED,
                created_at=self.clock(),
                payload={
                    "title": "Submittal attachment evidence changed",
                    "status": "re_review_required",
                    "summary": summary,
                },
            )
        )

    def _notify_findings(self, package: SubmittalPackage, evidence_set: PackageEvidenceSet) -> None:
        counts = {
            "missing": len(evidence_set.missing_attachments),
            "conflicts": len(evidence_set.conflicts),
            "mismatches": len(evidence_set.mismatches),
            "possible_deviations": len(evidence_set.possible_deviations),
        }
        summary = ", ".join(f"{value} {key}" for key, value in counts.items() if value)
        self._notify(package, f"Attachment analysis requires human review: {summary}.")

    def _is_duplicate(self, project_id: str, package_id: str, revision: AttachmentRevision) -> bool:
        return any(
            other.id != revision.attachment_id
            and any(item.content_hash == revision.content_hash for item in other.revisions)
            for other in self.attachments.list_attachments(project_id, package_id)
        )

    def _audit(
        self,
        project_id: str,
        entity_id: str,
        actor: ActorReference,
        event_type: str,
        previous: str | None,
        new: str | None,
    ) -> None:
        self.submittals.append_audit(
            SubmittalAuditEvent(
                id=f"subaudit_{uuid4().hex}",
                project_id=project_id,
                entity_type="submittal_attachment_intelligence",
                entity_id=entity_id,
                event_type=event_type,
                actor=actor,
                timestamp=self.clock(),
                previous_state=previous,
                new_state=new,
            )
        )


class PackageRevisionComparisonService:
    def __init__(
        self,
        attachments: JsonAttachmentIntelligenceRepository,
        submittals: JsonSubmittalRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.attachments = attachments
        self.submittals = submittals
        self.clock = clock or (lambda: datetime.now(UTC))

    def compare(
        self,
        project_id: str,
        package_id: str,
        old_revision: int,
        new_revision: int,
        actor: ActorReference,
    ) -> PackageRevisionComparison:
        SubmittalService(self.submittals).get_package(project_id, package_id)
        old = self._latest(project_id, package_id, old_revision)
        new = self._latest(project_id, package_id, new_revision)
        changes = list(self._attachment_changes(project_id, old, new))
        changes.extend(self._attribute_changes(project_id, old, new))
        changes.extend(self._mapping_changes(old, new))
        if len(old.conflicts) > len(new.conflicts):
            changes.append(
                AttachmentSetChange(
                    change_type=PackageChangeType.CONFLICT_RESOLVED,
                    subject="package conflicts",
                    old_value=str(len(old.conflicts)),
                    new_value=str(len(new.conflicts)),
                )
            )
        identity = sha256(f"{project_id}\0{package_id}\0{old.id}\0{new.id}".encode()).hexdigest()[
            :24
        ]
        existing = self.attachments.get_comparison(project_id, f"pkgcompare_{identity}")
        if existing is not None:
            return existing
        summary: dict[str, int] = {}
        for change in changes:
            summary[change.change_type.value] = summary.get(change.change_type.value, 0) + 1
        comparison = PackageRevisionComparison(
            id=f"pkgcompare_{identity}",
            project_id=project_id,
            package_id=package_id,
            old_package_revision=old_revision,
            new_package_revision=new_revision,
            old_evidence_set_id=old.id,
            new_evidence_set_id=new.id,
            old_evidence_set_hash=old.evidence_set_hash,
            new_evidence_set_hash=new.evidence_set_hash,
            changes=tuple(changes),
            summary=summary,
            re_review_required=old.evidence_set_hash != new.evidence_set_hash,
            compared_at=self.clock(),
        )
        self.attachments.save_comparison(comparison)
        self.submittals.append_audit(
            SubmittalAuditEvent(
                id=f"subaudit_{uuid4().hex}",
                project_id=project_id,
                entity_type="submittal_package_comparison",
                entity_id=comparison.id,
                event_type="package_comparison_generated",
                actor=actor,
                timestamp=self.clock(),
                previous_state=old.evidence_set_hash,
                new_state=new.evidence_set_hash,
            )
        )
        return comparison

    def _latest(self, project_id: str, package_id: str, revision: int) -> PackageEvidenceSet:
        sets = self.attachments.list_evidence_sets(project_id, package_id, revision)
        if not sets:
            raise SubmittalNotFoundError("Package revision evidence set not found")
        return sets[-1]

    def _attachment_changes(
        self, project_id: str, old: PackageEvidenceSet, new: PackageEvidenceSet
    ) -> tuple[AttachmentSetChange, ...]:
        old_revisions = self._revision_map(project_id, old)
        new_revisions = self._revision_map(project_id, new)
        changes = []
        for attachment_id in sorted(old_revisions.keys() | new_revisions.keys()):
            old_item = old_revisions.get(attachment_id)
            new_item = new_revisions.get(attachment_id)
            if old_item is None and new_item:
                changes.append(
                    AttachmentSetChange(
                        change_type=PackageChangeType.ATTACHMENT_ADDED,
                        subject=new_item.display_name,
                        new_value=new_item.content_hash,
                        new_evidence=self._revision_evidence(project_id, new_item),
                    )
                )
            elif new_item is None and old_item:
                changes.append(
                    AttachmentSetChange(
                        change_type=PackageChangeType.ATTACHMENT_REMOVED,
                        subject=old_item.display_name,
                        old_value=old_item.content_hash,
                        old_evidence=self._revision_evidence(project_id, old_item),
                    )
                )
            elif old_item and new_item and old_item.content_hash != new_item.content_hash:
                changes.append(
                    AttachmentSetChange(
                        change_type=PackageChangeType.ATTACHMENT_MODIFIED,
                        subject=new_item.display_name,
                        old_value=old_item.content_hash,
                        new_value=new_item.content_hash,
                        old_evidence=self._revision_evidence(project_id, old_item),
                        new_evidence=self._revision_evidence(project_id, new_item),
                    )
                )
        return tuple(changes)

    def _attribute_changes(
        self, project_id: str, old: PackageEvidenceSet, new: PackageEvidenceSet
    ) -> tuple[AttachmentSetChange, ...]:
        old_values = self._attribute_map(project_id, old)
        new_values = self._attribute_map(project_id, new)
        changes = []
        for name in sorted(old_values.keys() | new_values.keys()):
            old_attributes = old_values.get(name, ())
            new_attributes = new_values.get(name, ())
            old_text = ", ".join(sorted({item.value for item in old_attributes})) or None
            new_text = ", ".join(sorted({item.value for item in new_attributes})) or None
            if old_text == new_text:
                continue
            change_type = (
                PackageChangeType.MODEL_CHANGED
                if name == "model_number"
                else PackageChangeType.DIMENSION_CHANGED
                if name == "dimensions"
                else PackageChangeType.WARRANTY_CHANGED
                if name == "warranty_duration"
                else PackageChangeType.RATING_CHANGED
            )
            changes.append(
                AttachmentSetChange(
                    change_type=change_type,
                    subject=name,
                    old_value=old_text,
                    new_value=new_text,
                    old_evidence=tuple(item.evidence for item in old_attributes),
                    new_evidence=tuple(item.evidence for item in new_attributes),
                )
            )
        return tuple(changes)

    @staticmethod
    def _mapping_changes(
        old: PackageEvidenceSet, new: PackageEvidenceSet
    ) -> tuple[AttachmentSetChange, ...]:
        old_map = {item.requirement_id: item for item in old.compliance_mappings}
        new_map = {item.requirement_id: item for item in new.compliance_mappings}
        return tuple(
            AttachmentSetChange(
                change_type=PackageChangeType.REQUIREMENT_STATUS_CHANGED,
                subject=requirement_id,
                old_value=old_map[requirement_id].proposed_status.value,
                new_value=new_map[requirement_id].proposed_status.value,
                old_evidence=old_map[requirement_id].supporting_evidence,
                new_evidence=new_map[requirement_id].supporting_evidence,
            )
            for requirement_id in sorted(old_map.keys() & new_map.keys())
            if old_map[requirement_id].proposed_status != new_map[requirement_id].proposed_status
        )

    def _revision_map(
        self, project_id: str, evidence_set: PackageEvidenceSet
    ) -> dict[str, AttachmentRevision]:
        wanted = set(evidence_set.attachment_revision_ids)
        return {
            revision.attachment_id: revision
            for attachment in self.attachments.list_attachments(project_id, evidence_set.package_id)
            for revision in attachment.revisions
            if revision.id in wanted
        }

    def _attribute_map(
        self, project_id: str, evidence_set: PackageEvidenceSet
    ) -> dict[str, tuple[AttachmentTechnicalAttribute, ...]]:
        values: dict[str, list[AttachmentTechnicalAttribute]] = {}
        for extraction_id in evidence_set.extraction_result_ids:
            extraction = self.attachments.get_extraction(project_id, extraction_id)
            if not extraction:
                continue
            for identity in extraction.identities:
                if identity.model_number and identity.evidence:
                    synthetic = AttachmentTechnicalAttribute(
                        id=f"attr_model_{sha256((extraction.id + identity.model_number).encode()).hexdigest()[:16]}",
                        name="model_number",
                        value=identity.model_number,
                        evidence=identity.evidence[0],
                    )
                    values.setdefault("model_number", []).append(synthetic)
            for attribute in extraction.technical_attributes:
                values.setdefault(attribute.name, []).append(attribute)
        return {key: tuple(value) for key, value in values.items()}

    def _revision_evidence(
        self, project_id: str, revision: AttachmentRevision
    ) -> tuple[AttachmentEvidenceReference, ...]:
        if not revision.extraction_result_id:
            return ()
        extraction = self.attachments.get_extraction(project_id, revision.extraction_result_id)
        return _extraction_evidence(extraction) if extraction else ()


def _document_text(document: IngestedDocument | None) -> str:
    return "\n".join(chunk.content for chunk in document.chunks) if document else ""


def _first_group(pattern: str, text: str) -> str | None:
    match = re.search(pattern, text)
    return match.group(1).strip() if match else None


def _normalize_value(name: str, value: str) -> str | None:
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    if name == "warranty_duration":
        return words.get(value.casefold(), value)
    if name in {"nema_rating", "short_circuit_rating", "voltage", "material"}:
        return re.sub(r"\s+", "", value).upper()
    return value


def _specified_attributes(text: str) -> dict[str, str]:
    result = {}
    for name, pattern, _ in ATTRIBUTE_PATTERNS:
        match = pattern.search(text)
        if match:
            result[name] = (
                " x ".join(match.groups()[:2]) if name == "dimensions" else match.group(1)
            )
    return result


def _comparable(value: str) -> str:
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5"}
    normalized = words.get(value.casefold(), value)
    return re.sub(r"[^a-z0-9]", "", normalized.casefold())


def _extraction_evidence(
    extraction: AttachmentExtractionResult,
) -> tuple[AttachmentEvidenceReference, ...]:
    return tuple(
        dict.fromkeys(
            tuple(item for identity in extraction.identities for item in identity.evidence)
            + tuple(item.evidence for item in extraction.technical_attributes)
            + tuple(item.evidence for item in extraction.references)
        )
    )


def _safe_id(value: str) -> str:
    if not value or not value.replace("_", "").replace("-", "").isalnum():
        raise AttachmentSecurityError("Unsafe storage identifier")
    return value


def _extraction_terms(extraction: AttachmentExtractionResult) -> set[str]:
    text = " ".join(item.excerpt for item in _extraction_evidence(extraction)).casefold()
    return {token for token in re.findall(r"[a-z0-9.-]+", text) if len(token) > 2}
