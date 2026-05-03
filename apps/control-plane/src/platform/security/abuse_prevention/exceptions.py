"""Exceptions raised by the abuse-prevention bounded context (UPD-050).

Stable error codes per the contracts under
``specs/100-abuse-prevention/contracts/``.
"""

from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class DisposableEmailNotAllowedError(PlatformError):
    """The submitted email's domain is on the curated disposable list."""

    status_code = 400

    def __init__(self, domain: str) -> None:
        super().__init__(
            "disposable_email_not_allowed",
            "This email provider is not supported. Please use a different email address.",
            {"domain": domain},
        )


class CaptchaRequiredError(PlatformError):
    """CAPTCHA is enabled but no token was provided."""

    status_code = 400

    def __init__(self) -> None:
        super().__init__(
            "captcha_required",
            "A CAPTCHA token is required to complete signup.",
            {},
        )


class CaptchaInvalidError(PlatformError):
    """Provider verification failed or token has been replayed."""

    status_code = 400

    def __init__(self, reason: str) -> None:
        super().__init__(
            "captcha_invalid",
            "CAPTCHA verification failed.",
            {"reason": reason},
        )


class GeoBlockedError(PlatformError):
    """The source IP is in a country that the geo-policy refuses."""

    status_code = 400

    def __init__(self, country_code: str) -> None:
        super().__init__(
            "geo_blocked",
            "Signups from your region are not currently accepted.",
            {"country_code": country_code},
        )


class SignupRateLimitExceededError(PlatformError):
    """One of the three velocity counters reached its threshold."""

    status_code = 429

    def __init__(self, counter_key: str, retry_after_seconds: int) -> None:
        super().__init__(
            "signup_rate_limit_exceeded",
            "Too many signup attempts. Please wait before trying again.",
            {
                "counter_key": counter_key,
                "retry_after_seconds": retry_after_seconds,
            },
        )
        self.retry_after_seconds = retry_after_seconds


class SuspendedAccountError(PlatformError):
    """The account has an active suspension; login (and reset) refused.

    The user-facing message is intentionally non-leaky per FR-010 — we
    don't disclose the reason or evidence to the suspended user.
    """

    status_code = 403

    def __init__(self, appeal_contact: str) -> None:
        super().__init__(
            "account_suspended",
            (
                "Your account is suspended pending review. "
                f"To appeal, contact {appeal_contact}."
            ),
            {"appeal_contact": appeal_contact},
        )


class SettingKeyUnknownError(PlatformError):
    """The PATCH targets a setting that is not in the documented allowlist."""

    status_code = 422

    def __init__(self, setting_key: str) -> None:
        super().__init__(
            "setting_key_unknown",
            "Setting key is not in the documented allowlist.",
            {"setting_key": setting_key},
        )


class SuspensionAlreadyLiftedError(PlatformError):
    """The targeted suspension has already been lifted."""

    status_code = 409

    def __init__(self, suspension_id: UUID) -> None:
        super().__init__(
            "suspension_already_lifted",
            "This suspension has already been lifted.",
            {"suspension_id": str(suspension_id)},
        )
