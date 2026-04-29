from __future__ import annotations

import pytest

from ._chart_lifecycle import (
    NAMESPACE,
    helm_install,
    helm_uninstall,
    kubectl_json,
    require_chart_lifecycle_enabled,
)

pytestmark = [pytest.mark.e2e, pytest.mark.observability, pytest.mark.slow]


def test_observability_chart_uninstall_leaves_no_labelled_orphans() -> None:
    require_chart_lifecycle_enabled()
    helm_install()
    helm_uninstall()

    labelled = kubectl_json(
        [
            "-n",
            NAMESPACE,
            "get",
            "configmaps,pvc",
            "-l",
            "app.kubernetes.io/instance=observability",
            "--ignore-not-found",
        ]
    )
    assert labelled.get("items", []) == []

    webhooks = kubectl_json(
        [
            "get",
            "validatingwebhookconfigurations,mutatingwebhookconfigurations",
            "-l",
            "app.kubernetes.io/instance=observability",
            "--ignore-not-found",
        ]
    )
    assert webhooks.get("items", []) == []
