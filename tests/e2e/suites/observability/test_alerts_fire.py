from __future__ import annotations

import asyncio

import pytest

from suites.observability._helpers import (
    ROOT,
    push_loki_log,
    query_loki_until,
    require_live_alert_fire,
    unique_event,
)

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


def _loki_alerts_manifest() -> str:
    return (ROOT / "deploy/helm/observability/templates/alerts/loki-alerts.yaml").read_text(
        encoding="utf-8"
    )


def _values_manifest() -> str:
    return (ROOT / "deploy/helm/observability/values.yaml").read_text(encoding="utf-8")


async def test_loki_alert_rules_cover_required_log_signals() -> None:
    manifest = _loki_alerts_manifest()
    for alert in (
        "HighErrorLogRate",
        "SecurityEventSpike",
        "DLPViolationSpike",
        "AuditChainAnomaly",
        "CostAnomalyLogged",
    ):
        assert f"alert: {alert}" in manifest

    assert 'severity: critical' in manifest
    assert 'severity: warning' in manifest
    assert "incident_trigger: audit_chain_anomaly" in manifest
    assert '{service="api",bounded_context="audit",level="error"' in manifest
    assert '{bounded_context="cost_governance"' in manifest


async def test_audit_chain_alert_routes_to_incident_response_webhook() -> None:
    values = _values_manifest()
    assert "receiver: incident-response-audit-chain-anomaly" in values
    assert 'incident_trigger = "audit_chain_anomaly"' in values
    assert "/api/v1/internal/alerts/audit-chain-anomaly" in values
    assert "send_resolved: false" in values


async def test_loki_alert_rules_fire_when_enabled(
    loki_client,
    alertmanager_client,
) -> None:
    require_live_alert_fire()
    event_id = unique_event("audit-chain-alert")
    await push_loki_log(
        loki_client,
        service="api",
        bounded_context="audit",
        level="error",
        message=f"chain mismatch invalid hash {event_id}",
        fields={"correlation_id": event_id, "entry_hash": event_id},
    )
    await query_loki_until(
        loki_client,
        f'{{service="api",bounded_context="audit"}} | json | correlation_id="{event_id}"',
        lambda streams: bool(streams),
        timeout=30.0,
    )

    async def _audit_alert_present() -> bool:
        response = await alertmanager_client.get("/api/v2/alerts")
        response.raise_for_status()
        alerts = response.json()
        return any(
            alert.get("labels", {}).get("alertname") == "AuditChainAnomaly"
            and alert.get("labels", {}).get("incident_trigger") == "audit_chain_anomaly"
            for alert in alerts
        )

    for _ in range(18):
        if await _audit_alert_present():
            return
        await push_loki_log(
            loki_client,
            service="api",
            bounded_context="audit",
            level="error",
            message=f"chain mismatch invalid hash {event_id}",
            fields={"correlation_id": event_id, "entry_hash": event_id},
        )
        await asyncio.sleep(10)

    raise AssertionError("AuditChainAnomaly did not appear in Alertmanager")
