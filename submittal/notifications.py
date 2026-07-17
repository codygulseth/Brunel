"""Local-only submittal due-date notification orchestration."""

from datetime import UTC, datetime, timedelta

from change_workflow.models import NotificationRequest, NotificationType
from change_workflow.notifications import NotificationOutboxService
from change_workflow.repository import JsonChangeWorkflowRepository

from .models import SubmittalStatus
from .repository import JsonSubmittalRepository


class SubmittalNotificationService:
    def __init__(
        self,
        repository: JsonSubmittalRepository,
        workflow_repository: JsonChangeWorkflowRepository,
    ) -> None:
        self.repository = repository
        self.outbox = NotificationOutboxService(workflow_repository)

    def queue_due_notifications(
        self, project_id: str, *, due_soon_days: int = 7, now: datetime | None = None
    ) -> int:
        current = now or datetime.now(UTC)
        queued = 0
        for item in self.repository.list_register(project_id):
            reviewer = item.internal_reviewer
            if reviewer is None or item.status in {
                SubmittalStatus.CLOSED,
                SubmittalStatus.VOID,
                SubmittalStatus.SUPERSEDED,
            }:
                continue
            dates = tuple(
                value
                for value in (
                    item.planned_submit_date,
                    item.required_response_date,
                    item.procurement.derived_latest_submit_date,
                    item.required_on_site_date,
                )
                if value
            )
            for due_date in dates:
                notification_type: NotificationType | None = None
                if due_date < current.date():
                    notification_type = NotificationType.ITEM_OVERDUE
                elif due_date <= (current + timedelta(days=due_soon_days)).date():
                    notification_type = NotificationType.DUE_DATE_APPROACHING
                if notification_type is None:
                    continue
                self.outbox.queue(
                    NotificationRequest(
                        id="pending",
                        project_id=project_id,
                        change_id=item.related_project_change_ids[0]
                        if item.related_project_change_ids
                        else item.id,
                        event_id=f"{item.id}:{due_date}:{notification_type.value}",
                        recipient=reviewer,
                        notification_type=notification_type,
                        created_at=current,
                        payload={
                            "title": "Submittal deadline",
                            "status": item.status.value,
                            "due_date": due_date.isoformat(),
                        },
                    )
                )
                queued += 1
        return queued
