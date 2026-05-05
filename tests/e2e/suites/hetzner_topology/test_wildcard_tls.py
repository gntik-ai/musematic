"""UPD-053 (106) US4 — wildcard cert reaches Ready within 10 minutes.

Skip-marked by default; runs only inside the kind-cluster e2e matrix
where cert-manager CRDs and the Hetzner DNS-01 webhook are pre-installed.

The journey-level renewal test lives at
``tests/e2e/journeys/test_j35_wildcard_tls_renewal.py``.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("E2E_KIND_CLUSTER_READY", "0") != "1",
    reason=(
        "Requires the kind-cluster e2e fixture with cert-manager CRDs + "
        "the Hetzner DNS-01 webhook bound to a real Hetzner DNS API token. "
        "CI sets E2E_KIND_CLUSTER_READY=1 in the e2e job step."
    ),
)


def test_wildcard_certificate_reaches_ready() -> None:
    pytest.fail(
        "Body lands when the kind-cluster e2e harness exposes a "
        "cert-manager-bound test fixture. Tracked under specs/106-hetzner"
        "-clusters/tasks.md T078.",
    )


def test_wildcard_certificate_has_valid_not_after() -> None:
    pytest.fail(
        "Body lands when the e2e harness can parse `kubectl get "
        "certificate wildcard-musematic-ai -o jsonpath='{.status.notAfter}'`. "
        "Tracked under specs/106-hetzner-clusters/tasks.md T078.",
    )
