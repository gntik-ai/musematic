from __future__ import annotations

import pytest

from suites.observability._helpers import (
    BASELINE_DASHBOARDS,
    assert_dashboard_load_budget,
    grafana_dashboard,
    load_dashboard_file,
    panel_links,
    panel_titles,
    panels,
)

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.asyncio]


async def test_platform_overview_exposes_metric_to_log_pivot(grafana_client) -> None:
    dashboard = await grafana_dashboard(grafana_client, "platform-overview")
    assert_dashboard_load_budget(dashboard)
    assert "View Related Logs" in panel_titles(dashboard)


def test_baseline_metric_dashboards_have_view_related_logs_links() -> None:
    missing: dict[str, list[str]] = {}
    for uid, filename in BASELINE_DASHBOARDS.items():
        if uid == "platform-overview":
            continue
        dashboard = load_dashboard_file(filename)
        for panel in panels(dashboard):
            if panel.get("datasource", {}).get("type") != "prometheus":
                continue
            links = panel_links(panel)
            if not any(link.get("title") == "View related logs" for link in links):
                missing.setdefault(uid, []).append(str(panel.get("title")))
    assert missing == {}
