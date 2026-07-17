"""Local-only RFI due-date notification orchestration."""

from datetime import UTC, datetime, timedelta

from change_workflow.models import NotificationRequest, NotificationType
from change_workflow.notifications import NotificationOutboxService
from change_workflow.repository import JsonChangeWorkflowRepository

from .repository import JsonRFIRepository
from .reporting import OPEN


class RFINotificationService:
    def __init__(
        self,
        rfi_repository: JsonRFIRepository,
        workflow_repository: JsonChangeWorkflowRepository,
    ) -> None:
        self.rfis = rfi_repository
        self.outbox = NotificationOutboxService(workflow_repository)

    def queue_due_notifications(
        self, project_id: str, *, due_soon_days: int = 7, now: datetime | None = None
    ) -> int:
        current = now or datetime.now(UTC)
        queued = 0
        for item in self.rfis.list(project_id):
            if not item.required_date or not item.assigned_reviewer or item.status not in OPEN:
                continue
            notification_type: NotificationType | None = None
            if item.required_date < current.date():
                notification_type = NotificationType.ITEM_OVERDUE
            elif item.required_date <= (current + timedelta(days=due_soon_days)).date():
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
                    event_id=f"{item.id}:{item.required_date}:{notification_type.value}",
                    recipient=item.assigned_reviewer,
                    notification_type=notification_type,
                    created_at=current,
                    payload={
                        "title": "RFI response due date",
                        "status": item.status.value,
                        "due_date": item.required_date.isoformat(),
                    },
                )
            )
            queued += 1
        return queued
