from __future__ import annotations

import pytest

from suites.observability._helpers import assert_dashboard_load_budget, grafana_dashboard, panel_links, panel_titles, panels

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_d14_security_dashboard_loads_supply_chain_panels(grafana_client) -> None:
    dashboard = await grafana_dashboard(grafana_client, "d14-security-compliance")
    assert_dashboard_load_budget(dashboard)
    titles = panel_titles(dashboard)
    assert {
        "SBOM Publication Status",
        "CVE Counts by Severity",
        "Pen-Test Findings by Status",
        "Upcoming Rotations",
        "Active JIT Grants",
        "Audit Chain Integrity",
    } <= titles

    cve_panel = next(panel for panel in panels(dashboard) if panel.get("title") == "CVE Counts by Severity")
    assert "dependency_scope" in cve_panel["targets"][0]["expr"]
    jit_panel = next(panel for panel in panels(dashboard) if panel.get("title") == "Active JIT Grants")
    assert any("security_compliance" in str(link.get("url")) for link in panel_links(jit_panel))
