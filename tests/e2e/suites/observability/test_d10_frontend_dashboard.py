from __future__ import annotations

import pytest

from suites.observability._helpers import assert_dashboard_load_budget, grafana_dashboard, panel_titles, panels

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_d10_frontend_dashboard_loads_client_server_correlation_panels(grafana_client) -> None:
    dashboard = await grafana_dashboard(grafana_client, "d10-frontend-web-logs")
    assert_dashboard_load_budget(dashboard)
    titles = panel_titles(dashboard)
    assert {
        "Client JS Errors",
        "Next.js Server Logs",
        "Correlated API Errors",
        "Slow Page Loads",
        "Source Maps Available",
    } <= titles
    assert any(variable.get("name") == "user_id" for variable in dashboard["templating"]["list"])
    correlated = next(panel for panel in panels(dashboard) if panel.get("title") == "Correlated API Errors")
    assert "correlation_id" in correlated["targets"][0]["expr"]
