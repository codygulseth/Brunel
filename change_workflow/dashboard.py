"""Deterministic project dashboard and prioritized review queue."""

from datetime import UTC, date, datetime, timedelta

from .models import (
    ChangePriority,
    ChangeStatus,
    DashboardMetric,
    ProjectChange,
    ProjectChangeDashboard,
)
from .repository import JsonChangeWorkflowRepository


class ProjectChangeDashboardService:
    def __init__(self, repository: JsonChangeWorkflowRepository, due_soon_days: int = 7) -> None:
        self.repository = repository
        self.due_soon_days = due_soon_days

    def build(self, project_id: str, *, today: date | None = None) -> ProjectChangeDashboard:
        current = today or datetime.now(UTC).date()
        items = self.repository.list_changes(project_id)
        open_statuses = {
            ChangeStatus.NEW,
            ChangeStatus.UNREVIEWED,
            ChangeStatus.ASSIGNED,
            ChangeStatus.UNDER_REVIEW,
            ChangeStatus.NEEDS_INFORMATION,
            ChangeStatus.ACTION_REQUIRED,
            ChangeStatus.ACCEPTED,
        }

        def due(item: ProjectChange) -> date | None:
            active = next((a for a in reversed(item.assignments) if a.active and a.primary), None)
            return active.due_date if active else None

        def is_overdue(item: ProjectChange) -> bool:
            value = due(item)
            return value is not None and value < current and item.status in open_statuses

        def is_due_soon(item: ProjectChange) -> bool:
            value = due(item)
            return value is not None and current <= value <= current + timedelta(
                days=self.due_soon_days
            )

        metrics = (
            DashboardMetric(name="total_open", count=sum(i.status in open_statuses for i in items)),
            DashboardMetric(
                name="unreviewed", count=sum(i.status == ChangeStatus.UNREVIEWED for i in items)
            ),
            DashboardMetric(
                name="assigned", count=sum(i.status == ChangeStatus.ASSIGNED for i in items)
            ),
            DashboardMetric(
                name="overdue",
                count=sum(is_overdue(i) for i in items),
            ),
            DashboardMetric(
                name="high_priority",
                count=sum(
                    i.priority in {ChangePriority.CRITICAL, ChangePriority.HIGH}
                    and i.status in open_statuses
                    for i in items
                ),
            ),
            DashboardMetric(
                name="needs_information",
                count=sum(i.status == ChangeStatus.NEEDS_INFORMATION for i in items),
            ),
            DashboardMetric(
                name="resolved", count=sum(i.status == ChangeStatus.RESOLVED for i in items)
            ),
            DashboardMetric(
                name="closed", count=sum(i.status == ChangeStatus.CLOSED for i in items)
            ),
            DashboardMetric(name="stale_source", count=sum(i.source_stale for i in items)),
            DashboardMetric(
                name="due_soon",
                count=sum(is_due_soon(i) for i in items),
            ),
        )
        rank = {
            ChangePriority.CRITICAL: 0,
            ChangePriority.HIGH: 1,
            ChangePriority.MEDIUM: 2,
            ChangePriority.LOW: 3,
            ChangePriority.INFORMATIONAL: 4,
        }
        queue = tuple(
            sorted(
                (i for i in items if i.status in open_statuses),
                key=lambda i: (rank[i.priority], due(i) or date.max, i.updated_at, i.id),
            )
        )
        return ProjectChangeDashboard(project_id=project_id, metrics=metrics, priority_queue=queue)
