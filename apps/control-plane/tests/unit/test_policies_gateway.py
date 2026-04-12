from __future__ import annotations

from platform.policies.gateway import MemoryWriteGateService, ToolGatewayService
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementBundle,
    MaturityGateRuleSchema,
    ValidationManifest,
)
from uuid import uuid4

import pytest

from tests.policies_support import MemoryServiceStub, ReasoningClientStub


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


class RegistryServiceStub:
    async def get_agent(
        self,
        workspace_id,
        agent_id,
        actor_id=None,
        requesting_agent_id=None,
    ):
        del workspace_id, agent_id, actor_id, requesting_agent_id
        return type("Profile", (), {"maturity_level": 1})()


class FailingPolicyService:
    async def get_enforcement_bundle(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("boom")


@pytest.mark.asyncio
async def test_tool_gateway_covers_allow_block_budget_and_fail_safe() -> None:
    bundle = EnforcementBundle(
        fingerprint="f" * 64,
        allowed_tool_patterns=["finance:*"],
        denied_tool_patterns=["finance:wire"],
        allowed_purposes=["analysis"],
        budget_limits=BudgetLimitsSchema(max_tool_invocations_per_execution=1),
        maturity_gate_rules=[
            MaturityGateRuleSchema(
                min_maturity_level=2,
                capability_patterns=["finance:wire"],
            )
        ],
        log_allowed_tools=["finance:read"],
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    )
    policy_service = PolicyServiceStub(bundle)
    registry_service = RegistryServiceStub()
    gateway = ToolGatewayService(
        policy_service=policy_service,
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=ReasoningClientStub(
            remaining_by_execution={uuid4(): {"remaining_tool_invocations": 0}}
        ),
        registry_service=registry_service,
    )
    workspace_id = uuid4()
    blocked_execution_id = next(iter(gateway.reasoning_client.remaining_by_execution))

    denied = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:wire",
        "analysis",
        uuid4(),
        workspace_id,
        None,
    )
    budget_block = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "analysis",
        blocked_execution_id,
        workspace_id,
        None,
    )
    allowed = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "analysis",
        uuid4(),
        workspace_id,
        None,
    )

    assert denied.allowed is False
    assert denied.block_reason == "permission_denied"
    assert budget_block.allowed is False
    assert budget_block.block_reason == "budget_exceeded"
    assert allowed.allowed is True
    assert len(policy_service.blocked_calls) == 2
    assert len(policy_service.allowed_calls) == 1

    fail_safe = await ToolGatewayService(
        policy_service=FailingPolicyService(),  # type: ignore[arg-type]
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=None,
        registry_service=None,
    ).validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "analysis",
        None,
        workspace_id,
        None,
    )
    assert fail_safe.allowed is False
    assert fail_safe.block_reason == "policy_resolution_failure"


@pytest.mark.asyncio
async def test_memory_write_gate_covers_namespace_rate_limit_and_contradictions() -> None:
    bundle = EnforcementBundle(
        fingerprint="f" * 64,
        allowed_tool_patterns=[],
        denied_tool_patterns=[],
        allowed_namespaces=["finance"],
        budget_limits=BudgetLimitsSchema(max_memory_writes_per_minute=2),
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    )
    policy_service = PolicyServiceStub(bundle)
    from tests.policies_support import build_fake_redis

    _memory, redis_client = build_fake_redis()
    policy_service.redis_client = redis_client
    memory_service = MemoryServiceStub(
        known_namespaces={"finance"},
        contradictory_hashes={("hash-3", "finance")},
    )
    gateway = MemoryWriteGateService(policy_service=policy_service, memory_service=memory_service)
    workspace_id = uuid4()

    first = await gateway.validate_memory_write(
        uuid4(), "finance:agent", "finance", "hash-1", workspace_id, None
    )
    second = await gateway.validate_memory_write(
        uuid4(), "finance:agent", "finance", "hash-2", workspace_id, None
    )
    third = await gateway.validate_memory_write(
        uuid4(), "finance:agent", "finance", "hash-3", workspace_id, None
    )
    denied_namespace = await gateway.validate_memory_write(
        uuid4(), "finance:agent", "hr", "hash-4", workspace_id, None
    )

    assert first.allowed is True
    assert second.allowed is True
    assert third.allowed is False
    assert third.block_reason in {"rate_limit_exceeded", "contradiction_detected"}
    assert denied_namespace.allowed is False
    assert denied_namespace.block_reason == "namespace_unauthorized"
