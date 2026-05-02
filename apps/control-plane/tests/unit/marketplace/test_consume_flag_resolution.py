"""UPD-049 — TenantContext consume_public_marketplace resolution unit test.

Asserts that the resolver correctly derives the explicit
``consume_public_marketplace`` field from the tenant's ``feature_flags_json``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.tenants.models import Tenant
from platform.tenants.resolver import HostnameTenantResolver
from typing import Any
from uuid import UUID, uuid4

import pytest


def _make_tenant(*, kind: str, feature_flags: dict[str, Any] | None) -> Tenant:
    """Build an in-memory ``Tenant`` ORM instance suitable for ``_to_context``."""
    tenant = Tenant.__new__(Tenant)
    tenant.id = uuid4()
    tenant.slug = "acme" if kind == "enterprise" else "default"
    tenant.subdomain = tenant.slug
    tenant.display_name = tenant.slug.title()
    tenant.kind = kind
    tenant.status = "active"
    tenant.region = "global"
    tenant.branding_config_json = {}
    tenant.feature_flags_json = feature_flags
    tenant.contract_metadata_json = None
    tenant.scheduled_deletion_at = None
    tenant.created_at = datetime.now(tz=UTC)
    tenant.updated_at = tenant.created_at
    return tenant


@pytest.fixture
def resolver() -> HostnameTenantResolver:
    # Construct the resolver via __new__ to avoid the wiring / Redis dependency
    # of the normal init — we only exercise _to_context here.
    return HostnameTenantResolver.__new__(HostnameTenantResolver)


def test_default_tenant_consume_flag_false(resolver: HostnameTenantResolver) -> None:
    tenant = _make_tenant(kind="default", feature_flags=None)
    ctx = resolver._to_context(tenant)
    assert ctx.consume_public_marketplace is False


def test_enterprise_tenant_with_flag_set(resolver: HostnameTenantResolver) -> None:
    tenant = _make_tenant(
        kind="enterprise",
        feature_flags={"consume_public_marketplace": True},
    )
    ctx = resolver._to_context(tenant)
    assert ctx.consume_public_marketplace is True


def test_enterprise_tenant_without_flag(resolver: HostnameTenantResolver) -> None:
    tenant = _make_tenant(
        kind="enterprise",
        feature_flags={"some_other_flag": True},
    )
    ctx = resolver._to_context(tenant)
    assert ctx.consume_public_marketplace is False


def test_round_trip_through_payload(resolver: HostnameTenantResolver) -> None:
    tenant = _make_tenant(
        kind="enterprise",
        feature_flags={"consume_public_marketplace": True},
    )
    ctx = resolver._to_context(tenant)
    payload = resolver._context_to_payload(ctx)
    assert payload["consume_public_marketplace"] is True
    rehydrated = resolver._context_from_payload(payload)
    assert rehydrated.consume_public_marketplace is True
