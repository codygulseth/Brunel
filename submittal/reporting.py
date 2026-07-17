"""Project submittal logs, dashboards, aging, and exports."""

import csv
import io
from collections.abc import Callable
from datetime import UTC, date, datetime
from statistics import median

from .models import (
    OfficialDisposition,
    ProcurementExposureStatus,
    SubmittalDashboard,
    SubmittalPackage,
    SubmittalRegisterItem,
    SubmittalStatus,
    SubmittalType,
)
from .repository import JsonSubmittalRepository


OPEN_STATUSES = {
    status
    for status in SubmittalStatus
    if status not in {SubmittalStatus.CLOSED, SubmittalStatus.VOID, SubmittalStatus.SUPERSEDED}
}


class SubmittalLogService:
    def __init__(self, repository: JsonSubmittalRepository) -> None:
        self.repository = repository

    def list(
        self,
        project_id: str,
        *,
        status: SubmittalStatus | None = None,
        discipline: str | None = None,
        subcontractor: str | None = None,
        reviewer_id: str | None = None,
        specification_section: str | None = None,
        submittal_type: SubmittalType | None = None,
        overdue: bool | None = None,
        exposure: ProcurementExposureStatus | None = None,
        related_rfi_id: str | None = None,
        related_change_id: str | None = None,
        search: str | None = None,
        today: date | None = None,
    ) -> tuple[SubmittalRegisterItem, ...]:
        current = today or datetime.now(UTC).date()
        items = self.repository.list_register(project_id)
        if status:
            items = tuple(item for item in items if item.status == status)
        if discipline:
            items = tuple(item for item in items if item.discipline == discipline)
        if subcontractor:
            items = tuple(item for item in items if item.responsible_subcontractor == subcontractor)
        if reviewer_id:
            items = tuple(
                item
                for item in items
                if item.internal_reviewer and item.internal_reviewer.id == reviewer_id
            )
        if specification_section:
            items = tuple(
                item for item in items if item.specification_section == specification_section
            )
        if submittal_type:
            items = tuple(
                item
                for item in items
                if any(req.submittal_type == submittal_type for req in item.requirements)
            )
        if overdue is not None:
            items = tuple(item for item in items if self._is_overdue(item, current) == overdue)
        if exposure:
            items = tuple(item for item in items if item.procurement.exposure_status == exposure)
        if related_rfi_id:
            items = tuple(item for item in items if related_rfi_id in item.related_rfi_ids)
        if related_change_id:
            items = tuple(
                item for item in items if related_change_id in item.related_project_change_ids
            )
        if search:
            needle = search.casefold()
            items = tuple(
                item
                for item in items
                if needle
                in " ".join(
                    (
                        item.register_number,
                        item.specification_section,
                        item.description,
                        item.discipline or "",
                        item.responsible_subcontractor or "",
                        " ".join(item.drawing_references),
                        " ".join(item.equipment_references),
                        " ".join(item.related_rfi_ids),
                        " ".join(item.related_project_change_ids),
                    )
                ).casefold()
            )
        return tuple(sorted(items, key=lambda item: (item.register_number, item.id)))

    def dashboard(self, project_id: str, *, today: date | None = None) -> SubmittalDashboard:
        current = today or datetime.now(UTC).date()
        items = self.repository.list_register(project_id)
        packages = self.repository.list_packages(project_id)
        review_durations = [
            (item.actual_response_date - item.actual_submit_date).days
            for item in items
            if item.actual_submit_date and item.actual_response_date
        ]
        resubmittals = [max(package.current_revision - 1, 0) for package in packages]
        metrics: dict[str, int | float] = {
            "total": len(items),
            "candidate_requirements": sum(
                candidate.status.value == "pending_review"
                for candidate in self.repository.list_candidates(project_id)
            ),
            "planned": sum(item.status == SubmittalStatus.PLANNED for item in items),
            "in_preparation": sum(item.status == SubmittalStatus.IN_PREPARATION for item in items),
            "pending_subcontractor": sum(
                item.status == SubmittalStatus.PENDING_SUBCONTRACTOR for item in items
            ),
            "pending_internal_review": sum(
                item.status == SubmittalStatus.PENDING_INTERNAL_REVIEW for item in items
            ),
            "ready_to_submit": sum(
                item.status == SubmittalStatus.READY_TO_SUBMIT for item in items
            ),
            "under_design_review": sum(
                item.status == SubmittalStatus.UNDER_DESIGN_REVIEW for item in items
            ),
            "overdue_submissions": sum(
                bool(
                    item.planned_submit_date
                    and item.planned_submit_date < current
                    and item.actual_submit_date is None
                    and item.status in OPEN_STATUSES
                )
                for item in items
            ),
            "overdue_responses": sum(
                bool(
                    item.required_response_date
                    and item.required_response_date < current
                    and item.actual_response_date is None
                    and item.status == SubmittalStatus.UNDER_DESIGN_REVIEW
                )
                for item in items
            ),
            "approved": sum(item.status == SubmittalStatus.APPROVED for item in items),
            "approved_as_noted": sum(
                item.status == SubmittalStatus.APPROVED_AS_NOTED for item in items
            ),
            "revise_and_resubmit": sum(
                item.status == SubmittalStatus.REVISE_AND_RESUBMIT for item in items
            ),
            "rejected": sum(item.status == SubmittalStatus.REJECTED for item in items),
            "procurement_critical": sum(
                item.procurement_criticality.value in {"critical", "high"}
                or item.procurement.long_lead
                for item in items
            ),
            "at_risk_required_on_site": sum(
                item.procurement.exposure_status
                in {ProcurementExposureStatus.AT_RISK, ProcurementExposureStatus.OVERDUE}
                for item in items
            ),
            "average_review_days": round(sum(review_durations) / len(review_durations), 2)
            if review_durations
            else 0.0,
            "median_review_days": float(median(review_durations)) if review_durations else 0.0,
            "average_resubmittal_count": round(sum(resubmittals) / len(resubmittals), 2)
            if resubmittals
            else 0.0,
            "current_approved_packages": sum(
                bool(
                    package.official_review_status
                    in {OfficialDisposition.APPROVED, OfficialDisposition.APPROVED_AS_NOTED}
                    and (
                        not package.staleness_assessments
                        or package.staleness_assessments[-1].status.value == "current"
                    )
                )
                for package in packages
            ),
            "superseded_package_revisions": sum(
                max(package.current_revision - 1, 0) for package in packages
            ),
        }
        return SubmittalDashboard(
            project_id=project_id,
            metrics=metrics,
            by_discipline=self._group(items, lambda item: item.discipline or "unassigned"),
            by_subcontractor=self._group(
                items, lambda item: item.responsible_subcontractor or "unassigned"
            ),
            by_specification_section=self._group(items, lambda item: item.specification_section),
            oldest_outstanding=tuple(
                sorted(
                    (item for item in items if item.status in OPEN_STATUSES),
                    key=lambda item: item.created_at,
                )[:10]
            ),
        )

    @staticmethod
    def aging(item: SubmittalRegisterItem, *, today: date | None = None) -> dict[str, int]:
        current = today or datetime.now(UTC).date()
        return {
            "days_outstanding": (current - item.created_at.date()).days,
            "days_overdue_submission": max((current - item.planned_submit_date).days, 0)
            if item.planned_submit_date and item.actual_submit_date is None
            else 0,
            "days_overdue_response": max((current - item.required_response_date).days, 0)
            if item.required_response_date and item.actual_response_date is None
            else 0,
            "total_cycle_days": (
                (item.closed_at.date() - item.created_at.date()).days if item.closed_at else 0
            ),
        }

    @staticmethod
    def _is_overdue(item: SubmittalRegisterItem, current: date) -> bool:
        return bool(
            item.status in OPEN_STATUSES
            and (
                item.planned_submit_date
                and item.planned_submit_date < current
                and item.actual_submit_date is None
                or item.required_response_date
                and item.required_response_date < current
                and item.actual_response_date is None
            )
        )

    @staticmethod
    def _group(
        items: tuple[SubmittalRegisterItem, ...], key: Callable[[SubmittalRegisterItem], str]
    ) -> dict[str, int]:
        result: dict[str, int] = {}
        for item in items:
            label = key(item)
            result[label] = result.get(label, 0) + 1
        return result


class SubmittalRenderer:
    def __init__(self, repository: JsonSubmittalRepository | None = None) -> None:
        self.repository = repository

    def markdown(self, item: SubmittalRegisterItem, packages: tuple[SubmittalPackage, ...]) -> str:
        lines = [
            f"# {item.register_number}: {item.description}",
            "",
            f"- **Project:** {item.project_id}",
            f"- **Specification:** {item.specification_section}",
            f"- **Status:** {item.status.value}",
            f"- **Subcontractor:** {item.responsible_subcontractor or 'Unassigned'}",
            f"- **Planned submit:** {item.planned_submit_date or 'Not set'}",
            f"- **Required response:** {item.required_response_date or 'Not set'}",
            f"- **Required on site:** {item.required_on_site_date or 'Not set'}",
            "",
            "## Specification requirements",
            "",
        ]
        for requirement in item.requirements:
            lines.append(f"- **{requirement.submittal_type.value}:** {requirement.description}")
            for evidence in requirement.evidence:
                lines.append(
                    f"  - {evidence.citation.document_name}, page {evidence.citation.page_number}, chunk `{evidence.citation.chunk_id}`"
                )
        lines.extend(["", "## Packages", ""])
        for package in packages:
            revision = package.revisions[-1]
            lines.extend(
                [
                    f"### {package.package_number} Revision {revision.revision}",
                    "",
                    revision.description,
                    "",
                    f"Included types: {', '.join(item.value for item in revision.included_types) or 'None'}",
                    f"Attachments: {', '.join(item.filename for item in revision.attachments) or 'None'}",
                    f"Official disposition: {package.official_review_status.value if package.official_review_status else 'None'}",
                    "",
                ]
            )
        lines.extend(
            [
                "## Authority notice",
                "",
                "Completeness does not equal technical compliance. Official dispositions must be explicitly recorded, and procurement release remains human-controlled.",
                "",
            ]
        )
        return "\n".join(lines)

    def log_markdown(self, items: tuple[SubmittalRegisterItem, ...]) -> str:
        lines = [
            "# Submittal Log",
            "",
            "| Number | Specification | Description | Status | Subcontractor |",
            "| --- | --- | --- | --- | --- |",
        ]
        lines.extend(
            f"| {item.register_number} | {item.specification_section} | {item.description} | {item.status.value} | {item.responsible_subcontractor or ''} |"
            for item in items
        )
        return "\n".join(lines) + "\n"

    def csv_log(self, items: tuple[SubmittalRegisterItem, ...]) -> str:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            (
                "register_number",
                "specification_section",
                "description",
                "discipline",
                "subcontractor",
                "status",
                "planned_submit",
                "actual_submit",
                "required_response",
                "actual_response",
                "required_on_site",
                "procurement_exposure",
                "resubmittal_count",
            )
        )
        for item in items:
            writer.writerow(
                (
                    item.register_number,
                    item.specification_section,
                    item.description,
                    item.discipline or "",
                    item.responsible_subcontractor or "",
                    item.status.value,
                    item.planned_submit_date or "",
                    item.actual_submit_date or "",
                    item.required_response_date or "",
                    item.actual_response_date or "",
                    item.required_on_site_date or "",
                    item.procurement.exposure_status.value,
                    self._resubmittal_count(item),
                )
            )
        return output.getvalue()

    def _resubmittal_count(self, item: SubmittalRegisterItem) -> int:
        if self.repository is None:
            return 0
        revisions = []
        for package_id in item.package_ids:
            package = self.repository.get_package(item.project_id, package_id)
            if package:
                revisions.append(max(package.current_revision - 1, 0))
        return max(revisions, default=0)
