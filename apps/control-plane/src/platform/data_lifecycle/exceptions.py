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
    ``WorkspacePendingDeletion("...")`` without supplying the code.
    """

    status_code: int = 400
    code: str = "data_lifecycle_error"

    def __init__(self, message: str, details: dict | None = None) -> None:  # type: ignore[override]
        super().__init__(self.code, message, details)


# ----- Export errors ---------------------------------------------------------


class ExportRateLimitExceeded(DataLifecycleError):
    status_code = 429
    code = "export_rate_limit_exceeded"


class CrossRegionExportBlocked(DataLifecycleError):
    status_code = 422
    code = "cross_region_export_blocked"


class ExportJobNotFound(DataLifecycleError):
    status_code = 404
    code = "export_job_not_found"


class ExportUrlExpired(DataLifecycleError):
    status_code = 410
    code = "export_url_expired"


# ----- Deletion errors -------------------------------------------------------


class DeletionJobAlreadyActive(DataLifecycleError):
    status_code = 409
    code = "deletion_job_already_active"


class WorkspacePendingDeletion(DataLifecycleError):
    status_code = 423
    code = "workspace_pending_deletion"


class TenantPendingDeletion(DataLifecycleError):
    status_code = 423
    code = "tenant_pending_deletion"


class TypedConfirmationMismatch(DataLifecycleError):
    status_code = 400
    code = "typed_confirmation_mismatch"


class CascadeInProgress(DataLifecycleError):
    status_code = 409
    code = "cascade_in_progress"


class DeletionJobAlreadyFinalised(DataLifecycleError):
    status_code = 410
    code = "deletion_job_already_finalised"


class GracePeriodOutOfRange(DataLifecycleError):
    status_code = 422
    code = "grace_period_out_of_range"


class SubscriptionActiveCancelFirst(DataLifecycleError):
    status_code = 409
    code = "subscription_active_cancel_first"


class DefaultTenantCannotBeDeleted(DataLifecycleError):
    status_code = 409
    code = "default_tenant_cannot_be_deleted"


class TwoPATokenRequired(DataLifecycleError):
    status_code = 403
    code = "2pa_token_required"


class TwoPATokenInvalid(DataLifecycleError):
    status_code = 403
    code = "2pa_token_invalid"


# ----- DPA errors ------------------------------------------------------------


class DPAPdfInvalid(DataLifecycleError):
    status_code = 400
    code = "dpa_pdf_invalid"


class DPATooLarge(DataLifecycleError):
    status_code = 413
    code = "dpa_too_large"


class DPAVirusDetected(DataLifecycleError):
    status_code = 422
    code = "dpa_virus_detected"


class DPAScanUnavailable(DataLifecycleError):
    status_code = 503
    code = "dpa_scan_unavailable"


class DPAVersionAlreadyExists(DataLifecycleError):
    status_code = 409
    code = "dpa_version_already_exists"


class DPAVersionNotFound(DataLifecycleError):
    status_code = 404
    code = "dpa_version_not_found"


class VaultUnreachable(DataLifecycleError):
    status_code = 502
    code = "vault_unreachable"


# ----- Sub-processor errors --------------------------------------------------


class SubProcessorNotFound(DataLifecycleError):
    status_code = 404
    code = "sub_processor_not_found"


class SubProcessorNameConflict(DataLifecycleError):
    status_code = 409
    code = "sub_processor_name_conflict"
