from __future__ import annotations

import asyncio
import json
import os
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[4]
DASHBOARD_DIR = ROOT / "deploy/helm/observability/templates/dashboards"

REQUIRED_FIELDS = {"timestamp", "level", "service", "bounded_context", "message"}
OPTIONAL_FIELDS = {
    "trace_id",
    "span_id",
    "correlation_id",
    "workspace_id",
    "goal_id",
    "user_id",
    "execution_id",
}
LEVELS = {"debug", "info", "warn", "error", "fatal"}

D8_D21_DASHBOARDS = {
    "d8-control-plane-logs": "control-plane-logs.yaml",
    "d9-go-services-logs": "go-services-logs.yaml",
    "d10-frontend-web-logs": "frontend-web-logs.yaml",
    "d11-audit-event-stream": "audit-event-stream.yaml",
    "d12-cross-service-errors": "cross-service-errors.yaml",
    "d13-privacy-compliance": "privacy-compliance.yaml",
    "d14-security-compliance": "security-compliance.yaml",
    "cost-governance": "cost-governance.yaml",
    "multi-region-ops": "multi-region-ops.yaml",
    "d17-model-catalog": "model-catalog.yaml",
    "notifications-channels": "notifications-channels.yaml",
    "incident-response-runbooks": "incident-response.yaml",
    "d20-goal-lifecycle": "goal-lifecycle.yaml",
    "d21-governance-pipeline": "governance-pipeline.yaml",
}

BASELINE_DASHBOARDS = {
    "platform-overview": "platform-overview.yaml",
    "workflow-execution": "workflow-execution.yaml",
    "reasoning-engine": "reasoning-engine.yaml",
    "data-stores": "data-stores.yaml",
    "fleet-health": "fleet-health.yaml",
    "cost-intelligence": "cost-intelligence.yaml",
    "self-correction": "self-correction.yaml",
    "trust-content-moderation": "trust-content-moderation.yaml",
}


def unique_event(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def strict_data_enabled() -> bool:
    return os.environ.get("MUSEMATIC_E2E_OBSERVABILITY_STRICT_DATA") == "1"


async def push_loki_log(
    loki_client: httpx.AsyncClient,
    *,
    service: str,
    bounded_context: str,
    level: str,
    message: str,
    fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    now = time.time_ns()
    event = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now / 1_000_000_000)),
        "level": level,
        "service": service,
        "bounded_context": bounded_context,
        "message": message,
        **(fields or {}),
    }
    response = await loki_client.post(
        "/loki/api/v1/push",
        json={
            "streams": [
                {
                    "stream": {
                        "service": service,
                        "bounded_context": bounded_context,
                        "level": level,
                    },
                    "values": [[str(now), json.dumps(event, separators=(",", ":"))]],
                }
            ]
        },
    )
    assert response.status_code in {200, 204}, response.text
    return event


async def query_loki_until(
    loki_client: httpx.AsyncClient,
    query: str,
    predicate,
    *,
    timeout: float = 15.0,
    interval: float = 1.0,
) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout
    start_ns = int((time.time() - timeout - 5) * 1_000_000_000)
    last_streams: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        response = await loki_client.get(
            "/loki/api/v1/query_range",
            params={"query": query, "start": start_ns, "limit": 1000},
        )
        response.raise_for_status()
        last_streams = response.json().get("data", {}).get("result", [])
        if predicate(last_streams):
            return last_streams
        await asyncio.sleep(interval)
    raise AssertionError(f"Loki query {query!r} did not satisfy predicate: {last_streams!r}")


def log_lines(streams: Iterable[dict[str, Any]]) -> list[tuple[dict[str, str], dict[str, Any]]]:
    rows: list[tuple[dict[str, str], dict[str, Any]]] = []
    for stream in streams:
        labels = stream.get("stream", {})
        for _ts, line in stream.get("values", []):
            rows.append((labels, json.loads(line)))
    return rows


async def grafana_dashboard(grafana_client: httpx.AsyncClient, uid: str) -> dict[str, Any]:
    start = time.perf_counter()
    response = await grafana_client.get(f"/api/dashboards/uid/{uid}")
    elapsed = time.perf_counter() - start
    assert response.status_code == 200, response.text
    payload = response.json()
    dashboard = payload.get("dashboard")
    assert isinstance(dashboard, dict)
    dashboard["_api_load_seconds"] = elapsed
    return dashboard


def load_dashboard_file(filename: str) -> dict[str, Any]:
    text = (DASHBOARD_DIR / filename).read_text(encoding="utf-8")
    marker_index = text.index(": |\n") + len(": |\n")
    block = text[marker_index:]
    json_text = "\n".join(
        line[4:] if line.startswith("    ") else line for line in block.splitlines() if line.strip()
    )
    return json.loads(json_text)


def panels(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    return [panel for panel in dashboard.get("panels", []) if isinstance(panel, dict)]


def panel_titles(dashboard: dict[str, Any]) -> set[str]:
    return {str(panel.get("title")) for panel in panels(dashboard)}


def panel_links(panel: dict[str, Any]) -> list[dict[str, Any]]:
    links = list(panel.get("links", []))
    defaults = panel.get("fieldConfig", {}).get("defaults", {})
    links.extend(defaults.get("links", []))
    return [link for link in links if isinstance(link, dict)]


def assert_dashboard_load_budget(dashboard: dict[str, Any], *, seconds: float = 5.0) -> None:
    elapsed = dashboard.get("_api_load_seconds", 0)
    assert elapsed <= seconds, f"{dashboard.get('uid')} loaded in {elapsed:.3f}s"


def require_live_alert_fire() -> None:
    if os.environ.get("MUSEMATIC_E2E_ALERT_FIRE") != "1":
        pytest.skip("Set MUSEMATIC_E2E_ALERT_FIRE=1 to run long live alert firing checks")


def require_live_retention() -> None:
    if os.environ.get("MUSEMATIC_E2E_RETENTION") != "1":
        pytest.skip("Set MUSEMATIC_E2E_RETENTION=1 to run clock-advanced retention checks")
