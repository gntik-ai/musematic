from __future__ import annotations

from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.governance.events import (
    EnforcementExecutedPayload,
    publish_enforcement_executed,
)
from platform.governance.models import ActionType, EnforcementAction, GovernanceVerdict
from platform.governance.repository import GovernanceRepository
from platform.governance.services.pipeline_config import ChainConfig
from typing import Any
from uuid import UUID


class EnforcerService:
    def __init__(
        self,
        *,
        repository: GovernanceRepository,
        producer: EventProducer | None,
        certification_service: Any | None,
    ) -> None:
        self.repository = repository
        self.producer = producer
        self.certification_service = certification_service

    async def process_verdict(
        self,
        verdict: GovernanceVerdict,
        chain_config: ChainConfig,
    ) -> EnforcementAction:
        existing = await self.repository.get_enforcement_action_for_verdict(verdict.id)
        if existing is not None:
            return existing

        action_name = chain_config.verdict_to_action_mapping.get(
            verdict.verdict_type.value,
            ActionType.log_and_continue.value,
        )
        try:
            action_type = ActionType(action_name)
        except ValueError:
            action_type = ActionType.log_and_continue

        enforcer_agent_fqn = (
            chain_config.enforcer_fqns[0]
            if chain_config.enforcer_fqns
            else "platform:default-enforcer"
        )
        target_agent_fqn = self._target_agent_fqn(verdict)
        try:
            outcome = await self._execute_action(action_type, verdict, target_agent_fqn)
        except LookupError:
            outcome = {"error": "target_not_found", "target_agent_fqn": target_agent_fqn}

        action = await self.repository.create_enforcement_action(
            EnforcementAction(
                enforcer_agent_fqn=enforcer_agent_fqn,
                verdict_id=verdict.id,
                action_type=action_type,
                target_agent_fqn=target_agent_fqn,
                outcome=outcome,
                workspace_id=verdict.workspace_id,
            )
        )
        await publish_enforcement_executed(
            self.producer,
            EnforcementExecutedPayload(
                action_id=action.id,
                verdict_id=action.verdict_id,
                enforcer_agent_fqn=action.enforcer_agent_fqn,
                action_type=action.action_type.value,
                target_agent_fqn=action.target_agent_fqn,
                workspace_id=action.workspace_id,
                created_at=action.created_at,
            ),
            CorrelationContext(
                correlation_id=verdict.id,
                workspace_id=verdict.workspace_id,
                fleet_id=verdict.fleet_id,
            ),
        )
        return action

    async def _execute_action(
        self,
        action_type: ActionType,
        verdict: GovernanceVerdict,
        target_agent_fqn: str | None,
    ) -> dict[str, object]:
        if action_type is ActionType.block:
            return await self._execute_block(target_agent_fqn)
        if action_type is ActionType.quarantine:
            return await self._execute_quarantine(target_agent_fqn)
        if action_type is ActionType.notify:
            return await self._execute_notify(target_agent_fqn)
        if action_type is ActionType.revoke_cert:
            return await self._execute_revoke_cert(verdict, target_agent_fqn)
        return await self._execute_log_and_continue(verdict)

    async def _execute_block(self, target_agent_fqn: str | None) -> dict[str, object]:
        if not target_agent_fqn:
            raise LookupError
        return {"blocked": True, "target_agent_fqn": target_agent_fqn}

    async def _execute_quarantine(self, target_agent_fqn: str | None) -> dict[str, object]:
        if not target_agent_fqn:
            raise LookupError
        return {"quarantined": True, "target_agent_fqn": target_agent_fqn}

    async def _execute_notify(self, target_agent_fqn: str | None) -> dict[str, object]:
        if not target_agent_fqn:
            raise LookupError
        return {"notified": True, "target_agent_fqn": target_agent_fqn}

    async def _execute_revoke_cert(
        self,
        verdict: GovernanceVerdict,
        target_agent_fqn: str | None,
    ) -> dict[str, object]:
        certification_id = self._uuid_or_none(verdict.evidence.get("certification_id"))
        if certification_id is None or self.certification_service is None:
            return {
                "revoked": False,
                "target_agent_fqn": target_agent_fqn,
                "reason": "missing_certification_context",
            }
        response = await self.certification_service.revoke(
            certification_id,
            f"{verdict.verdict_type.value} verdict",
            verdict.id,
        )
        return {
            "revoked": True,
            "target_agent_fqn": target_agent_fqn,
            "revoked_cert_id": str(getattr(response, "id", certification_id)),
        }

    async def _execute_log_and_continue(self, verdict: GovernanceVerdict) -> dict[str, object]:
        return {
            "logged": True,
            "unmapped_verdict_type": verdict.verdict_type.value,
        }

    @staticmethod
    def _target_agent_fqn(verdict: GovernanceVerdict) -> str | None:
        for key in ("target_agent_fqn", "agent_fqn"):
            value = verdict.evidence.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
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
