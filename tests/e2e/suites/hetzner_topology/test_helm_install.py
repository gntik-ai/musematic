"""UPD-053 (106) US1 — `helm install` smoke test.

Asserts the platform chart installs cleanly against a freshly bootstrapped
kind cluster pre-loaded with cert-manager CRDs. Renders against
``values.dev.yaml`` (smaller footprint; same template surface as prod).

Skip-marked by default — runs only inside the kind-cluster CI matrix where
the e2e job's prerequisite step has installed cert-manager.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("E2E_KIND_CLUSTER_READY", "0") != "1",
    reason=(
        "Requires the kind-cluster e2e fixture (helm/kind-action + cert-"
        "manager CRDs installed). CI sets E2E_KIND_CLUSTER_READY=1 in the "
        "e2e job step; skip on developer laptops."
    ),
)


def test_helm_install_completes_within_10_minutes() -> None:
    pytest.fail(
        "Body lands when the kind-cluster e2e harness exposes a "
        "helm-install fixture. Tracked under specs/106-hetzner-clusters/"
        "tasks.md T078.",
    )
