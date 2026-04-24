from __future__ import annotations

from platform.common.clients.model_provider_http import ProviderOutage
from uuid import uuid4

import pytest
from tests.unit.model_catalog.test_model_router import (
    ProviderStub,
    RedisStub,
    RepositoryStub,
    _entry,
    _policy,
    _provider_payload,
    _router,
    _with_credential,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_sticky_cache_skips_primary_until_ttl_expires() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    primary = _entry()
    fallback = _entry("anthropic", "claude-sonnet-4-6")
    repo.add_entry(primary)
    repo.add_entry(fallback)
    repo.policies[("global", None, primary.id)] = _policy(primary, fallback)
    _with_credential(repo, workspace_id, "openai")
    _with_credential(repo, workspace_id, "anthropic")
    redis = RedisStub()
    provider = ProviderStub(
        [
            ProviderOutage("primary"),
            ProviderOutage("primary again"),
            _provider_payload("first fallback"),
            _provider_payload("sticky fallback"),
        ]
    )
    router = _router(repo, provider, redis)

    first = await router.complete(
        workspace_id=workspace_id,
        step_binding="openai:gpt-4o",
        messages=[],
    )
    second = await router.complete(
        workspace_id=workspace_id,
        step_binding="openai:gpt-4o",
        messages=[],
    )

    assert first.content == "first fallback"
    assert second.content == "sticky fallback"
    assert provider.calls[-1]["model_id"] == "claude-sonnet-4-6"
