"""RFI log, dashboard, Markdown, JSON, and CSV rendering."""

import csv
import io
from datetime import UTC, date, datetime
from statistics import median
from .models import RFI, RFIDashboard, RFIImpactType, RFIPriority, RFIStatus
from .repository import JsonRFIRepository


OPEN = {
    RFIStatus.DRAFT,
    RFIStatus.PENDING_INTERNAL_REVIEW,
    RFIStatus.REVISIONS_REQUIRED,
    RFIStatus.APPROVED_FOR_ISSUE,
    RFIStatus.ISSUED,
    RFIStatus.ACKNOWLEDGED,
    RFIStatus.UNDER_REVIEW,
    RFIStatus.RESPONSE_RECEIVED,
    RFIStatus.CLARIFICATION_REQUIRED,
    RFIStatus.ANSWERED,
}


class RFILogService:
    def __init__(self, repository: JsonRFIRepository) -> None:
        self.repository = repository

    def list(
        self,
        project_id: str,
        *,
        status: RFIStatus | None = None,
        discipline: str | None = None,
        priority: RFIPriority | None = None,
        reviewer_id: str | None = None,
        responsible_party: str | None = None,
        overdue: bool | None = None,
        open_only: bool | None = None,
        project_change_id: str | None = None,
        drawing_reference: str | None = None,
        specification_section: str | None = None,
        created_from: date | None = None,
        created_to: date | None = None,
        search: str | None = None,
        today: date | None = None,
    ) -> tuple[RFI, ...]:
        current = today or datetime.now(UTC).date()
        items = self.repository.list(project_id)
        if status:
            items = tuple(x for x in items if x.status == status)
        if discipline:
            items = tuple(x for x in items if x.discipline == discipline)
        if priority:
            items = tuple(x for x in items if x.priority == priority)
        if reviewer_id:
            items = tuple(
                x for x in items if x.assigned_reviewer and x.assigned_reviewer.id == reviewer_id
            )
        if responsible_party:
            items = tuple(x for x in items if x.responsible_party == responsible_party)
        if open_only is not None:
            items = tuple(x for x in items if (x.status in OPEN) == open_only)
        if project_change_id:
            items = tuple(x for x in items if project_change_id in x.related_project_change_ids)
        if drawing_reference:
            items = tuple(x for x in items if drawing_reference in x.drawing_references)
        if specification_section:
            items = tuple(x for x in items if specification_section in x.specification_references)
        if created_from:
            items = tuple(x for x in items if x.created_at.date() >= created_from)
        if created_to:
            items = tuple(x for x in items if x.created_at.date() <= created_to)
        if overdue is not None:
            items = tuple(
                x
                for x in items
                if bool(x.required_date and x.required_date < current and x.status in OPEN)
                == overdue
            )
        if search:
            items = tuple(
                x
                for x in items
                if search.casefold()
                in f"{x.number} {x.subject} {x.question} {x.background}".casefold()
            )
        return tuple(sorted(items, key=lambda x: (x.number, x.id)))

    def dashboard(self, project_id: str, today: date | None = None) -> RFIDashboard:
        current = today or datetime.now(UTC).date()
        items = self.repository.list(project_id)
        open_items = tuple(x for x in items if x.status in OPEN)
        response_days = [
            (x.answered_at.date() - x.issued_at.date()).days
            for x in items
            if x.answered_at and x.issued_at
        ]
        metrics = {
            "total": len(items),
            "draft": sum(x.status == RFIStatus.DRAFT for x in items),
            "pending_internal_review": sum(
                x.status == RFIStatus.PENDING_INTERNAL_REVIEW for x in items
            ),
            "issued": sum(x.status == RFIStatus.ISSUED for x in items),
            "approved_for_issue": sum(x.status == RFIStatus.APPROVED_FOR_ISSUE for x in items),
            "awaiting_response": sum(
                x.status in {RFIStatus.ISSUED, RFIStatus.ACKNOWLEDGED, RFIStatus.UNDER_REVIEW}
                for x in items
            ),
            "overdue": sum(
                bool(x.required_date and x.required_date < current and x.status in OPEN)
                for x in items
            ),
            "responses_received": sum(bool(x.responses) for x in items),
            "clarifications_required": sum(
                x.status == RFIStatus.CLARIFICATION_REQUIRED for x in items
            ),
            "resolved": sum(x.status == RFIStatus.RESOLVED for x in items),
            "closed": sum(x.status == RFIStatus.CLOSED for x in items),
            "average_response_days": round(sum(response_days) / len(response_days), 2)
            if response_days
            else 0.0,
            "median_response_days": float(median(response_days)) if response_days else 0.0,
            "potential_procurement_exposure": sum(
                any(impact.impact_type == RFIImpactType.PROCUREMENT for impact in x.impacts)
                for x in items
            ),
            "possible_schedule_impact": sum(
                any(impact.impact_type == RFIImpactType.SCHEDULE for impact in x.impacts)
                for x in items
            ),
        }
        return RFIDashboard(
            project_id=project_id,
            metrics=metrics,
            oldest_open=tuple(sorted(open_items, key=lambda x: x.created_at)[:10]),
        )


class RFIRenderer:
    def markdown(self, rfi: RFI) -> str:
        lines = [
            f"# {rfi.number}: {rfi.subject}",
            "",
            f"- **Project:** {rfi.project_id}",
            f"- **Status:** {rfi.status.value}",
            f"- **Created:** {rfi.created_at.date()}",
            f"- **To:** {rfi.responsible_party or 'Not assigned'}",
            f"- **From:** {rfi.created_by.display_name}",
            f"- **Required response:** {rfi.required_date or 'Not set'}",
            f"- **Discipline:** {rfi.discipline or 'Not specified'}",
            f"- **Drawing references:** {', '.join(rfi.drawing_references) or 'None'}",
            f"- **Specification references:** {', '.join(rfi.specification_references) or 'None'}",
            "",
            "## Question",
            "",
            rfi.question,
            "",
            "## Background",
            "",
            rfi.background or "No background provided.",
            "",
            "## Suggested resolution",
            "",
            rfi.suggested_resolution or "None proposed.",
            "",
            "## Evidence",
            "",
        ]
        lines.extend(
            f"- {x.citation.document_name}, page {x.citation.page_number}, chunk `{x.citation.chunk_id}`"
            for x in rfi.evidence
        )
        if rfi.impacts:
            lines.extend(["", "## Recorded impacts", ""])
            lines.extend(
                f"- {impact.impact_type.value}: {impact.certainty.value} — {impact.description}"
                for impact in rfi.impacts
            )
        official = [x for x in rfi.responses if x.response_type.value == "official"]
        if official:
            lines.extend(["", "## Official response", "", official[-1].text])
        lines.extend(
            [
                "",
                "## Potential impact notice",
                "",
                "Any cost, schedule, procurement, scope, or quality implications remain unconfirmed unless explicitly recorded by an authorized reviewer.",
                "",
            ]
        )
        return "\n".join(lines)

    def csv_log(self, items: tuple[RFI, ...]) -> str:
        output = io.StringIO()
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow(
            (
                "number",
                "subject",
                "status",
                "priority",
                "discipline",
                "created",
                "issued",
                "required",
                "closed",
            )
        )
        writer.writerows(
            (
                x.number,
                x.subject,
                x.status.value,
                x.priority.value,
                x.discipline or "",
                x.created_at.date(),
                x.issued_at.date() if x.issued_at else "",
                x.required_date or "",
                x.closed_at.date() if x.closed_at else "",
            )
            for x in items
        )
        return output.getvalue()
