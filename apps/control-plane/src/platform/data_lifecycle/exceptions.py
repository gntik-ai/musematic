"""Exceptions for the data_lifecycle bounded context.

All inherit from ``platform.common.exceptions.PlatformError`` so the
existing FastAPI exception handler renders them as RFC 7807-style
problem responses with the correct status codes.
"""

from __future__ import annotations

from platform.common.exceptions import PlatformError


class DataLifecycleError(PlatformError):
    """Base for all data_lifecycle errors.

    Subclasses set ``status_code`` and ``code`` as class attributes; the
    ``__init__`` here forwards them to PlatformError so callers can raise
    ``WorkspacePendingDeletionError("...")`` without supplying the code.
    """

    status_code: int = 400
    code: str = "data_lifecycle_error"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(self.code, message, details)


# ----- Export errors ---------------------------------------------------------


class ExportRateLimitExceededError(DataLifecycleError):
    status_code = 429
    code = "export_rate_limit_exceeded"


class CrossRegionExportBlockedError(DataLifecycleError):
    status_code = 422
    code = "cross_region_export_blocked"


class ExportJobNotFoundError(DataLifecycleError):
    status_code = 404
    code = "export_job_not_found"


class ExportUrlExpiredError(DataLifecycleError):
    status_code = 410
    code = "export_url_expired"


# ----- Deletion errors -------------------------------------------------------


class DeletionJobAlreadyActiveError(DataLifecycleError):
    status_code = 409
    code = "deletion_job_already_active"


class WorkspacePendingDeletionError(DataLifecycleError):
    status_code = 423
    code = "workspace_pending_deletion"


class TenantPendingDeletionError(DataLifecycleError):
    status_code = 423
    code = "tenant_pending_deletion"


class TypedConfirmationMismatchError(DataLifecycleError):
    status_code = 400
    code = "typed_confirmation_mismatch"


class CascadeInProgressError(DataLifecycleError):
    status_code = 409
    code = "cascade_in_progress"


class DeletionJobAlreadyFinalisedError(DataLifecycleError):
    status_code = 410
    code = "deletion_job_already_finalised"


class GracePeriodOutOfRangeError(DataLifecycleError):
    status_code = 422
    code = "grace_period_out_of_range"


class SubscriptionActiveCancelFirstError(DataLifecycleError):
    status_code = 409
    code = "subscription_active_cancel_first"


class DefaultTenantCannotBeDeletedError(DataLifecycleError):
    status_code = 409
    code = "default_tenant_cannot_be_deleted"


class TwoPATokenRequiredError(DataLifecycleError):
    status_code = 403
    code = "2pa_token_required"


class TwoPATokenInvalidError(DataLifecycleError):
    status_code = 403
    code = "2pa_token_invalid"


# ----- DPA errors ------------------------------------------------------------


class DPAPdfInvalidError(DataLifecycleError):
    status_code = 400
    code = "dpa_pdf_invalid"


class DPATooLargeError(DataLifecycleError):
    status_code = 413
    code = "dpa_too_large"


class DPAVirusDetectedError(DataLifecycleError):
    status_code = 422
    code = "dpa_virus_detected"


class DPAScanUnavailableError(DataLifecycleError):
    status_code = 503
    code = "dpa_scan_unavailable"


class DPAVersionAlreadyExistsError(DataLifecycleError):
    status_code = 409
    code = "dpa_version_already_exists"


class DPAVersionNotFoundError(DataLifecycleError):
    status_code = 404
    code = "dpa_version_not_found"


class VaultUnreachableError(DataLifecycleError):
    status_code = 502
    code = "vault_unreachable"


# ----- Sub-processor errors --------------------------------------------------


class SubProcessorNotFoundError(DataLifecycleError):
    status_code = 404
    code = "sub_processor_not_found"


class SubProcessorNameConflictError(DataLifecycleError):
    status_code = 409
    code = "sub_processor_name_conflict"
