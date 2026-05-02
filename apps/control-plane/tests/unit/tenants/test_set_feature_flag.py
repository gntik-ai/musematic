"""UPD-049 — TenantsService.set_feature_flag unit tests.

Verifies allowlist enforcement, kind validation, audit-chain integration,
Kafka emission, and idempotence. The full integration variant (DB + real
audit chain + real Kafka + real cache invalidation) lives in
``tests/integration/tenants/test_admin_patch_feature_flags.py``.
"""

from __future__ import annotations

from platform.tenants.exceptions import (
    FeatureFlagInvalidForTenantKindError,
    FeatureFlagNotInAllowlistError,
    TenantNotFoundError,
)
from platform.tenants.events import TenantEventType
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _build_service_with_tenant(*, tenant_kind: str, feature_flags: dict[str, Any] | None):
    """Build a TenantsService instance with mocked dependencies and a
    ``feature_flags_json`` matching the requested seed."""
    from platform.tenants.service import TenantsService

    tenant = MagicMock()
    tenant.id = uuid4()
    tenant.slug = "acme" if tenant_kind == "enterprise" else "default"
    tenant.kind = tenant_kind
    tenant.feature_flags_json = feature_flags

    repository = MagicMock()
    repository.get_by_id = AsyncMock(return_value=tenant)
    repository.update = AsyncMock(return_value=None)

    session = MagicMock()
    session.commit = AsyncMock()
    session.flush = AsyncMock()

    audit_chain = MagicMock()
    audit_chain.append = AsyncMock()

    producer = MagicMock()
    producer.publish = AsyncMock()

    service = TenantsService.__new__(TenantsService)
    service.session = session
    service.repository = repository
    service.settings = MagicMock()
    service.producer = producer
    service.audit_chain = audit_chain
    service.dns_automation = MagicMock()
    service.notifications = None
    service.object_storage = None
    service.redis_client = None
    service.subscription_service = None
    return service, tenant


@pytest.mark.asyncio
async def test_set_consume_flag_on_enterprise_succeeds() -> None:
    service, tenant = _build_service_with_tenant(tenant_kind="enterprise", feature_flags={})
    actor = {"user_id": uuid4()}
    # Skip the cache invalidation path which depends on Redis pub/sub.
    service._publish_cache_invalidation = AsyncMock()  # type: ignore[method-assign]

    result = await service.set_feature_flag(
        actor, tenant.id, "consume_public_marketplace", True
    )
    assert result is tenant
    service.repository.update.assert_awaited_once()
    service.audit_chain.append.assert_awaited_once()
    service.producer.publish.assert_awaited_once()
    publish_call = service.producer.publish.call_args
    assert publish_call.kwargs["event_type"] == TenantEventType.feature_flag_changed.value


@pytest.mark.asyncio
async def test_set_consume_flag_on_default_tenant_refused() -> None:
    service, tenant = _build_service_with_tenant(tenant_kind="default", feature_flags={})
    actor = {"user_id": uuid4()}
    service._publish_cache_invalidation = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(FeatureFlagInvalidForTenantKindError):
        await service.set_feature_flag(
            actor, tenant.id, "consume_public_marketplace", True
        )
    service.repository.update.assert_not_awaited()
    service.audit_chain.append.assert_not_awaited()
    service.producer.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_unknown_flag_refused() -> None:
    service, tenant = _build_service_with_tenant(tenant_kind="enterprise", feature_flags={})
    actor = {"user_id": uuid4()}
    service._publish_cache_invalidation = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(FeatureFlagNotInAllowlistError):
        await service.set_feature_flag(actor, tenant.id, "ufo_mode", True)
    service.repository.update.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_flag_on_unknown_tenant_raises_not_found() -> None:
    service, tenant = _build_service_with_tenant(tenant_kind="enterprise", feature_flags={})
    service.repository.get_by_id = AsyncMock(return_value=None)
    actor = {"user_id": uuid4()}
    service._publish_cache_invalidation = AsyncMock()  # type: ignore[method-assign]
    with pytest.raises(TenantNotFoundError):
        await service.set_feature_flag(
            actor, tenant.id, "consume_public_marketplace", True
        )


@pytest.mark.asyncio
async def test_set_flag_idempotent_no_op_when_value_unchanged() -> None:
    service, tenant = _build_service_with_tenant(
        tenant_kind="enterprise",
        feature_flags={"consume_public_marketplace": True},
    )
    actor = {"user_id": uuid4()}
    service._publish_cache_invalidation = AsyncMock()  # type: ignore[method-assign]
    await service.set_feature_flag(
        actor, tenant.id, "consume_public_marketplace", True
    )
    # No write, no audit, no event when value is already what's requested.
    service.repository.update.assert_not_awaited()
    service.audit_chain.append.assert_not_awaited()
    service.producer.publish.assert_not_awaited()
