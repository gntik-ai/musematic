from __future__ import annotations

from platform.policies.gateway import MemoryWriteGateService, ToolGatewayService
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementBundle,
    MaturityGateRuleSchema,
    SanitizationResult,
    ValidationManifest,
)
from uuid import uuid4

import pytest

from tests.policies_support import MemoryServiceStub


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
    def __init__(self, maturity_level: int) -> None:
        self.maturity_level = maturity_level

    async def get_agent(
        self,
        workspace_id,
        agent_id,
        actor_id=None,
        requesting_agent_id=None,
    ):
        del workspace_id, agent_id, actor_id, requesting_agent_id
        return type("Profile", (), {"maturity_level": self.maturity_level})()


class RedisBudgetResult:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed


class RedisBudgetClient:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    async def decrement_budget(self, execution_id, component, dimension, amount):
        del execution_id, component, dimension, amount
        return RedisBudgetResult(self.allowed)


class SanitizerStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def sanitize(self, output: str, **kwargs) -> SanitizationResult:
        self.calls.append({"output": output, **kwargs})
        return SanitizationResult(
            output="[redacted]",
            redaction_count=1,
            redacted_types=["api_key"],
        )


class FailingPolicyService:
    redis_client = None

    async def get_enforcement_bundle(self, *args, **kwargs):
        del args, kwargs
        raise RuntimeError("boom")


def build_bundle(**overrides):
    payload = {
        "fingerprint": "f" * 64,
        "allowed_tool_patterns": ["finance:*"],
        "denied_tool_patterns": [],
        "allowed_purposes": [],
        "denied_purposes": [],
        "allowed_namespaces": ["finance"],
        "budget_limits": BudgetLimitsSchema(),
        "maturity_gate_rules": [],
        "safety_rules": [],
        "log_allowed_tools": [],
        "manifest": ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    }
    payload.update(overrides)
    return EnforcementBundle(**payload)


@pytest.mark.asyncio
async def test_tool_gateway_covers_maturity_purpose_safety_and_permission_paths() -> None:
    workspace_id = uuid4()
    execution_id = uuid4()

    maturity_gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(
            build_bundle(
                allowed_tool_patterns=["finance:*"],
                maturity_gate_rules=[
                    MaturityGateRuleSchema(
                        min_maturity_level=2,
                        capability_patterns=["finance:wire"],
                    )
                ],
            )
        ),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=RegistryServiceStub(maturity_level=1),
    )
    maturity_block = await maturity_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:wire",
        "analysis",
        execution_id,
        workspace_id,
        None,
    )
    assert maturity_block.block_reason == "maturity_level_insufficient"

    denied_purpose_gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(
            build_bundle(
                allowed_tool_patterns=["finance:*"],
                denied_purposes=["trading"],
            )
        ),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )
    denied_purpose = await denied_purpose_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "trading",
        execution_id,
        workspace_id,
        None,
    )
    assert denied_purpose.block_reason == "purpose_mismatch"

    allowed_purpose_gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(
            build_bundle(
                allowed_tool_patterns=["finance:*"],
                allowed_purposes=["analysis"],
            )
        ),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )
    allowed_purpose_block = await allowed_purpose_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "trading",
        execution_id,
        workspace_id,
        None,
    )
    assert allowed_purpose_block.block_reason == "purpose_mismatch"

    safety_gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(
            build_bundle(
                allowed_tool_patterns=["finance:*"],
                safety_rules=[{"id": "no-wire", "pattern": "wire"}],
            )
        ),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )
    safety_block = await safety_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:wire",
        "analysis",
        execution_id,
        workspace_id,
        None,
    )
    assert safety_block.block_reason == "safety_rule_blocked"

    permission_gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle(allowed_tool_patterns=[])),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )
    permission_block = await permission_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "analysis",
        execution_id,
        workspace_id,
        None,
    )
    assert permission_block.block_reason == "permission_denied"


@pytest.mark.asyncio
async def test_tool_gateway_uses_redis_budget_and_sanitizer_and_memory_gate_extra_paths() -> None:
    workspace_id = uuid4()
    execution_id = uuid4()

    budget_policy = PolicyServiceStub(
        build_bundle(
            allowed_tool_patterns=["finance:*"],
            budget_limits=BudgetLimitsSchema(max_tool_invocations_per_execution=1),
        )
    )
    budget_policy.redis_client = RedisBudgetClient(allowed=False)
    sanitizer = SanitizerStub()
    gateway = ToolGatewayService(
        policy_service=budget_policy,
        sanitizer=sanitizer,
        reasoning_client=None,
        registry_service=None,
    )

    budget_block = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "finance:read",
        "analysis",
        execution_id,
        workspace_id,
        None,
    )
    sanitized = await gateway.sanitize_tool_output(
        "apiKey=123",
        uuid4(),
        "finance:agent",
        "finance:read",
        execution_id,
        None,
        workspace_id=workspace_id,
    )

    assert budget_block.block_reason == "budget_exceeded"
    assert sanitized.output == "[redacted]"
    assert sanitizer.calls[0]["tool_fqn"] == "finance:read"

    namespace_gateway = MemoryWriteGateService(
        policy_service=PolicyServiceStub(build_bundle(allowed_namespaces=["finance"])),
        memory_service=MemoryServiceStub(known_namespaces=set()),
    )
    namespace_block = await namespace_gateway.validate_memory_write(
        uuid4(),
        "finance:agent",
        "finance",
        "hash-1",
        workspace_id,
        None,
    )
    assert namespace_block.block_reason == "namespace_not_found"

    contradiction_gateway = MemoryWriteGateService(
        policy_service=PolicyServiceStub(build_bundle(allowed_namespaces=["finance"])),
        memory_service=MemoryServiceStub(
            known_namespaces={"finance"},
            contradictory_hashes={("hash-2", "finance")},
        ),
    )
    contradiction_block = await contradiction_gateway.validate_memory_write(
        uuid4(),
        "finance:agent",
        "finance",
        "hash-2",
        workspace_id,
        None,
    )
    assert contradiction_block.block_reason == "contradiction_detected"

    failure_block = await MemoryWriteGateService(
        policy_service=FailingPolicyService(),  # type: ignore[arg-type]
        memory_service=None,
    ).validate_memory_write(
        uuid4(),
        "finance:agent",
        "finance",
        "hash-3",
        workspace_id,
        None,
    )
    assert failure_block.block_reason == "policy_resolution_failure"
