"""UPD-053 (106) US3 — bookend tenant-subdomain provisioning journey.

Creates a tenant, dig-resolves the 6 records, browses
``https://<slug>.musematic.ai/healthz`` (200 OK with valid wildcard cert),
schedules deletion, then dig-resolves NXDOMAIN.

Skip-marked by default — runs only against a real Hetzner project gated
by ``RUN_J29=1``.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_J29", "0") != "1",
    reason=(
        "Live tenant-subdomain provisioning against Hetzner DNS + the "
        "wildcard cert. Set RUN_J29=1 in an operator-driven run."
    ),
)


def test_tenant_subdomain_full_lifecycle() -> None:
    pytest.fail(
        "Body lands when the Hetzner project fixture, admin API client, "
        "and TLS verification helper are wired into tests/e2e/conftest.py. "
        "Tracked under specs/106-hetzner-clusters/tasks.md T078 / T080.",
    )
