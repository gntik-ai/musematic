from __future__ import annotations

import pytest

from suites.observability._helpers import assert_dashboard_load_budget, grafana_dashboard, panel_links, panel_titles, panels

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_d21_governance_dashboard_loads_realtime_pipeline_panels(grafana_client) -> None:
    dashboard = await grafana_dashboard(grafana_client, "d21-governance-pipeline")
    assert_dashboard_load_budget(dashboard)
    assert dashboard["refresh"] in {"15s", "10s", "5s"}
    titles = panel_titles(dashboard)
    assert {
        "Observer Signal Volume",
        "Verdict Rate",
        "Verdicts by Type",
        "Enforcement Actions",
        "Per-Chain Latency",
        "Top Offending Agents",
        "Verdict Rationale Drilldown",
    } <= titles
    drilldown = next(panel for panel in panels(dashboard) if panel.get("title") == "Verdict Rationale Drilldown")
    assert any("governance" in str(link.get("url")) for link in panel_links(drilldown)) or "rationale" in str(
        drilldown.get("targets")
    )
