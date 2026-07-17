"""CLI commands for deterministic submittal attachment intelligence."""

import argparse
import json
from pathlib import Path
from typing import Any

from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config.settings import Settings
from storage import JsonDocumentRepository
from submittal.attachment_intelligence import (
    AttachmentIngestionService,
    LocalAttachmentFileStore,
    PackageAttachmentAnalysisService,
    PackageRevisionComparisonService,
)
from submittal.attachment_models import (
    AttachmentRole,
    AttachmentType,
    HumanConfirmationStatus,
)
from submittal.attachment_qa import AttachmentQuestionService, AttachmentSearchService
from submittal.attachment_reporting import AttachmentIntelligenceRenderer
from submittal.attachment_repository import JsonAttachmentIntelligenceRepository
from submittal.models import MatrixStatus
from submittal.repository import JsonSubmittalRepository

COMMANDS = {
    "submittal-attachment-add",
    "submittal-attachment-list",
    "submittal-attachment-show",
    "submittal-attachment-extraction",
    "submittal-attachment-analyze",
    "submittal-package-analyze",
    "submittal-package-conflicts",
    "submittal-package-missing",
    "submittal-attachment-mappings",
    "submittal-compliance-generate",
    "submittal-attachment-review-mapping",
    "submittal-compliance-review",
    "submittal-attachment-compare",
    "submittal-package-compare",
    "submittal-attachment-staleness",
    "submittal-package-stale-check",
    "submittal-attachment-staleness-acknowledge",
    "submittal-attachment-search",
    "submittal-attachment-ask",
    "submittal-attachment-export",
    "submittal-attachment-demo",
}


def register_submittal_attachment_commands(commands: Any) -> None:
    add = commands.add_parser("submittal-attachment-add", help="Register and analyze an attachment")
    _package_ids(add)
    add.add_argument("--file", required=True, type=Path)
    add.add_argument("--package-revision", type=int)
    add.add_argument("--attachment-id")
    add.add_argument("--declared-type", choices=[item.value for item in AttachmentType])
    add.add_argument("--role", choices=[item.value for item in AttachmentRole], default="unknown")
    add.add_argument("--display-name")
    add.add_argument("--revision-label")
    add.add_argument("--supersedes")

    listing = commands.add_parser("submittal-attachment-list")
    _package_ids(listing)
    show = commands.add_parser("submittal-attachment-show")
    _attachment_ids(show)
    extraction = commands.add_parser("submittal-attachment-extraction")
    extraction.add_argument("--project-id", required=True)
    extraction.add_argument("--extraction-id", required=True)
    analyze = commands.add_parser(
        "submittal-attachment-analyze", aliases=("submittal-package-analyze",)
    )
    _package_ids(analyze)
    conflicts = commands.add_parser("submittal-package-conflicts")
    _package_ids(conflicts)
    missing = commands.add_parser("submittal-package-missing")
    _package_ids(missing)
    mappings = commands.add_parser(
        "submittal-attachment-mappings", aliases=("submittal-compliance-generate",)
    )
    _package_ids(mappings)
    review = commands.add_parser(
        "submittal-attachment-review-mapping", aliases=("submittal-compliance-review",)
    )
    _package_ids(review)
    review.add_argument("--requirement-id", required=True)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--reviewer-name", default="Reviewer")
    review.add_argument(
        "--confirmation", choices=[item.value for item in HumanConfirmationStatus], required=True
    )
    review.add_argument("--status", choices=[item.value for item in MatrixStatus])
    review.add_argument("--note")
    compare = commands.add_parser(
        "submittal-attachment-compare", aliases=("submittal-package-compare",)
    )
    _package_ids(compare)
    compare.add_argument("--old-revision", type=int, required=True)
    compare.add_argument("--new-revision", type=int, required=True)
    compare.add_argument("--output", type=Path)
    stale = commands.add_parser(
        "submittal-attachment-staleness", aliases=("submittal-package-stale-check",)
    )
    _package_ids(stale)
    acknowledge = commands.add_parser("submittal-attachment-staleness-acknowledge")
    _package_ids(acknowledge)
    search = commands.add_parser("submittal-attachment-search")
    search.add_argument("--project-id", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--package-id")
    search.add_argument("--package-revision", type=int)
    search.add_argument("--attachment-type", choices=[item.value for item in AttachmentType])
    ask = commands.add_parser("submittal-attachment-ask")
    ask.add_argument("--project-id", required=True)
    ask.add_argument("--question", required=True)
    ask.add_argument("--package-id")
    export = commands.add_parser("submittal-attachment-export")
    _package_ids(export)
    export.add_argument("--format", choices=("markdown", "json"), default="markdown")
    export.add_argument("--output", type=Path)
    demo = commands.add_parser("submittal-attachment-demo")
    demo.add_argument("--project-id", default="synthetic-attachment-demo")


def run_submittal_attachment_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.command == "submittal-attachment-demo":
        from app.submittal_attachment_demo import run_synthetic_attachment_demo

        print(
            json.dumps(
                run_synthetic_attachment_demo(settings.data_directory, args.project_id), indent=2
            )
        )
        return 0
    attachments, submittals, analysis = _services(settings)
    actor = ActorReference(id="cli-user", display_name="CLI User")
    if args.command == "submittal-attachment-add":
        ingestion_result = AttachmentIngestionService(
            attachments,
            submittals,
            JsonDocumentRepository(settings.data_directory / "ingested"),
            LocalAttachmentFileStore(
                settings.data_directory / settings.submittal.attachment_storage_directory
            ),
            JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
            maximum_file_size=settings.submittal.attachment_max_file_size,
            allowed_input_root=Path.cwd(),
            extraction_policy_version=settings.submittal.attachment_extractor_version,
            mapping_policy_version=settings.submittal.attachment_mapping_policy,
        ).ingest(
            args.project_id,
            args.package_id,
            args.file,
            actor,
            package_revision=args.package_revision,
            attachment_id=args.attachment_id,
            declared_type=AttachmentType(args.declared_type) if args.declared_type else None,
            role=AttachmentRole(args.role),
            display_name=args.display_name,
            revision_label=args.revision_label,
            supersedes_attachment_revision_id=args.supersedes,
        )
        print(
            ingestion_result.model_dump_json(
                indent=2, exclude={"attachment": {"revisions": {"__all__": {"storage_reference"}}}}
            )
        )
        return 0
    if args.command == "submittal-attachment-list":
        for item in attachments.list_attachments(args.project_id, args.package_id):
            active = next(rev for rev in item.revisions if rev.id == item.active_revision_id)
            print(
                f"{item.id}\t{active.id}\t{active.inferred_type.value}\t{active.readability_status.value}"
            )
        return 0
    if args.command == "submittal-attachment-show":
        attachment_record = attachments.get_attachment(args.project_id, args.attachment_id)
        print(
            attachment_record.model_dump_json(
                indent=2, exclude={"revisions": {"__all__": {"storage_reference"}}}
            )
            if attachment_record
            else "Attachment not found."
        )
        return 0 if attachment_record else 1
    if args.command == "submittal-attachment-extraction":
        extraction_record = attachments.get_extraction(args.project_id, args.extraction_id)
        print(
            extraction_record.model_dump_json(indent=2)
            if extraction_record
            else "Extraction not found."
        )
        return 0 if extraction_record else 1
    if args.command in {"submittal-attachment-analyze", "submittal-package-analyze"}:
        print(
            analysis.analyze_package(args.project_id, args.package_id, actor).model_dump_json(
                indent=2
            )
        )
        return 0
    if args.command == "submittal-package-conflicts":
        evidence = analysis.latest_evidence_set(args.project_id, args.package_id)
        print(
            json.dumps(
                [item.model_dump(mode="json") for item in evidence.conflicts] if evidence else [],
                indent=2,
            )
        )
        return 0
    if args.command == "submittal-package-missing":
        evidence = analysis.latest_evidence_set(args.project_id, args.package_id)
        print(
            json.dumps(
                [item.model_dump(mode="json") for item in evidence.missing_attachments]
                if evidence
                else [],
                indent=2,
            )
        )
        return 0
    if args.command in {"submittal-attachment-mappings", "submittal-compliance-generate"}:
        if args.command == "submittal-compliance-generate":
            analysis.analyze_package(args.project_id, args.package_id, actor)
        print(
            json.dumps(
                [
                    item.model_dump(mode="json")
                    for item in attachments.list_mappings(args.project_id, args.package_id)
                ],
                indent=2,
            )
        )
        return 0
    if args.command in {
        "submittal-attachment-review-mapping",
        "submittal-compliance-review",
    }:
        mapping_review = analysis.review_mapping(
            args.project_id,
            args.package_id,
            args.requirement_id,
            ReviewerReference(id=args.reviewer_id, display_name=args.reviewer_name),
            actor,
            confirmation=HumanConfirmationStatus(args.confirmation),
            status=MatrixStatus(args.status) if args.status else None,
            note=args.note,
        )
        print(mapping_review.model_dump_json(indent=2))
        return 0
    if args.command in {"submittal-attachment-compare", "submittal-package-compare"}:
        comparison_result = PackageRevisionComparisonService(attachments, submittals).compare(
            args.project_id, args.package_id, args.old_revision, args.new_revision, actor
        )
        if args.output:
            target = args.output.resolve()
            workspace = Path.cwd().resolve()
            if target != workspace and workspace not in target.parents:
                raise ValueError("Comparison export path must stay within workspace")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(
                AttachmentIntelligenceRenderer.comparison_markdown(comparison_result),
                encoding="utf-8",
            )
            print(target)
        else:
            print(comparison_result.model_dump_json(indent=2))
        return 0
    if args.command in {
        "submittal-attachment-staleness",
        "submittal-package-stale-check",
    }:
        print(
            analysis.check_staleness(args.project_id, args.package_id, actor).model_dump_json(
                indent=2
            )
        )
        return 0
    if args.command == "submittal-attachment-staleness-acknowledge":
        print(
            analysis.acknowledge_staleness(args.project_id, args.package_id, actor).model_dump_json(
                indent=2
            )
        )
        return 0
    if args.command == "submittal-attachment-search":
        print(
            json.dumps(
                [
                    item.model_dump(mode="json")
                    for item in AttachmentSearchService(attachments, submittals).search(
                        args.project_id,
                        args.query,
                        package_id=args.package_id,
                        package_revision=args.package_revision,
                        attachment_type=AttachmentType(args.attachment_type)
                        if args.attachment_type
                        else None,
                    )
                ],
                indent=2,
            )
        )
        return 0
    if args.command == "submittal-attachment-ask":
        print(
            AttachmentQuestionService(attachments, submittals)
            .answer(args.project_id, args.question, package_id=args.package_id)
            .model_dump_json(indent=2)
        )
        return 0
    if args.command == "submittal-attachment-export":
        suffix = "json" if args.format == "json" else "md"
        target = (
            args.output
            or settings.submittal.exports_directory / "attachments" / f"{args.package_id}.{suffix}"
        )
        target = target.resolve()
        workspace = Path.cwd().resolve()
        if target != workspace and workspace not in target.parents:
            raise ValueError("Export path must stay within workspace")
        print(
            AttachmentIntelligenceRenderer(attachments, analysis).export(
                args.project_id, args.package_id, target, format=args.format
            )
        )
        return 0
    return 1


def _services(
    settings: Settings,
) -> tuple[
    JsonAttachmentIntelligenceRepository,
    JsonSubmittalRepository,
    PackageAttachmentAnalysisService,
]:
    attachments = JsonAttachmentIntelligenceRepository(
        settings.data_directory / "submittal-attachment-intelligence"
    )
    submittals = JsonSubmittalRepository(settings.data_directory / "submittals")
    analysis = PackageAttachmentAnalysisService(
        attachments,
        submittals,
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        extraction_policy_version=settings.submittal.attachment_extractor_version,
        mapping_policy_version=settings.submittal.attachment_mapping_policy,
    )
    return attachments, submittals, analysis


def _package_ids(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--package-id", required=True)


def _attachment_ids(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--attachment-id", required=True)
