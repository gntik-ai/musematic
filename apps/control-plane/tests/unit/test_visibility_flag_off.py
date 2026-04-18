from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.interactions.schemas import ConversationCreate, InteractionCreate, ParticipantAdd
from platform.policies.gateway import ToolGatewayService
from platform.policies.schemas import BudgetLimitsSchema, EnforcementBundle, ValidationManifest
from platform.registry.models import LifecycleStatus
from platform.registry.schemas import AgentDiscoveryParams
from platform.registry.service import RegistryService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.interactions_support import build_service as build_interactions_service
from tests.marketplace_support import RegistryServiceStub as MarketplaceRegistryStub
from tests.marketplace_support import (
    build_agent_document,
    build_marketplace_settings,
    build_search_service,
)
from tests.registry_support import (
    AsyncOpenSearchStub,
    AsyncQdrantStub,
    ObjectStorageStub,
    RegistryRepoStub,
    build_namespace,
    build_profile,
    build_registry_settings,
)


class PolicyServiceStub:
    def __init__(self, bundle: EnforcementBundle) -> None:
        self.bundle = bundle
        self.blocked_calls: list[dict[str, object]] = []
        self.allowed_calls: list[dict[str, object]] = []
        self.redis_client = None

    async def get_enforcement_bundle(self, agent_id, workspace_id, execution_id=None):
        del agent_id, workspace_id, execution_id
        return self.bundle

    async def create_blocked_record(self, **kwargs):
        self.blocked_calls.append(kwargs)
        return kwargs

    async def publish_allowed_event(self, **kwargs) -> None:
        self.allowed_calls.append(kwargs)


class ToolRegistryStub:
    def __init__(self, tool_patterns: list[str]) -> None:
        self.tool_patterns = tool_patterns

    async def resolve_effective_visibility(self, agent_id, workspace_id):
        del agent_id, workspace_id
        return SimpleNamespace(agent_patterns=[], tool_patterns=list(self.tool_patterns))


class InteractionRegistryStub:
    def __init__(self, agent_patterns: dict[UUID, list[str]]) -> None:
        self.agent_patterns = agent_patterns

    async def resolve_effective_visibility(self, agent_id, workspace_id):
        del workspace_id
        return SimpleNamespace(
            agent_patterns=list(self.agent_patterns.get(agent_id, [])),
            tool_patterns=[],
        )


def _build_registry_service(
    *,
    settings: PlatformSettings,
    requester_visibility: list[str],
) -> tuple[RegistryService, UUID, UUID, UUID]:
    workspace_id = uuid4()
    namespace = build_namespace(workspace_id=workspace_id, name="finance-ops")
    hidden_namespace = build_namespace(workspace_id=workspace_id, name="secret-ops")
    visible = build_profile(
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="visible",
        status=LifecycleStatus.published,
    )
    hidden = build_profile(
        workspace_id=workspace_id,
        namespace=hidden_namespace,
        local_name="hidden",
        status=LifecycleStatus.published,
    )
    requester_id = uuid4()
    requester = build_profile(
        profile_id=requester_id,
        workspace_id=workspace_id,
        namespace=namespace,
        local_name="requester",
        visibility_agents=requester_visibility,
        status=LifecycleStatus.published,
    )
    repo = RegistryRepoStub()
    for profile in (visible, hidden, requester):
        repo.profiles_by_id[profile.id] = profile
        repo.profiles_by_fqn[(workspace_id, profile.fqn)] = profile
        repo.revisions_by_profile[profile.id] = []
    service = RegistryService(
        repository=repo,
        object_storage=ObjectStorageStub(),
        opensearch=AsyncOpenSearchStub(),
        qdrant=AsyncQdrantStub(),
        workspaces_service=None,
        event_producer=RecordingProducer(),
        settings=settings,
    )
    return service, workspace_id, requester_id, hidden.id


def _tool_bundle() -> EnforcementBundle:
    return EnforcementBundle(
        fingerprint="f" * 64,
        allowed_tool_patterns=["tools:*"],
        denied_tool_patterns=[],
        allowed_purposes=[],
        denied_purposes=[],
        allowed_namespaces=[],
        budget_limits=BudgetLimitsSchema(),
        maturity_gate_rules=[],
        safety_rules=[],
        log_allowed_tools=[],
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    )


@pytest.mark.asyncio
async def test_visibility_flag_off_preserves_behavior_across_enforcement_points() -> None:
    registry_service, workspace_id, requester_id, hidden_id = _build_registry_service(
        settings=build_registry_settings(VISIBILITY_ZERO_TRUST_ENABLED=False),
        requester_visibility=[],
    )
    listed = await registry_service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )
    fetched = await registry_service.get_agent(
        workspace_id,
        hidden_id,
        actor_id=None,
        requesting_agent_id=requester_id,
    )

    gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(_tool_bundle()),
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=None,
        registry_service=ToolRegistryStub([]),
        settings=PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=False),
    )
    gate_result = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "tools:finance:hidden",
        "analysis",
        None,
        workspace_id,
        None,
    )

    interactions_service, _repo, _workspaces, _producer = build_interactions_service(
        settings=PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=False),
        registry_service=InteractionRegistryStub({requester_id: []}),
    )
    conversation = await interactions_service.create_conversation(
        ConversationCreate(title="Legacy"),
        "user-1",
        workspace_id,
    )
    interaction = await interactions_service.create_interaction(
        InteractionCreate(conversation_id=conversation.id),
        "user-1",
        workspace_id,
    )
    participant = await interactions_service.add_participant(
        interaction.id,
        ParticipantAdd(identity="finance-ops:hidden", role="responder"),
        workspace_id,
        requesting_agent_id=requester_id,
    )

    search_service = build_search_service(
        documents=[build_agent_document(fqn="secret-ops:hidden")],
        settings=build_marketplace_settings(VISIBILITY_ZERO_TRUST_ENABLED=False),
        registry_service=MarketplaceRegistryStub(
            visibility_by_agent={requester_id: ([], [])}
        ),
    )[0]
    patterns = await search_service._get_visibility_patterns(
        workspace_id,
        requesting_agent_id=requester_id,
    )

    assert listed.total == 3
    assert fetched.id == hidden_id
    assert gate_result.allowed is True
    assert participant.identity == "finance-ops:hidden"
    assert patterns == ["*"]


@pytest.mark.asyncio
async def test_visibility_flag_toggle_takes_effect_on_next_request() -> None:
    settings = build_registry_settings(VISIBILITY_ZERO_TRUST_ENABLED=False)
    registry_service, workspace_id, requester_id, _hidden_id = _build_registry_service(
        settings=settings,
        requester_visibility=[],
    )
    first = await registry_service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    settings.visibility.zero_trust_enabled = True
    second = await registry_service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    settings.visibility.zero_trust_enabled = False
    third = await registry_service.list_agents(
        AgentDiscoveryParams(workspace_id=workspace_id, limit=10, offset=0),
        requesting_agent_id=requester_id,
    )

    assert first.total == 3
    assert second.total == 0
    assert third.total == 3
