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


class ProfileCompletionNotAllowedError(AccountsError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "profile_completion_not_allowed",
            "Profile completion is only available for users pending profile completion",
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


class TenantSignupNotAllowedError(AccountsError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("tenant_signup_not_allowed", "Not Found")


class SetupTokenInvalidError(AccountsError):
    status_code = 410

    def __init__(self) -> None:
        super().__init__("setup_token_invalid", "Setup invitation is invalid or expired")


class MfaEnrollmentRequiredError(AccountsError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("mfa_enrollment_required", "MFA enrollment is required")


class OnboardingWizardAlreadyDismissedError(AccountsError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "wizard_already_dismissed_at_this_step",
            "Onboarding wizard is already dismissed at this step",
        )


class CrossTenantInviteAcceptanceError(AccountsError):
    status_code = 409

    def __init__(self, other_tenant: str | None = None) -> None:
        details = {"other_tenant": other_tenant} if other_tenant else None
        super().__init__(
            "cross_tenant_invite_acceptance_blocked",
            "Sign out of the other tenant before accepting this invitation",
            details,
        )


class DefaultWorkspaceNotProvisionedError(AccountsError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__(
            "default_workspace_not_yet_provisioned",
            "Default workspace has not been provisioned yet",
        )
