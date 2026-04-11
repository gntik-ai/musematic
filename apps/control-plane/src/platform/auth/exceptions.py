from __future__ import annotations

from platform.common.exceptions import PlatformError


class InvalidCredentialsError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid email or password") -> None:
        super().__init__("INVALID_CREDENTIALS", message)


class AccountLockedError(PlatformError):
    status_code = 403

    def __init__(self, message: str = "Account is locked") -> None:
        super().__init__("ACCOUNT_LOCKED", message)


class InvalidMfaCodeError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid MFA code") -> None:
        super().__init__("INVALID_MFA_CODE", message)


class InvalidMfaTokenError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid MFA token") -> None:
        super().__init__("INVALID_MFA_TOKEN", message)


class MfaAlreadyEnrolledError(PlatformError):
    status_code = 409

    def __init__(self, message: str = "MFA is already enrolled") -> None:
        super().__init__("MFA_ALREADY_ENROLLED", message)


class NoPendingEnrollmentError(PlatformError):
    status_code = 404

    def __init__(self, message: str = "No pending MFA enrollment found") -> None:
        super().__init__("NO_PENDING_ENROLLMENT", message)


class InvalidRefreshTokenError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid refresh token") -> None:
        super().__init__("INVALID_REFRESH_TOKEN", message)


class ApiKeyInvalidError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid API key") -> None:
        super().__init__("INVALID_API_KEY", message)


class InvalidAccessTokenError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid authentication token") -> None:
        super().__init__("UNAUTHORIZED", message)


class AccessTokenExpiredError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Authentication token expired") -> None:
        super().__init__("TOKEN_EXPIRED", message)


class InactiveUserError(PlatformError):
    status_code = 403

    def __init__(self, message: str = "User is not allowed to connect") -> None:
        super().__init__("FORBIDDEN", message)
