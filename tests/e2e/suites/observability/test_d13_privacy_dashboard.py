from __future__ import annotations

import pytest

from suites.observability._helpers import (
    assert_dashboard_load_budget,
    grafana_dashboard,
    load_dashboard_file,
    panel_links,
    panel_titles,
    panels,
    strict_data_enabled,
)

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_d13_privacy_dashboard_loads_filters_and_drills_down(grafana_client, prom_client) -> None:
    dashboard = await grafana_dashboard(grafana_client, "d13-privacy-compliance")
    assert_dashboard_load_budget(dashboard)
    titles = panel_titles(dashboard)
    assert {
        "DSR Timeline",
        "DSR by Type",
        "Cascade Deletion Progress",
        "DLP Events by Classification",
        "Residency Violations",
        "PIA Pending Review",
        "Consent Grants by Type",
    } <= titles
    assert any(variable.get("name") == "workspace" for variable in dashboard["templating"]["list"])

    static_dashboard = load_dashboard_file("privacy-compliance.yaml")
    assert any(
        "privacy_compliance" in str(link.get("url"))
        for panel in panels(static_dashboard)
        for link in panel_links(panel)
    )

    if not strict_data_enabled():
        return
    response = await prom_client.get("/api/v1/query", params={"query": "privacy_dsr_requests_total"})
    response.raise_for_status()
    results = response.json().get("data", {}).get("result", [])
    if not results:
        pytest.skip("privacy-compliance BC has no seeded metrics; dashboard empty state is acceptable")
