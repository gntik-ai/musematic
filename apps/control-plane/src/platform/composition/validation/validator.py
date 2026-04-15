from __future__ import annotations

import asyncio
from collections.abc import Iterable
from platform.composition.models import AgentBlueprint, FleetBlueprint
from platform.composition.schemas import CheckResult
from typing import Any
from uuid import UUID


class BlueprintValidator:
    """Validate agent and fleet blueprints against workspace constraints."""

    def __init__(
        self,
        *,
        registry_service: Any,
        policy_service: Any,
        connector_service: Any,
    ) -> None:
        self.registry_service = registry_service
        self.policy_service = policy_service
        self.connector_service = connector_service

    async def validate_agent(
        self,
        blueprint: AgentBlueprint,
        workspace_id: UUID,
    ) -> dict[str, CheckResult | None | bool]:
        """Validate an agent blueprint."""
        tools, model, connectors, policy = await asyncio.gather(
            self._tools_check(blueprint.tool_selections, workspace_id),
            self._model_check(blueprint.model_config, workspace_id),
            self._connectors_check(blueprint.connector_suggestions, workspace_id),
            self._policy_check(blueprint.policy_recommendations, workspace_id),
        )
        return {
            "overall_valid": _all_passed([tools, model, connectors, policy]),
            "tools_check": tools,
            "model_check": model,
            "connectors_check": connectors,
            "policy_check": policy,
            "cycle_check": None,
        }

    async def validate_fleet(
        self,
        blueprint: FleetBlueprint,
        workspace_id: UUID,
    ) -> dict[str, CheckResult | None | bool]:
        """Validate a fleet blueprint."""
        inline_agents = _inline_agent_payloads(blueprint.member_roles)
        tool_payload = _flatten_lists(inline_agents, "tool_selections")
        connector_payload = _flatten_lists(inline_agents, "connector_suggestions")
        policy_payload = _flatten_lists(inline_agents, "policy_recommendations")
        model_payload = _first_mapping(inline_agents, "model_config")
        tools, model, connectors, policy = await asyncio.gather(
            self._tools_check(tool_payload, workspace_id),
            self._model_check(model_payload, workspace_id),
            self._connectors_check(connector_payload, workspace_id),
            self._policy_check(policy_payload, workspace_id),
        )
        cycle = self._cycle_check(blueprint.delegation_rules + blueprint.escalation_rules)
        return {
            "overall_valid": _all_passed([tools, model, connectors, policy, cycle]),
            "tools_check": tools,
            "model_check": model,
            "connectors_check": connectors,
            "policy_check": policy,
            "cycle_check": cycle,
        }

    async def _tools_check(
        self,
        tool_selections: list[dict[str, Any]],
        workspace_id: UUID,
    ) -> CheckResult:
        try:
            available = await self.registry_service.get_available_tools(workspace_id)
        except Exception:
            return _unavailable("tools service unavailable")
        accessible = {_name(item): bool(_field(item, "is_accessible", True)) for item in available}
        details = []
        for item in tool_selections:
            name = str(item.get("tool_name", ""))
            ok = accessible.get(name, False)
            details.append(
                {
                    "tool_name": name,
                    "status": "available" if ok else "not_available",
                    "remediation": None if ok else f"Enable or replace tool '{name}'",
                }
            )
        return CheckResult(
            passed=all(entry["status"] == "available" for entry in details),
            details=details,
        )

    async def _model_check(
        self,
        model_config: dict[str, Any],
        workspace_id: UUID,
    ) -> CheckResult:
        try:
            available = await self.registry_service.get_available_models(workspace_id)
        except Exception:
            return _unavailable("models service unavailable")
        model_id = str(model_config.get("model_id", ""))
        accessible = {
            str(_field(item, "identifier", _field(item, "model_id", ""))): bool(
                _field(item, "is_accessible", True)
            )
            for item in available
        }
        ok = accessible.get(model_id, False)
        status = "available" if ok else "not_available"
        return CheckResult(
            passed=ok,
            details={
                "model_id": model_id,
                "status": status,
                "remediation": None if ok else f"Use an accessible model instead of '{model_id}'",
            },
        )

    async def _connectors_check(
        self,
        connector_suggestions: list[dict[str, Any]],
        workspace_id: UUID,
    ) -> CheckResult:
        details = []
        try:
            for item in connector_suggestions:
                name = str(item.get("connector_name", ""))
                status = await self.connector_service.check_connector_status(name, workspace_id)
                configured = bool(_field(status, "configured", False))
                operational = bool(_field(status, "operational", configured))
                ok = configured and operational
                details.append(
                    {
                        "connector_name": name,
                        "status": "configured" if ok else "not_configured",
                        "remediation": None if ok else f"Configure connector '{name}'",
                    }
                )
        except Exception:
            return _unavailable("connector service unavailable")
        return CheckResult(
            passed=all(entry["status"] == "configured" for entry in details),
            details=details,
        )

    async def _policy_check(
        self,
        policy_recommendations: list[dict[str, Any]],
        workspace_id: UUID,
    ) -> CheckResult:
        try:
            result = await self.policy_service.evaluate_conformance(
                "draft.composition",
                None,
                workspace_id,
            )
        except Exception:
            return _unavailable("policy service unavailable")
        passed = bool(_field(result, "passed", True))
        violations = list(_field(result, "violations", []))
        details = [
            {
                "policy_id": str(item.get("policy_id", "")),
                "status": "compatible" if passed else "conflict",
                "conflict_description": None if passed else violations,
            }
            for item in policy_recommendations
        ]
        if not details:
            details = [{"policy_id": "", "status": "compatible" if passed else "conflict"}]
        return CheckResult(passed=passed, details=details)

    def _cycle_check(self, rules: list[dict[str, Any]]) -> CheckResult:
        adjacency: dict[str, list[str]] = {}
        for rule in rules:
            source = str(rule.get("from_role", ""))
            target = str(rule.get("to_role", ""))
            if not source or not target:
                continue
            adjacency.setdefault(source, []).append(target)
        cycles = _find_cycles(adjacency)
        return CheckResult(
            passed=not cycles,
            details={"cycles_found": [{"path": cycle} for cycle in cycles]},
            remediation=None if not cycles else "Remove cyclic delegation or escalation paths",
        )


def _all_passed(results: Iterable[CheckResult]) -> bool:
    return all(result.passed is True for result in results)


def _unavailable(message: str) -> CheckResult:
    return CheckResult(
        passed=None,
        status="validation_unavailable",
        details={"status": "validation_unavailable", "reason": message},
        remediation="Retry validation after the dependent service is available",
    )


def _field(item: Any, field: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _name(item: Any) -> str:
    return str(_field(item, "name", _field(item, "tool_name", "")))


def _inline_agent_payloads(member_roles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(role.get("agent_blueprint_inline", {}))
        for role in member_roles
        if isinstance(role.get("agent_blueprint_inline"), dict)
    ]


def _flatten_lists(payloads: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for payload in payloads:
        nested = payload.get(key, [])
        if isinstance(nested, list):
            values.extend(item for item in nested if isinstance(item, dict))
    return values


def _first_mapping(payloads: list[dict[str, Any]], key: str) -> dict[str, Any]:
    for payload in payloads:
        nested = payload.get(key)
        if isinstance(nested, dict):
            return nested
    return {}


def _find_cycles(adjacency: dict[str, list[str]]) -> list[list[str]]:
    cycles: list[list[str]] = []
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> None:
        if node in stack:
            cycles.append([*stack[stack.index(node) :], node])
            return
        if node in visited:
            return
        visited.add(node)
        stack.append(node)
        for target in adjacency.get(node, []):
            visit(target)
        stack.pop()

    for node in adjacency:
        visit(node)
    return cycles
