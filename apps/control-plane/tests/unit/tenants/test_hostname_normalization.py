from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.tenants.resolver import TenantResolver
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest


class StaticTenantResolver(TenantResolver):
    def __init__(self, tenants_by_subdomain: dict[str, SimpleNamespace]) -> None:
        super().__init__(
            settings=PlatformSettings(PLATFORM_DOMAIN="musematic.ai"),
            session_factory=lambda: None,  # type: ignore[arg-type]
        )
        self.tenants_by_subdomain = tenants_by_subdomain

    async def _query_tenant(self, subdomain: str) -> SimpleNamespace | None:  # type: ignore[override]
        return self.tenants_by_subdomain.get(subdomain)


def _tenant(slug: str, subdomain: str, kind: str = "enterprise") -> SimpleNamespace:
    return SimpleNamespace(
        id=UUID("00000000-0000-0000-0000-000000000001") if kind == "default" else uuid4(),
        slug=slug,
        subdomain=subdomain,
        kind=kind,
        status="active",
        region="eu-central",
        branding_config_json={},
        feature_flags_json={},
    )


@pytest.mark.asyncio
async def test_default_tenant_hosts_resolve_identically() -> None:
    resolver = StaticTenantResolver(
        {"app": _tenant("default", "app", kind="default")}
    )

    contexts = [
        await resolver.resolve("app.musematic.ai"),
        await resolver.resolve("APP.MUSEMATIC.AI"),
        await resolver.resolve("app.musematic.ai:443"),
        await resolver.resolve("app.musematic.ai:8080"),
        await resolver.resolve("musematic.ai"),
    ]

    assert {context.id for context in contexts if context is not None} == {
        UUID("00000000-0000-0000-0000-000000000001")
    }


@pytest.mark.asyncio
async def test_tenant_api_and_grafana_surfaces_resolve_to_tenant() -> None:
    tenant_id = uuid4()
    resolver = StaticTenantResolver(
        {
            "acme": SimpleNamespace(
                id=tenant_id,
                slug="acme",
                subdomain="acme",
                kind="enterprise",
                status="active",
                region="eu-central",
                branding_config_json={},
                feature_flags_json={},
            )
        }
    )

    assert (await resolver.resolve("acme.api.musematic.ai")).id == tenant_id
    assert (await resolver.resolve("acme.grafana.musematic.ai")).id == tenant_id
