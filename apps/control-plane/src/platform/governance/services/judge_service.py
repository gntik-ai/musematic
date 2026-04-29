from __future__ import annotations

import asyncio
from dataclasses import asdict, is_dataclass
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.events.producer import EventProducer
from platform.common.tagging.label_expression.cache import LabelExpressionCache
from platform.common.tagging.label_expression.evaluator import LabelExpressionEvaluator
from platform.fleets.repository import FleetPolicyBindingRepository
from platform.governance.events import VerdictIssuedPayload, publish_verdict_issued
from platform.governance.models import GovernanceVerdict, VerdictType
from platform.governance.repository import GovernanceRepository
from platform.governance.services.pipeline_config import ChainConfig, PipelineConfigService
from platform.policies.repository import PolicyRepository
from typing import Any, cast
from uuid import UUID, uuid4


class JudgeService:
    def __init__(
        self,
        *,
        repository: GovernanceRepository,
        pipeline_config: PipelineConfigService,
        fleet_policy_repo: FleetPolicyBindingRepository,
        policy_repo: PolicyRepository,
        settings: PlatformSettings,
        producer: EventProducer | None,
        redis_client: AsyncRedisClient,
        label_expression_cache: LabelExpressionCache | None = None,
        label_expression_evaluator: LabelExpressionEvaluator | None = None,
    ) -> None:
        self.repository = repository
        self.pipeline_config = pipeline_config
        self.fleet_policy_repo = fleet_policy_repo
        self.policy_repo = policy_repo
        self.settings = settings
        self.producer = producer
        self.redis_client = redis_client
        tagging_settings = getattr(settings, "tagging", None)
        self.label_expression_cache = label_expression_cache or LabelExpressionCache(
            redis_client,
            lru_size=getattr(tagging_settings, "label_expression_lru_size", 256),
            ttl_seconds=getattr(tagging_settings, "label_expression_redis_ttl_seconds", 86_400),
        )
        self.label_expression_evaluator = label_expression_evaluator or LabelExpressionEvaluator()

    async def process_signal(
        self,
        signal_envelope: EventEnvelope,
        fleet_id: UUID | None,
        workspace_id: UUID | None,
    ) -> list[GovernanceVerdict]:
        chain = await self.pipeline_config.resolve_chain(fleet_id, workspace_id)
        if chain is None:
            return []

        observer_fqn = self._observer_fqn(signal_envelope)
        if chain.observer_fqns and observer_fqn and observer_fqn not in chain.observer_fqns:
            return []

        if observer_fqn:
            scope_key = str(workspace_id or fleet_id or observer_fqn)
            rate_limit = await self.redis_client.check_rate_limit(
                "governance",
                f"{observer_fqn}:{scope_key}",
                self.settings.governance.rate_limit_per_observer_per_minute,
                60_000,
            )
            if not rate_limit.allowed:
                return []

        policy = await self._resolve_policy(chain, fleet_id)
        if policy is None:
            escalation_judge = (
                chain.judge_fqns[0] if chain.judge_fqns else "platform:governance-judge"
            )
            escalation = await self._persist_verdict(
                judge_agent_fqn=escalation_judge,
                verdict_type=VerdictType.ESCALATE_TO_HUMAN,
                policy_id=None,
                evidence=self._signal_payload(signal_envelope),
                rationale="Governance policy not found for configured chain",
                recommended_action=chain.verdict_to_action_mapping.get(
                    VerdictType.ESCALATE_TO_HUMAN.value
                ),
                source_event_id=self._source_event_id(signal_envelope),
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                correlation_ctx=signal_envelope.correlation_context,
            )
            return [escalation]

        if not await self._policy_matches_label_expression(policy, signal_envelope):
            return []

        persisted: list[GovernanceVerdict] = []
        for judge_fqn in chain.judge_fqns:
            try:
                raw_verdict = await asyncio.wait_for(
                    self._invoke_judge(judge_fqn=judge_fqn, signal=signal_envelope, policy=policy),
                    timeout=self.settings.governance.judge_timeout_seconds,
                )
            except TimeoutError:
                raw_verdict = {
                    "verdict_type": VerdictType.ESCALATE_TO_HUMAN.value,
                    "rationale": "judge unavailable",
                    "evidence": self._signal_payload(signal_envelope),
                }

            verdict = self._normalize_verdict(raw_verdict)
            if verdict is None:
                verdict = {
                    "verdict_type": VerdictType.ESCALATE_TO_HUMAN.value,
                    "rationale": "judge returned an invalid verdict payload",
                    "evidence": self._signal_payload(signal_envelope),
                }

            evidence = cast(dict[str, object], verdict["evidence"])
            recommended_action = cast(str | None, verdict.get("recommended_action"))
            if not recommended_action:
                recommended_action = chain.verdict_to_action_mapping.get(
                    str(verdict["verdict_type"])
                )

            created = await self._persist_verdict(
                judge_agent_fqn=judge_fqn,
                verdict_type=VerdictType(str(verdict["verdict_type"])),
                policy_id=getattr(policy, "id", None),
                evidence=evidence,
                rationale=str(verdict["rationale"]),
                recommended_action=recommended_action,
                source_event_id=self._source_event_id(signal_envelope),
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                correlation_ctx=signal_envelope.correlation_context,
            )
            persisted.append(created)
            if created.verdict_type in {VerdictType.VIOLATION, VerdictType.ESCALATE_TO_HUMAN}:
                break
        return persisted

    async def process_fleet_anomaly_signal(
        self,
        fleet_id: UUID,
        chain: object,
        signal: dict[str, object],
    ) -> dict[str, object]:
        chain_config = self._coerce_chain_config(chain)
        envelope = EventEnvelope(
            event_type=str(signal.get("event_type", "monitor.alert")),
            source="platform.governance",
            correlation_context=CorrelationContext(
                correlation_id=uuid4(),
                fleet_id=fleet_id,
                workspace_id=self._uuid_or_none(getattr(chain, "workspace_id", None)),
                agent_fqn=str(signal.get("agent_fqn", "")) or None,
            ),
            payload=dict(signal),
        )
        verdicts = await self.process_signal(
            envelope,
            fleet_id,
            envelope.correlation_context.workspace_id,
        )
        return {
            "status": "processed" if verdicts else "skipped",
            "fleet_id": str(fleet_id),
            "verdict_ids": [str(item.id) for item in verdicts],
            "scope": chain_config.scope,
        }

    async def _resolve_policy(self, chain: ChainConfig, fleet_id: UUID | None) -> object | None:
        policy_id: UUID | None = None
        if chain.scope == "fleet" and fleet_id is not None:
            for raw_binding_id in chain.policy_binding_ids:
                binding_id = self._uuid_or_none(raw_binding_id)
                if binding_id is None:
                    continue
                binding = await self.fleet_policy_repo.get_by_id(binding_id, fleet_id)
                if binding is not None:
                    policy_id = binding.policy_id
                    break
        else:
            for raw_policy_id in chain.policy_binding_ids:
                policy_id = self._uuid_or_none(raw_policy_id)
                if policy_id is not None:
                    break
        if policy_id is None:
            return None
        return await self.policy_repo.get_by_id(policy_id)

    async def _invoke_judge(
        self,
        *,
        judge_fqn: str,
        signal: EventEnvelope,
        policy: object,
    ) -> dict[str, object]:
        payload = self._signal_payload(signal)
        judge_verdicts = payload.get("judge_verdicts")
        if isinstance(judge_verdicts, dict) and judge_fqn in judge_verdicts:
            override = judge_verdicts[judge_fqn]
            if isinstance(override, dict):
                return dict(override)
            if isinstance(override, str):
                return {
                    "verdict_type": override,
                    "rationale": f"Synthetic verdict from {judge_fqn}",
                    "evidence": payload,
                }
        judge_verdict = payload.get("judge_verdict")
        if isinstance(judge_verdict, dict):
            return dict(judge_verdict)

        threshold = self._extract_threshold(policy)
        value = self._extract_signal_value(payload)
        if threshold is None or value is None:
            return {
                "verdict_type": VerdictType.ESCALATE_TO_HUMAN.value,
                "rationale": "judge could not evaluate the signal payload",
                "evidence": payload,
            }
        verdict = VerdictType.VIOLATION if value > threshold else VerdictType.COMPLIANT
        return {
            "verdict_type": verdict.value,
            "rationale": f"Signal value {value} compared against threshold {threshold}",
            "evidence": {**payload, "threshold": threshold, "signal_value": value},
        }

    def _normalize_verdict(self, value: object) -> dict[str, object] | None:
        if hasattr(value, "model_dump"):
            payload = value.model_dump(mode="json")
        elif not isinstance(value, type) and is_dataclass(value):
            payload = asdict(cast(Any, value))
        elif isinstance(value, dict):
            payload = dict(value)
        else:
            return None

        verdict_type = payload.get("verdict_type") or payload.get("verdict")
        rationale = payload.get("rationale") or payload.get("reasoning")
        evidence = payload.get("evidence")
        if not isinstance(verdict_type, str) or not isinstance(rationale, str):
            return None
        if evidence is None:
            evidence = {}
        if not isinstance(evidence, dict):
            return None
        try:
            VerdictType(verdict_type)
        except ValueError:
            return None
        normalized = dict(payload)
        normalized["verdict_type"] = verdict_type
        normalized["rationale"] = rationale
        normalized["evidence"] = evidence
        return normalized

    async def _persist_verdict(
        self,
        *,
        judge_agent_fqn: str,
        verdict_type: VerdictType,
        policy_id: UUID | None,
        evidence: dict[str, object],
        rationale: str,
        recommended_action: str | None,
        source_event_id: UUID | None,
        fleet_id: UUID | None,
        workspace_id: UUID | None,
        correlation_ctx: CorrelationContext,
    ) -> GovernanceVerdict:
        verdict = await self.repository.create_verdict(
            GovernanceVerdict(
                judge_agent_fqn=judge_agent_fqn,
                verdict_type=verdict_type,
                policy_id=policy_id,
                evidence=evidence,
                rationale=rationale,
                recommended_action=recommended_action,
                source_event_id=source_event_id,
                fleet_id=fleet_id,
                workspace_id=workspace_id,
            )
        )
        await publish_verdict_issued(
            self.producer,
            VerdictIssuedPayload(
                verdict_id=verdict.id,
                judge_agent_fqn=verdict.judge_agent_fqn,
                verdict_type=verdict.verdict_type.value,
                policy_id=verdict.policy_id,
                fleet_id=verdict.fleet_id,
                workspace_id=verdict.workspace_id,
                source_event_id=verdict.source_event_id,
                created_at=verdict.created_at,
            ),
            correlation_ctx,
        )
        return verdict

    @staticmethod
    def _signal_payload(signal: EventEnvelope) -> dict[str, object]:
        return dict(signal.payload)

    @staticmethod
    def _observer_fqn(signal: EventEnvelope) -> str | None:
        for key in ("observer_fqn", "agent_fqn"):
            value = signal.payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if signal.correlation_context.agent_fqn:
            return signal.correlation_context.agent_fqn
        return None

    async def _policy_matches_label_expression(
        self,
        policy: object,
        signal: EventEnvelope,
    ) -> bool:
        expression = self._extract_label_expression(policy)
        if expression is None:
            return True
        current_version = getattr(policy, "current_version", None)
        policy_id = getattr(policy, "id", None)
        if policy_id is None:
            return True
        version = getattr(current_version, "version_number", 1)
        ast = await self.label_expression_cache.get_or_compile(policy_id, int(version), expression)
        if ast is None:
            return True
        return await self.label_expression_evaluator.evaluate(
            ast,
            self._extract_target_labels(signal.payload),
        )

    @staticmethod
    def _extract_label_expression(policy: object) -> str | None:
        current_version = getattr(policy, "current_version", None)
        rules = getattr(current_version, "rules", None) if current_version is not None else None
        if not isinstance(rules, dict):
            return None
        value = rules.get("label_expression")
        if isinstance(value, str) and value.strip():
            return value.strip()
        camel_value = rules.get("labelExpression")
        if isinstance(camel_value, str) and camel_value.strip():
            return camel_value.strip()
        conditions = rules.get("conditions")
        if isinstance(conditions, dict):
            condition_value = conditions.get("label_expression")
            if isinstance(condition_value, str) and condition_value.strip():
                return condition_value.strip()
        return None

    @staticmethod
    def _extract_target_labels(payload: dict[str, object]) -> dict[str, str]:
        for key in ("target_labels", "labels"):
            value = payload.get(key)
            if isinstance(value, dict):
                return {str(item_key): str(item_value) for item_key, item_value in value.items()}
        target = payload.get("target")
        if isinstance(target, dict):
            labels = target.get("labels")
            if isinstance(labels, dict):
                return {str(item_key): str(item_value) for item_key, item_value in labels.items()}
        return {}

    @staticmethod
    def _extract_threshold(policy: object) -> float | None:
        current_version = getattr(policy, "current_version", None)
        rules = getattr(current_version, "rules", None) if current_version is not None else None
        if not isinstance(rules, dict):
            return None
        for key in ("threshold",):
            value = rules.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        conditions = rules.get("conditions")
        if isinstance(conditions, dict):
            threshold = conditions.get("threshold")
            if isinstance(threshold, (int, float)):
                return float(threshold)
        return None

    @staticmethod
    def _extract_signal_value(payload: dict[str, object]) -> float | None:
        for key in ("value", "signal_value", "score"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value)
        return None

    @staticmethod
    def _source_event_id(signal: EventEnvelope) -> UUID | None:
        for key in ("source_event_id", "execution_id", "signal_id"):
            value = signal.payload.get(key)
            parsed = JudgeService._uuid_or_none(value)
            if parsed is not None:
                return parsed
        return None

    @staticmethod
    def _uuid_or_none(value: object) -> UUID | None:
        if isinstance(value, UUID):
            return value
        if value is None:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _coerce_chain_config(chain: object) -> ChainConfig:
        if isinstance(chain, ChainConfig):
            return chain
        return ChainConfig(
            observer_fqns=list(getattr(chain, "observer_fqns", [])),
            judge_fqns=list(getattr(chain, "judge_fqns", [])),
            enforcer_fqns=list(getattr(chain, "enforcer_fqns", [])),
            policy_binding_ids=[str(item) for item in getattr(chain, "policy_binding_ids", [])],
            verdict_to_action_mapping=dict(getattr(chain, "verdict_to_action_mapping", {})),
            scope="workspace" if getattr(chain, "workspace_id", None) is not None else "fleet",
        )
