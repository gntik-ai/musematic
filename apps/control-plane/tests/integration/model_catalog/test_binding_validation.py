from __future__ import annotations

from platform.common.clients.model_provider_http import ProviderResponse
from platform.model_catalog.exceptions import ModelBlockedError
from uuid import uuid4

import pytest
from tests.unit.model_catalog.test_model_router import (
    ProviderStub,
    RepositoryStub,
    _entry,
    _router,
    _with_credential,
)

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_binding_validation_status_matrix() -> None:
    workspace_id = uuid4()
    repo = RepositoryStub()
    approved = _entry(model_id="approved")
    deprecated = _entry(model_id="deprecated", status="deprecated")
    blocked = _entry(model_id="blocked", status="blocked")
    for entry in (approved, deprecated, blocked):
        repo.add_entry(entry)
    _with_credential(repo, workspace_id)
    provider = ProviderStub(
        [
            ProviderResponse(status_code=200, payload={"choices": [{"message": {"content": "a"}}]}),
            ProviderResponse(status_code=200, payload={"choices": [{"message": {"content": "d"}}]}),
        ]
    )
    router = _router(repo, provider)

    assert (
        await router.complete(
            workspace_id=workspace_id,
            step_binding="openai:approved",
            messages=[],
        )
    ).content == "a"
    assert (
        await router.complete(
            workspace_id=workspace_id,
            step_binding="openai:deprecated",
            messages=[],
        )
    ).content == "d"
    with pytest.raises(ModelBlockedError):
        await router.complete(
            workspace_id=workspace_id,
            step_binding="openai:blocked",
            messages=[],
        )
