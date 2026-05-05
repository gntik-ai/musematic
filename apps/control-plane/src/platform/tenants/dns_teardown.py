"""UPD-053 (106) — DNS teardown service used by the data-lifecycle phase-2
cascade (UPD-051) to remove per-tenant DNS records on tenant deletion.

Wraps the existing ``DnsAutomationClient.remove_tenant_subdomain`` so the
data-lifecycle BC can call a narrow Protocol surface
(``data_lifecycle/cascade_dispatch/tenant_cascade.py:_DNSTeardownService``)
without importing tenants/internals directly.

The service is wired onto ``app.state.dns_teardown_service`` at FastAPI
startup. When the ``feature_upd053_dns_teardown`` flag is off OR the
service is unwired (e.g. local mode), the cascade records a skip without
failing the broader teardown.
"""
from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.logging import get_logger
from platform.tenants.dns_automation import DnsAutomationClient
from typing import Any
from uuid import uuid4

LOGGER = get_logger(__name__)


class DnsTeardownService:
    """Adapter implementing the data_lifecycle ``_DNSTeardownService`` Protocol.

    Methods MUST stay structurally compatible with
    ``data_lifecycle/cascade_dispatch/tenant_cascade.py:_DNSTeardownService``.
    """

    def __init__(self, *, dns_automation: DnsAutomationClient) -> None:
        self.dns_automation = dns_automation

    async def teardown(self, tenant_slug: str) -> dict[str, Any]:
        """Remove the 6-record bundle for ``tenant_slug`` and return a result
        dict per the data-lifecycle cascade contract.
        """
        LOGGER.info("tenants.dns.teardown_invoked", tenant_slug=tenant_slug)
        await self.dns_automation.remove_tenant_subdomain(
            tenant_slug,
            correlation_ctx=CorrelationContext(correlation_id=uuid4()),
        )
        return {"status": "completed", "tenant_slug": tenant_slug}


__all__ = ["DnsTeardownService"]
