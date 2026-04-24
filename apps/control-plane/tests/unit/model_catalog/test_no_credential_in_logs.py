from __future__ import annotations

from platform.common.clients.model_provider_http import ProviderResponse
from platform.common.clients.model_router import ModelRouter
from uuid import uuid4

import pytest
from tests.unit.model_catalog.test_model_router import (
    ProviderStub,
    RepositoryStub,
    SecretProviderStub,
    _entry,
    _with_credential,
)


@pytest.mark.asyncio
async def test_model_router_does_not_log_credential_material(
    caplog: pytest.LogCaptureFixture,
) -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    repo.add_entry(_entry())
    _with_credential(repo, workspace_id)
    provider = ProviderStub(
        [
            ProviderResponse(
                status_code=200,
                payload={"choices": [{"message": {"content": "ok"}}]},
            )
        ]
    )
    router = ModelRouter(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=SecretProviderStub(),
        provider_call=provider,
    )

    await router.complete(
        workspace_id=workspace_id,
        step_binding="openai:gpt-4o",
        messages=[{"role": "user", "content": "hello"}],
    )

    assert "key:vault://openai" not in caplog.text
