from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from ._chart_lifecycle import helm_install, require_chart_lifecycle_enabled, wait_for_ready_pods

ROOT = Path(__file__).resolve().parents[4]
INVENTORY = ROOT / "specs/085-extended-e2e-journey/contracts/dashboard-inventory.md"


pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.slow]


def _inventory_uids() -> set[str]:
    uids: set[str] = set()
    for line in INVENTORY.read_text(encoding="utf-8").splitlines():
        if line.startswith("| ") and "`" in line:
            parts = line.split("|")
            if len(parts) >= 4 and parts[3].strip().startswith("`"):
                uids.add(parts[3].strip().strip("`"))
    return uids


def test_observability_chart_installs_and_exposes_backends() -> None:
    require_chart_lifecycle_enabled()
    helm_install()
    pods = wait_for_ready_pods()
    assert {pod["metadata"]["name"] for pod in pods}

    auth = httpx.BasicAuth("admin", "admin")
    with httpx.Client(base_url="http://localhost:3000", auth=auth, timeout=30.0) as grafana:
        health = grafana.get("/api/health")
        health.raise_for_status()
        datasources = grafana.get("/api/datasources")
        datasources.raise_for_status()
        names = {item["name"] for item in datasources.json()}
        assert {"Prometheus", "Loki", "Jaeger"} <= names
        for datasource in datasources.json():
            if datasource["name"] in {"Prometheus", "Loki", "Jaeger"}:
                probe = grafana.get(f"/api/datasources/{datasource['id']}/health")
                assert probe.status_code < 500, probe.text
        search = grafana.get("/api/search", params={"type": "dash-db"})
        search.raise_for_status()
        loaded_uids = {item["uid"] for item in search.json()}
        assert _inventory_uids() <= loaded_uids

    with httpx.Client(base_url="http://localhost:9090", timeout=30.0) as prom:
        rules = prom.get("/api/v1/rules")
        rules.raise_for_status()
        serialized = json.dumps(rules.json())
        assert "ServiceDown" in serialized
        assert "HighErrorRate" in serialized

    with httpx.Client(base_url="http://localhost:3100", timeout=30.0) as loki:
        rules = loki.get("/loki/api/v1/rules")
        rules.raise_for_status()
        assert "HighErrorLogRate" in json.dumps(rules.json())
