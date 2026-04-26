from __future__ import annotations

from decimal import Decimal
from platform.cost_governance.constants import BLOCK_REASON_COST_BUDGET
from platform.policies.gateway import MemoryWriteGateService, ToolGatewayService, _decimalish
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementBundle,
    MaturityGateRuleSchema,
    SanitizationResult,
    ValidationManifest,
)
from platform.privacy_compliance.dlp.scanner import DLPEventInput, DLPScanResult
from platform.privacy_compliance.exceptions import ToolOutputBlocked
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.policies_support import MemoryServiceStub, build_fake_redis


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


class DLPServiceStub:
    def __init__(self, blocked: bool) -> None:
        self.blocked = blocked
        self.emitted: list[DLPEventInput] = []

    async def scan_and_apply(self, output: str, workspace_id) -> DLPScanResult:
        del output
        return DLPScanResult(
            output_text="[dlp]",
            blocked=self.blocked,
            events=[
                DLPEventInput(
                    rule_id=uuid4(),
                    rule_name="internal_project_alpha",
                    classification="confidential",
                    action_taken="block",
                    match_summary="confidential:internal_project_alpha",
                    workspace_id=workspace_id,
                )
            ],
        )

    async def emit_events(self, events: list[DLPEventInput], *, execution_id=None):
        del execution_id
        self.emitted.extend(events)
        return events


class SessionCommitStub:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class ResidencyServiceStub:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object]] = []

    async def enforce(self, workspace_id, origin_region) -> None:
        self.calls.append((workspace_id, origin_region))


class VisibilityRegistryStub:
    def __init__(
        self,
        *,
        tool_patterns: list[str],
        mcp_servers: list[str] | None = None,
        maturity_level: int = 3,
    ) -> None:
        self.tool_patterns = tool_patterns
        self.mcp_servers = mcp_servers or []
        self.maturity_level = maturity_level

    async def resolve_effective_visibility(self, agent_id, workspace_id):
        del agent_id, workspace_id
        return SimpleNamespace(tool_patterns=self.tool_patterns)

    async def get_agent(
        self,
        workspace_id,
        agent_id,
        actor_id=None,
        requesting_agent_id=None,
    ):
        del workspace_id, agent_id, actor_id, requesting_agent_id
        return SimpleNamespace(
            maturity_level=self.maturity_level,
            mcp_servers=self.mcp_servers,
        )


class BudgetCheckServiceStub:
    def __init__(self, *, allowed: bool) -> None:
        self.allowed = allowed
        self.calls: list[tuple[object, Decimal, object]] = []

    async def check_budget_for_start(self, workspace_id, estimate, *, override_token=None):
        self.calls.append((workspace_id, estimate, override_token))
        return SimpleNamespace(
            allowed=self.allowed,
            budget_cents=100,
            projected_spend_cents=Decimal("125"),
            override_endpoint="/api/v1/costs/workspaces/budget/override",
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


def _cost_settings() -> SimpleNamespace:
    return SimpleNamespace(
        privacy_compliance=SimpleNamespace(
            dlp_enabled=False,
            residency_enforcement_enabled=True,
        ),
        visibility=SimpleNamespace(zero_trust_enabled=True),
        feature_cost_hard_caps=True,
    )


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
async def test_tool_gateway_cost_visibility_mcp_and_residency_paths() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    residency = ResidencyServiceStub()
    budget = BudgetCheckServiceStub(allowed=False)
    session = SimpleNamespace(
        origin_region="eu-west",
        estimated_tool_cost_cents="125",
        cost_override_token="override-token",
    )
    gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle(allowed_tool_patterns=["finance:*"])),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=VisibilityRegistryStub(tool_patterns=["finance:*"]),
        settings=_cost_settings(),
        residency_service=residency,
        budget_service=budget,
    )

    blocked = await gateway.validate_tool_invocation(
        agent_id,
        "finance:agent",
        "finance:read",
        "analysis",
        None,
        workspace_id,
        session,
    )
    allowed_budget = BudgetCheckServiceStub(allowed=True)
    allowed = await ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle(allowed_tool_patterns=["finance:*"])),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=VisibilityRegistryStub(tool_patterns=["finance:*"]),
        settings=_cost_settings(),
        residency_service=ResidencyServiceStub(),
        budget_service=allowed_budget,
    ).validate_tool_invocation(
        agent_id,
        "finance:agent",
        "finance:read",
        "analysis",
        None,
        workspace_id,
        SimpleNamespace(cost_estimate_cents="25"),
    )
    visibility_block = await ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle(allowed_tool_patterns=["finance:*"])),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=VisibilityRegistryStub(tool_patterns=["tools:*"]),
        settings=_cost_settings(),
        budget_service=BudgetCheckServiceStub(allowed=True),
    ).validate_tool_invocation(
        agent_id,
        "finance:agent",
        "finance:read",
        "analysis",
        None,
        workspace_id,
        SimpleNamespace(estimated_cost_cents="1"),
    )
    mcp_block = await ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle(allowed_tool_patterns=["mcp:*"])),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    ).validate_tool_invocation(
        agent_id,
        "finance:agent",
        "mcp:server-a:tool",
        "analysis",
        None,
        workspace_id,
        None,
    )
    mcp_allowed = await ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle(allowed_tool_patterns=["mcp:*"])),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=VisibilityRegistryStub(
            tool_patterns=["mcp:*"],
            mcp_servers=["server-a"],
        ),
    ).validate_tool_invocation(
        agent_id,
        "finance:agent",
        "mcp:server-a:tool",
        "analysis",
        None,
        workspace_id,
        None,
    )
    malformed_ref = await gateway._check_mcp_server_membership(
        agent_id,
        workspace_id,
        "mcp:malformed",
    )

    assert blocked.block_reason == BLOCK_REASON_COST_BUDGET
    assert blocked.policy_rule_ref == {
        "budget_cents": 100,
        "projected_spend_cents": "125",
        "override_endpoint": "/api/v1/costs/workspaces/budget/override",
    }
    assert budget.calls == [(workspace_id, Decimal("125"), "override-token")]
    assert residency.calls == [(workspace_id, "eu-west")]
    assert allowed.allowed is True
    assert allowed_budget.calls[0][1] == Decimal("25")
    assert visibility_block.block_reason == "visibility_denied"
    assert mcp_block.block_reason == "permission_denied"
    assert mcp_allowed.allowed is True
    assert malformed_ref is None


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


@pytest.mark.asyncio
async def test_memory_gate_redis_rate_limit_success_path_and_decimal_helper() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    _memory, redis_client = build_fake_redis()
    policy = PolicyServiceStub(
        build_bundle(
            allowed_namespaces=["finance*"],
            budget_limits=BudgetLimitsSchema(max_memory_writes_per_minute=2),
        )
    )
    policy.redis_client = redis_client
    gateway = MemoryWriteGateService(
        policy_service=policy,
        memory_service=None,
    )

    first = await gateway.validate_memory_write(
        agent_id,
        "finance:agent",
        "finance-notes",
        "hash-1",
        workspace_id,
        None,
    )
    second = await gateway.validate_memory_write(
        agent_id,
        "finance:agent",
        "finance-notes",
        "hash-2",
        workspace_id,
        None,
    )
    third = await gateway.validate_memory_write(
        agent_id,
        "finance:agent",
        "finance-notes",
        "hash-3",
        workspace_id,
        None,
    )

    assert first.allowed is True
    assert second.allowed is True
    assert third.block_reason == "rate_limit_exceeded"
    assert _decimalish(None) == Decimal("0")
    assert _decimalish("3.5") == Decimal("3.5")


@pytest.mark.asyncio
async def test_gateway_allows_non_matching_private_checks_and_no_redis_memory_limit() -> None:
    workspace_id = uuid4()
    agent_id = uuid4()
    bundle = build_bundle(
        allowed_tool_patterns=["ops:*"],
        maturity_gate_rules=[
            MaturityGateRuleSchema(
                min_maturity_level=1,
                capability_patterns=["finance:*"],
            )
        ],
    )
    gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(bundle),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=VisibilityRegistryStub(
            tool_patterns=["finance:*"],
            mcp_servers=["server-a"],
            maturity_level=3,
        ),
        settings=_cost_settings(),
        budget_service=BudgetCheckServiceStub(allowed=True),
    )

    assert gateway._permission_ref(bundle, "finance:read") is None
    assert await gateway._check_mcp_server_membership(
        agent_id,
        workspace_id,
        "mcp:server-b:tool",
    ) is None
    assert await ToolGatewayService(
        policy_service=PolicyServiceStub(bundle),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )._check_maturity(agent_id, workspace_id, "finance:read", bundle) == {
        "required_level": 1
    }
    assert await gateway._check_maturity(agent_id, workspace_id, "finance:read", bundle) is None

    budget_policy = PolicyServiceStub(
        build_bundle(
            allowed_tool_patterns=["finance:*"],
            budget_limits=BudgetLimitsSchema(max_tool_invocations_per_execution=1),
        )
    )
    budget_policy.redis_client = RedisBudgetClient(allowed=True)
    assert await ToolGatewayService(
        policy_service=budget_policy,
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )._check_budget(budget_policy.bundle, uuid4()) is None
    budget_policy.redis_client = object()
    assert await ToolGatewayService(
        policy_service=budget_policy,
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
    )._check_budget(budget_policy.bundle, uuid4()) is None
    assert await gateway._check_workspace_cost_budget(
        workspace_id,
        SimpleNamespace(estimated_cost_cents="0"),
        None,
    ) is None
    assert gateway._check_safety(
        [{"pattern": ""}, {"id": "wire", "pattern": "wire"}],
        "finance:read",
    ) is None

    memory_policy = PolicyServiceStub(
        build_bundle(
            allowed_namespaces=["finance"],
            budget_limits=BudgetLimitsSchema(max_memory_writes_per_minute=1),
        )
    )
    allowed = await MemoryWriteGateService(
        policy_service=memory_policy,
        memory_service=None,
    ).validate_memory_write(
        agent_id,
        "finance:agent",
        "finance",
        "hash",
        workspace_id,
        None,
    )

    assert allowed.allowed is True


@pytest.mark.asyncio
async def test_tool_gateway_commits_dlp_events_before_blocking() -> None:
    workspace_id = uuid4()
    execution_id = uuid4()
    dlp_service = DLPServiceStub(blocked=True)
    session = SessionCommitStub()
    gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle()),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
        dlp_service=dlp_service,
        settings=SimpleNamespace(privacy_compliance=SimpleNamespace(dlp_enabled=True)),
    )

    with pytest.raises(ToolOutputBlocked):
        await gateway.sanitize_tool_output(
            "Project Alpha",
            uuid4(),
            "finance:agent",
            "finance:read",
            execution_id,
            session,
            workspace_id=workspace_id,
        )

    assert session.commits == 1
    assert [event.match_summary for event in dlp_service.emitted] == [
        "confidential:internal_project_alpha"
    ]


@pytest.mark.asyncio
async def test_tool_gateway_applies_non_blocking_dlp_output() -> None:
    workspace_id = uuid4()
    dlp_service = DLPServiceStub(blocked=False)
    gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle()),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
        dlp_service=dlp_service,
        settings=SimpleNamespace(privacy_compliance=SimpleNamespace(dlp_enabled=True)),
    )

    sanitized = await gateway.sanitize_tool_output(
        "Project Alpha",
        uuid4(),
        "finance:agent",
        "finance:read",
        None,
        None,
        workspace_id=workspace_id,
    )

    assert sanitized.output == "[dlp]"
    assert [event.match_summary for event in dlp_service.emitted] == [
        "confidential:internal_project_alpha"
    ]


@pytest.mark.asyncio
async def test_tool_gateway_blocks_dlp_without_explicit_commit_handle() -> None:
    gateway = ToolGatewayService(
        policy_service=PolicyServiceStub(build_bundle()),
        sanitizer=SanitizerStub(),
        reasoning_client=None,
        registry_service=None,
        dlp_service=DLPServiceStub(blocked=True),
        settings=SimpleNamespace(privacy_compliance=SimpleNamespace(dlp_enabled=True)),
    )

    with pytest.raises(ToolOutputBlocked):
        await gateway.sanitize_tool_output(
            "Project Alpha",
            uuid4(),
            "finance:agent",
            "finance:read",
            None,
            object(),
            workspace_id=uuid4(),
        )
