"""Local outbox only; no adapter sends externally."""

from hashlib import sha256

from .models import NotificationRequest
from .repository import JsonChangeWorkflowRepository


class NotificationOutboxService:
    def __init__(self, repository: JsonChangeWorkflowRepository) -> None:
        self.repository = repository

    def queue(self, request: NotificationRequest) -> NotificationRequest:
        safe = request.model_copy(
            update={
                "payload": {
                    key: value
                    for key, value in request.payload.items()
                    if key in {"title", "status", "due_date", "summary"}
                }
            }
        )
        stable_id = f"notify_{sha256(f'{safe.project_id}{safe.change_id}{safe.event_id}{safe.recipient.id}{safe.notification_type}'.encode()).hexdigest()[:24]}"
        safe = safe.model_copy(update={"id": stable_id})
        self.repository.queue_notification(safe)
        return safe


class NoOpNotificationAdapter:
    def deliver(self, request: NotificationRequest) -> None:
        return None


class TestNotificationAdapter:
    def __init__(self) -> None:
        self.delivered: list[NotificationRequest] = []

    def deliver(self, request: NotificationRequest) -> None:
        self.delivered.append(request)
