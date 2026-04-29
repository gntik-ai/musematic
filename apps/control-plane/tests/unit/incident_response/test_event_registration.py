from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.incident_response.events import (
    INCIDENT_RESPONSE_EVENT_SCHEMAS,
    IncidentResolvedPayload,
    IncidentTriggeredPayload,
    register_incident_response_event_types,
)
from uuid import uuid4


def test_register_incident_response_event_types_registers_all_payloads() -> None:
    register_incident_response_event_types()

    for event_type in INCIDENT_RESPONSE_EVENT_SCHEMAS:
        assert event_registry.is_registered(event_type)


def test_incident_event_payload_schemas_validate_correlation_context() -> None:
    register_incident_response_event_types()
    now = datetime.now(UTC)
    correlation = CorrelationContext(correlation_id=uuid4(), workspace_id=uuid4())

    payloads = {
        "incident.triggered": IncidentTriggeredPayload(
            incident_id=uuid4(),
            condition_fingerprint="alert:workspace",
            severity="critical",
            alert_rule_class="kafka_lag",
            related_execution_ids=[uuid4()],
            runbook_scenario="kafka_lag",
            triggered_at=now,
            correlation_context=correlation,
        ).model_dump(mode="json"),
        "incident.resolved": IncidentResolvedPayload(
            incident_id=uuid4(),
            condition_fingerprint="alert:workspace",
            severity="critical",
            status="resolved",
            resolved_at=now,
            correlation_context=correlation,
        ).model_dump(mode="json"),
    }

    for event_type, payload in payloads.items():
        validated = event_registry.validate(event_type, payload)
        assert validated.correlation_context.correlation_id == correlation.correlation_id
