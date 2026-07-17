"""CLI adapter for canonical evidence-backed submittal workflows."""

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from change_workflow.models import ActorReference, ReviewerReference
from change_workflow.repository import JsonChangeWorkflowRepository
from config.settings import Settings
from rfi.repository import JsonRFIRepository
from storage import JsonDocumentRepository
from submittal.extraction import SubmittalRequirementExtractionService
from submittal.models import (
    AttachmentMetadata,
    InternalReviewDecision,
    OfficialDisposition,
    RequirementReviewDecision,
    SubmittalManufacturer,
    SubmittalProduct,
    SubmittalStatus,
    SubmittalType,
)
from submittal.numbering import ProjectSubmittalNumberingService
from submittal.reporting import SubmittalLogService, SubmittalRenderer
from submittal.repository import JsonSubmittalRepository
from submittal.service import SubmittalService

COMMANDS = {
    "submittal-extract",
    "submittal-requirements-extract",
    "submittal-candidates",
    "submittal-review-candidate",
    "submittal-candidate-accept",
    "submittal-create",
    "submittal-list",
    "submittal-show",
    "submittal-assign",
    "submittal-package-create",
    "submittal-completeness",
    "submittal-completeness-review",
    "submittal-submit-review",
    "submittal-submit-internal-review",
    "submittal-review",
    "submittal-internal-review",
    "submittal-issue",
    "submittal-response",
    "submittal-resubmit",
    "submittal-dashboard",
    "submittal-log",
    "submittal-export",
    "submittal-demo",
}


def register_submittal_commands(commands: Any) -> None:
    extract = commands.add_parser(
        "submittal-extract",
        aliases=("submittal-requirements-extract",),
        help="Extract cited spec requirements",
    )
    extract.add_argument("--project-id", required=True)
    extract.add_argument("--document-id", action="append", default=[])
    extract.add_argument("--specification-section", action="append", default=[])
    extract.add_argument("--use-model", action="store_true")
    candidates = commands.add_parser("submittal-candidates", help="List requirement candidates")
    candidates.add_argument("--project-id", required=True)
    review_candidate = commands.add_parser("submittal-review-candidate")
    review_candidate.add_argument("--project-id", required=True)
    review_candidate.add_argument("--candidate-id", required=True)
    review_candidate.add_argument(
        "--decision", choices=[item.value for item in RequirementReviewDecision], required=True
    )
    review_candidate.add_argument("--explanation", required=True)
    review_candidate.add_argument("--subcontractor")
    accept_candidate = commands.add_parser("submittal-candidate-accept")
    accept_candidate.add_argument("--project-id", required=True)
    accept_candidate.add_argument("--candidate-id", required=True)
    accept_candidate.add_argument(
        "--explanation", default="Accepted after human review of cited requirement."
    )
    accept_candidate.add_argument("--subcontractor")

    create = commands.add_parser("submittal-create", help="Create a manual register item")
    create.add_argument("--project-id", required=True)
    create.add_argument("--specification-section", "--spec-section", required=True)
    create.add_argument("--description", required=True)
    create.add_argument("--discipline")
    create.add_argument("--subcontractor")
    listing = commands.add_parser("submittal-list")
    listing.add_argument("--project-id", required=True)
    listing.add_argument("--status", choices=[item.value for item in SubmittalStatus])
    show = commands.add_parser("submittal-show")
    _item_ids(show)
    assign = commands.add_parser("submittal-assign")
    _item_ids(assign)
    assign.add_argument("--reviewer-id")
    assign.add_argument("--reviewer-name", default="Reviewer")
    assign.add_argument("--subcontractor")
    assign.add_argument("--planned-submit", type=date.fromisoformat)
    assign.add_argument("--required-response", type=date.fromisoformat)

    package = commands.add_parser("submittal-package-create")
    _item_ids(package)
    package.add_argument("--submitter", required=True)
    package.add_argument("--title")
    package.add_argument("--description", default="")
    package.add_argument("--manufacturer")
    package.add_argument("--product")
    package.add_argument(
        "--included-type",
        action="append",
        choices=[item.value for item in SubmittalType],
        default=[],
    )
    package.add_argument("--attachment", action="append", type=Path, default=[])
    completeness = commands.add_parser(
        "submittal-completeness", aliases=("submittal-completeness-review",)
    )
    _package_ids(completeness)
    submit = commands.add_parser(
        "submittal-submit-review", aliases=("submittal-submit-internal-review",)
    )
    _package_ids(submit)
    submit.add_argument("--reviewer-id", required=True)
    submit.add_argument("--reviewer-name", default="Reviewer")
    review = commands.add_parser("submittal-review", aliases=("submittal-internal-review",))
    _package_ids(review)
    review.add_argument("--reviewer-id", required=True)
    review.add_argument("--reviewer-name", default="Reviewer")
    review.add_argument(
        "--decision", choices=[item.value for item in InternalReviewDecision], required=True
    )
    review.add_argument("--comments")
    issue = commands.add_parser("submittal-issue")
    _package_ids(issue)
    response = commands.add_parser("submittal-response")
    _package_ids(response)
    response.add_argument("--organization", required=True)
    response.add_argument(
        "--disposition", choices=[item.value for item in OfficialDisposition], required=True
    )
    response_source = response.add_mutually_exclusive_group(required=True)
    response_source.add_argument("--response")
    response_source.add_argument("--response-file", type=Path)
    response.add_argument("--correction", action="append", default=[])
    response.add_argument("--informal", action="store_true")
    resubmit = commands.add_parser("submittal-resubmit")
    _package_ids(resubmit)
    resubmit.add_argument("--change-summary", required=True)

    dashboard = commands.add_parser("submittal-dashboard")
    dashboard.add_argument("--project-id", required=True)
    log = commands.add_parser("submittal-log")
    log.add_argument("--project-id", required=True)
    export = commands.add_parser("submittal-export")
    _item_ids(export)
    export.add_argument("--format", choices=("markdown", "json"), default="markdown")
    export.add_argument("--output", type=Path)
    demo = commands.add_parser("submittal-demo")
    demo.add_argument("--project-id", default="synthetic-submittal-demo")


def _item_ids(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--submittal-id", required=True)


def _package_ids(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--package-id", required=True)


def _repository(settings: Settings) -> JsonSubmittalRepository:
    return JsonSubmittalRepository(settings.data_directory / "submittals")


def _service(settings: Settings, repository: JsonSubmittalRepository) -> SubmittalService:
    return SubmittalService(
        repository,
        JsonChangeWorkflowRepository(settings.data_directory / "change-workflow"),
        JsonRFIRepository(settings.data_directory / "rfi"),
        numbering=ProjectSubmittalNumberingService(
            repository,
            prefix=settings.submittal.numbering_prefix,
            digits=settings.submittal.numbering_digits,
            mode=settings.submittal.numbering_mode,
        ),
    )


def run_submittal_command(args: argparse.Namespace, settings: Settings) -> int:
    if args.command == "submittal-demo":
        from app.submittal_demo import run_synthetic_submittal_demo

        print(
            json.dumps(
                run_synthetic_submittal_demo(settings.data_directory, args.project_id), indent=2
            )
        )
        return 0
    repository = _repository(settings)
    service = _service(settings, repository)
    actor = ActorReference(id="cli-user", display_name="CLI User")
    if args.command in {"submittal-extract", "submittal-requirements-extract"}:
        extraction_result = SubmittalRequirementExtractionService(
            JsonDocumentRepository(settings.data_directory / "ingested"), repository
        ).extract(
            args.project_id,
            document_ids=tuple(args.document_id),
            specification_sections=tuple(args.specification_section),
            use_model=args.use_model and settings.submittal.model_assistance_enabled,
        )
        print(extraction_result.model_dump_json(indent=2))
        return 0
    if args.command == "submittal-candidates":
        for item in repository.list_candidates(args.project_id):
            print(
                f"{item.id}\t{item.status.value}\t{item.submittal_type.value}\t{item.description}"
            )
        return 0
    if args.command in {"submittal-review-candidate", "submittal-candidate-accept"}:
        decision = (
            RequirementReviewDecision.ACCEPT
            if args.command == "submittal-candidate-accept"
            else RequirementReviewDecision(args.decision)
        )
        admission_result = service.review_candidate(
            args.project_id,
            args.candidate_id,
            decision,
            actor,
            explanation=args.explanation,
            responsible_subcontractor=args.subcontractor,
        )
        print(admission_result.model_dump_json(indent=2))
        return 0
    if args.command == "submittal-create":
        created_item = service.create_register(
            project_id=args.project_id,
            specification_section=args.specification_section,
            description=args.description,
            actor=actor,
            discipline=args.discipline,
            responsible_subcontractor=args.subcontractor,
        )
        print(f"Created {created_item.register_number} ({created_item.id}).")
        return 0
    if args.command in {"submittal-list", "submittal-log"}:
        status = SubmittalStatus(args.status) if getattr(args, "status", None) else None
        for log_item in SubmittalLogService(repository).list(args.project_id, status=status):
            print(
                f"{log_item.register_number}\t{log_item.status.value}\t"
                f"{log_item.description}\t{log_item.id}"
            )
        return 0
    if args.command == "submittal-show":
        print(service.get_register(args.project_id, args.submittal_id).model_dump_json(indent=2))
        return 0
    if args.command == "submittal-assign":
        reviewer = (
            ReviewerReference(id=args.reviewer_id, display_name=args.reviewer_name)
            if args.reviewer_id
            else None
        )
        service.assign(
            args.project_id,
            args.submittal_id,
            actor,
            reviewer=reviewer,
            subcontractor=args.subcontractor,
            planned_submit_date=args.planned_submit,
            required_response_date=args.required_response,
        )
        print("Assignment updated.")
        return 0
    if args.command == "submittal-package-create":
        included = tuple(SubmittalType(value) for value in args.included_type)
        attachments = tuple(
            AttachmentMetadata(
                id=f"cli-{index}",
                filename=path.name,
                document_type=included[min(index - 1, len(included) - 1)]
                if included
                else SubmittalType.OTHER,
                storage_reference=str(path),
            )
            for index, path in enumerate(args.attachment, start=1)
        )
        package = service.create_package(
            args.project_id,
            args.submittal_id,
            actor,
            title=args.title,
            description=args.description,
            submitter=args.submitter,
            manufacturer=(
                SubmittalManufacturer(name=args.manufacturer, project_id=args.project_id)
                if args.manufacturer
                else None
            ),
            product=(SubmittalProduct(name=args.product) if args.product else None),
            included_types=included,
            attachments=attachments,
        )
        print(package.model_dump_json(indent=2))
        return 0
    if args.command in {"submittal-completeness", "submittal-completeness-review"}:
        print(
            service.review_completeness(args.project_id, args.package_id, actor).model_dump_json(
                indent=2
            )
        )
        return 0
    if args.command in {"submittal-submit-review", "submittal-submit-internal-review"}:
        service.submit_internal_review(
            args.project_id,
            args.package_id,
            ReviewerReference(id=args.reviewer_id, display_name=args.reviewer_name),
            actor,
        )
        print("Submitted for internal review.")
        return 0
    if args.command in {"submittal-review", "submittal-internal-review"}:
        service.internal_review(
            args.project_id,
            args.package_id,
            InternalReviewDecision(args.decision),
            ReviewerReference(id=args.reviewer_id, display_name=args.reviewer_name),
            actor,
            comments=args.comments,
        )
        print(f"Internal review decision: {args.decision}.")
        return 0
    if args.command == "submittal-issue":
        service.issue_package(args.project_id, args.package_id, actor)
        print("Package issued.")
        return 0
    if args.command == "submittal-response":
        response_text = (
            args.response_file.resolve().read_text(encoding="utf-8")
            if args.response_file
            else args.response
        )
        service.record_response(
            args.project_id,
            args.package_id,
            actor,
            responding_organization=args.organization,
            disposition=OfficialDisposition(args.disposition),
            original_disposition_text=response_text,
            required_corrections=tuple(args.correction),
            official=not args.informal,
        )
        print("Response recorded.")
        return 0
    if args.command == "submittal-resubmit":
        service.resubmit(
            args.project_id, args.package_id, actor, change_summary=args.change_summary
        )
        print("Resubmittal revision created.")
        return 0
    if args.command == "submittal-dashboard":
        print(SubmittalLogService(repository).dashboard(args.project_id).model_dump_json(indent=2))
        return 0
    if args.command == "submittal-export":
        export_item = service.record_export(args.project_id, args.submittal_id, actor, args.format)
        packages = tuple(
            package
            for package in repository.list_packages(args.project_id)
            if export_item.id in package.register_item_ids
        )
        content = (
            export_item.model_dump_json(indent=2)
            if args.format == "json"
            else SubmittalRenderer(repository).markdown(export_item, packages)
        )
        target = (
            args.output
            or settings.submittal.exports_directory
            / f"{export_item.register_number}.{args.format if args.format == 'json' else 'md'}"
        ).resolve()
        root = Path.cwd().resolve()
        if target != root and root not in target.parents:
            raise ValueError("Export path must stay within workspace")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        print(f"Exported {target}")
        return 0
    return 1
