from __future__ import annotations

from platform.common.exceptions import PlatformError


class InvalidCredentialsError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "Invalid email or password") -> None:
        super().__init__("INVALID_CREDENTIALS", message)


class AccountPendingApprovalError(PlatformError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "account_pending_approval",
            "Account is pending administrator approval",
            {"redirect_to": "/waiting-approval"},
        )


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


class IBORConnectorConflictError(PlatformError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__("IBOR_CONNECTOR_CONFLICT", f"IBOR connector '{name}' already exists")


class IBORConnectorNotFoundError(PlatformError):
    status_code = 404

    def __init__(self, connector_id: str) -> None:
        super().__init__("IBOR_CONNECTOR_NOT_FOUND", f"IBOR connector '{connector_id}' not found")


class IBORSyncInProgressError(PlatformError):
    status_code = 409

    def __init__(self, connector_id: str) -> None:
        super().__init__(
            "IBOR_SYNC_IN_PROGRESS",
            f"A sync is already in progress for connector '{connector_id}'",
        )


class IBORCredentialResolutionError(PlatformError):
    status_code = 422

    def __init__(self, connector_name: str) -> None:
        super().__init__(
            "IBOR_CREDENTIAL_RESOLUTION_FAILED",
            f"Unable to resolve credentials for connector '{connector_name}'",
        )



class OAuthProviderNotFoundError(PlatformError):
    status_code = 404

    def __init__(self, provider_type: str) -> None:
        super().__init__(
            "OAUTH_PROVIDER_NOT_FOUND",
            f"OAuth provider '{provider_type}' not found",
        )


class OAuthProviderDisabledError(PlatformError):
    status_code = 404

    def __init__(self, provider_type: str) -> None:
        super().__init__(
            "OAUTH_PROVIDER_DISABLED",
            f"OAuth provider '{provider_type}' is disabled",
        )


class OAuthStateInvalidError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "OAuth state is invalid") -> None:
        super().__init__("OAUTH_STATE_INVALID", message)


class OAuthStateExpiredError(PlatformError):
    status_code = 401

    def __init__(self, message: str = "OAuth state has expired") -> None:
        super().__init__("OAUTH_STATE_EXPIRED", message)


class OAuthLinkConflictError(PlatformError):
    status_code = 409

    def __init__(self, message: str = "External identity is already linked") -> None:
        super().__init__("OAUTH_LINK_CONFLICT", message)


class OAuthUnlinkLastMethodError(PlatformError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "OAUTH_LAST_AUTH_METHOD",
            "Cannot unlink: this is your only authentication method",
        )


class OAuthRestrictionError(PlatformError):
    status_code = 403

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)
