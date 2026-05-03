"""Tenant cascade dispatch — thin adapter over CascadeOrchestrator + UPD-053.

Per R8, the DNS/TLS teardown leg is feature-flagged behind
``feature_upd053_dns_teardown``. When the flag is off, the cascade
proceeds against data planes only and emits a structured warning so
operators can run the manual cleanup runbook
(``deploy/runbooks/data-lifecycle/dns-teardown-manual.md``).

The backup-purge leg is scheduled (NOT executed inline) by the caller
30 days after cascade completion per FR-759 / R4.

DPA Vault paths are also enumerated and cleaned during the cascade to
honor FR-756.5 (cascade deletes tenant DPA versions; tombstones retain
hashes only).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol
from uuid import UUID

from platform.common.config import PlatformSettings
from platform.privacy_compliance.services.cascade_orchestrator import (
    CascadeOrchestrator,
)

logger = logging.getLogger(__name__)


class _DNSTeardownService(Protocol):
    """Minimal protocol for the UPD-053 tenant-domain teardown service."""

    async def teardown(self, tenant_slug: str) -> dict[str, Any]:
        ...


class _VaultDPACleaner(Protocol):
    """Best-effort cleanup of DPA Vault paths during phase_2."""

    async def delete_dpa_paths(
        self, *, tenant_id: UUID, paths: list[str]
    ) -> dict[str, int]:
        ...


async def dispatch_tenant_cascade(
    *,
    orchestrator: CascadeOrchestrator,
    settings: PlatformSettings,
    tenant_id: UUID,
    tenant_slug: str,
    requested_by_user_id: UUID | None,
    dns_teardown: _DNSTeardownService | None = None,
    vault_dpa_cleaner: _VaultDPACleaner | None = None,
    dpa_vault_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Run the tenant cascade across data planes + (optionally) DNS/TLS.

    The data-store legs always run. The DNS leg is gated by
    ``feature_upd053_dns_teardown`` AND a non-None ``dns_teardown``
    service. If either is missing, the result records the skip without
    failing the overall cascade.
    """

    logger.info(
        "data_lifecycle.tenant_cascade_dispatching",
        extra={"tenant_id": str(tenant_id), "tenant_slug": tenant_slug},
    )
    result = await orchestrator.execute_tenant_cascade(
        tenant_id, requested_by_user_id=requested_by_user_id
    )

    # DNS / TLS teardown leg (R8).
    dns_result: dict[str, Any] = {
        "status": "skipped",
        "reason": "feature_flag_disabled",
    }
    if not settings.feature_upd053_dns_teardown:
        logger.warning(
            "data_lifecycle.dns_teardown_skipped",
            extra={
                "tenant_id": str(tenant_id),
                "tenant_slug": tenant_slug,
                "reason": "feature_flag_disabled",
            },
        )
    elif dns_teardown is None:
        dns_result = {"status": "skipped", "reason": "service_unavailable"}
        logger.warning(
            "data_lifecycle.dns_teardown_skipped",
            extra={
                "tenant_id": str(tenant_id),
                "tenant_slug": tenant_slug,
                "reason": "service_unavailable",
            },
        )
    else:
        try:
            dns_result = await dns_teardown.teardown(tenant_slug)
            dns_result.setdefault("status", "completed")
        except Exception as exc:
            logger.error(
                "data_lifecycle.dns_teardown_failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "tenant_slug": tenant_slug,
                    "error": str(exc),
                },
            )
            dns_result = {"status": "failed", "error": str(exc)}
            result.setdefault("errors", []).append(f"dns_teardown: {exc}")

    result["dns_teardown"] = dns_result

    # DPA Vault cleanup (FR-756.5).
    dpa_result: dict[str, Any] = {"status": "skipped", "deleted": 0}
    if vault_dpa_cleaner is not None and dpa_vault_paths:
        try:
            cleanup = await vault_dpa_cleaner.delete_dpa_paths(
                tenant_id=tenant_id, paths=dpa_vault_paths
            )
            dpa_result = {"status": "completed", **cleanup}
        except Exception as exc:
            logger.error(
                "data_lifecycle.dpa_vault_cleanup_failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "error": str(exc),
                },
            )
            dpa_result = {"status": "failed", "error": str(exc)}
            result.setdefault("errors", []).append(f"dpa_vault_cleanup: {exc}")
    result["dpa_vault_cleanup"] = dpa_result

    logger.info(
        "data_lifecycle.tenant_cascade_completed",
        extra={
            "tenant_id": str(tenant_id),
            "errors": len(result.get("errors", [])),
            "dns_status": dns_result["status"],
            "dpa_cleanup_status": dpa_result["status"],
        },
    )
    return result
