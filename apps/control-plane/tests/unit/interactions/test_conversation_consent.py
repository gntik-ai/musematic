from __future__ import annotations

from platform.interactions.schemas import ConversationCreate
from platform.interactions.service import InteractionsService
from platform.privacy_compliance.exceptions import ConsentRequired
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException


class ConsentServiceStub:
    async def require_or_prompt(self, *_args: object, **_kwargs: object) -> None:
        raise ConsentRequired(["ai_interaction"])


@pytest.mark.asyncio
async def test_create_conversation_returns_machine_readable_consent_428() -> None:
    service = InteractionsService(
        repository=SimpleNamespace(),
        settings=SimpleNamespace(),
        producer=None,
        workspaces_service=None,
        registry_service=None,
        consent_service=ConsentServiceStub(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await service.create_conversation(
            ConversationCreate(title="Needs consent"),
            created_by=str(uuid4()),
            workspace_id=uuid4(),
        )

    assert exc_info.value.status_code == 428
    assert exc_info.value.detail == {
        "error": "consent_required",
        "missing_consents": ["ai_interaction"],
        "disclosure_text_ref": "/api/v1/me/consents/disclosure",
    }
