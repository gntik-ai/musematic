from __future__ import annotations

from platform.auth.exceptions import (
    AccountLockedError,
    ApiKeyInvalidError,
    InvalidCredentialsError,
    InvalidMfaCodeError,
    InvalidMfaTokenError,
    InvalidRefreshTokenError,
    MfaAlreadyEnrolledError,
    NoPendingEnrollmentError,
)


def test_auth_exceptions_expose_expected_codes_and_statuses() -> None:
    exceptions = [
        InvalidCredentialsError(),
        AccountLockedError(),
        InvalidMfaCodeError(),
        InvalidMfaTokenError(),
        MfaAlreadyEnrolledError(),
        NoPendingEnrollmentError(),
        InvalidRefreshTokenError(),
        ApiKeyInvalidError(),
    ]

    assert [exc.code for exc in exceptions] == [
        "INVALID_CREDENTIALS",
        "ACCOUNT_LOCKED",
        "INVALID_MFA_CODE",
        "INVALID_MFA_TOKEN",
        "MFA_ALREADY_ENROLLED",
        "NO_PENDING_ENROLLMENT",
        "INVALID_REFRESH_TOKEN",
        "INVALID_API_KEY",
    ]
    assert [exc.status_code for exc in exceptions] == [401, 403, 401, 401, 409, 404, 401, 401]
