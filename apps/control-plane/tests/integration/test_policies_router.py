from __future__ import annotations

from platform.policies.models import AttachmentTargetType, EnforcementComponent, PolicyScopeType
from platform.policies.schemas import MaturityGateRuleSchema, PolicyAttachRequest
from platform.policies.service import PolicyService
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from tests.auth_support import RecordingProducer
from tests.policies_support import (
    InMemoryPolicyRepository,
    RegistryPolicyStub,
    WorkspacesPolicyStub,
    build_fake_redis,
    build_policy_create,
    build_policy_service_app,
    build_policy_settings,
    build_rules,
)


@pytest.mark.asyncio
async def test_policy_router_exposes_auxiliary_endpoints() -> None:
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
        }
    )
    registry.repository.revisions_by_id[revision_id] = SimpleNamespace(id=revision_id)
    registry.repository.latest_revision_by_agent[agent_id] = SimpleNamespace(id=revision_id)
    service = PolicyService(
        repository=InMemoryPolicyRepository(),
        settings=build_policy_settings(),
        producer=RecordingProducer(),
        redis_client=redis_client,
        registry_service=registry,
        workspaces_service=WorkspacesPolicyStub(workspace_ids={workspace_id}),
    )
    app = build_policy_service_app(service)

    global_policy = await service.create_policy(
        build_policy_create(
            scope_type=PolicyScopeType.global_scope,
            rules=build_rules(
                maturity_gate_rules=[
                    MaturityGateRuleSchema(
                        min_maturity_level=2,
                        capability_patterns=["finance:wire"],
                    )
                ]
            ),
        ),
        actor_id,
    )
    workspace_policy = await service.create_policy(
        build_policy_create(workspace_id=workspace_id),
        actor_id,
    )
    await service.attach_policy(
        global_policy.id,
        PolicyAttachRequest(target_type=AttachmentTargetType.global_scope, target_id=None),
        actor_id,
    )
    attachment = await service.attach_policy(
        workspace_policy.id,
        PolicyAttachRequest(
            target_type=AttachmentTargetType.workspace,
            target_id=str(workspace_id),
        ),
        actor_id,
    )
    await service.get_enforcement_bundle(agent_id, workspace_id)
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

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        policy_response = await client.get(f"/api/v1/policies/{workspace_policy.id}")
        attachments_response = await client.get(
            f"/api/v1/policies/{workspace_policy.id}/attachments"
        )
        blocked_list = await client.get(
            "/api/v1/policies/blocked-actions",
            params={"workspace_id": str(workspace_id)},
        )
        blocked_one = await client.get(f"/api/v1/policies/blocked-actions/{blocked.id}")
        maturity = await client.get("/api/v1/policies/maturity-gates")
        invalidated = await client.post(f"/api/v1/policies/bundle/{agent_id}/invalidate")

    assert policy_response.status_code == 200
    assert policy_response.json()["id"] == str(workspace_policy.id)
    assert attachments_response.json()["items"][0]["id"] == str(attachment.id)
    assert blocked_list.json()["total"] == 1
    assert blocked_one.json()["id"] == str(blocked.id)
    assert maturity.json()["levels"][0]["capabilities"] == ["finance:wire"]
    assert invalidated.status_code == 204
    assert not memory.strings
