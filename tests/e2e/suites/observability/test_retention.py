from __future__ import annotations

import pytest

from suites.observability._helpers import ROOT, push_loki_log, query_loki_until, require_live_retention, unique_event

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


def _values_manifest() -> str:
    return (ROOT / "deploy/helm/observability/values.yaml").read_text(encoding="utf-8")


async def test_loki_retention_policy_is_configured_for_annual_finance_cycle() -> None:
    values = _values_manifest()
    assert "retention_period: 336h" in values
    assert "hot: 336h" in values
    assert "cold: 2160h" in values
    assert "retention_enabled: true" in values
    assert "delete_request_store: s3" in values
    assert "platform-loki-chunks" in values


async def test_live_retention_boundary_when_clock_control_is_enabled(loki_client) -> None:
    require_live_retention()
    event_id = unique_event("retention-boundary")
    await push_loki_log(
        loki_client,
        service="api",
        bounded_context="observability",
        level="info",
        message=f"retention boundary {event_id}",
        fields={"correlation_id": event_id},
    )
    await query_loki_until(
        loki_client,
        f'{{service="api",bounded_context="observability"}} | json | correlation_id="{event_id}"',
        lambda streams: bool(streams),
        timeout=30.0,
    )
