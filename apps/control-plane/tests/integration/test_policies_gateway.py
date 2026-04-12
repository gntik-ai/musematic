from __future__ import annotations

from platform.policies.gateway import ToolGatewayService
from platform.policies.models import AttachmentTargetType, PolicyScopeType
from platform.policies.sanitizer import OutputSanitizer
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementRuleSchema,
    MaturityGateRuleSchema,
    PurposeScopeSchema,
)
from platform.policies.service import PolicyService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.policies_support import (
    InMemoryPolicyRepository,
    ReasoningClientStub,
    RegistryPolicyStub,
    WorkspacesPolicyStub,
    build_attachment,
    build_fake_redis,
    build_policy,
    build_policy_settings,
    build_rules,
    build_version,
)


@pytest.mark.asyncio
async def test_tool_gateway_flow_blocks_and_allows_with_real_policy_service() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    revision_id = uuid4()
    execution_id = uuid4()
    rules = build_rules(
        enforcement_rules=[
            EnforcementRuleSchema(
                id="allow-finance",
                action="allow",
                tool_patterns=["finance:*"],
                log_allowed_invocations=True,
            ),
            EnforcementRuleSchema(
                id="deny-wire",
                action="deny",
                tool_patterns=["finance:wire"],
            ),
        ],
        purpose_scopes=[
            PurposeScopeSchema(
                id="purpose",
                allowed_purposes=["analysis"],
                denied_purposes=["trading"],
            )
        ],
        maturity_gate_rules=[
            MaturityGateRuleSchema(
                min_maturity_level=2,
                capability_patterns=["finance:wire"],
            )
        ],
        budget_limits=BudgetLimitsSchema(max_tool_invocations_per_execution=1),
    )
    policy = build_policy(workspace_id=workspace_id, scope_type=PolicyScopeType.workspace)
    version = build_version(policy_id=policy.id, rules=rules)
    policy.current_version = version
    policy.current_version_id = version.id
    policy.versions = [version]
    repository = InMemoryPolicyRepository(
        policies={policy.id: policy},
        versions_by_policy={policy.id: [version]},
        version_by_id={version.id: version},
    )
    await repository.create_attachment(
        build_attachment(
            policy=policy,
            version=version,
            target_type=AttachmentTargetType.workspace,
            target_id=str(workspace_id),
        )
    )
    _memory, redis_client = build_fake_redis()
    registry = RegistryPolicyStub(
        agents={
            agent_id: SimpleNamespace(
                id=agent_id,
                maturity_level=1,
                current_revision=SimpleNamespace(id=revision_id),
            )
        }
    )
    registry.repository.latest_revision_by_agent[agent_id] = SimpleNamespace(id=revision_id)
    reasoning = ReasoningClientStub(
        remaining_by_execution={execution_id: {"remaining_tool_invocations": 0}}
    )
    service = PolicyService(
        repository=repository,
        settings=build_policy_settings(),
        producer=RecordingProducer(),
        redis_client=redis_client,
        registry_service=registry,
        workspaces_service=WorkspacesPolicyStub(workspace_ids={workspace_id}),
        reasoning_client=reasoning,
    )
    gateway = ToolGatewayService(
        policy_service=service,
        sanitizer=OutputSanitizer(repository),
        reasoning_client=reasoning,
        registry_service=registry,
    )

    denied = await gateway.validate_tool_invocation(
        agent_id,
        "finance:agent",
        "finance:wire",
        "analysis",
        None,
        workspace_id,
        None,
    )
    purpose_block = await gateway.validate_tool_invocation(
        agent_id,
        "finance:agent",
        "finance:read",
        "trading",
        None,
        workspace_id,
        None,
    )
    budget_block = await gateway.validate_tool_invocation(
        agent_id,
        "finance:agent",
        "finance:read",
        "analysis",
        execution_id,
        workspace_id,
        None,
    )

    assert denied.block_reason == "permission_denied"
    assert purpose_block.block_reason == "purpose_mismatch"
    assert budget_block.block_reason == "budget_exceeded"
    assert len(repository.blocked_records) == 3
