from __future__ import annotations

from platform.common.exceptions import PlatformError


class AccountsError(PlatformError):
    status_code = 400


class SelfRegistrationDisabledError(AccountsError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("SELF_REGISTRATION_DISABLED", "Self-registration is disabled")


class InvalidTransitionError(AccountsError):
    status_code = 409

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            "INVALID_TRANSITION",
            f"Cannot transition user from {from_status} to {to_status}",
            {"from_status": from_status, "to_status": to_status},
        )


class InvalidOrExpiredTokenError(AccountsError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("INVALID_OR_EXPIRED_TOKEN", "Invalid or expired token")


class RateLimitError(AccountsError):
    status_code = 429

    def __init__(self, retry_after: int) -> None:
        super().__init__(
            "RATE_LIMIT_EXCEEDED",
            "Rate limit exceeded",
            {"retry_after": retry_after},
        )


class InvitationError(AccountsError):
    pass


class InvitationAlreadyConsumedError(InvitationError):
    def __init__(self) -> None:
        super().__init__("INVITATION_ALREADY_CONSUMED", "Invitation has already been consumed")


class InvitationExpiredError(InvitationError):
    def __init__(self) -> None:
        super().__init__("INVITATION_EXPIRED", "Invitation has expired")


class InvitationRevokedError(InvitationError):
    def __init__(self) -> None:
        super().__init__("INVITATION_REVOKED", "Invitation has been revoked")


class InvitationNotFoundError(InvitationError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("INVITATION_NOT_FOUND", "Invitation was not found")


class EmailAlreadyRegisteredError(AccountsError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("EMAIL_ALREADY_REGISTERED", "Email is already registered")
