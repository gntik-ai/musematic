from __future__ import annotations

import os
import shlex

import pytest

from ._chart_lifecycle import NAMESPACE, helm_install, require_chart_lifecycle_enabled, run

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.slow]


def test_platform_cli_observability_status_reports_component_failure() -> None:
    require_chart_lifecycle_enabled()
    helm_install()
    cli = shlex.split(os.environ.get("PLATFORM_CLI_BIN", "platform-cli"))
    ok = run(
        [
            *cli,
            "observability",
            "status",
            "--namespace",
            NAMESPACE,
        ],
        timeout=120,
    )
    assert ok.returncode == 0, ok.stdout
    assert "Loki" in ok.stdout

    scaled = run(
        [
            "kubectl",
            "-n",
            NAMESPACE,
            "scale",
            "deployment,statefulset",
            "-l",
            "app.kubernetes.io/name=loki",
            "--replicas=0",
        ],
        timeout=120,
    )
    assert scaled.returncode == 0, scaled.stdout
    failed = run(
        [
            *cli,
            "observability",
            "status",
            "--namespace",
            NAMESPACE,
        ],
        timeout=120,
    )
    assert failed.returncode == 1, failed.stdout
    assert "Loki" in failed.stdout
