from __future__ import annotations

from platform.policies.models import PolicyScopeType
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementBundle,
    EnforcementRuleSchema,
    PolicyCreate,
    PolicyRulesSchema,
    ValidationManifest,
    build_bundle_fingerprint,
)
from uuid import uuid4


def test_schema_normalization_bundle_sharding_and_lazy_exports() -> None:
    policy = PolicyCreate(
        name=" Finance Policy ",
        description="  desc  ",
        scope_type=PolicyScopeType.workspace,
        workspace_id=uuid4(),
        rules=PolicyRulesSchema(
            enforcement_rules=[
                EnforcementRuleSchema(
                    id="rule-1",
                    action="allow",
                    tool_patterns=[" finance:* ", " "],
                    applicable_step_types=[" tool_invocation ", "memory_write"],
                    log_allowed_invocations=True,
                )
            ],
            budget_limits=BudgetLimitsSchema(max_memory_writes_per_minute=3),
            allowed_namespaces=[" finance ", " "],
        ),
        change_summary="  init  ",
    )
    bundle = EnforcementBundle(
        fingerprint=build_bundle_fingerprint([uuid4(), uuid4()]),
        allowed_tool_patterns=["finance:*", "memory:*"],
        denied_tool_patterns=["finance:deny"],
        allowed_namespaces=["finance"],
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    )
    bundle.set_step_maps(
        allowed={"tool_invocation": ["finance:*"], "memory_write": ["memory:*"]},
        denied={"tool_invocation": ["finance:deny"]},
    )
    from platform.policies import get_policy_service

    shard = bundle.get_shard("memory_write")

    assert policy.name == "Finance Policy"
    assert policy.description == "desc"
    assert policy.change_summary == "init"
    assert policy.rules.enforcement_rules[0].tool_patterns == ["finance:*"]
    assert shard.allowed_tool_patterns == ["memory:*"]
    assert shard.denied_tool_patterns == []
    assert callable(get_policy_service)
