"""UPD-049 — RegistryService.fork_agent smoke tests.

Exercises the fork happy path and the source-not-visible refusal at the
service layer with mocks. The full live-DB cross-tenant matrix lives in
``tests/integration/marketplace/test_fork_*.py`` (T064–T069).
"""

from __future__ import annotations

from platform.common.tenant_context import TenantContext, current_tenant
from platform.registry.exceptions import (
    NameTakenInTargetNamespaceError,
    SourceAgentNotVisibleError,
)
from platform.registry.schemas import ForkAgentRequest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest


def _build_service():
    from platform.registry.service import RegistryService

    service = RegistryService.__new__(RegistryService)
    service.repository = MagicMock()
    service.repository.session = MagicMock()
    service.repository.session.commit = AsyncMock()
    service.repository.session.add = MagicMock()
    service.repository.session.flush = AsyncMock()
    service.repository.session.execute = AsyncMock()
    service.repository.get_namespace_by_name = AsyncMock()
    service.repository.create_namespace = AsyncMock()
    service.repository.get_agent_by_fqn = AsyncMock(return_value=None)
    service.event_producer = MagicMock()
    service.event_producer.publish = AsyncMock()
    service.opensearch = MagicMock()
    service.qdrant = MagicMock()
    service.workspaces_service = MagicMock()
    service.settings = MagicMock()
    service._index_or_flag = AsyncMock()  # type: ignore[method-assign]
    service._assert_workspace_access = AsyncMock()  # type: ignore[method-assign]
    return service


@pytest.fixture
def acme_tenant_context() -> TenantContext:
    return TenantContext(
        id=uuid4(),
        slug="acme",
        subdomain="acme",
        kind="enterprise",
        status="active",
        region="global",
        consume_public_marketplace=True,
    )


@pytest.mark.asyncio
async def test_fork_source_not_visible_returns_404(
    acme_tenant_context: TenantContext,
) -> None:
    service = _build_service()
    # Repository's fork-source lookup returns no row → SourceAgentNotVisibleError.
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=None)
    service.repository.session.execute = AsyncMock(return_value=result)
    actor_id = uuid4()
    request = ForkAgentRequest(
        target_scope="tenant",
        new_name="acme-fork",
    )
    token = current_tenant.set(acme_tenant_context)
    try:
        with pytest.raises(SourceAgentNotVisibleError):
            await service.fork_agent(uuid4(), request, actor_id)
    finally:
        current_tenant.reset(token)


@pytest.mark.asyncio
async def test_fork_name_taken_returns_409(acme_tenant_context: TenantContext) -> None:
    service = _build_service()
    # Mock source row lookup
    source = MagicMock()
    source.id = uuid4()
    source.fqn = "musematic-tools:pdf-extractor"
    source.display_name = "PDF Extractor"
    source.purpose = "Extract structured data from PDFs"
    source.approach = None
    source.role_types = ["executor"]
    source.custom_role_description = None
    source.tags = ["pdf"]
    source.mcp_server_refs = []
    source.data_categories = []
    source.default_model_binding = None
    result = MagicMock()
    result.scalar_one_or_none = MagicMock(return_value=source)
    service.repository.session.execute = AsyncMock(return_value=result)
    # Workspace authorization passes
    service._assert_workspace_access = AsyncMock()  # type: ignore[method-assign]
    # Namespace lookup returns existing namespace
    namespace = MagicMock()
    namespace.id = uuid4()
    namespace.name = "musematic-tools"
    service.repository.get_namespace_by_name = AsyncMock(return_value=namespace)
    # FQN already taken → name conflict
    service.repository.get_agent_by_fqn = AsyncMock(return_value=MagicMock())
    actor_id = uuid4()
    workspace_id = uuid4()
    request = ForkAgentRequest(
        target_scope="workspace",
        target_workspace_id=workspace_id,
        new_name="acme-fork",
    )
    token = current_tenant.set(acme_tenant_context)
    try:
        with pytest.raises(NameTakenInTargetNamespaceError):
            await service.fork_agent(source.id, request, actor_id)
    finally:
        current_tenant.reset(token)
