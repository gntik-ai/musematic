from __future__ import annotations

from platform.policies.exceptions import PolicyAttachmentError, PolicyNotFoundError
from platform.policies.models import (
    AttachmentTargetType,
    EnforcementComponent,
    PolicyScopeType,
    PolicyStatus,
)
from platform.policies.schemas import (
    EnforcementRuleSchema,
    MaturityGateRuleSchema,
    PolicyAttachRequest,
    PolicyUpdate,
)
from platform.policies.service import PolicyService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.policies_support import (
    InMemoryPolicyRepository,
    RegistryPolicyStub,
    WorkspacesPolicyStub,
    build_fake_redis,
    build_policy,
    build_policy_create,
    build_policy_settings,
    build_rules,
)


def build_service(
    *,
    workspace_ids: set[UUID] | frozenset[UUID] = frozenset(),
    registry_service: object | None = None,
    redis_client: object | None = None,
    producer: RecordingProducer | None = None,
) -> tuple[PolicyService, InMemoryPolicyRepository, RecordingProducer]:
    repository = InMemoryPolicyRepository()
    event_producer = producer or RecordingProducer()
    service = PolicyService(
        repository=repository,
        settings=build_policy_settings(),
        producer=event_producer,
        redis_client=redis_client,
        registry_service=registry_service,
        workspaces_service=WorkspacesPolicyStub(workspace_ids=set(workspace_ids)),
    )
    return service, repository, event_producer


@pytest.mark.asyncio
async def test_policy_service_crud_history_and_archive_flow() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    service, _repository, producer = build_service(workspace_ids={workspace_id})

    created = await service.create_policy(
        build_policy_create(workspace_id=workspace_id),
        actor_id,
    )
    updated = await service.update_policy(
        created.id,
        PolicyUpdate(
            name=" Updated Policy ",
            description=None,
            change_summary="second version",
        ),
        actor_id,
    )
    fetched = await service.get_policy(created.id)
    history = await service.get_version_history(created.id)
    version_one = await service.get_version_by_number(created.id, 1)
    listing = await service.list_policies(
        scope_type=PolicyScopeType.workspace,
        status=None,
        workspace_id=workspace_id,
        page=1,
        page_size=20,
    )
    archived = await service.archive_policy(created.id, actor_id)
    archived_listing = await service.list_policies(
        scope_type=None,
        status=PolicyStatus.active,
        workspace_id=workspace_id,
        page=1,
        page_size=20,
    )

    assert created.current_version is not None
    assert created.current_version.version_number == 1
    assert updated.name == "Updated Policy"
    assert updated.description is None
    assert updated.current_version is not None
    assert updated.current_version.version_number == 2
    assert fetched.current_version is not None
    assert fetched.current_version.version_number == 2
    assert history.total == 2
    assert version_one.version_number == 1
    assert listing.total == 1
    assert archived.status.value == "archived"
    assert archived_listing.total == 0
    assert [event["event_type"] for event in producer.events] == [
        "policy.created",
        "policy.updated",
        "policy.archived",
    ]

    with pytest.raises(PolicyNotFoundError):
        await service.get_version_by_number(created.id, 99)

    with pytest.raises(PolicyNotFoundError):
        await service.get_policy(uuid4())


@pytest.mark.asyncio
async def test_policy_service_attachment_resolution_cache_and_visibility_flow() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    revision_id = uuid4()
    actor_id = uuid4()
    memory, redis_client = build_fake_redis()
    registry = RegistryPolicyStub(
        agents={
            agent_id: SimpleNamespace(
                id=agent_id,
                maturity_level=3,
                current_revision=SimpleNamespace(id=revision_id),
            )
        },
        visibility_by_agent={agent_id: (["finance:*"], ["tools:*"])},
    )
    registry.repository.latest_revision_by_agent[agent_id] = SimpleNamespace(id=revision_id)
    registry.repository.revisions_by_id[revision_id] = SimpleNamespace(id=revision_id)
    service, repository, _producer = build_service(
        workspace_ids={workspace_id},
        registry_service=registry,
        redis_client=redis_client,
    )

    global_policy = await service.create_policy(
        build_policy_create(
            scope_type=PolicyScopeType.global_scope,
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="global-allow",
                        action="allow",
                        tool_patterns=["finance:*"],
                    )
                ]
            ),
        ),
        actor_id,
    )
    workspace_policy = await service.create_policy(
        build_policy_create(
            workspace_id=workspace_id,
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="workspace-deny",
                        action="deny",
                        tool_patterns=["finance:wire"],
                    )
                ]
            ),
        ),
        actor_id,
    )
    agent_policy = await service.create_policy(
        build_policy_create(
            workspace_id=workspace_id,
            scope_type=PolicyScopeType.agent,
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="agent-allow",
                        action="allow",
                        tool_patterns=["finance:wire"],
                    )
                ]
            ),
        ),
        actor_id,
    )

    await service.attach_policy(
        global_policy.id,
        PolicyAttachRequest(target_type=AttachmentTargetType.global_scope, target_id=None),
        actor_id,
    )
    await service.attach_policy(
        workspace_policy.id,
        PolicyAttachRequest(
            target_type=AttachmentTargetType.workspace,
            target_id=str(workspace_id),
        ),
        actor_id,
    )
    agent_attachment = await service.attach_policy(
        agent_policy.id,
        PolicyAttachRequest(
            target_type=AttachmentTargetType.agent_revision,
            target_id=str(revision_id),
        ),
        actor_id,
    )

    with pytest.raises(PolicyAttachmentError):
        await service.attach_policy(
            agent_policy.id,
            PolicyAttachRequest(
                target_type=AttachmentTargetType.agent_revision,
                target_id=str(revision_id),
            ),
            actor_id,
        )

    with pytest.raises(PolicyAttachmentError):
        await service.attach_policy(
            agent_policy.id,
            PolicyAttachRequest(
                target_type=AttachmentTargetType.agent_revision,
                target_id=str(revision_id),
                policy_version_id=uuid4(),
            ),
            actor_id,
        )

    effective = await service.get_effective_policy(agent_id, workspace_id)
    attachments = await service.list_attachments(agent_policy.id)
    bundle = await service.get_enforcement_bundle(agent_id, workspace_id)
    cached_bundle = await service.get_enforcement_bundle(agent_id, workspace_id)
    visibility = await service.get_visibility_filter(agent_id, workspace_id)

    assert attachments.total == 1
    assert effective.conflicts[0].resolution == "more_specific_scope_wins"
    assert bundle.fingerprint == cached_bundle.fingerprint
    assert len(repository.bundle_cache) == 1
    assert visibility.agent_patterns == ["finance:*"]
    assert visibility.tool_patterns == ["tools:*"]

    agent_index_key = f"policy:bundle_keys:{agent_id}"
    revision_index_key = f"policy:bundle_keys:revision:{revision_id}"
    cache_key = next(iter(memory.sets[agent_index_key]))
    assert cache_key in memory.strings
    assert memory.sets[revision_index_key] == {cache_key}

    await service.invalidate_bundle_by_revision(str(revision_id))
    assert revision_index_key not in memory.sets
    assert cache_key not in memory.strings

    bundle_after_invalidation = await service.get_enforcement_bundle(agent_id, workspace_id)
    replacement_cache_key = next(iter(memory.sets[agent_index_key]))
    assert bundle_after_invalidation.fingerprint == bundle.fingerprint

    await service.invalidate_bundle(agent_id)
    assert replacement_cache_key not in memory.strings
    assert agent_index_key not in memory.sets

    await service.detach_policy(agent_policy.id, agent_attachment.id)
    assert (await service.list_attachments(agent_policy.id)).total == 0
    with pytest.raises(PolicyAttachmentError):
        await service.detach_policy(agent_policy.id, uuid4())

    default_visibility_service, _, _ = build_service(workspace_ids={workspace_id})
    default_visibility = await default_visibility_service.get_visibility_filter(
        agent_id,
        workspace_id,
    )
    assert default_visibility.agent_patterns == []
    assert default_visibility.tool_patterns == []


@pytest.mark.asyncio
async def test_policy_service_records_context_maturity_and_private_helpers() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    actor_id = uuid4()
    _memory, redis_client = build_fake_redis()
    registry = RegistryPolicyStub()
    service, repository, producer = build_service(
        workspace_ids={workspace_id},
        registry_service=registry,
        redis_client=redis_client,
    )

    global_policy = await service.create_policy(
        build_policy_create(
            scope_type=PolicyScopeType.global_scope,
            rules=build_rules(
                maturity_gate_rules=[
                    MaturityGateRuleSchema(
                        min_maturity_level=2,
                        capability_patterns=["finance:wire", "finance:read"],
                    )
                ]
            ),
        ),
        actor_id,
    )
    context_policy = await service.create_policy(
        build_policy_create(
            workspace_id=workspace_id,
            rules=build_rules(
                allowed_classifications=["internal"],
                allowed_agent_fqns=["finance:lead"],
            ),
        ),
        actor_id,
    )
    assert global_policy.id is not None
    assert context_policy.id is not None

    blocked = await service.create_blocked_record(
        agent_id=agent_id,
        agent_fqn="finance:agent",
        enforcement_component=EnforcementComponent.tool_gateway,
        action_type="tool_invocation",
        target="finance:wire",
        block_reason="permission_denied",
        workspace_id=workspace_id,
        execution_id=None,
        policy_rule_ref={"tool_fqn": "finance:wire"},
    )
    blocked_listing = await service.list_blocked_action_records(
        agent_id=agent_id,
        enforcement_component=EnforcementComponent.tool_gateway,
        workspace_id=workspace_id,
        execution_id=None,
        since=None,
        page=1,
        page_size=10,
    )
    fetched_blocked = await service.get_blocked_action_record(blocked.id)
    maturity_levels = await service.get_maturity_gates()
    active_context = await service.get_active_context_policies(workspace_id, "finance:agent")
    await service.publish_allowed_event(
        agent_id=agent_id,
        agent_fqn="finance:agent",
        target="finance:read",
        workspace_id=workspace_id,
        execution_id=None,
    )

    assert blocked_listing.total == 1
    assert fetched_blocked.id == blocked.id
    assert maturity_levels.levels[0].capabilities == ["finance:read", "finance:wire"]
    assert active_context[0]["allowed_classifications"] == ["internal"]
    assert producer.events[-1]["event_type"] == "policy.gate.allowed"

    await redis_client.set("policy:bundle:array", b"[1, 2, 3]")
    assert await service._redis_get_json("policy:bundle:array") is None
    await service._redis_set_json("policy:bundle:dict", {"ok": True}, ttl=30)
    assert await service._redis_get_json("policy:bundle:dict") == {"ok": True}

    with pytest.raises(PolicyNotFoundError):
        await service.get_blocked_action_record(uuid4())

    policy = build_policy()
    repository.policies[policy.id] = policy
    repository.versions_by_policy[policy.id] = []
    with pytest.raises(PolicyAttachmentError):
        await service.attach_policy(
            policy.id,
            PolicyAttachRequest(
                target_type=AttachmentTargetType.workspace,
                target_id=str(workspace_id),
            ),
            actor_id,
        )


@pytest.mark.asyncio
async def test_policy_service_private_resolution_and_attachment_validation_branches() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    revision_id = uuid4()

    no_registry_service, _, _ = build_service(
        workspace_ids={workspace_id},
        registry_service=None,
    )
    assert (
        await no_registry_service._resolve_agent_revision_id(agent_id, workspace_id)
        == str(agent_id)
    )

    class LegacyRegistry:
        async def get_agent(self, current_workspace_id, current_agent_id):
            assert current_workspace_id == workspace_id
            assert current_agent_id == agent_id
            return SimpleNamespace(current_revision=SimpleNamespace(id=revision_id))

    legacy_service, _, _ = build_service(
        workspace_ids={workspace_id},
        registry_service=LegacyRegistry(),
    )
    assert (
        await legacy_service._resolve_agent_revision_id(agent_id, workspace_id)
        == str(revision_id)
    )

    class RepoOnlyRegistry:
        def __init__(self) -> None:
            self.repository = SimpleNamespace()

        async def get_latest_revision(self, current_agent_id):
            assert current_agent_id == agent_id
            return SimpleNamespace(id=revision_id)

    repository_backed_registry = RepoOnlyRegistry()
    repository_backed_registry.repository.get_latest_revision = (
        repository_backed_registry.get_latest_revision
    )
    repository_service, _, _ = build_service(
        workspace_ids={workspace_id},
        registry_service=repository_backed_registry,
    )
    assert (
        await repository_service._resolve_agent_revision_id(agent_id, workspace_id)
        == str(revision_id)
    )

    with pytest.raises(PolicyAttachmentError):
        await repository_service._validate_attachment_target(
            AttachmentTargetType.global_scope,
            "unexpected",
            None,
        )

    with pytest.raises(PolicyAttachmentError):
        await repository_service._validate_attachment_target(
            AttachmentTargetType.workspace,
            None,
            workspace_id,
        )

    with pytest.raises(PolicyAttachmentError):
        await repository_service._validate_attachment_target(
            AttachmentTargetType.workspace,
            str(uuid4()),
            workspace_id,
        )

    validation_service, _, _ = build_service(
        workspace_ids={workspace_id},
        registry_service=RegistryPolicyStub(),
    )

    with pytest.raises(PolicyAttachmentError):
        await validation_service._validate_attachment_target(
            AttachmentTargetType.agent_revision,
            str(uuid4()),
            workspace_id,
        )
