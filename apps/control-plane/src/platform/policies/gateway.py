from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from fnmatch import fnmatch
from platform.common.config import PlatformSettings
from platform.policies.models import EnforcementComponent
from platform.policies.sanitizer import OutputSanitizer
from platform.policies.schemas import GateResult, SanitizationResult
from platform.policies.service import PolicyService
from platform.privacy_compliance.exceptions import ToolOutputBlocked
from typing import Any
from uuid import UUID


class ToolGatewayService:
    def __init__(
        self,
        *,
        policy_service: PolicyService,
        sanitizer: OutputSanitizer,
        reasoning_client: Any | None,
        registry_service: Any | None,
        settings: PlatformSettings | None = None,
        dlp_service: Any | None = None,
        residency_service: Any | None = None,
    ) -> None:
        self.policy_service = policy_service
        self.sanitizer = sanitizer
        self.reasoning_client = reasoning_client
        self.registry_service = registry_service
        self.settings = settings
        self.dlp_service = dlp_service
        self.residency_service = residency_service

    async def validate_tool_invocation(
        self,
        agent_id: UUID,
        agent_fqn: str,
        tool_fqn: str,
        declared_purpose: str,
        execution_id: UUID | None,
        workspace_id: UUID,
        session: Any,
    ) -> GateResult:
        origin_region = getattr(session, "origin_region", None)
        started = time.perf_counter()
        try:
            if (
                self.settings is not None
                and self.settings.privacy_compliance.residency_enforcement_enabled
                and self.residency_service is not None
            ):
                await self.residency_service.enforce(
                    workspace_id,
                    origin_region,
                )
            if (
                self.settings is not None
                and self.settings.visibility.zero_trust_enabled
                and self.registry_service is not None
                and hasattr(self.registry_service, "resolve_effective_visibility")
            ):
                effective_visibility = await self.registry_service.resolve_effective_visibility(
                    agent_id,
                    workspace_id,
                )
                if not any(
                    fnmatch(tool_fqn, pattern) or tool_fqn == pattern
                    for pattern in getattr(effective_visibility, "tool_patterns", [])
                ):
                    return await self._blocked(
                        agent_id=agent_id,
                        agent_fqn=agent_fqn,
                        target=tool_fqn,
                        workspace_id=workspace_id,
                        execution_id=execution_id,
                        block_reason="visibility_denied",
                        policy_rule_ref={"tool_fqn": tool_fqn},
                        started=started,
                    )

            if tool_fqn.startswith("mcp:"):
                membership_ref = await self._check_mcp_server_membership(
                    agent_id,
                    workspace_id,
                    tool_fqn,
                )
                if membership_ref is None:
                    return await self._blocked(
                        agent_id=agent_id,
                        agent_fqn=agent_fqn,
                        target=tool_fqn,
                        workspace_id=workspace_id,
                        execution_id=execution_id,
                        block_reason="permission_denied",
                        policy_rule_ref={"tool_fqn": tool_fqn},
                        started=started,
                    )

            bundle = await self.policy_service.get_enforcement_bundle(
                agent_id,
                workspace_id,
                execution_id=execution_id,
            )
            permission_ref = self._permission_ref(bundle, tool_fqn)
            if permission_ref is None:
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    block_reason="permission_denied",
                    policy_rule_ref=None,
                    started=started,
                )

            maturity_ref = await self._check_maturity(agent_id, workspace_id, tool_fqn, bundle)
            if maturity_ref is not None:
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    block_reason="maturity_level_insufficient",
                    policy_rule_ref=maturity_ref,
                    started=started,
                )

            if bundle.denied_purposes and declared_purpose in bundle.denied_purposes:
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    block_reason="purpose_mismatch",
                    policy_rule_ref={"declared_purpose": declared_purpose},
                    started=started,
                )
            if bundle.allowed_purposes and declared_purpose not in bundle.allowed_purposes:
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    block_reason="purpose_mismatch",
                    policy_rule_ref={"declared_purpose": declared_purpose},
                    started=started,
                )

            budget_ref = await self._check_budget(bundle, execution_id)
            if budget_ref is not None:
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    block_reason="budget_exceeded",
                    policy_rule_ref=budget_ref,
                    started=started,
                )

            safety_ref = self._check_safety(bundle.safety_rules, tool_fqn)
            if safety_ref is not None:
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    block_reason="safety_rule_blocked",
                    policy_rule_ref=safety_ref,
                    started=started,
                )

            if any(
                fnmatch(tool_fqn, pattern) or tool_fqn == pattern
                for pattern in bundle.log_allowed_tools
            ):
                await self.policy_service.publish_allowed_event(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=tool_fqn,
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                )
            return GateResult(allowed=True, check_latency_ms=(time.perf_counter() - started) * 1000)
        except Exception:
            return GateResult(
                allowed=False,
                block_reason="policy_resolution_failure",
                check_latency_ms=(time.perf_counter() - started) * 1000,
            )

    async def sanitize_tool_output(
        self,
        output: str,
        agent_id: UUID,
        agent_fqn: str,
        tool_fqn: str,
        execution_id: UUID | None,
        session: Any,
        *,
        workspace_id: UUID | None = None,
    ) -> SanitizationResult:
        sanitized = await self.sanitizer.sanitize(
            output,
            agent_id=agent_id,
            agent_fqn=agent_fqn,
            tool_fqn=tool_fqn,
            execution_id=execution_id,
            workspace_id=workspace_id,
            session=session,
        )
        if (
            self.settings is not None
            and self.settings.privacy_compliance.dlp_enabled
            and self.dlp_service is not None
            and workspace_id is not None
        ):
            scan_result = await self.dlp_service.scan_and_apply(sanitized.output, workspace_id)
            await self.dlp_service.emit_events(scan_result.events, execution_id=execution_id)
            if scan_result.blocked:
                commit = getattr(session, "commit", None)
                if callable(commit):
                    await commit()
                raise ToolOutputBlocked([event.match_summary for event in scan_result.events])
            return SanitizationResult(
                output=scan_result.output_text,
                redaction_count=sanitized.redaction_count,
                redacted_types=sanitized.redacted_types,
            )
        return sanitized

    def _permission_ref(self, bundle: Any, tool_fqn: str) -> dict[str, Any] | None:
        if any(
            fnmatch(tool_fqn, pattern) or tool_fqn == pattern
            for pattern in bundle.denied_tool_patterns
        ):
            return None
        if not bundle.allowed_tool_patterns:
            return None
        if any(
            fnmatch(tool_fqn, pattern) or tool_fqn == pattern
            for pattern in bundle.allowed_tool_patterns
        ):
            return {"tool_fqn": tool_fqn}
        return None

    async def _check_mcp_server_membership(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        tool_fqn: str,
    ) -> dict[str, Any] | None:
        if self.registry_service is None or not hasattr(self.registry_service, "get_agent"):
            return None
        try:
            _scheme, server_id, _tool_name = tool_fqn.split(":", 2)
        except ValueError:
            return None
        profile = await self.registry_service.get_agent(
            workspace_id,
            agent_id,
            actor_id=None,
            requesting_agent_id=None,
        )
        allowed = {str(item) for item in getattr(profile, "mcp_servers", [])}
        if server_id not in allowed:
            return None
        return {"server_id": server_id}

    async def _check_maturity(
        self,
        agent_id: UUID,
        workspace_id: UUID,
        tool_fqn: str,
        bundle: Any,
    ) -> dict[str, Any] | None:
        if not bundle.maturity_gate_rules:
            return None
        maturity_level = 0
        if self.registry_service is not None and hasattr(self.registry_service, "get_agent"):
            profile = await self.registry_service.get_agent(
                workspace_id,
                agent_id,
                actor_id=None,
                requesting_agent_id=None,
            )
            maturity_level = int(getattr(profile, "maturity_level", 0))
        for rule in bundle.maturity_gate_rules:
            if any(
                fnmatch(tool_fqn, pattern) or tool_fqn == pattern
                for pattern in rule.capability_patterns
            ):
                if maturity_level < rule.min_maturity_level:
                    return {"required_level": rule.min_maturity_level}
        return None

    async def _check_budget(self, bundle: Any, execution_id: UUID | None) -> dict[str, Any] | None:
        limit = bundle.budget_limits.max_tool_invocations_per_execution
        if limit is None or execution_id is None:
            return None
        if self.reasoning_client is not None and hasattr(
            self.reasoning_client, "get_remaining_budget"
        ):
            remaining = await self.reasoning_client.get_remaining_budget(execution_id)
            remaining_count = int(
                remaining.get("remaining_tool_invocations", remaining.get("remaining", limit))
            )
            if remaining_count <= 0:
                return {"limit": limit}
            return None
        redis_client = getattr(self.policy_service, "redis_client", None)
        if redis_client is not None and hasattr(redis_client, "decrement_budget"):
            result = await redis_client.decrement_budget(
                str(execution_id), "tool_gateway", "rounds", 1
            )
            if not result.allowed:
                return {"limit": limit}
        return None

    @staticmethod
    def _check_safety(safety_rules: list[dict[str, Any]], tool_fqn: str) -> dict[str, Any] | None:
        for rule in safety_rules:
            pattern = str(rule.get("pattern", "")).strip()
            if not pattern:
                continue
            if re.search(pattern, tool_fqn):
                return {"rule_id": rule.get("id"), "pattern": pattern}
        return None

    async def _blocked(
        self,
        *,
        agent_id: UUID,
        agent_fqn: str,
        target: str,
        workspace_id: UUID,
        execution_id: UUID | None,
        block_reason: str,
        policy_rule_ref: dict[str, Any] | None,
        started: float,
    ) -> GateResult:
        await self.policy_service.create_blocked_record(
            agent_id=agent_id,
            agent_fqn=agent_fqn,
            enforcement_component=EnforcementComponent.tool_gateway,
            action_type="tool_invocation",
            target=target,
            block_reason=block_reason,
            workspace_id=workspace_id,
            execution_id=execution_id,
            policy_rule_ref=policy_rule_ref,
        )
        return GateResult(
            allowed=False,
            block_reason=block_reason,
            policy_rule_ref=policy_rule_ref,
            check_latency_ms=(time.perf_counter() - started) * 1000,
        )


class MemoryWriteGateService:
    def __init__(
        self,
        *,
        policy_service: PolicyService,
        memory_service: Any | None,
    ) -> None:
        self.policy_service = policy_service
        self.memory_service = memory_service

    async def validate_memory_write(
        self,
        agent_id: UUID,
        agent_fqn: str,
        target_namespace: str,
        content_hash: str,
        workspace_id: UUID,
        session: Any,
    ) -> GateResult:
        del session
        started = time.perf_counter()
        try:
            bundle = await self.policy_service.get_enforcement_bundle(agent_id, workspace_id)
            if not bundle.allowed_namespaces or not any(
                fnmatch(target_namespace, pattern) or target_namespace == pattern
                for pattern in bundle.allowed_namespaces
            ):
                return await self._blocked(
                    agent_id=agent_id,
                    agent_fqn=agent_fqn,
                    target=target_namespace,
                    workspace_id=workspace_id,
                    block_reason="namespace_unauthorized",
                    policy_rule_ref={"namespace": target_namespace},
                    started=started,
                )

            limit = bundle.budget_limits.max_memory_writes_per_minute
            if limit is not None:
                minute_bucket = datetime.now(UTC).strftime("%Y%m%d%H%M")
                key = f"policy:write_rate:{agent_id}:{minute_bucket}"
                redis_client = getattr(self.policy_service, "redis_client", None)
                if redis_client is not None:
                    client = await redis_client._get_client()
                    current = await client.incr(key)
                    if current == 1:
                        await client.expire(key, 120)
                    if int(current) > int(limit):
                        return await self._blocked(
                            agent_id=agent_id,
                            agent_fqn=agent_fqn,
                            target=target_namespace,
                            workspace_id=workspace_id,
                            block_reason="rate_limit_exceeded",
                            policy_rule_ref={"limit": limit},
                            started=started,
                        )

            if self.memory_service is not None and hasattr(self.memory_service, "namespace_exists"):
                exists = await self.memory_service.namespace_exists(workspace_id, target_namespace)
                if not exists:
                    return await self._blocked(
                        agent_id=agent_id,
                        agent_fqn=agent_fqn,
                        target=target_namespace,
                        workspace_id=workspace_id,
                        block_reason="namespace_not_found",
                        policy_rule_ref={"namespace": target_namespace},
                        started=started,
                    )

            if self.memory_service is not None and hasattr(
                self.memory_service, "check_contradiction"
            ):
                contradiction = await self.memory_service.check_contradiction(
                    content_hash, target_namespace
                )
                if contradiction:
                    return await self._blocked(
                        agent_id=agent_id,
                        agent_fqn=agent_fqn,
                        target=target_namespace,
                        workspace_id=workspace_id,
                        block_reason="contradiction_detected",
                        policy_rule_ref={"namespace": target_namespace},
                        started=started,
                    )
            return GateResult(
                allowed=True,
                policy_rule_ref={"retention": "policy_managed"},
                check_latency_ms=(time.perf_counter() - started) * 1000,
            )
        except Exception:
            return GateResult(
                allowed=False,
                block_reason="policy_resolution_failure",
                check_latency_ms=(time.perf_counter() - started) * 1000,
            )

    async def _blocked(
        self,
        *,
        agent_id: UUID,
        agent_fqn: str,
        target: str,
        workspace_id: UUID,
        block_reason: str,
        policy_rule_ref: dict[str, Any] | None,
        started: float,
    ) -> GateResult:
        await self.policy_service.create_blocked_record(
            agent_id=agent_id,
            agent_fqn=agent_fqn,
            enforcement_component=EnforcementComponent.memory_write_gate,
            action_type="memory_write",
            target=target,
            block_reason=block_reason,
            workspace_id=workspace_id,
            execution_id=None,
            policy_rule_ref=policy_rule_ref,
        )
        return GateResult(
            allowed=False,
            block_reason=block_reason,
            policy_rule_ref=policy_rule_ref,
            check_latency_ms=(time.perf_counter() - started) * 1000,
        )
