from __future__ import annotations

from platform.policies.compiler import GovernanceCompiler
from platform.policies.exceptions import PolicyCompilationError
from platform.policies.models import PolicyScopeType
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementRuleSchema,
    MaturityGateRuleSchema,
    PurposeScopeSchema,
)
from uuid import uuid4

import pytest

from tests.policies_support import attach_version_scope, build_rules, build_version


def test_compile_bundle_merges_precedence_and_builds_shards() -> None:
    compiler = GovernanceCompiler()
    global_version = attach_version_scope(
        build_version(
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="global-allow",
                        action="allow",
                        tool_patterns=["finance:*"],
                        applicable_step_types=["tool_invocation"],
                    )
                ],
                purpose_scopes=[
                    PurposeScopeSchema(
                        id="global-purpose",
                        allowed_purposes=["analysis"],
                        denied_purposes=["trading"],
                    )
                ],
            ),
        ),
        level=0,
        scope_type=PolicyScopeType.global_scope,
    )
    workspace_version = attach_version_scope(
        build_version(
            policy_id=global_version.policy_id,
            version_number=2,
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="workspace-deny",
                        action="deny",
                        tool_patterns=["finance:wire"],
                        applicable_step_types=["tool_invocation"],
                    ),
                    EnforcementRuleSchema(
                        id="memory-allow",
                        action="allow",
                        tool_patterns=["memory:*"],
                        applicable_step_types=["memory_write"],
                        log_allowed_invocations=True,
                    ),
                ],
                maturity_gate_rules=[
                    MaturityGateRuleSchema(
                        min_maturity_level=2,
                        capability_patterns=["finance:wire"],
                    )
                ],
                budget_limits=BudgetLimitsSchema(max_tool_invocations_per_execution=4),
                allowed_namespaces=["finance"],
            ),
        ),
        level=2,
        scope_type=PolicyScopeType.workspace,
        scope_target_id="workspace-1",
    )
    agent_version = attach_version_scope(
        build_version(
            policy_id=global_version.policy_id,
            version_number=3,
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="agent-allow",
                        action="allow",
                        tool_patterns=["finance:wire"],
                        applicable_step_types=["tool_invocation"],
                    )
                ]
            ),
        ),
        level=3,
        scope_type=PolicyScopeType.agent,
        scope_target_id="revision-1",
    )

    bundle = compiler.compile_bundle(
        [global_version, workspace_version, agent_version],
        uuid4(),
        uuid4(),
    )

    assert "finance:*" in bundle.allowed_tool_patterns
    assert "finance:wire" in bundle.allowed_tool_patterns
    assert bundle.budget_limits.max_tool_invocations_per_execution == 4
    assert bundle.allowed_namespaces == ["finance"]
    assert bundle.allowed_purposes == ["analysis"]
    assert bundle.denied_purposes == ["trading"]
    assert bundle.log_allowed_tools == ["memory:*"]
    assert bundle.maturity_gate_rules[0].min_maturity_level == 2
    assert bundle.manifest.conflicts[0].resolution == "more_specific_scope_wins"

    tool_shard = bundle.get_shard("tool_invocation")
    memory_shard = bundle.get_shard("memory_write")
    assert "finance:*" in tool_shard.allowed_tool_patterns
    assert "memory:*" not in tool_shard.allowed_tool_patterns
    assert memory_shard.allowed_tool_patterns == ["memory:*"]
    assert memory_shard.allowed_namespaces == ["finance"]


def test_compile_bundle_rejects_invalid_budget_and_empty_policy_set() -> None:
    compiler = GovernanceCompiler()
    invalid_version = attach_version_scope(
        build_version(
            rules={
                "budget_limits": {"max_tool_invocations_per_execution": -1},
                "enforcement_rules": [],
            }
        ),
        level=0,
        scope_type=PolicyScopeType.global_scope,
    )

    with pytest.raises(PolicyCompilationError):
        compiler.compile_bundle([], uuid4(), uuid4())

    with pytest.raises(PolicyCompilationError):
        compiler.compile_bundle([invalid_version], uuid4(), uuid4())


def test_tool_matches_supports_wildcards_and_exact_matches() -> None:
    assert GovernanceCompiler.tool_matches(["finance:*"], "finance:wire") is True
    assert GovernanceCompiler.tool_matches(["finance:wire"], "finance:wire") is True
    assert GovernanceCompiler.tool_matches(["finance:wire"], "finance:other") is False
