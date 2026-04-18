from __future__ import annotations

import hashlib
import json
import re
from platform.trust.events import (
    GuardrailBlockedPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.models import (
    GuardrailLayer,
    TrustBlockedActionRecord,
    TrustProofLink,
    TrustSignal,
)
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    BlockedActionResponse,
    BlockedActionsListResponse,
    GuardrailEvaluationRequest,
    GuardrailEvaluationResponse,
    GuardrailPipelineConfigResponse,
)
from typing import Any, ClassVar
from uuid import UUID

import httpx
from opentelemetry import metrics as otel_metrics

_INPUT_SANITIZATION_PATTERNS = [
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"drop\s+table", re.IGNORECASE),
    re.compile(r"rm\s+-rf", re.IGNORECASE),
]
_PROMPT_INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"bypass\s+(the\s+)?guardrail", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
]
_OUTPUT_MODERATION_PATTERNS = [
    re.compile(r"\bkill yourself\b", re.IGNORECASE),
    re.compile(r"\bcredit card number\b", re.IGNORECASE),
    re.compile(r"\bsocial security\b", re.IGNORECASE),
]


def _emit_prescreener_latency(latency_ms: float, version: str | None) -> None:
    otel_metrics.get_meter(__name__).create_histogram("prescreener.latency_ms").record(
        latency_ms,
        {"rule_set_version": version or "none"},
    )


class GuardrailPipelineService:
    LAYER_ORDER: ClassVar[list[GuardrailLayer]] = [
        GuardrailLayer.pre_screener,
        GuardrailLayer.input_sanitization,
        GuardrailLayer.prompt_injection,
        GuardrailLayer.output_moderation,
        GuardrailLayer.tool_control,
        GuardrailLayer.memory_write,
        GuardrailLayer.action_commit,
    ]

    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
        policy_engine: Any | None,
        pre_screener: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.events = TrustEventPublisher(producer)
        self.policy_engine = policy_engine
        self.pre_screener = pre_screener

    async def evaluate_full_pipeline(
        self,
        request: GuardrailEvaluationRequest,
    ) -> GuardrailEvaluationResponse:
        stop_index = self.LAYER_ORDER.index(request.layer)
        for layer in self.LAYER_ORDER[: stop_index + 1]:
            response = await self.evaluate_layer(layer, request.payload, request.model_dump())
            if not response.allowed:
                return response
        await self.repository.create_signal(
            TrustSignal(
                agent_id=request.agent_id,
                signal_type="guardrail.allowed",
                score_contribution=1,
                source_type="guardrail",
                source_id=str(
                    request.execution_id or request.interaction_id or request.layer.value
                ),
                workspace_id=request.workspace_id,
            )
        )
        return GuardrailEvaluationResponse(allowed=True, layer=request.layer)

    async def evaluate_layer(
        self,
        layer: GuardrailLayer,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> GuardrailEvaluationResponse:
        try:
            if layer == GuardrailLayer.pre_screener:
                basis = await self._evaluate_pre_screener(payload, context)
            elif layer == GuardrailLayer.input_sanitization:
                basis = self._match_patterns(
                    payload, _INPUT_SANITIZATION_PATTERNS, "input_sanitization"
                )
            elif layer == GuardrailLayer.prompt_injection:
                basis = self._match_patterns(
                    payload, _PROMPT_INJECTION_PATTERNS, "prompt_injection"
                )
            elif layer == GuardrailLayer.output_moderation:
                basis = await self._moderate_output(payload)
            elif layer == GuardrailLayer.tool_control:
                basis = await self._evaluate_tool_access(payload, context)
            elif layer == GuardrailLayer.memory_write:
                basis = await self._evaluate_memory_write(payload, context)
            else:
                basis = await self._evaluate_action_commit(payload, context)
        except Exception:
            basis = f"guardrail_layer_unavailable:{layer.value}"
        if basis is None:
            return GuardrailEvaluationResponse(allowed=True, layer=layer)
        record = await self.record_blocked_action(context, layer, basis)
        await self.events.publish_guardrail_blocked(
            GuardrailBlockedPayload(
                blocked_action_id=record.id,
                agent_id=record.agent_id,
                agent_fqn=record.agent_fqn,
                layer=record.layer.value,
                policy_basis=record.policy_basis,
                execution_id=record.execution_id,
                workspace_id=record.workspace_id,
                occurred_at=utcnow(),
            ),
            make_correlation(
                workspace_id=context.get("workspace_id"),
                execution_id=context.get("execution_id"),
                interaction_id=context.get("interaction_id"),
            ),
        )
        return GuardrailEvaluationResponse(
            allowed=False,
            layer=layer,
            policy_basis=basis,
            blocked_action_id=record.id,
        )

    async def record_blocked_action(
        self,
        context: dict[str, Any],
        layer: GuardrailLayer,
        policy_basis: str,
    ) -> TrustBlockedActionRecord:
        payload = context.get("payload", {})
        serialized = json.dumps(payload, sort_keys=True, default=str)
        preview = serialized[:500] if serialized else None
        record = await self.repository.create_blocked_action_record(
            TrustBlockedActionRecord(
                agent_id=str(context["agent_id"]),
                agent_fqn=str(context["agent_fqn"]),
                layer=layer,
                policy_basis=policy_basis,
                policy_basis_detail=str(context.get("policy_basis_detail") or ""),
                input_context_hash=hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
                input_context_preview=preview,
                execution_id=self._optional_text(context.get("execution_id")),
                interaction_id=self._optional_text(context.get("interaction_id")),
                workspace_id=self._optional_text(context.get("workspace_id")),
            )
        )
        signal = await self.repository.create_signal(
            TrustSignal(
                agent_id=record.agent_id,
                signal_type="guardrail.blocked",
                score_contribution=-1,
                source_type="guardrail_block",
                source_id=str(record.id),
                workspace_id=record.workspace_id,
            )
        )
        await self.repository.create_proof_link(
            TrustProofLink(
                signal_id=signal.id,
                proof_type="guardrail_event",
                proof_reference_type="blocked_action_record",
                proof_reference_id=str(record.id),
            )
        )
        return record

    async def get_config(
        self,
        workspace_id: str,
        fleet_id: str | None,
    ) -> GuardrailPipelineConfigResponse | None:
        item = await self.repository.get_guardrail_config(workspace_id, fleet_id)
        return None if item is None else GuardrailPipelineConfigResponse.model_validate(item)

    async def update_config(
        self,
        workspace_id: str,
        fleet_id: str | None,
        config: dict[str, Any],
        *,
        is_active: bool = True,
    ) -> GuardrailPipelineConfigResponse:
        item = await self.repository.upsert_guardrail_config(
            workspace_id=workspace_id,
            fleet_id=fleet_id,
            config=config,
            is_active=is_active,
        )
        return GuardrailPipelineConfigResponse.model_validate(item)

    async def list_blocked_actions(
        self,
        *,
        agent_id: str | None,
        layer: GuardrailLayer | None,
        workspace_id: str | None,
        since: Any,
        until: Any,
        page: int,
        page_size: int,
    ) -> BlockedActionsListResponse:
        items, total = await self.repository.list_blocked_actions_paginated(
            agent_id=agent_id,
            layer=layer,
            workspace_id=workspace_id,
            since=since,
            until=until,
            offset=(page - 1) * page_size,
            limit=page_size,
        )
        return BlockedActionsListResponse(
            items=[BlockedActionResponse.model_validate(item) for item in items],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def get_blocked_action(self, record_id: UUID) -> BlockedActionResponse | None:
        item = await self.repository.get_blocked_action(record_id)
        return None if item is None else BlockedActionResponse.model_validate(item)

    @staticmethod
    def _match_patterns(
        payload: dict[str, Any],
        patterns: list[re.Pattern[str]],
        prefix: str,
    ) -> str | None:
        text = json.dumps(payload, sort_keys=True, default=str)
        for index, pattern in enumerate(patterns, start=1):
            if pattern.search(text):
                return f"{prefix}:pattern_{index}"
        return None

    async def _evaluate_pre_screener(
        self,
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> str | None:
        if self.pre_screener is None:
            return None
        response = await self.pre_screener.screen(
            json.dumps(payload, sort_keys=True, default=str),
            str(context.get("context_type", "input")),
        )
        if response.latency_ms is not None:
            _emit_prescreener_latency(response.latency_ms, response.rule_set_version)
        if not response.blocked:
            return None
        context["policy_basis_detail"] = json.dumps(
            {
                "matched_rule": response.matched_rule,
                "rule_set_version": response.rule_set_version,
            }
        )
        return f"pre_screener:{response.matched_rule}"

    async def _moderate_output(self, payload: dict[str, Any]) -> str | None:
        matched = self._match_patterns(payload, _OUTPUT_MODERATION_PATTERNS, "output_moderation")
        if matched is not None:
            return matched
        url = getattr(getattr(self.settings, "trust", self.settings), "output_moderation_url", "")
        if not url:
            return None
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code >= 400:
                return "output_moderation:provider_error"
            body = response.json()
            if isinstance(body, dict) and body.get("blocked") is True:
                return str(body.get("policy_basis") or "output_moderation:provider_blocked")
        return None

    async def _evaluate_tool_access(
        self, payload: dict[str, Any], context: dict[str, Any]
    ) -> str | None:
        checker = getattr(self.policy_engine, "evaluate_tool_access", None)
        if checker is None:
            return None
        result = await checker(
            agent_id=context.get("agent_id"),
            tool_id=payload.get("tool_id"),
            workspace_id=context.get("workspace_id"),
        )
        return self._extract_policy_block_reason(result, "tool_control")

    async def _evaluate_memory_write(
        self, payload: dict[str, Any], context: dict[str, Any]
    ) -> str | None:
        checker = getattr(self.policy_engine, "evaluate_memory_write", None)
        if checker is None:
            return None
        result = await checker(
            agent_id=context.get("agent_id"),
            namespace=payload.get("namespace"),
            workspace_id=context.get("workspace_id"),
        )
        return self._extract_policy_block_reason(result, "memory_write")

    async def _evaluate_action_commit(
        self, payload: dict[str, Any], context: dict[str, Any]
    ) -> str | None:
        response = await self.get_config(
            str(context.get("workspace_id")),
            self._optional_text(context.get("fleet_id")),
        )
        action_commit = response.config.get("action_commit") if response is not None else None
        if isinstance(action_commit, dict) and action_commit.get("enabled") is False:
            return "action_commit:disabled"
        if payload.get("blocked") is True:
            return "action_commit:payload_blocked"
        return None

    @staticmethod
    def _extract_policy_block_reason(result: Any, fallback: str) -> str | None:
        if isinstance(result, bool):
            return None if result else fallback
        if isinstance(result, dict):
            allowed = result.get("allowed")
            if allowed is False:
                return str(result.get("policy_basis") or fallback)
            return None
        allowed = getattr(result, "allowed", None)
        if allowed is False:
            return str(getattr(result, "policy_basis", fallback))
        return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value in {None, ""}:
            return None
        return str(value)
