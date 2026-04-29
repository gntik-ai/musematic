from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[4]
CHART = ROOT / "deploy/helm/observability"
VALUES_E2E = CHART / "values-e2e.yaml"
NAMESPACE = os.environ.get("OBSERVABILITY_NAMESPACE", "platform-observability")
RELEASE = os.environ.get("OBSERVABILITY_RELEASE_NAME", "observability")


def require_chart_lifecycle_enabled() -> None:
    if os.environ.get("MUSEMATIC_E2E_CHART_LIFECYCLE") != "1":
        pytest.skip("Set MUSEMATIC_E2E_CHART_LIFECYCLE=1 to run chart lifecycle checks")


def run(args: list[str], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def assert_success(result: subprocess.CompletedProcess[str]) -> None:
    assert result.returncode == 0, result.stdout


def helm_install(*, values: Path = VALUES_E2E) -> None:
    assert_success(
        run(
            [
                "helm",
                "upgrade",
                "--install",
                RELEASE,
                str(CHART),
                "--namespace",
                NAMESPACE,
                "--create-namespace",
                "-f",
                str(values),
                "--wait",
                "--timeout",
                "10m",
            ],
            timeout=900,
        )
    )


def helm_uninstall() -> None:
    result = run(["helm", "uninstall", RELEASE, "--namespace", NAMESPACE], timeout=300)
    assert result.returncode in {0, 1}, result.stdout


def kubectl_json(args: list[str]) -> dict[str, Any]:
    result = run(["kubectl", *args, "-o", "json"], timeout=120)
    assert_success(result)
    return json.loads(result.stdout)


def wait_for_ready_pods(timeout_seconds: int = 300) -> list[dict[str, Any]]:
    deadline = time.monotonic() + timeout_seconds
    last_items: list[dict[str, Any]] = []
    while time.monotonic() < deadline:
        payload = kubectl_json(
            [
                "-n",
                NAMESPACE,
                "get",
                "pods",
                "-l",
                f"app.kubernetes.io/instance={RELEASE}",
            ]
        )
        last_items = payload.get("items", [])
        if last_items and all(_pod_ready(item) for item in last_items):
            return last_items
        time.sleep(5)
    raise AssertionError(f"observability pods did not become ready: {last_items}")


def _pod_ready(pod: dict[str, Any]) -> bool:
    if pod.get("status", {}).get("phase") != "Running":
        return False
    conditions = pod.get("status", {}).get("conditions", [])
    return any(item.get("type") == "Ready" and item.get("status") == "True" for item in conditions)


def temporary_values_overlay(text: str) -> Path:
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False)
    with handle:
        handle.write(text)
    return Path(handle.name)
