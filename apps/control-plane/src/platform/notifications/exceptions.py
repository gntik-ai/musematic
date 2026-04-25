from __future__ import annotations

from platform.common.exceptions import AuthorizationError, NotFoundError, PlatformError


class NotificationsError(PlatformError):
    pass


class NotificationsConflictError(NotificationsError):
    status_code = 409


class AlertNotFoundError(NotFoundError):
    def __init__(self, alert_id: object) -> None:
        super().__init__("ALERT_NOT_FOUND", f"Alert {alert_id} was not found")


class AlertAuthorizationError(AuthorizationError):
    def __init__(self) -> None:
        super().__init__(
            "ALERT_FORBIDDEN",
            "You are not allowed to access this alert",
        )


class ChannelVerificationError(NotificationsError):
    def __init__(self, message: str = "Channel verification failed") -> None:
        super().__init__("CHANNEL_VERIFICATION_FAILED", message)


class ChannelNotFoundError(NotFoundError):
    def __init__(self, channel_id: object) -> None:
        super().__init__("CHANNEL_NOT_FOUND", f"Notification channel {channel_id} was not found")


class WebhookNotFoundError(NotFoundError):
    def __init__(self, webhook_id: object) -> None:
        super().__init__("WEBHOOK_NOT_FOUND", f"Outbound webhook {webhook_id} was not found")


class WebhookInactiveError(NotificationsConflictError):
    def __init__(self, webhook_id: object) -> None:
        super().__init__("WEBHOOK_INACTIVE", f"Outbound webhook {webhook_id} is inactive")


class ResidencyViolationError(NotificationsError):
    def __init__(
        self,
        message: str = "Notification delivery violates data residency policy",
    ) -> None:
        super().__init__("RESIDENCY_VIOLATION", message)


class DlpBlockedError(NotificationsError):
    def __init__(self, message: str = "Notification delivery blocked by DLP policy") -> None:
        super().__init__("DLP_BLOCKED", message)


class QuotaExceededError(NotificationsConflictError):
    def __init__(self, message: str = "Notification quota exceeded") -> None:
        super().__init__("NOTIFICATION_QUOTA_EXCEEDED", message)


class InvalidWebhookUrlError(NotificationsError):
    def __init__(self, message: str = "Webhook URL is invalid") -> None:
        super().__init__("INVALID_WEBHOOK_URL", message)


class DeadLetterNotReplayableError(NotificationsConflictError):
    def __init__(self, delivery_id: object) -> None:
        super().__init__(
            "DEAD_LETTER_NOT_REPLAYABLE",
            f"Webhook delivery {delivery_id} cannot be replayed",
        )
