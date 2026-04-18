from __future__ import annotations

from platform.common.config import PlatformSettings
from platform.policies.gateway import ToolGatewayService
from platform.policies.schemas import BudgetLimitsSchema, EnforcementBundle, ValidationManifest
from types import SimpleNamespace
from uuid import uuid4

import pytest


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


class RegistryVisibilityStub:
    def __init__(self, tool_patterns: list[str]) -> None:
        self.tool_patterns = tool_patterns

    async def resolve_effective_visibility(self, agent_id, workspace_id):
        del agent_id, workspace_id
        return SimpleNamespace(agent_patterns=[], tool_patterns=list(self.tool_patterns))


def _bundle() -> EnforcementBundle:
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
        log_allowed_tools=["tools:*"],
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    )


@pytest.mark.asyncio
async def test_tool_gateway_allows_visible_tool_before_policy_checks() -> None:
    policy_service = PolicyServiceStub(_bundle())
    gateway = ToolGatewayService(
        policy_service=policy_service,
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=None,
        registry_service=RegistryVisibilityStub(["tools:search:*"]),
        settings=PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=True),
    )

    result = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "tools:search:web",
        "analysis",
        None,
        uuid4(),
        None,
    )

    assert result.allowed is True
    assert policy_service.blocked_calls == []


@pytest.mark.asyncio
async def test_tool_gateway_blocks_invisible_tool_with_distinct_reason() -> None:
    policy_service = PolicyServiceStub(_bundle())
    gateway = ToolGatewayService(
        policy_service=policy_service,
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=None,
        registry_service=RegistryVisibilityStub(["tools:search:*"]),
        settings=PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=True),
    )

    result = await gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        "tools:finance:wire-transfer",
        "analysis",
        None,
        uuid4(),
        None,
    )

    assert result.allowed is False
    assert result.block_reason == "visibility_denied"
    assert policy_service.blocked_calls[-1]["block_reason"] == "visibility_denied"


@pytest.mark.asyncio
async def test_tool_gateway_skips_visibility_check_when_flag_is_off_or_settings_are_missing(
) -> None:
    invisible_tool = "tools:finance:wire-transfer"

    disabled_policy_service = PolicyServiceStub(_bundle())
    disabled_gateway = ToolGatewayService(
        policy_service=disabled_policy_service,
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=None,
        registry_service=RegistryVisibilityStub(["tools:search:*"]),
        settings=PlatformSettings(VISIBILITY_ZERO_TRUST_ENABLED=False),
    )
    disabled_result = await disabled_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        invisible_tool,
        "analysis",
        None,
        uuid4(),
        None,
    )

    legacy_policy_service = PolicyServiceStub(_bundle())
    legacy_gateway = ToolGatewayService(
        policy_service=legacy_policy_service,
        sanitizer=None,  # type: ignore[arg-type]
        reasoning_client=None,
        registry_service=RegistryVisibilityStub(["tools:search:*"]),
        settings=None,
    )
    legacy_result = await legacy_gateway.validate_tool_invocation(
        uuid4(),
        "finance:agent",
        invisible_tool,
        "analysis",
        None,
        uuid4(),
        None,
    )

    assert disabled_result.allowed is True
    assert legacy_result.allowed is True
