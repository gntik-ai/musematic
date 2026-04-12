from __future__ import annotations

from platform.policies.models import PolicyScopeType
from platform.policies.schemas import EnforcementRuleSchema
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
    build_policy_create,
    build_policy_service_app,
    build_policy_settings,
    build_rules,
)


@pytest.mark.asyncio
async def test_policy_composition_and_bundle_endpoints_honor_precedence() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    revision_id = uuid4()
    registry = RegistryPolicyStub(
        agents={
            agent_id: SimpleNamespace(
                id=agent_id,
                maturity_level=3,
                current_revision=SimpleNamespace(id=revision_id),
            )
        }
    )
    registry.repository.latest_revision_by_agent[agent_id] = SimpleNamespace(id=revision_id)
    registry.repository.revisions_by_id[revision_id] = SimpleNamespace(id=revision_id)
    repository = InMemoryPolicyRepository()
    service = PolicyService(
        repository=repository,
        settings=build_policy_settings(),
        producer=RecordingProducer(),
        redis_client=None,
        registry_service=registry,
        workspaces_service=WorkspacesPolicyStub(workspace_ids={workspace_id}),
    )
    app = build_policy_service_app(service)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        global_policy = await client.post(
            "/api/v1/policies",
            json=build_policy_create(
                scope_type=PolicyScopeType.global_scope,
                rules=build_rules(
                    enforcement_rules=[
                        EnforcementRuleSchema(
                            id="global-allow",
                            action="allow",
                            tool_patterns=["*"],
                        )
                    ]
                ),
            ).model_dump(mode="json"),
        )
        workspace_policy = await client.post(
            "/api/v1/policies",
            json=build_policy_create(
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
            ).model_dump(mode="json"),
        )
        agent_policy = await client.post(
            "/api/v1/policies",
            json=build_policy_create(
                workspace_id=workspace_id,
                rules=build_rules(
                    enforcement_rules=[
                        EnforcementRuleSchema(
                            id="agent-allow",
                            action="allow",
                            tool_patterns=["finance:wire"],
                        )
                    ]
                ),
            ).model_dump(mode="json"),
        )
        await client.post(
            f"/api/v1/policies/{global_policy.json()['id']}/attach",
            json={"target_type": "global", "target_id": None},
        )
        await client.post(
            f"/api/v1/policies/{workspace_policy.json()['id']}/attach",
            json={"target_type": "workspace", "target_id": str(workspace_id)},
        )
        attached_agent = await client.post(
            f"/api/v1/policies/{agent_policy.json()['id']}/attach",
            json={"target_type": "agent_revision", "target_id": str(revision_id)},
        )
        effective = await client.get(
            f"/api/v1/policies/effective/{agent_id}",
            params={"workspace_id": str(workspace_id)},
        )
        bundle = await client.get(
            f"/api/v1/policies/bundle/{agent_id}",
            params={"workspace_id": str(workspace_id), "step_type": "tool_invocation"},
        )
        await client.delete(
            f"/api/v1/policies/{agent_policy.json()['id']}/attach/{attached_agent.json()['id']}"
        )
        fallback = await client.get(
            f"/api/v1/policies/effective/{agent_id}",
            params={"workspace_id": str(workspace_id)},
        )

    assert effective.status_code == 200
    assert effective.json()["conflicts"][0]["resolution"] == "more_specific_scope_wins"
    assert any(
        item["rule"]["tool_patterns"] == ["finance:wire"]
        for item in effective.json()["resolved_rules"]
    )
    assert bundle.json()["allowed_tool_patterns"] == ["*", "finance:wire"]
    assert any(
        item["rule"]["tool_patterns"] == ["finance:wire"]
        for item in fallback.json()["resolved_rules"]
    )
