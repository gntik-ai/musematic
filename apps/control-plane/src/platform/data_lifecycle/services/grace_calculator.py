"""Grace-period resolver for workspace and tenant deletion (R6).

Workspace deletion default = ``data_lifecycle.grace_default_days`` (7).
Tenant deletion default = ``data_lifecycle.tenant_grace_default_days`` (30).

Per-Enterprise-tenant overrides live in ``tenants.contract_metadata_json``
under the key ``deletion_grace_period_days``. Validation: any override
MUST satisfy ``7 <= value <= grace_max_days``.

Workspaces inherit their tenant's override (if any). A workspace MAY
specify a per-workspace override under
``workspaces_settings.settings_json.deletion_grace_period_days`` (not
implemented in v1; reserved for future Pro-tier customization).
"""

from __future__ import annotations

from dataclasses import dataclass
from platform.common.config import DataLifecycleSettings
from platform.data_lifecycle.exceptions import GracePeriodOutOfRangeError
from typing import Any


@dataclass(frozen=True, slots=True)
class GraceResolution:
    days: int
    source: str  # "default" | "tenant_override" | "request_override"


def resolve_workspace_grace(
    *,
    settings: DataLifecycleSettings,
    tenant_contract_metadata: dict[str, Any] | None,
    request_override_days: int | None = None,
) -> GraceResolution:
    """Resolve the grace period for a workspace deletion.

    Order of precedence: explicit per-request override > tenant contract
    override > platform default.
    """

    if request_override_days is not None:
        _validate_bounds(request_override_days, settings.grace_max_days)
        return GraceResolution(days=request_override_days, source="request_override")

    tenant_override = _read_override(tenant_contract_metadata)
    if tenant_override is not None:
        _validate_bounds(tenant_override, settings.grace_max_days)
        return GraceResolution(days=tenant_override, source="tenant_override")

    return GraceResolution(days=settings.grace_default_days, source="default")


def resolve_tenant_grace(
    *,
    settings: DataLifecycleSettings,
    tenant_contract_metadata: dict[str, Any] | None,
    request_override_days: int | None = None,
) -> GraceResolution:
    """Resolve the grace period for a tenant deletion.

    Same precedence as workspace; defaults to ``tenant_grace_default_days``.
    """

    if request_override_days is not None:
        _validate_bounds(request_override_days, settings.grace_max_days)
        return GraceResolution(days=request_override_days, source="request_override")

    tenant_override = _read_override(tenant_contract_metadata)
    if tenant_override is not None:
        _validate_bounds(tenant_override, settings.grace_max_days)
        return GraceResolution(days=tenant_override, source="tenant_override")

    return GraceResolution(
        days=settings.tenant_grace_default_days, source="default"
    )


def _read_override(metadata: dict[str, Any] | None) -> int | None:
    if not metadata:
        return None
    raw = metadata.get("deletion_grace_period_days")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _validate_bounds(days: int, upper_bound: int) -> None:
    if not (7 <= days <= upper_bound):
        raise GracePeriodOutOfRangeError(
            f"grace_period_days must be between 7 and {upper_bound}, got {days}"
        )
