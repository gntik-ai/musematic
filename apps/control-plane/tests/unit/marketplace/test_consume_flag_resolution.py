"""UPD-049 — TenantContext consume_public_marketplace resolution unit test.

Asserts that the resolver correctly derives the explicit
``consume_public_marketplace`` field from the tenant's ``feature_flags_json``.
"""

from __future__ import annotations

from platform.tenants.resolver import TenantResolver
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest


def _make_tenant(*, kind: str, feature_flags: dict[str, Any] | None) -> MagicMock:
    """Build a mock tenant with the same shape `_to_context` reads from.

    The resolver's `_to_context` only accesses .id/.slug/.subdomain/.kind/
    .status/.region/.branding_config_json/.feature_flags_json — a MagicMock
    with those attributes set is sufficient.
    """
    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.slug = "acme" if kind == "enterprise" else "default"
    tenant.subdomain = tenant.slug
    tenant.kind = kind
    tenant.status = "active"
    tenant.region = "global"
    tenant.branding_config_json = {}
    tenant.feature_flags_json = feature_flags
    return tenant


@pytest.fixture
def resolver() -> TenantResolver:
    # Construct the resolver via __new__ to avoid the wiring / Redis dependency
    # of the normal init — we only exercise _to_context here.
    return TenantResolver.__new__(TenantResolver)


def test_default_tenant_consume_flag_false(resolver: TenantResolver) -> None:
    tenant = _make_tenant(kind="default", feature_flags=None)
    ctx = resolver._to_context(tenant)
    assert ctx.consume_public_marketplace is False


def test_enterprise_tenant_with_flag_set(resolver: TenantResolver) -> None:
    tenant = _make_tenant(
        kind="enterprise",
        feature_flags={"consume_public_marketplace": True},
    )
    ctx = resolver._to_context(tenant)
    assert ctx.consume_public_marketplace is True


def test_enterprise_tenant_without_flag(resolver: TenantResolver) -> None:
    tenant = _make_tenant(
        kind="enterprise",
        feature_flags={"some_other_flag": True},
    )
    ctx = resolver._to_context(tenant)
    assert ctx.consume_public_marketplace is False


def test_round_trip_through_payload(resolver: TenantResolver) -> None:
    tenant = _make_tenant(
        kind="enterprise",
        feature_flags={"consume_public_marketplace": True},
    )
    ctx = resolver._to_context(tenant)
    payload = resolver._context_to_payload(ctx)
    assert payload["consume_public_marketplace"] is True
    rehydrated = resolver._context_from_payload(payload)
    assert rehydrated.consume_public_marketplace is True
