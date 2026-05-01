from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

WORKSPACE_ID = "11111111-1111-4111-8111-111111111111"
USER_ID = "99999999-9999-4999-8999-999999999999"
NOW = "2026-05-01T10:00:00.000Z"
SCENARIO_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
REPORT_ID = "44444444-4444-4444-8444-444444444444"
DISCOVERY_SESSION_ID = "session-1"
HYPOTHESIS_ID = "hypothesis-1"
EXPERIMENT_ID = "experiment-1"


@pytest_asyncio.fixture
async def ui_page() -> AsyncIterator[Any]:
    playwright_api = pytest.importorskip("playwright.async_api")
    async with playwright_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            headless=os.environ.get("MUSEMATIC_E2E_UI_HEADLESS", "1") != "0",
        )
        page = await browser.new_page()
        await install_authenticated_state(page)
        try:
            yield page
        finally:
            await browser.close()


async def install_authenticated_state(
    page: Any,
    *,
    workspace_id: str = WORKSPACE_ID,
    email: str = "e2e-user@musematic.dev",
    roles: list[str] | None = None,
) -> None:
    user = {
        "id": USER_ID,
        "email": email,
        "displayName": "E2E User",
        "avatarUrl": None,
        "roles": roles or ["workspace_admin", "superadmin", "evaluator", "researcher"],
        "workspaceId": workspace_id,
        "mfaEnrolled": True,
    }
    workspace = {
        "id": workspace_id,
        "name": "E2E Workspace",
        "slug": "e2e",
        "description": "UI E2E workspace",
        "memberCount": 3,
        "createdAt": NOW,
    }
    script = f"""
    (() => {{
      const style = document.createElement("style");
      style.textContent = ".tsqd-parent-container,[data-nextjs-dev-tools-button]{{display:none!important}}";
      document.documentElement.appendChild(style);
      window.localStorage.setItem("auth-storage", JSON.stringify({{
        state: {{
          user: {json.dumps(user)},
          accessToken: "mock-access-token",
          refreshToken: "mock-refresh-token",
          isAuthenticated: true,
          isLoading: false
        }},
        version: 0
      }}));
      window.localStorage.setItem("workspace-storage", JSON.stringify({{
        state: {{
          currentWorkspace: {json.dumps(workspace)},
          sidebarCollapsed: false
        }},
        version: 0
      }}));
      window.sessionStorage.clear();
    }})();
    """
    await page.add_init_script(script=script)


async def fulfill_json(route: Any, payload: Any, status: int = 200) -> None:
    await route.fulfill(
        status=status,
        content_type="application/json",
        body=json.dumps(payload),
    )


async def fulfill_xml(route: Any, body: str, content_type: str) -> None:
    await route.fulfill(status=200, content_type=content_type, body=body)


async def assert_no_serious_axe_violations(page: Any) -> None:
    from journeys.helpers.axe_runner import run_axe_scan

    allowlist = Path(__file__).resolve().parents[1] / "journeys/fixtures/axe_allowlist.json"
    violations = await run_axe_scan(page, allowlist, impact="serious")
    assert violations == []


async def route_status_app_apis(
    page: Any,
    *,
    snapshot: dict[str, Any] | None = None,
) -> None:
    status_snapshot = snapshot or public_status_snapshot()

    async def handler(route: Any) -> None:
        url = route.request.url
        path = _path(url)
        if path == "/api/v1/public/status":
            await fulfill_json(route, status_snapshot)
            return
        if path == "/api/v1/public/incidents":
            await fulfill_json(
                route,
                {
                    "incidents": status_snapshot["active_incidents"]
                    + status_snapshot["recently_resolved_incidents"],
                    "next_cursor": None,
                },
            )
            return
        if path.startswith("/api/v1/public/components/"):
            component_id = path.rsplit("/", 1)[-1]
            await fulfill_json(route, component_detail(component_id))
            return
        if path.endswith("/status/feed.rss"):
            await fulfill_xml(route, rss_feed(), "application/rss+xml")
            return
        if path.endswith("/status/feed.atom"):
            await fulfill_xml(route, atom_feed(), "application/atom+xml")
            return
        if path.startswith("/api/v1/public/subscribe/"):
            await fulfill_json(route, {"message": "accepted"}, status=202)
            return
        await fulfill_json(route, {"detail": f"unhandled route {path}"}, status=404)

    await page.route("**/api/v1/**", handler)


async def route_platform_shell_apis(
    page: Any,
    *,
    maintenance_state: str = "scheduled",
    read_status: int = 200,
) -> dict[str, int]:
    calls = {"write_attempts": 0}

    async def handler(route: Any) -> None:
        request = route.request
        path = _path(request.url)
        method = request.method
        if path == "/api/v1/me/platform-status":
            await fulfill_json(route, my_platform_status(maintenance_state))
            return
        if path == "/api/v1/maintenance/windows/active":
            await fulfill_json(
                route,
                my_platform_status("started")["active_maintenance"],
            )
            return
        if path == "/api/v1/maintenance/windows":
            await fulfill_json(route, [])
            return
        if path == "/api/v1/regions" or path.startswith("/api/v1/regions/"):
            await fulfill_json(route, [])
            return
        if path.startswith("/api/v1/admin/maintenance/windows") and method == "POST":
            calls["write_attempts"] += 1
            await fulfill_json(
                route,
                {
                    "code": "platform.maintenance.blocked",
                    "message": "Writes are blocked during maintenance.",
                    "details": {
                        "window_end_at": "2026-05-01T11:00:00.000Z",
                        "retry_after_seconds": 600,
                    },
                },
                status=503,
            )
            return
        if method == "GET":
            await fulfill_json(route, {"items": [], "status": "ok"}, status=read_status)
            return
        await fulfill_json(route, {"status": "ok"}, status=200)

    await page.route("**/api/v1/**", handler)
    return calls


async def route_simulation_apis(page: Any) -> dict[str, list[dict[str, Any]]]:
    state: dict[str, list[dict[str, Any]]] = {"created": [], "runs": []}

    async def handler(route: Any) -> None:
        request = route.request
        path = _path(request.url)
        method = request.method
        if path == "/api/v1/me/platform-status":
            await fulfill_json(route, my_platform_status("none"))
            return
        if path == "/api/v1/simulations/scenarios" and method == "GET":
            await fulfill_json(route, {"items": [simulation_scenario()], "next_cursor": None})
            return
        if path == "/api/v1/simulations/scenarios" and method == "POST":
            payload = _request_json(request)
            created = simulation_scenario(name=payload.get("name", "Scenario"))
            state["created"].append(created)
            await fulfill_json(route, created, status=201)
            return
        if path == f"/api/v1/simulations/scenarios/{SCENARIO_ID}" and method == "GET":
            await fulfill_json(route, simulation_scenario())
            return
        if path == f"/api/v1/simulations/scenarios/{SCENARIO_ID}" and method == "PUT":
            await fulfill_json(route, simulation_scenario(name="Updated regression scenario"))
            return
        if path == f"/api/v1/simulations/scenarios/{SCENARIO_ID}" and method == "DELETE":
            await fulfill_json(route, {"status": "archived"})
            return
        if path == f"/api/v1/simulations/scenarios/{SCENARIO_ID}/run" and method == "POST":
            payload = _request_json(request)
            queued = [RUN_ID, "33333333-3333-4333-8333-333333333334"][
                : int(payload.get("iterations", 1))
            ]
            state["runs"].append({"iterations": len(queued), "queued": queued})
            await fulfill_json(
                route,
                {"scenario_id": SCENARIO_ID, "queued_runs": queued, "iterations": len(queued)},
            )
            return
        if path == f"/api/v1/simulations/{RUN_ID}":
            await fulfill_json(route, simulation_run())
            return
        if path == f"/api/v1/simulations/comparisons/{REPORT_ID}":
            await fulfill_json(route, simulation_comparison())
            return
        await fulfill_json(route, {"items": [], "next_cursor": None})

    await page.route("**/api/v1/**", handler)
    return state


async def route_discovery_apis(page: Any) -> dict[str, list[dict[str, Any]]]:
    state: dict[str, list[dict[str, Any]]] = {"experiments": []}

    async def handler(route: Any) -> None:
        request = route.request
        path = _path(request.url)
        method = request.method
        if path == "/api/v1/me/platform-status":
            await fulfill_json(route, my_platform_status("none"))
            return
        if path == f"/api/v1/discovery/sessions/{DISCOVERY_SESSION_ID}":
            await fulfill_json(route, discovery_session())
            return
        if path == f"/api/v1/discovery/sessions/{DISCOVERY_SESSION_ID}/hypotheses":
            if _query(request.url).get("status") == ["merged"]:
                await fulfill_json(route, {"items": [], "next_cursor": None})
                return
            await fulfill_json(route, {"items": discovery_hypotheses(), "next_cursor": None})
            return
        if path == f"/api/v1/discovery/sessions/{DISCOVERY_SESSION_ID}/experiments":
            await fulfill_json(
                route,
                {"items": state["experiments"] or [discovery_experiment()], "next_cursor": None},
            )
            return
        if path == f"/api/v1/discovery/hypotheses/{HYPOTHESIS_ID}":
            await fulfill_json(route, discovery_hypotheses()[0])
            return
        if path == f"/api/v1/discovery/hypotheses/{HYPOTHESIS_ID}/critiques":
            await fulfill_json(route, discovery_critiques())
            return
        if path == f"/api/v1/discovery/hypotheses/{HYPOTHESIS_ID}/experiment" and method == "POST":
            experiment = discovery_experiment(execution_status="running")
            state["experiments"].append(experiment)
            await fulfill_json(route, experiment, status=201)
            return
        if path.endswith("/clusters"):
            await fulfill_json(route, {"items": [{"cluster_id": "cluster-1"}], "next_cursor": None})
            return
        await fulfill_json(route, {"items": [], "next_cursor": None})

    await page.route("**/api/v1/**", handler)
    return state


async def expect_text(page: Any, text: str) -> None:
    playwright_api = pytest.importorskip("playwright.async_api")
    await playwright_api.expect(page.get_by_text(text).first).to_be_visible()


def _path(url: str) -> str:
    from urllib.parse import urlparse

    return urlparse(url).path.rstrip("/") or "/"


def _query(url: str) -> dict[str, list[str]]:
    from urllib.parse import parse_qs, urlparse

    return parse_qs(urlparse(url).query)


def _request_json(request: Any) -> dict[str, Any]:
    try:
        return json.loads(request.post_data or "{}")
    except json.JSONDecodeError:
        return {}


def public_status_snapshot(state: str = "degraded") -> dict[str, Any]:
    return {
        "snapshot_id": "snapshot-1",
        "generated_at": NOW,
        "overall_state": state,
        "components": [
            {
                "id": "control-plane-api",
                "name": "Control Plane API",
                "state": "degraded",
                "last_check_at": NOW,
                "uptime_30d_pct": 99.91,
            },
            {
                "id": "reasoning-engine",
                "name": "Reasoning Engine",
                "state": "operational",
                "last_check_at": NOW,
                "uptime_30d_pct": 99.99,
            },
        ],
        "active_incidents": [
            {
                "id": "incident-1",
                "title": "Elevated API latency",
                "severity": "warning",
                "started_at": NOW,
                "resolved_at": None,
                "components_affected": ["control-plane-api"],
                "last_update_at": NOW,
                "last_update_summary": "Mitigation is in progress.",
            }
        ],
        "scheduled_maintenance": [],
        "active_maintenance": None,
        "recently_resolved_incidents": [
            {
                "id": "incident-resolved-1",
                "title": "Webhook delivery delay",
                "severity": "info",
                "started_at": "2026-04-30T08:00:00.000Z",
                "resolved_at": "2026-04-30T09:00:00.000Z",
                "components_affected": ["notifications"],
                "last_update_at": "2026-04-30T09:00:00.000Z",
                "last_update_summary": "Delivery queue recovered.",
            }
        ],
        "uptime_30d": {
            "control-plane-api": {"pct": 99.91, "incidents": 1},
            "reasoning-engine": {"pct": 99.99, "incidents": 0},
        },
        "source_kind": "live",
    }


def component_detail(component_id: str) -> dict[str, Any]:
    return {
        "component": {
            "id": component_id,
            "name": component_id.replace("-", " ").title(),
            "state": "degraded",
            "last_check_at": NOW,
            "uptime_30d_pct": 99.91,
        },
        "history": [
            {"date": "2026-05-01", "state": "degraded", "uptime_pct": 99.91},
            {"date": "2026-04-30", "state": "operational", "uptime_pct": 100},
        ],
    }


def rss_feed() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<rss version='2.0'><channel><title>Musematic Platform Status</title>"
        "<item><guid>incident-1</guid><title>Elevated API latency</title></item>"
        "</channel></rss>"
    )


def atom_feed() -> str:
    return (
        "<?xml version='1.0' encoding='UTF-8'?>"
        "<feed xmlns='http://www.w3.org/2005/Atom'><title>Musematic Platform Status</title>"
        "<entry><id>incident-1</id><title>Elevated API latency</title></entry></feed>"
    )


def my_platform_status(state: str) -> dict[str, Any]:
    maintenance = None
    if state in {"scheduled", "started"}:
        starts_at = (
            "2099-05-01T09:30:00.000Z"
            if state == "scheduled"
            else "2000-05-01T09:30:00.000Z"
        )
        maintenance = {
            "window_id": "maintenance-1",
            "title": "Database maintenance",
            "starts_at": starts_at,
            "ends_at": "2099-05-01T11:00:00.000Z",
            "blocks_writes": True,
            "components_affected": ["workflow-engine"],
        }
    return {
        "overall_state": "maintenance" if maintenance else "operational",
        "active_maintenance": maintenance if state in {"scheduled", "started"} else None,
        "active_incidents": [] if state != "incident" else public_status_snapshot()["active_incidents"],
        "affects_my_features": {"workflow-trigger": state in {"scheduled", "started"}},
    }


def simulation_scenario(name: str = "Regression scenario") -> dict[str, Any]:
    return {
        "id": SCENARIO_ID,
        "workspace_id": WORKSPACE_ID,
        "name": name,
        "description": "E2E reusable scenario",
        "agents_config": {"agents": ["ops:triage"]},
        "workflow_template_id": None,
        "mock_set_config": {"llm_provider": "mock-llm"},
        "input_distribution": {"type": "fixed", "values": ["ping"]},
        "twin_fidelity": {"tools": "mock", "planner": "real"},
        "success_criteria": [{"metric": "success_rate", "operator": ">=", "value": 0.95}],
        "run_schedule": None,
        "archived_at": None,
        "created_by": USER_ID,
        "created_at": NOW,
        "updated_at": NOW,
    }


def simulation_run() -> dict[str, Any]:
    return {
        "run_id": RUN_ID,
        "workspace_id": WORKSPACE_ID,
        "name": "Regression scenario run",
        "description": None,
        "status": "completed",
        "digital_twin_ids": [],
        "scenario_config": {"twin_fidelity": {"tools": "mock", "planner": "real"}},
        "scenario_id": SCENARIO_ID,
        "isolation_policy_id": None,
        "controller_run_id": None,
        "started_at": NOW,
        "completed_at": NOW,
        "results": {"simulated_time_ms": 1400},
        "initiated_by": USER_ID,
        "created_at": NOW,
    }


def simulation_comparison() -> dict[str, Any]:
    return {
        "report_id": REPORT_ID,
        "comparison_type": "simulation_vs_production",
        "primary_run_id": RUN_ID,
        "secondary_run_id": None,
        "production_baseline_period": {"reference_execution_id": "prod-exec-1"},
        "prediction_id": None,
        "status": "completed",
        "compatible": True,
        "incompatibility_reasons": [],
        "metric_differences": [
            {
                "metric_name": "latency_ms",
                "primary_value": 1400,
                "secondary_value": 1200,
                "delta": 200,
                "delta_percent": 16.7,
                "direction": "worse",
            }
        ],
        "overall_verdict": "secondary_better",
        "created_at": NOW,
    }


def discovery_session() -> dict[str, Any]:
    return {
        "session_id": DISCOVERY_SESSION_ID,
        "workspace_id": WORKSPACE_ID,
        "research_question": "Which catalyst improves hydrogen yield?",
        "corpus_refs": [],
        "config": {},
        "status": "active",
        "current_cycle": 2,
        "convergence_metrics": None,
        "initiated_by": USER_ID,
        "created_at": NOW,
        "updated_at": NOW,
    }


def discovery_hypotheses() -> list[dict[str, Any]]:
    return [
        {
            "hypothesis_id": HYPOTHESIS_ID,
            "session_id": DISCOVERY_SESSION_ID,
            "title": "Catalyst alpha improves yield",
            "description": "Alpha ligand geometry improves low-temperature yield.",
            "reasoning": "Observed from seed corpus.",
            "confidence": 0.82,
            "generating_agent_fqn": "science:generator",
            "status": "active",
            "elo_score": 1280,
            "rank": 1,
            "wins": 3,
            "losses": 0,
            "draws": 1,
            "cluster_id": "cluster-1",
            "embedding_status": "indexed",
            "rationale_metadata": None,
            "created_at": NOW,
        },
        {
            "hypothesis_id": "hypothesis-2",
            "session_id": DISCOVERY_SESSION_ID,
            "title": "Control catalyst is stable",
            "description": "Gamma underperforms but has stability advantages.",
            "reasoning": "Control observation.",
            "confidence": 0.38,
            "generating_agent_fqn": "science:generator",
            "status": "retired",
            "elo_score": 1110,
            "rank": 2,
            "wins": 0,
            "losses": 2,
            "draws": 0,
            "cluster_id": "cluster-2",
            "embedding_status": "indexed",
            "rationale_metadata": None,
            "created_at": NOW,
        },
    ]


def discovery_experiment(execution_status: str = "completed") -> dict[str, Any]:
    return {
        "experiment_id": EXPERIMENT_ID,
        "hypothesis_id": HYPOTHESIS_ID,
        "session_id": DISCOVERY_SESSION_ID,
        "plan": {"objective": "Validate yield and stability."},
        "governance_status": "approved",
        "governance_violations": [],
        "execution_status": execution_status,
        "sandbox_execution_id": "sandbox-exec-1",
        "results": {},
        "designed_by_agent_fqn": "science:planner",
        "created_at": NOW,
        "updated_at": NOW,
    }


def discovery_critiques() -> dict[str, Any]:
    critique = {
        "critique_id": "critique-1",
        "hypothesis_id": HYPOTHESIS_ID,
        "reviewer_agent_fqn": "science:reviewer",
        "is_aggregated": False,
        "scores": {
            "evidence_strength": {
                "score": 0.78,
                "confidence": 0.8,
                "reasoning": "Multiple seed observations support the hypothesis.",
            }
        },
        "composite_summary": None,
        "created_at": NOW,
    }
    return {"items": [critique], "aggregated": critique | {"is_aggregated": True}}


async def assert_route_called(calls: dict[str, int], key: str) -> None:
    assert calls.get(key, 0) > 0


def noop_fixture() -> Callable[[], None]:
    return lambda: None
