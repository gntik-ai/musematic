from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.trust.dependencies import build_contract_service
from platform.trust.events import ContractEnforcementPayload, TrustEventType, make_correlation
from platform.trust.models import AgentContract
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = logging.getLogger(__name__)


class ContractMonitorConsumer:
    def __init__(
        self,
        *,
        settings: Any,
        producer: EventProducer | None,
        session_factory: Callable[[], AsyncSession],
    ) -> None:
        self.settings = settings
        self.producer = producer
        self.session_factory = session_factory

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            "workflow.runtime",
            f"{self.settings.kafka.consumer_group}.trust-contract-monitor",
            self.handle_event,
        )
        manager.subscribe(
            "runtime.lifecycle",
            f"{self.settings.kafka.consumer_group}.trust-contract-monitor-lifecycle",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        payload = envelope.payload
        event_type = str(payload.get("event_type") or envelope.event_type)
        execution_id = self._uuid_or_none(payload.get("execution_id"))
        execution_id = execution_id or envelope.correlation_context.execution_id
        interaction_id = self._uuid_or_none(payload.get("interaction_id"))
        interaction_id = interaction_id or envelope.correlation_context.interaction_id

        async with self.session_factory() as session:
            contract_service = build_contract_service(session=session, producer=self.producer)
            target_type: str | None = None
            target_id: UUID | None = None
            snapshot: dict[str, object] | None = None

            if execution_id is not None:
                target_type = "execution"
                target_id = execution_id
                snapshot = await contract_service.get_attached_execution_snapshot(execution_id)
            elif interaction_id is not None:
                target_type = "interaction"
                target_id = interaction_id
                snapshot = await contract_service.get_attached_interaction_snapshot(interaction_id)

            if target_type is None or target_id is None or snapshot is None:
                return

            contract_id = self._uuid_or_none(snapshot.get("id"))
            if contract_id is None:
                return
            contract = await contract_service.repository.get_contract(contract_id)
            if contract is None:
                return

            for breach in self._evaluate_breaches(
                event_type=event_type,
                payload=payload,
                snapshot=snapshot,
            ):
                existing, _ = await contract_service.repository.list_breach_events(
                    contract.id,
                    target_type=target_type,
                )
                if any(
                    item.target_id == target_id
                    and item.breached_term == str(breach["term"])
                    and item.enforcement_action == str(breach["action"])
                    for item in existing
                ):
                    continue
                outcome = await self._enforce(contract, target_type, target_id, breach["action"])
                breach_record = await contract_service.record_breach(
                    contract=contract,
                    target_type=target_type,
                    target_id=target_id,
                    breached_term=str(breach["term"]),
                    observed_value=dict(cast(dict[str, object], breach["observed"])),
                    threshold_value=dict(cast(dict[str, object], breach["threshold"])),
                    enforcement_action=str(breach["action"]),
                    enforcement_outcome=outcome,
                )
                await contract_service.publish_enforcement(
                    contract=contract,
                    breach_event_id=breach_record.id,
                    target_type=target_type,
                    target_id=target_id,
                    action=str(breach["action"]),
                    outcome=outcome,
                )
            await session.commit()

    def _evaluate_breaches(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        snapshot: dict[str, object],
    ) -> list[dict[str, object]]:
        breaches: list[dict[str, object]] = []
        enforcement_action = str(snapshot.get("enforcement_policy") or "warn")

        cost_limit = snapshot.get("cost_limit_tokens")
        token_count = payload.get("token_count")
        if (
            event_type.startswith("workflow.runtime")
            and isinstance(cost_limit, int)
            and isinstance(token_count, int)
            and token_count > cost_limit
        ):
            breaches.append(
                {
                    "term": "cost_limit",
                    "observed": {"token_count": token_count},
                    "threshold": {"cost_limit_tokens": cost_limit},
                    "action": enforcement_action,
                }
            )

        time_limit = snapshot.get("time_constraint_seconds")
        elapsed_seconds = payload.get("elapsed_seconds") or payload.get("duration_seconds")
        if (
            isinstance(time_limit, int)
            and isinstance(elapsed_seconds, (int, float))
            and float(elapsed_seconds) > float(time_limit)
        ):
            breaches.append(
                {
                    "term": "time_constraint",
                    "observed": {"elapsed_seconds": float(elapsed_seconds)},
                    "threshold": {"time_constraint_seconds": time_limit},
                    "action": enforcement_action,
                }
            )

        quality_thresholds = snapshot.get("quality_thresholds")
        if (
            event_type.endswith("completed")
            and isinstance(quality_thresholds, dict)
            and quality_thresholds
        ):
            comparable_keys: list[tuple[str, str]] = []
            for key in quality_thresholds:
                payload_key = key
                if key.endswith(("_min", "_max")):
                    payload_key = key[:-4]
                if payload_key in payload:
                    comparable_keys.append((key, payload_key))
                elif key in payload:
                    comparable_keys.append((key, key))
            if not comparable_keys:
                breaches.append(
                    {
                        "term": "quality_threshold",
                        "observed": {"status": "not_evaluated"},
                        "threshold": dict(quality_thresholds),
                        "action": enforcement_action,
                    }
                )
            else:
                for key, payload_key in comparable_keys:
                    expected = quality_thresholds[key]
                    observed = payload.get(payload_key)
                    if not isinstance(expected, (int, float)) or not isinstance(
                        observed,
                        (int, float),
                    ):
                        continue
                    failed = False
                    if key.endswith("_min"):
                        failed = float(observed) < float(expected)
                    elif key.endswith("_max"):
                        failed = float(observed) > float(expected)
                    if failed:
                        breaches.append(
                            {
                                "term": "quality_threshold",
                                "observed": {key: float(observed)},
                                "threshold": {key: float(expected)},
                                "action": enforcement_action,
                            }
                        )
        return breaches

    async def _enforce(
        self,
        contract: AgentContract,
        target_type: str,
        target_id: UUID,
        action: object,
    ) -> str:
        action_text = str(action)
        if action_text == "warn":
            LOGGER.warning(
                "Contract breach warning for %s %s contract=%s",
                target_type,
                target_id,
                contract.id,
            )
            return "success"
        if self.producer is None:
            if action_text == "terminate":
                return "failed: quarantine_required"
            return "failed"
        try:
            payload = ContractEnforcementPayload(
                contract_id=contract.id,
                breach_event_id=None,
                action=action_text,
                outcome="pending",
                target_type=target_type,
                target_id=target_id,
                occurred_at=datetime.now(UTC),
            )
            await self.producer.publish(
                topic="monitor.alerts",
                key=str(target_id),
                event_type=TrustEventType.contract_enforcement.value,
                payload=payload.model_dump(mode="json"),
                correlation_ctx=make_correlation(),
                source="platform.trust",
            )
            return "success"
        except Exception:
            LOGGER.exception("Contract enforcement publish failed")
            if action_text == "terminate":
                return "failed: quarantine_required"
            return "failed"

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
