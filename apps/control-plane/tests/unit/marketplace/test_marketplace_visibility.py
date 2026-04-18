from __future__ import annotations

from platform.marketplace.schemas import MarketplaceSearchRequest
from uuid import uuid4

import pytest
from tests.marketplace_support import (
    RegistryServiceStub,
    build_agent_document,
    build_marketplace_settings,
    build_search_service,
)


@pytest.mark.asyncio
async def test_marketplace_visibility_patterns_use_effective_visibility_when_enabled() -> None:
    workspace_id = uuid4()
    requester_id = uuid4()
    registry_service = RegistryServiceStub(
        visibility_by_agent={
            requester_id: (["finance-ops:*", "shared:*"], []),
        }
    )
    service = build_search_service(
        settings=build_marketplace_settings(VISIBILITY_ZERO_TRUST_ENABLED=True),
        registry_service=registry_service,
    )[0]

    patterns = await service._get_visibility_patterns(
        workspace_id,
        requesting_agent_id=requester_id,
    )

    assert patterns == ["finance-ops:*", "shared:*"]


@pytest.mark.asyncio
async def test_marketplace_visibility_patterns_default_to_empty_when_agent_has_no_grants() -> None:
    workspace_id = uuid4()
    requester_id = uuid4()
    service = build_search_service(
        settings=build_marketplace_settings(VISIBILITY_ZERO_TRUST_ENABLED=True),
        registry_service=RegistryServiceStub(),
    )[0]

    assert (
        await service._get_visibility_patterns(
            workspace_id,
            requesting_agent_id=requester_id,
        )
        == []
    )
    assert service._is_visible("finance-ops:visible", []) is False


@pytest.mark.asyncio
async def test_marketplace_visibility_patterns_fall_back_when_flag_is_off() -> None:
    workspace_id = uuid4()
    requester_id = uuid4()
    service = build_search_service(
        settings=build_marketplace_settings(VISIBILITY_ZERO_TRUST_ENABLED=False),
        registry_service=RegistryServiceStub(
            visibility_by_agent={requester_id: (["finance-ops:*"], [])}
        ),
    )[0]

    assert await service._get_visibility_patterns(
        workspace_id,
        requesting_agent_id=requester_id,
    ) == ["*"]


@pytest.mark.asyncio
async def test_marketplace_search_total_reflects_post_filter_count() -> None:
    workspace_id = uuid4()
    requester_id = uuid4()
    service = build_search_service(
        documents=[
            build_agent_document(agent_id=uuid4(), fqn="finance-ops:visible"),
            build_agent_document(agent_id=uuid4(), fqn="secret-ops:hidden"),
        ],
        settings=build_marketplace_settings(VISIBILITY_ZERO_TRUST_ENABLED=True),
        registry_service=RegistryServiceStub(
            visibility_by_agent={requester_id: (["finance-ops:*"], [])}
        ),
    )[0]

    response = await service.search(
        MarketplaceSearchRequest(query="", page=1, page_size=20),
        workspace_id,
        uuid4(),
        requesting_agent_id=requester_id,
    )

    assert response.total == 1
    assert [item.fqn for item in response.results] == ["finance-ops:visible"]
