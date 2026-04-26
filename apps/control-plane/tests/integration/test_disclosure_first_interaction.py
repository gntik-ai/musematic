from __future__ import annotations

from datetime import UTC, datetime
from platform.interactions.schemas import ConversationCreate
from platform.interactions.service import InteractionsService
from platform.privacy_compliance.exceptions import ConsentRequired
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException


class FakeSession:
    async def commit(self) -> None:
        return None


class FakeConversationRepository:
    session = FakeSession()

    async def create_conversation(
        self,
        *,
        workspace_id,
        title: str,
        created_by: str,
        metadata: dict[str, object],
    ) -> SimpleNamespace:
        now = datetime.now(UTC)
        return SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            title=title,
            created_by=created_by,
            metadata_json=metadata,
            message_count=0,
            created_at=now,
            updated_at=now,
        )


class ConsentServiceStub:
    def __init__(self) -> None:
        self.granted = False

    async def require_or_prompt(self, *_args: object, **_kwargs: object) -> None:
        if not self.granted:
            raise ConsentRequired(["ai_interaction"])

    def acknowledge(self) -> None:
        self.granted = True

    def revoke_or_material_update(self) -> None:
        self.granted = False


def _service(consent: ConsentServiceStub) -> InteractionsService:
    return InteractionsService(
        repository=FakeConversationRepository(),  # type: ignore[arg-type]
        settings=SimpleNamespace(),
        producer=None,
        workspaces_service=None,
        registry_service=None,
        consent_service=consent,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_disclosure_first_interaction_ack_revoke_and_material_update() -> None:
    consent = ConsentServiceStub()
    service = _service(consent)
    user_id = str(uuid4())
    workspace_id = uuid4()

    with pytest.raises(HTTPException) as first_prompt:
        await service.create_conversation(
            ConversationCreate(title="first"),
            created_by=user_id,
            workspace_id=workspace_id,
        )

    consent.acknowledge()
    created = await service.create_conversation(
        ConversationCreate(title="after consent"),
        created_by=user_id,
        workspace_id=workspace_id,
    )

    consent.revoke_or_material_update()
    with pytest.raises(HTTPException) as revoked_prompt:
        await service.create_conversation(
            ConversationCreate(title="after revoke"),
            created_by=user_id,
            workspace_id=workspace_id,
        )

    consent.acknowledge()
    consent.revoke_or_material_update()
    with pytest.raises(HTTPException) as material_prompt:
        await service.create_conversation(
            ConversationCreate(title="after material update"),
            created_by=user_id,
            workspace_id=workspace_id,
        )

    assert first_prompt.value.status_code == 428
    assert first_prompt.value.detail["disclosure_text_ref"] == "/api/v1/me/consents/disclosure"
    assert created.title == "after consent"
    assert revoked_prompt.value.detail["missing_consents"] == ["ai_interaction"]
    assert material_prompt.value.status_code == 428
