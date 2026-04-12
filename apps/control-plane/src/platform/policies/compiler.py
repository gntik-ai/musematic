from __future__ import annotations

from datetime import UTC, datetime
from fnmatch import fnmatch
from hashlib import sha256
from platform.policies.exceptions import PolicyCompilationError
from platform.policies.models import PolicyScopeType, PolicyVersion
from platform.policies.schemas import (
    BudgetLimitsSchema,
    EnforcementBundle,
    MaturityGateRuleSchema,
    PolicyConflict,
    ValidationManifest,
)
from typing import Any
from uuid import UUID

from pydantic import ValidationError


def _scope_level(version: PolicyVersion) -> int:
    return int(getattr(version, "_scope_level", 0))


def _scope_type(version: PolicyVersion) -> PolicyScopeType:
    value = getattr(version, "_scope_type", PolicyScopeType.global_scope)
    return value if isinstance(value, PolicyScopeType) else PolicyScopeType(str(value))


def _scope_target(version: PolicyVersion) -> str | None:
    value = getattr(version, "_scope_target_id", None)
    return None if value is None else str(value)


class GovernanceCompiler:
    def compile_bundle(
        self,
        policy_versions: list[PolicyVersion],
        agent_id: UUID,
        workspace_id: UUID,
    ) -> EnforcementBundle:
        del agent_id, workspace_id
        if not policy_versions:
            raise PolicyCompilationError("Cannot compile an empty policy set")

        ordered = sorted(
            policy_versions,
            key=lambda version: (_scope_level(version), version.version_number, version.created_at),
        )
        warnings: list[str] = []
        conflicts: list[PolicyConflict] = []
        allowed_by_step: dict[str, list[str]] = {}
        denied_by_step: dict[str, list[str]] = {}
        merged_rules: dict[str, tuple[str, int, PolicyScopeType]] = {}
        log_allowed_tools: set[str] = set()
        allowed_purposes: set[str] = set()
        denied_purposes: set[str] = set()
        allowed_namespaces: list[str] = []
        budget_limits = BudgetLimitsSchema()
        maturity_gate_rules: list[MaturityGateRuleSchema] = []
        safety_rules: list[dict[str, Any]] = []

        for version in ordered:
            rules = dict(version.rules)
            if not rules:
                raise PolicyCompilationError("Policy version contains no rules")
            budgets = rules.get("budget_limits") or {}
            try:
                budget_model = BudgetLimitsSchema.model_validate(budgets)
            except ValidationError as exc:
                raise PolicyCompilationError(str(exc)) from exc
            if budget_model.max_tool_invocations_per_execution is not None:
                budget_limits.max_tool_invocations_per_execution = (
                    budget_model.max_tool_invocations_per_execution
                )
            if budget_model.max_memory_writes_per_minute is not None:
                budget_limits.max_memory_writes_per_minute = (
                    budget_model.max_memory_writes_per_minute
                )

            raw_namespaces = rules.get("allowed_namespaces") or []
            if raw_namespaces:
                allowed_namespaces = [
                    str(item).strip() for item in raw_namespaces if str(item).strip()
                ]

            for raw_scope in rules.get("purpose_scopes") or []:
                allowed_purposes.update(
                    str(item).strip()
                    for item in raw_scope.get("allowed_purposes", [])
                    if str(item).strip()
                )
                denied_purposes.update(
                    str(item).strip()
                    for item in raw_scope.get("denied_purposes", [])
                    if str(item).strip()
                )

            for raw_gate in rules.get("maturity_gate_rules") or []:
                try:
                    maturity_gate_rules.append(MaturityGateRuleSchema.model_validate(raw_gate))
                except ValidationError as exc:
                    raise PolicyCompilationError(str(exc)) from exc

            for raw_safety in rules.get("safety_rules") or []:
                safety_rules.append(dict(raw_safety))

            enforcement_rules = rules.get("enforcement_rules") or []
            if (
                not enforcement_rules
                and not raw_namespaces
                and not rules.get("maturity_gate_rules")
            ):
                warnings.append(f"Policy version {version.id} has no executable enforcement rules")

            for raw_rule in enforcement_rules:
                rule = dict(raw_rule)
                action = str(rule.get("action", "deny")).strip().lower()
                if action not in {"allow", "deny", "warn", "audit"}:
                    raise PolicyCompilationError(f"Unsupported enforcement action '{action}'")
                rule_id = str(rule.get("id") or version.id)
                patterns = [
                    str(item).strip() for item in rule.get("tool_patterns", []) if str(item).strip()
                ]
                step_types = [
                    str(item).strip()
                    for item in rule.get("applicable_step_types", [])
                    if str(item).strip()
                ] or ["tool_invocation"]
                if rule.get("log_allowed_invocations"):
                    log_allowed_tools.update(patterns)
                for pattern in patterns:
                    existing = merged_rules.get(pattern)
                    current_scope = _scope_type(version)
                    current_level = _scope_level(version)
                    if existing is not None:
                        existing_action, existing_level, existing_scope = existing
                        if existing_level == current_level and existing_action != action:
                            if "deny" in {existing_action, action}:
                                winner = current_scope if action == "deny" else existing_scope
                                loser = existing_scope if action == "deny" else current_scope
                                merged_rules[pattern] = ("deny", current_level, winner)
                                conflicts.append(
                                    PolicyConflict(
                                        rule_id=rule_id,
                                        winner_scope=winner,
                                        loser_scope=loser,
                                        resolution="deny_wins",
                                    )
                                )
                                continue
                        if current_level >= existing_level and existing_action != action:
                            conflicts.append(
                                PolicyConflict(
                                    rule_id=rule_id,
                                    winner_scope=current_scope,
                                    loser_scope=existing_scope,
                                    resolution="more_specific_scope_wins",
                                )
                            )
                    if existing is None or current_level >= existing[1]:
                        merged_rules[pattern] = (action, current_level, current_scope)
                    for step_type in step_types:
                        target = allowed_by_step if action == "allow" else denied_by_step
                        bucket = target.setdefault(step_type, [])
                        if pattern not in bucket:
                            bucket.append(pattern)

        allowed = sorted(
            pattern
            for pattern, (action, _, _) in merged_rules.items()
            if action in {"allow", "audit", "warn"}
        )
        denied = sorted(
            pattern for pattern, (action, _, _) in merged_rules.items() if action == "deny"
        )
        fingerprint = sha256(
            "|".join(sorted(str(version.id) for version in ordered)).encode("utf-8")
        ).hexdigest()
        bundle = EnforcementBundle(
            fingerprint=fingerprint,
            allowed_tool_patterns=allowed,
            denied_tool_patterns=denied,
            maturity_gate_rules=maturity_gate_rules,
            allowed_purposes=sorted(allowed_purposes),
            denied_purposes=sorted(denied_purposes),
            allowed_namespaces=allowed_namespaces,
            budget_limits=budget_limits,
            safety_rules=safety_rules,
            log_allowed_tools=sorted(log_allowed_tools),
            manifest=ValidationManifest(
                source_policy_ids=sorted({version.policy_id for version in ordered}, key=str),
                source_version_ids=[version.id for version in ordered],
                compiled_at=datetime.now(UTC),
                fingerprint=fingerprint,
                warnings=warnings,
                conflicts=conflicts,
            ),
        )
        bundle.set_step_maps(allowed=allowed_by_step, denied=denied_by_step)
        return bundle

    @staticmethod
    def tool_matches(patterns: list[str], tool_fqn: str) -> bool:
        return any(fnmatch(tool_fqn, pattern) or tool_fqn == pattern for pattern in patterns)
