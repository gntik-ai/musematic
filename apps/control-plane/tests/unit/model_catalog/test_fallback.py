from __future__ import annotations

from platform.common.clients.model_provider_http import ProviderOutage
from platform.model_catalog.exceptions import FallbackExhaustedError
from uuid import uuid4

import pytest
from tests.unit.model_catalog.test_model_router import (
    ProviderStub,
    RepositoryStub,
    _entry,
    _policy,
    _provider_payload,
    _router,
    _with_credential,
)


@pytest.mark.asyncio
async def test_fallback_chain_succeeds_then_exhausts_with_failure_list() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    primary = _entry()
    fallback = _entry("anthropic", "claude-sonnet-4-6")
    repo.add_entry(primary)
    repo.add_entry(fallback)
    repo.policies[("global", None, primary.id)] = _policy(primary, fallback)
    _with_credential(repo, workspace_id, "openai")
    _with_credential(repo, workspace_id, "anthropic")
    success_provider = ProviderStub(
        [ProviderOutage("primary"), ProviderOutage("primary again"), _provider_payload("ok")]
    )

    result = await _router(repo, success_provider).complete(
        workspace_id=workspace_id,
        step_binding="openai:gpt-4o",
        messages=[],
    )

    assert result.fallback_taken is not None
    assert result.content == "ok"

    exhausted_provider = ProviderStub(
        [ProviderOutage("primary"), ProviderOutage("primary again"), ProviderOutage("fallback")]
    )
    with pytest.raises(FallbackExhaustedError) as exc_info:
        await _router(repo, exhausted_provider).complete(
            workspace_id=workspace_id,
            step_binding="openai:gpt-4o",
            messages=[],
        )
    assert exc_info.value.details["failures"][0]["reason"] == "provider_5xx"
