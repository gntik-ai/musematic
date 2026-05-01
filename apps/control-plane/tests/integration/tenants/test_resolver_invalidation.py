from __future__ import annotations

import json
from platform.common.config import PlatformSettings
from platform.tenants.resolver import TenantResolver
from types import SimpleNamespace
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


class MutableResolver(TenantResolver):
    def __init__(self, tenant: SimpleNamespace) -> None:
        super().__init__(
            settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
            session_factory=lambda: None,  # type: ignore[arg-type]
        )
        self.tenant = tenant

    async def _query_tenant(self, subdomain: str) -> SimpleNamespace | None:  # type: ignore[override]
        return self.tenant if subdomain == self.tenant.subdomain else None


def _tenant(tenant_id, branding):
    return SimpleNamespace(
        id=tenant_id,
        slug="acme",
        subdomain="acme",
        kind="enterprise",
        status="active",
        region="eu-central",
        branding_config_json=branding,
        feature_flags_json={},
    )


@pytest.mark.asyncio
async def test_pubsub_invalidation_evicts_local_cache() -> None:
    tenant_id = uuid4()
    resolver = MutableResolver(_tenant(tenant_id, {"display_name_override": "Acme v1"}))
    assert (await resolver.resolve("acme.musematic.ai")).branding[
        "display_name_override"
    ] == "Acme v1"

    resolver.tenant = _tenant(tenant_id, {"display_name_override": "Acme v2"})
    assert (await resolver.resolve("acme.musematic.ai")).branding[
        "display_name_override"
    ] == "Acme v1"

    await resolver.handle_invalidation_message(
        json.dumps({"tenant_id": str(tenant_id), "hosts": ["acme.musematic.ai"]})
    )

    assert (await resolver.resolve("acme.musematic.ai")).branding[
        "display_name_override"
    ] == "Acme v2"
