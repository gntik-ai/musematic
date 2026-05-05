"""UPD-053 (106) US2 — dev cluster physical isolation from prod.

Per spec.md US2 acceptance scenario 5: a pod scheduled in the dev cluster
cannot resolve or reach any prod-cluster private hostname or IP. Dev's LB
IPv4 differs from prod's. Stripe is in test mode (no live charges).

Skip-marked by default — runs only when both prod and dev clusters are
provisioned and the operator opts in.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_J29", "0") != "1",
    reason=(
        "Requires both musematic-prod and musematic-dev clusters live + "
        "kubeconfigs for both. Set RUN_J29=1 to opt in."
    ),
)


def test_dev_cannot_reach_prod_private_hostnames() -> None:
    pytest.fail(
        "Body lands when the dual-kubeconfig harness is wired into the "
        "test runner. Tracked under specs/106-hetzner-clusters/tasks.md T080.",
    )


def test_dev_lb_ipv4_differs_from_prod() -> None:
    pytest.fail(
        "Body lands when the platform-state internal endpoint is wired "
        "into the smoke tests.",
    )


def test_dev_billing_runs_in_stripe_test_mode() -> None:
    pytest.fail(
        "Body lands alongside the J29 fixture — asserts BILLING_STRIPE_MODE=test "
        "in the dev cluster's control-plane Deployment env.",
    )
