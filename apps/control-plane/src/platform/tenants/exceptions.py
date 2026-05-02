from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError


class TenantNotFoundError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("tenant_not_found", "Tenant was not found.")


class ReservedSlugError(ValidationError):
    def __init__(self, slug: str) -> None:
        super().__init__("slug_reserved", "Tenant slug is reserved.", {"slug": slug})


class SlugTakenError(PlatformError):
    status_code = 409

    def __init__(self, slug: str) -> None:
        super().__init__("slug_taken", "Tenant slug is already in use.", {"slug": slug})


class SlugInvalidError(ValidationError):
    def __init__(self, slug: str) -> None:
        super().__init__("slug_invalid", "Tenant slug is invalid.", {"slug": slug})


class DefaultTenantImmutableError(PlatformError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "default_tenant_immutable",
            "The default tenant cannot be renamed, disabled, or deleted.",
        )


class TenantSuspendedError(PlatformError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__("tenant_suspended", "Tenant is suspended.")


class TenantPendingDeletionError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("tenant_pending_deletion", "Tenant is pending deletion.")


class DPAMissingError(ValidationError):
    def __init__(self) -> None:
        super().__init__("dpa_missing", "A signed DPA artifact is required.")


class RegionInvalidError(ValidationError):
    def __init__(self, region: str) -> None:
        super().__init__("region_invalid", "Tenant region is invalid.", {"region": region})


class ConcurrentLifecycleActionError(PlatformError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "concurrent_lifecycle_action",
            "Another tenant lifecycle action is already in progress.",
        )


class DnsAutomationFailedError(PlatformError):
    status_code = 500

    def __init__(self, reason: str) -> None:
        super().__init__("dns_automation_failed", "DNS automation failed.", {"reason": reason})


# --- UPD-049 per-tenant feature-flag setter exceptions ---------------------


class FeatureFlagNotInAllowlistError(ValidationError):
    def __init__(self, flag_name: str) -> None:
        super().__init__(
            "feature_flag_not_in_allowlist",
            "Feature flag is not in the documented allowlist.",
            {"flag_name": flag_name},
        )


class FeatureFlagInvalidForTenantKindError(ValidationError):
    def __init__(self, flag_name: str, tenant_kind: str) -> None:
        super().__init__(
            "feature_flag_invalid_for_tenant_kind",
            "Feature flag is not allowed on tenants of this kind.",
            {"flag_name": flag_name, "tenant_kind": tenant_kind},
        )
