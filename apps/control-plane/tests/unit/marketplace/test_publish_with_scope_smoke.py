"""UPD-049 — RegistryService.publish_with_scope smoke tests.

Covers the critical security paths from US1 and US2:

- T023 / T024 — workspace and tenant scopes transition directly to published.
- T025 — public scope transitions to pending_review with the right side effects.
- T048 — Enterprise tenant attempting public scope is refused before any side effect.

Heavy mocking — exercises the service-level branching without a live DB.
Live-DB end-to-end tests (T026–T030) live in
``tests/integration/marketplace/`` with skip markers pending the fixture wire-up.
"""

from __future__ import annotations

from platform.common.tenant_context import TenantContext, current_tenant
from platform.registry.exceptions import (
    MarketingMetadataRequiredError,
    PublicScopeNotAllowedForEnterpriseError,
)
from platform.registry.schemas import MarketingMetadata, PublishWithScopeRequest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _build_service(*, tenant_kind: str, slug: str = "default"):
    from platform.registry.service import RegistryService

    service = RegistryService.__new__(RegistryService)
    service.repository = MagicMock()
    service.repository.session = MagicMock()
    service.repository.session.commit = AsyncMock()
    service.repository.insert_lifecycle_audit = AsyncMock()
    service.repository.get_agent_by_id = AsyncMock()
    service.event_producer = MagicMock()
    service.event_producer.publish = AsyncMock()
    service.opensearch = MagicMock()
    service.qdrant = MagicMock()
    service.workspaces_service = MagicMock()
    service.workspaces_service.get_user_workspace_ids = AsyncMock(
        return_value=[uuid4()]
    )
    service.settings = MagicMock()
    service._index_or_flag = AsyncMock()  # type: ignore[method-assign]
    service._build_profile_response = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    service._assert_workspace_access = AsyncMock()  # type: ignore[method-assign]

    # Build a profile mock that satisfies the publish_with_scope path.
    profile = MagicMock()
    profile.id = uuid4()
    profile.fqn = "test:agent"
    profile.workspace_id = uuid4()
    profile.tenant_id = uuid4()
    profile.marketplace_scope = "workspace"
    profile.review_status = "draft"
    from platform.registry.models import LifecycleStatus
    profile.status = LifecycleStatus.validated
    service.repository.get_agent_by_id = AsyncMock(return_value=profile)
    return service, profile


@pytest.fixture
def default_tenant_context() -> TenantContext:
    return TenantContext(
        id=uuid4(),
        slug="default",
        subdomain="default",
        kind="default",
        status="active",
        region="global",
    )


@pytest.fixture
def acme_tenant_context() -> TenantContext:
    return TenantContext(
        id=uuid4(),
        slug="acme",
        subdomain="acme",
        kind="enterprise",
        status="active",
        region="global",
    )


@pytest.mark.asyncio
async def test_publish_workspace_scope_direct_published(default_tenant_context: TenantContext) -> None:
    """T023 — workspace scope publishes immediately, no review."""
    service, profile = _build_service(tenant_kind="default")
    actor_id = uuid4()
    workspace_id = profile.workspace_id
    service.workspaces_service.get_user_workspace_ids = AsyncMock(return_value=[workspace_id])
    token = current_tenant.set(default_tenant_context)
    try:
        await service.publish_with_scope(
            workspace_id,
            profile.id,
            PublishWithScopeRequest(scope="workspace"),
            actor_id,
        )
    finally:
        current_tenant.reset(token)
    assert profile.marketplace_scope == "workspace"
    assert profile.review_status == "published"
    # marketplace.published event was emitted
    assert service.event_producer.publish.await_count >= 1


@pytest.mark.asyncio
async def test_publish_tenant_scope_direct_published(default_tenant_context: TenantContext) -> None:
    """T024 — tenant scope publishes immediately."""
    service, profile = _build_service(tenant_kind="default")
    actor_id = uuid4()
    workspace_id = profile.workspace_id
    service.workspaces_service.get_user_workspace_ids = AsyncMock(return_value=[workspace_id])
    token = current_tenant.set(default_tenant_context)
    try:
        await service.publish_with_scope(
            workspace_id,
            profile.id,
            PublishWithScopeRequest(scope="tenant"),
            actor_id,
        )
    finally:
        current_tenant.reset(token)
    assert profile.marketplace_scope == "tenant"
    assert profile.review_status == "published"


@pytest.mark.asyncio
async def test_publish_public_scope_enters_review(default_tenant_context: TenantContext) -> None:
    """T025 — public scope from default tenant enters pending_review."""
    service, profile = _build_service(tenant_kind="default")
    actor_id = uuid4()
    workspace_id = profile.workspace_id
    service.workspaces_service.get_user_workspace_ids = AsyncMock(return_value=[workspace_id])
    rate_limiter = MagicMock()
    rate_limiter.check_and_record = AsyncMock()
    request = PublishWithScopeRequest(
        scope="public_default_tenant",
        marketing_metadata=MarketingMetadata(
            category="data-extraction",
            marketing_description="A clear, sufficiently long marketing description.",
            tags=["pdf"],
        ),
    )
    token = current_tenant.set(default_tenant_context)
    try:
        await service.publish_with_scope(
            workspace_id, profile.id, request, actor_id, rate_limiter=rate_limiter
        )
    finally:
        current_tenant.reset(token)
    assert profile.marketplace_scope == "public_default_tenant"
    assert profile.review_status == "pending_review"
    rate_limiter.check_and_record.assert_awaited_once_with(actor_id)
    # marketplace.submitted event emitted
    assert service.event_producer.publish.await_count >= 1


@pytest.mark.asyncio
async def test_enterprise_tenant_refused_before_any_side_effect(
    acme_tenant_context: TenantContext,
) -> None:
    """T048 — Enterprise tenant gets PublicScopeNotAllowedForEnterpriseError
    BEFORE the rate limiter, audit, or Kafka are touched."""
    service, profile = _build_service(tenant_kind="enterprise")
    actor_id = uuid4()
    workspace_id = profile.workspace_id
    service.workspaces_service.get_user_workspace_ids = AsyncMock(return_value=[workspace_id])
    rate_limiter = MagicMock()
    rate_limiter.check_and_record = AsyncMock()
    request = PublishWithScopeRequest(
        scope="public_default_tenant",
        marketing_metadata=MarketingMetadata(
            category="data-extraction",
            marketing_description="A description that is long enough for the validator.",
            tags=["pdf"],
        ),
    )
    token = current_tenant.set(acme_tenant_context)
    try:
        with pytest.raises(PublicScopeNotAllowedForEnterpriseError):
            await service.publish_with_scope(
                workspace_id, profile.id, request, actor_id, rate_limiter=rate_limiter
            )
    finally:
        current_tenant.reset(token)
    # No side effects must have run.
    rate_limiter.check_and_record.assert_not_awaited()
    service.repository.insert_lifecycle_audit.assert_not_awaited()
    service.event_producer.publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_scope_without_marketing_metadata_refused(
    default_tenant_context: TenantContext,
) -> None:
    """Defensive — Pydantic validator catches this, but service guard does too."""
    # Build a request that bypasses the Pydantic validator (we instantiate the
    # underlying object via construct() to test the service-level guard).
    request = PublishWithScopeRequest.model_construct(
        scope="public_default_tenant",
        marketing_metadata=None,
    )
    service, profile = _build_service(tenant_kind="default")
    actor_id = uuid4()
    workspace_id = profile.workspace_id
    service.workspaces_service.get_user_workspace_ids = AsyncMock(return_value=[workspace_id])
    token = current_tenant.set(default_tenant_context)
    try:
        with pytest.raises(MarketingMetadataRequiredError):
            await service.publish_with_scope(
                workspace_id, profile.id, request, actor_id
            )
    finally:
        current_tenant.reset(token)
