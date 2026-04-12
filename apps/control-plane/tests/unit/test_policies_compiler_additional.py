from __future__ import annotations

from platform.policies.compiler import GovernanceCompiler
from platform.policies.exceptions import PolicyCompilationError
from platform.policies.models import PolicyScopeType
from platform.policies.schemas import EnforcementBundle, EnforcementRuleSchema, ValidationManifest
from uuid import uuid4

import pytest

from tests.policies_support import attach_version_scope, build_rules, build_version


def test_compile_bundle_warns_and_resolves_same_scope_deny_wins() -> None:
    compiler = GovernanceCompiler()
    warning_version = attach_version_scope(
        build_version(rules={"purpose_scopes": [{"id": "purpose-only"}], "budget_limits": {}}),
        level=0,
        scope_type=PolicyScopeType.global_scope,
    )
    allow_version = attach_version_scope(
        build_version(
            policy_id=warning_version.policy_id,
            version_number=2,
            rules=build_rules(
                enforcement_rules=[
                    EnforcementRuleSchema(
                        id="allow-finance",
                        action="allow",
                        tool_patterns=["finance:wire"],
                        applicable_step_types=["tool_invocation"],
                    )
                ]
            ),
        ),
        level=2,
        scope_type=PolicyScopeType.workspace,
    )
    deny_version = attach_version_scope(
        build_version(
            policy_id=warning_version.policy_id,
            version_number=3,
            rules={
                "enforcement_rules": [
                    {
                        "id": "deny-finance",
                        "action": "deny",
                        "tool_patterns": ["finance:wire"],
                        "applicable_step_types": ["tool_invocation"],
                    }
                ],
                "safety_rules": [{"id": "safe", "pattern": "wire"}],
                "budget_limits": {"max_memory_writes_per_minute": 3},
            },
        ),
        level=2,
        scope_type=PolicyScopeType.workspace,
    )

    bundle = compiler.compile_bundle(
        [warning_version, allow_version, deny_version],
        uuid4(),
        uuid4(),
    )

    assert bundle.denied_tool_patterns == ["finance:wire"]
    assert bundle.budget_limits.max_memory_writes_per_minute == 3
    assert bundle.safety_rules[0]["id"] == "safe"
    assert bundle.manifest.warnings
    assert bundle.manifest.conflicts[0].resolution == "deny_wins"


def test_compile_bundle_rejects_empty_rules_and_invalid_actions_and_supports_plain_shards() -> None:
    compiler = GovernanceCompiler()
    empty_rules_version = attach_version_scope(
        build_version(rules={}),
        level=0,
        scope_type=PolicyScopeType.global_scope,
    )
    invalid_action_version = attach_version_scope(
        build_version(
            rules={
                "enforcement_rules": [
                    {
                        "id": "broken",
                        "action": "explode",
                        "tool_patterns": ["finance:*"],
                    }
                ],
                "budget_limits": {},
            }
        ),
        level=0,
        scope_type=PolicyScopeType.global_scope,
    )

    with pytest.raises(PolicyCompilationError, match="contains no rules"):
        compiler.compile_bundle([empty_rules_version], uuid4(), uuid4())

    with pytest.raises(PolicyCompilationError, match="Unsupported enforcement action"):
        compiler.compile_bundle([invalid_action_version], uuid4(), uuid4())

    bundle = EnforcementBundle(
        fingerprint="f" * 64,
        allowed_tool_patterns=["finance:*"],
        denied_tool_patterns=["finance:wire"],
        allowed_namespaces=["finance"],
        manifest=ValidationManifest(
            source_policy_ids=[],
            source_version_ids=[],
            fingerprint="f" * 64,
        ),
    )
    shard = bundle.get_shard("planning")

    assert shard.allowed_tool_patterns == []
    assert shard.denied_tool_patterns == []
    assert shard.allowed_namespaces == []
