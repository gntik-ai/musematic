from __future__ import annotations

from platform.common.exceptions import AuthorizationError, NotFoundError, PlatformError


class NotificationsError(PlatformError):
    pass


class AlertNotFoundError(NotFoundError):
    def __init__(self, alert_id: object) -> None:
        super().__init__("ALERT_NOT_FOUND", f"Alert {alert_id} was not found")


class AlertAuthorizationError(AuthorizationError):
    def __init__(self) -> None:
        super().__init__(
            "ALERT_FORBIDDEN",
            "You are not allowed to access this alert",
        )
