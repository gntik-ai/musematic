from __future__ import annotations

from platform.common.exceptions import AuthorizationError
from platform.common.tagging.tag_service import TagService
from uuid import UUID, uuid4

import httpx
import pytest
from tests.integration.common.tagging.support import (
    InMemoryTaggingRepository,
    RecordingAudit,
    build_router_app,
    requester,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_tag_mutation_refusal_returns_standard_authorization_error() -> None:
    repo = InMemoryTaggingRepository()
    audit = RecordingAudit()
    actor_id = uuid4()

    async def deny_mutation(
        entity_type: str,
        entity_id: UUID,
        current_user: object,
        action: str,
    ) -> bool:
        del entity_type, entity_id, current_user, action
        raise AuthorizationError(
            "TAGGING_ENTITY_MUTATION_FORBIDDEN",
            "The requester cannot mutate this entity.",
        )

    app = build_router_app(
        current_user=requester(actor_id),
        tag_service=TagService(repo, audit_chain=audit, entity_access_check=deny_mutation),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            f"/api/v1/tags/agent/{uuid4()}",
            json={"tag": "production"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "TAGGING_ENTITY_MUTATION_FORBIDDEN"
    assert audit.entries == []
