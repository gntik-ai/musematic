"""Status page exceptions for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

from platform.common.exceptions import PlatformError
from typing import Any


class StatusPageError(PlatformError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        status_code: int,
    ) -> None:
        super().__init__(code, message, details)
        self.status_code = status_code


class SubscriptionNotFoundError(StatusPageError):
    def __init__(self) -> None:
        super().__init__(
            "status.subscription.not_found",
            "Status subscription was not found",
            status_code=404,
        )


class ConfirmationTokenInvalidError(StatusPageError):
    def __init__(self) -> None:
        super().__init__(
            "status.subscription.confirmation_token_invalid",
            "Confirmation token is invalid",
            status_code=400,
        )


class ConfirmationTokenExpiredError(StatusPageError):
    def __init__(self) -> None:
        super().__init__(
            "status.subscription.confirmation_token_expired",
            "Confirmation token has expired",
            status_code=410,
        )


class RateLimitExceededError(StatusPageError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "status.subscription.rate_limit_exceeded",
            "Too many status subscription requests",
            {"retry_after_seconds": retry_after_seconds},
            status_code=429,
        )


class SubscriptionAlreadyConfirmedError(StatusPageError):
    def __init__(self) -> None:
        super().__init__(
            "status.subscription.already_confirmed",
            "Status subscription is already confirmed",
            status_code=409,
        )


class WebhookVerificationFailedError(StatusPageError):
    def __init__(self, reason: str = "delivery_failed") -> None:
        super().__init__(
            "status.subscription.webhook_verification_failed",
            "Webhook verification failed",
            {"reason": reason},
            status_code=400,
        )
