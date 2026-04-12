from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.fleet_learning.events import publish_adaptation_applied
from platform.fleet_learning.exceptions import AdaptationError
from platform.fleet_learning.models import FleetAdaptationLog, FleetAdaptationRule
from platform.fleet_learning.repository import (
    FleetAdaptationLogRepository,
    FleetAdaptationRuleRepository,
    FleetPerformanceProfileRepository,
)
from platform.fleet_learning.schemas import (
    FleetAdaptationLogResponse,
    FleetAdaptationRuleCreate,
    FleetAdaptationRuleResponse,
)
from platform.fleets.events import (
    FleetAdaptationAppliedPayload,
    FleetEventType,
    FleetRulesUpdatedPayload,
    publish_fleet_event,
)
from platform.fleets.repository import FleetOrchestrationRulesRepository
from platform.fleets.schemas import FleetOrchestrationRulesCreate
from typing import Any
from uuid import UUID, uuid4

_OPERATORS: dict[str, Any] = {
    "gt": lambda value, threshold: value > threshold,
    "lt": lambda value, threshold: value < threshold,
    "gte": lambda value, threshold: value >= threshold,
    "lte": lambda value, threshold: value <= threshold,
    "eq": lambda value, threshold: value == threshold,
}


class FleetAdaptationEngineService:
    def __init__(
        self,
        *,
        rule_repo: FleetAdaptationRuleRepository,
        log_repo: FleetAdaptationLogRepository,
        profile_repo: FleetPerformanceProfileRepository,
        rules_repo: FleetOrchestrationRulesRepository,
        fleet_service: Any,
        producer: Any | None,
    ) -> None:
        self.rule_repo = rule_repo
        self.log_repo = log_repo
        self.profile_repo = profile_repo
        self.rules_repo = rules_repo
        self.fleet_service = fleet_service
        self.producer = producer

    async def create_rule(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        request: FleetAdaptationRuleCreate,
    ) -> FleetAdaptationRuleResponse:
        rule = await self.rule_repo.create(
            FleetAdaptationRule(
                fleet_id=fleet_id,
                workspace_id=workspace_id,
                name=request.name,
                condition=request.condition.model_dump(mode="json"),
                action=request.action.model_dump(mode="json"),
                priority=request.priority,
                is_active=True,
            )
        )
        return FleetAdaptationRuleResponse.model_validate(rule)

    async def list_rules(
        self, fleet_id: UUID, workspace_id: UUID
    ) -> list[FleetAdaptationRuleResponse]:
        return [
            FleetAdaptationRuleResponse.model_validate(item)
            for item in await self.rule_repo.list_by_fleet(fleet_id)
            if item.workspace_id == workspace_id
        ]

    async def update_rule(
        self,
        fleet_id: UUID,
        rule_id: UUID,
        workspace_id: UUID,
        request: FleetAdaptationRuleCreate,
    ) -> FleetAdaptationRuleResponse:
        rule = await self.rule_repo.get_by_id(rule_id, fleet_id)
        if rule is None or rule.workspace_id != workspace_id:
            raise AdaptationError(
                "Adaptation rule was not found", code="FLEET_ADAPTATION_RULE_NOT_FOUND"
            )
        rule.name = request.name
        rule.condition = request.condition.model_dump(mode="json")
        rule.action = request.action.model_dump(mode="json")
        rule.priority = request.priority
        await self.rule_repo.update(rule)
        return FleetAdaptationRuleResponse.model_validate(rule)

    async def deactivate_rule(self, fleet_id: UUID, rule_id: UUID, workspace_id: UUID) -> None:
        rule = await self.rule_repo.get_by_id(rule_id, fleet_id)
        if rule is None or rule.workspace_id != workspace_id:
            raise AdaptationError(
                "Adaptation rule was not found", code="FLEET_ADAPTATION_RULE_NOT_FOUND"
            )
        await self.rule_repo.deactivate(rule)

    async def evaluate_rules_for_fleet(self, fleet_id: UUID) -> list[FleetAdaptationLogResponse]:
        profile = await self.profile_repo.get_latest(fleet_id)
        if profile is None:
            return []
        rules = await self.rule_repo.list_active_by_priority(fleet_id)
        if not rules:
            return []
        current_rules = await self.fleet_service.get_orchestration_rules(
            fleet_id, profile.workspace_id
        )
        current_payload = current_rules.model_dump(mode="json")
        current_payload.pop("id", None)
        current_payload.pop("fleet_id", None)
        current_payload.pop("version", None)
        current_payload.pop("is_current", None)
        current_payload.pop("created_at", None)
        for rule in rules:
            metric = str(rule.condition["metric"])
            operator = str(rule.condition["operator"])
            raw_threshold = rule.condition["threshold"]
            if not isinstance(raw_threshold, (int, float)):
                raise AdaptationError("Adaptation threshold must be numeric")
            threshold = float(raw_threshold)
            value = float(getattr(profile, metric))
            predicate = _OPERATORS[operator]
            if not predicate(value, threshold):
                continue
            patched = self._apply_action(current_payload, rule.action)
            updated = await self.fleet_service.update_orchestration_rules(
                fleet_id,
                profile.workspace_id,
                FleetOrchestrationRulesCreate.model_validate(patched),
            )
            log = await self.log_repo.create(
                FleetAdaptationLog(
                    fleet_id=fleet_id,
                    workspace_id=profile.workspace_id,
                    adaptation_rule_id=rule.id,
                    triggered_at=datetime.now(UTC),
                    before_rules_version=current_rules.version,
                    after_rules_version=updated.version,
                    performance_snapshot={metric: value},
                    is_reverted=False,
                )
            )
            correlation = CorrelationContext(
                workspace_id=profile.workspace_id,
                fleet_id=fleet_id,
                correlation_id=uuid4(),
            )
            await publish_adaptation_applied(
                self.producer,
                FleetAdaptationAppliedPayload(
                    fleet_id=fleet_id,
                    workspace_id=profile.workspace_id,
                    rule_id=rule.id,
                    before_version=current_rules.version,
                    after_version=updated.version,
                ),
                correlation,
            )
            return [FleetAdaptationLogResponse.model_validate(log)]
        return []

    async def evaluate_all_fleets(self) -> list[FleetAdaptationLogResponse]:
        results: list[FleetAdaptationLogResponse] = []
        for fleet_id in await self.rule_repo.list_fleet_ids_with_active_rules():
            results.extend(await self.evaluate_rules_for_fleet(fleet_id))
        return results

    async def list_log(
        self,
        fleet_id: UUID,
        workspace_id: UUID,
        *,
        is_reverted: bool | None = None,
    ) -> list[FleetAdaptationLogResponse]:
        return [
            FleetAdaptationLogResponse.model_validate(item)
            for item in await self.log_repo.list_by_fleet(fleet_id, is_reverted=is_reverted)
            if item.workspace_id == workspace_id
        ]

    async def revert_adaptation(
        self, log_id: UUID, workspace_id: UUID
    ) -> FleetAdaptationLogResponse:
        log = await self.log_repo.get_by_id(log_id)
        if log is None or log.workspace_id != workspace_id:
            raise AdaptationError(
                "Adaptation log entry was not found", code="FLEET_ADAPTATION_LOG_NOT_FOUND"
            )
        if log.is_reverted:
            raise AdaptationError(
                "Adaptation log entry is already reverted", code="FLEET_ADAPTATION_ALREADY_REVERTED"
            )
        reverted_rules = await self.rules_repo.set_current_version(
            log.fleet_id, log.before_rules_version
        )
        if reverted_rules is None:
            raise AdaptationError("Original orchestration rules version was not found")
        reverted = await self.log_repo.mark_reverted(log)
        await publish_fleet_event(
            self.producer,
            FleetEventType.fleet_orchestration_rules_updated,
            FleetRulesUpdatedPayload(
                fleet_id=log.fleet_id,
                workspace_id=workspace_id,
                version=log.before_rules_version,
            ),
            CorrelationContext(
                workspace_id=workspace_id, fleet_id=log.fleet_id, correlation_id=uuid4()
            ),
        )
        return FleetAdaptationLogResponse.model_validate(reverted)

    @staticmethod
    def _apply_action(
        current_payload: dict[str, Any],
        action: dict[str, Any],
    ) -> dict[str, Any]:
        patched = dict(current_payload)
        action_type = str(action["type"])
        value = action["value"]
        if action_type == "set_max_parallelism":
            patched["max_parallelism"] = int(value)
        elif action_type == "set_delegation_strategy":
            patched["delegation"] = dict(patched["delegation"])
            patched["delegation"]["strategy"] = str(value)
        elif action_type == "set_escalation_timeout":
            patched["escalation"] = dict(patched["escalation"])
            patched["escalation"]["timeout_seconds"] = int(value)
        elif action_type == "set_aggregation_strategy":
            patched["aggregation"] = dict(patched["aggregation"])
            patched["aggregation"]["strategy"] = str(value)
        else:
            raise AdaptationError(f"Unsupported adaptation action '{action_type}'")
        return patched
