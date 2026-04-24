from __future__ import annotations

from platform.common.clients.model_provider_http import ProviderOutage
from uuid import uuid4

import pytest
from tests.unit.model_catalog.test_model_router import (
    ProducerStub,
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
async def test_fallback_event_payload_and_response_audit() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    primary = _entry()
    fallback = _entry("anthropic", "claude-sonnet-4-6")
    repo.add_entry(primary)
    repo.add_entry(fallback)
    repo.policies[("global", None, primary.id)] = _policy(primary, fallback)
    _with_credential(repo, workspace_id, "openai")
    _with_credential(repo, workspace_id, "anthropic")
    producer = ProducerStub()
    provider = ProviderStub(
        [ProviderOutage("primary"), ProviderOutage("primary again"), _provider_payload("ok")]
    )

    response = await _router(repo, provider, RedisStub(), producer).complete(
        workspace_id=workspace_id,
        step_binding="openai:gpt-4o",
        messages=[],
    )

    assert response.fallback_taken is not None
    assert producer.calls[0]["event_type"] == "model.fallback.triggered"
    assert producer.calls[0]["payload"]["primary_model_id"] == str(primary.id)
