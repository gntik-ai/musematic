from __future__ import annotations

import pytest

from suites.observability._helpers import (
    BASELINE_DASHBOARDS,
    D8_D21_DASHBOARDS,
    assert_dashboard_load_budget,
    grafana_dashboard,
    load_dashboard_file,
    panels,
    panel_titles,
)

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_all_required_dashboard_files_are_valid_json() -> None:
    for uid, filename in {**D8_D21_DASHBOARDS, **BASELINE_DASHBOARDS}.items():
        dashboard = load_dashboard_file(filename)
        assert dashboard["uid"] == uid
        assert dashboard["title"]
        assert panels(dashboard), f"{filename} has no panels"


async def test_d8_through_d21_dashboard_contracts_are_complete() -> None:
    dashboards = {
        uid: load_dashboard_file(filename) for uid, filename in D8_D21_DASHBOARDS.items()
    }
    assert "Log Volume by Bounded Context" in panel_titles(dashboards["d8-control-plane-logs"])
    assert "Error Rate by Service" in panel_titles(dashboards["d9-go-services-logs"])
    assert "Client JS Errors" in panel_titles(dashboards["d10-frontend-web-logs"])
    assert "Real-Time Audit Feed" in panel_titles(dashboards["d11-audit-event-stream"])
    assert "Error Trend" in panel_titles(dashboards["d12-cross-service-errors"])
    assert "DSR Timeline" in panel_titles(dashboards["d13-privacy-compliance"])
    assert "CVE Counts by Severity" in panel_titles(dashboards["d14-security-compliance"])
    assert "Cost Governance Log Stream" in panel_titles(dashboards["cost-governance"])
    assert "Replication Lag by Component" in panel_titles(dashboards["multi-region-ops"])
    assert "Model Usage Distribution" in panel_titles(dashboards["d17-model-catalog"])
    assert "p95 Delivery Latency" in panel_titles(dashboards["notifications-channels"])
    assert "Open Incidents by Severity" in panel_titles(dashboards["incident-response-runbooks"])
    assert "Goals by State" in panel_titles(dashboards["d20-goal-lifecycle"])
    assert "Verdict Rationale Drilldown" in panel_titles(dashboards["d21-governance-pipeline"])


async def test_all_observability_dashboards_load_within_budget(grafana_client) -> None:
    for uid in (*D8_D21_DASHBOARDS.keys(), *BASELINE_DASHBOARDS.keys()):
        dashboard = await grafana_dashboard(grafana_client, uid)
        assert_dashboard_load_budget(dashboard, seconds=5.0)
