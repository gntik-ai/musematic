from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.cost_governance.events import (
    COST_GOVERNANCE_EVENT_SCHEMAS,
    CostExecutionAttributedPayload,
    CostGovernanceEventType,
    publish_cost_governance_event,
    register_cost_governance_event_types,
)
from uuid import uuid4


def test_register_cost_governance_event_types_registers_all_payloads() -> None:
    register_cost_governance_event_types()

    for event_type in COST_GOVERNANCE_EVENT_SCHEMAS:
        assert event_registry.is_registered(event_type)


def test_cost_event_payload_schemas_validate() -> None:
    register_cost_governance_event_types()
    workspace_id = uuid4()
    now = datetime.now(UTC)

    payloads = {
        "cost.execution.attributed": {
            "attribution_id": uuid4(),
            "execution_id": uuid4(),
            "workspace_id": workspace_id,
            "agent_id": uuid4(),
            "user_id": uuid4(),
            "total_cost_cents": Decimal("12.3400"),
            "currency": "USD",
            "attributed_at": now,
        },
        "cost.budget.threshold.reached": {
            "budget_id": uuid4(),
            "workspace_id": workspace_id,
            "threshold_percentage": 80,
            "period_start": now,
            "period_end": now,
            "spend_cents": Decimal("80.0000"),
            "budget_cents": 100,
        },
        "cost.budget.exceeded": {
            "budget_id": uuid4(),
            "workspace_id": workspace_id,
            "period_start": now,
            "period_end": now,
            "spend_cents": Decimal("120.0000"),
            "budget_cents": 100,
            "override_endpoint": f"/api/v1/costs/workspaces/{workspace_id}/budget/override",
        },
        "cost.anomaly.detected": {
            "anomaly_id": uuid4(),
            "workspace_id": workspace_id,
            "anomaly_type": "sudden_spike",
            "severity": "high",
            "baseline_cents": Decimal("20.0000"),
            "observed_cents": Decimal("120.0000"),
            "detected_at": now,
        },
        "cost.forecast.updated": {
            "forecast_id": uuid4(),
            "workspace_id": workspace_id,
            "period_start": now,
            "period_end": now,
            "forecast_cents": Decimal("250.0000"),
            "computed_at": now,
        },
    }

    for event_type, payload in payloads.items():
        assert event_registry.validate(event_type, payload).model_dump()


class Producer:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []

    async def publish(self, **payload: object) -> None:
        self.messages.append(payload)


async def test_publish_cost_governance_event_uses_workspace_key() -> None:
    producer = Producer()
    workspace_id = uuid4()
    correlation = CorrelationContext(workspace_id=workspace_id, correlation_id=uuid4())
    payload = CostExecutionAttributedPayload(
        attribution_id=uuid4(),
        execution_id=uuid4(),
        workspace_id=workspace_id,
        total_cost_cents=Decimal("1.23"),
        currency="USD",
        attributed_at=datetime.now(UTC),
    )

    await publish_cost_governance_event(
        producer,  # type: ignore[arg-type]
        CostGovernanceEventType.execution_attributed,
        payload,
        correlation,
    )

    assert producer.messages == [
        {
            "topic": "cost-governance.events",
            "key": str(workspace_id),
            "event_type": "cost.execution.attributed",
            "payload": payload.model_dump(mode="json"),
            "correlation_ctx": correlation,
            "source": "platform.cost_governance",
        }
    ]
