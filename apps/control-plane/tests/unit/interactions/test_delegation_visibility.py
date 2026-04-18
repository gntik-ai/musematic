from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.interactions.exceptions import InteractionNotFoundError
from platform.interactions.models import ParticipantRole
from platform.interactions.schemas import ConversationCreate, InteractionCreate, ParticipantAdd
from types import SimpleNamespace
from uuid import uuid4

import pytest
from tests.interactions_support import build_service


class RegistryVisibilityStub:
    def __init__(self, grants_by_agent: dict[object, list[str]]) -> None:
        self.grants_by_agent = grants_by_agent

    async def resolve_effective_visibility(self, agent_id, workspace_id):
        del workspace_id
        return SimpleNamespace(
            agent_patterns=list(self.grants_by_agent.get(agent_id, [])),
            tool_patterns=[],
        )


async def _setup_service(*, zero_trust_enabled: bool, registry_service=None):
    service, _repo, _workspaces, _producer = build_service(
        settings=PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=zero_trust_enabled),
        registry_service=registry_service,
    )
    workspace_id = uuid4()
    conversation = await service.create_conversation(
        ConversationCreate(title="Visibility"),
        "user-1",
        workspace_id,
    )
    interaction = await service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        workspace_id,
    )
    return service, workspace_id, interaction.id


@pytest.mark.asyncio
async def test_add_participant_blocks_invisible_target_when_zero_trust_is_enabled() -> None:
    requester_id = uuid4()
    service, workspace_id, interaction_id = await _setup_service(
        zero_trust_enabled=True,
        registry_service=RegistryVisibilityStub({requester_id: []}),
    )

    with pytest.raises(InteractionNotFoundError) as denied:
        await service.add_participant(
            interaction_id,
            ParticipantAdd(identity="finance-ops:secret-agent", role=ParticipantRole.responder),
            workspace_id,
            requesting_agent_id=requester_id,
        )

    expected = InteractionNotFoundError(interaction_id)
    assert denied.value.code == expected.code
    assert denied.value.message == expected.message


@pytest.mark.asyncio
async def test_add_participant_allows_visible_target_when_zero_trust_is_enabled() -> None:
    requester_id = uuid4()
    service, workspace_id, interaction_id = await _setup_service(
        zero_trust_enabled=True,
        registry_service=RegistryVisibilityStub({requester_id: ["finance-ops:*"]}),
    )

    participant = await service.add_participant(
        interaction_id,
        ParticipantAdd(identity="finance-ops:aml-checker", role=ParticipantRole.responder),
        workspace_id,
        requesting_agent_id=requester_id,
    )

    assert participant.identity == "finance-ops:aml-checker"


@pytest.mark.asyncio
async def test_add_participant_skips_visibility_for_flag_off_and_legacy_calls() -> None:
    requester_id = uuid4()
    off_service, off_workspace_id, off_interaction_id = await _setup_service(
        zero_trust_enabled=False,
        registry_service=RegistryVisibilityStub({requester_id: []}),
    )
    off_participant = await off_service.add_participant(
        off_interaction_id,
        ParticipantAdd(identity="finance-ops:any-agent", role=ParticipantRole.responder),
        off_workspace_id,
        requesting_agent_id=requester_id,
    )

    legacy_service, legacy_workspace_id, legacy_interaction_id = await _setup_service(
        zero_trust_enabled=True,
        registry_service=RegistryVisibilityStub({requester_id: []}),
    )
    legacy_participant = await legacy_service.add_participant(
        legacy_interaction_id,
        ParticipantAdd(identity="finance-ops:any-agent", role=ParticipantRole.responder),
        legacy_workspace_id,
    )

    assert off_participant.identity == "finance-ops:any-agent"
    assert legacy_participant.identity == "finance-ops:any-agent"
