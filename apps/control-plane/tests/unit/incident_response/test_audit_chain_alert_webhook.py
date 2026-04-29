from __future__ import annotations

import hashlib
from platform.incident_response import router
from platform.incident_response.schemas import IncidentRef
from uuid import uuid4

import pytest


class TriggerStub:
    def __init__(self) -> None:
        self.signals = []

    async def fire(self, signal):
        self.signals.append(signal)
        return IncidentRef(incident_id=uuid4())


@pytest.mark.asyncio
async def test_audit_chain_anomaly_webhook_fires_incident_trigger(monkeypatch) -> None:
    trigger = TriggerStub()
    monkeypatch.setattr(router, "get_incident_trigger", lambda: trigger)

    response = await router.receive_audit_chain_anomaly_alert(
        {
            "alerts": [
                {
                    "labels": {
                        "alertname": "AuditChainAnomaly",
                        "entry_hash": "hash-1",
                        "severity": "critical",
                    },
                    "annotations": {"description": "hash invalid at sequence 42"},
                }
            ]
        }
    )

    assert response.incident_id
    assert len(trigger.signals) == 1
    signal = trigger.signals[0]
    assert signal.alert_rule_class == "audit_chain_anomaly"
    assert signal.severity.value == "critical"
    assert signal.title == "Audit chain integrity violation"
    assert signal.description == "hash invalid at sequence 42"
    assert signal.runbook_scenario == "audit-chain-anomaly"
    assert signal.condition_fingerprint == hashlib.sha256(
        b"audit_chain_anomaly:hash-1"
    ).hexdigest()
