from __future__ import annotations

from decimal import Decimal
from platform.interactions.events import AttentionRequestedPayload, publish_attention_requested
from platform.interactions.models import AttentionUrgency
from platform.trust.events import make_correlation
from platform.trust.exceptions import OJEConfigError
from platform.trust.models import (
    OJEVerdictType,
    TrustOJEPipelineConfig,
    TrustProofLink,
    TrustSignal,
)
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    JudgeVerdictEvent,
    OJEPipelineConfigCreate,
    OJEPipelineConfigListResponse,
    OJEPipelineConfigResponse,
)
from typing import Any
from uuid import UUID, uuid4


class OJEPipelineService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
        registry_service: Any | None,
        interactions_service: Any | None,
        runtime_controller: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.registry_service = registry_service
        self.interactions_service = interactions_service
        self.runtime_controller = runtime_controller

    async def configure_pipeline(self, data: OJEPipelineConfigCreate) -> OJEPipelineConfigResponse:
        for group in (data.observer_fqns, data.judge_fqns, data.enforcer_fqns):
            for fqn in group:
                await self._ensure_fqn_exists(data.workspace_id, fqn)
        existing = await self.repository.get_oje_config(data.workspace_id, data.fleet_id)
        if existing is not None:
            existing.is_active = False
        config = await self.repository.create_oje_config(
            TrustOJEPipelineConfig(
                workspace_id=data.workspace_id,
                fleet_id=data.fleet_id,
                observer_fqns=list(data.observer_fqns),
                judge_fqns=list(data.judge_fqns),
                enforcer_fqns=list(data.enforcer_fqns),
                policy_refs=list(data.policy_refs),
                is_active=data.is_active,
            )
        )
        return OJEPipelineConfigResponse.model_validate(config)

    async def get_pipeline_config(
        self,
        workspace_id: str,
        fleet_id: str | None,
    ) -> OJEPipelineConfigResponse:
        config = await self.repository.get_oje_config(workspace_id, fleet_id)
        if config is None:
            raise OJEConfigError("OJE pipeline config not found")
        return OJEPipelineConfigResponse.model_validate(config)

    async def get_pipeline_config_by_id(self, config_id: UUID) -> OJEPipelineConfigResponse:
        config = await self.repository.get_oje_config_by_id(config_id)
        if config is None:
            raise OJEConfigError("OJE pipeline config not found")
        return OJEPipelineConfigResponse.model_validate(config)

    async def list_pipeline_configs(self, workspace_id: str) -> OJEPipelineConfigListResponse:
        items = await self.repository.list_oje_configs(workspace_id)
        return OJEPipelineConfigListResponse(
            items=[OJEPipelineConfigResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def deactivate_pipeline(self, config_id: UUID) -> OJEPipelineConfigResponse:
        item = await self.repository.deactivate_oje_config(config_id)
        if item is None:
            raise OJEConfigError("OJE pipeline config not found")
        return OJEPipelineConfigResponse.model_validate(item)

    async def process_observation(
        self,
        signal: dict[str, Any],
        pipeline_config_id: str,
    ) -> JudgeVerdictEvent:
        config = await self.repository.get_oje_config_by_id(UUID(pipeline_config_id))
        if config is None:
            raise OJEConfigError("OJE pipeline config not found")
        if isinstance(signal.get("judge_verdict"), dict):
            verdict = JudgeVerdictEvent.model_validate(signal["judge_verdict"])
        else:
            verdict = await self._invoke_judges(config, signal)
        await self.execute_enforcement(verdict)
        return verdict

    async def execute_enforcement(self, verdict: JudgeVerdictEvent) -> None:
        score_map = {
            OJEVerdictType.compliant: Decimal("1.0000"),
            OJEVerdictType.warning: Decimal("0.2500"),
            OJEVerdictType.violation: Decimal("-1.0000"),
            OJEVerdictType.escalate_to_human: Decimal("-0.5000"),
        }
        signal = await self.repository.create_signal(
            TrustSignal(
                agent_id=verdict.policy_basis,
                signal_type=f"oje.{verdict.verdict.value.lower()}",
                score_contribution=score_map[verdict.verdict],
                source_type="oje_verdict",
                source_id=verdict.observer_signal_id,
                workspace_id=None,
            )
        )
        await self.repository.create_proof_link(
            TrustProofLink(
                signal_id=signal.id,
                proof_type="oje_verdict",
                proof_reference_type="observer_signal",
                proof_reference_id=verdict.observer_signal_id,
            )
        )
        if verdict.verdict == OJEVerdictType.violation:
            stopper = getattr(self.runtime_controller, "stop_runtime", None)
            if stopper is not None:
                await stopper(
                    getattr(verdict, "runtime_id", None),
                    reason=verdict.reasoning,
                )
        elif verdict.verdict == OJEVerdictType.escalate_to_human:
            await publish_attention_requested(
                self.producer,
                AttentionRequestedPayload(
                    request_id=uuid4(),
                    workspace_id=self._workspace_uuid(),
                    source_agent_fqn=verdict.judge_fqn,
                    target_identity=self._attention_target_identity,
                    urgency=AttentionUrgency.high,
                    related_interaction_id=self._uuid_or_none(verdict.observer_signal_id),
                    related_goal_id=None,
                ),
                make_correlation(),
            )

    async def _invoke_judges(
        self,
        config: TrustOJEPipelineConfig,
        signal: dict[str, Any],
    ) -> JudgeVerdictEvent:
        invoker = getattr(self.interactions_service, "invoke_trust_judge", None)
        if invoker is not None:
            result = await invoker(config.judge_fqns, signal, trust_pipeline_context=True)
            return JudgeVerdictEvent.model_validate(result)
        return JudgeVerdictEvent(
            pipeline_config_id=str(config.id),
            observer_signal_id=str(signal.get("signal_id") or uuid4()),
            judge_fqn=config.judge_fqns[0],
            verdict=OJEVerdictType.compliant,
            reasoning="No judge integration configured",
            policy_basis=str(config.policy_refs[0] if config.policy_refs else "none"),
            enforcer_action_taken=None,
        )

    async def _ensure_fqn_exists(self, workspace_id: str, fqn: str) -> None:
        resolver = getattr(self.registry_service, "get_agent_by_fqn", None)
        if resolver is None:
            return
        item = await resolver(self._uuid_from_text(workspace_id), fqn)
        if item is None:
            raise OJEConfigError("Unknown OJE agent FQN", fqn=fqn)

    @property
    def _attention_target_identity(self) -> str:
        trust_settings = getattr(self.settings, "trust", None)
        return str(getattr(trust_settings, "attention_target_identity", "platform_admin"))

    def _workspace_uuid(self) -> UUID:
        default = getattr(getattr(self.settings, "trust", None), "default_workspace_id", None)
        return self._uuid_from_text(default or uuid4())

    @staticmethod
    def _uuid_from_text(value: Any) -> UUID:
        if isinstance(value, UUID):
            return value
        return UUID(str(value))

    @staticmethod
    def _uuid_or_none(value: Any) -> UUID | None:
        if value in {None, ""}:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None
