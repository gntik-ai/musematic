"""UPD-053 (106) US3 — DNS automation create-tenant happy path.

Provisions an Enterprise tenant via the admin API, asserts that all 6
records (3 subdomains × A/AAAA) resolve via a public resolver within
the SC-003 deadline (≤ 5 minutes p95).

Skip-marked by default — runs only against a real Hetzner project gated
by ``RUN_J29=1``. Live DNS automation is a chargeable operation and must
not run in PR CI.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_J29", "0") != "1",
    reason=(
        "Live DNS automation against Hetzner DNS. Set RUN_J29=1 in an "
        "operator-driven run with a sandbox Hetzner project."
    ),
)


def test_create_tenant_subdomain_resolves_six_records() -> None:
    pytest.fail(
        "Body lands when the Hetzner project fixture and admin API client "
        "are wired into tests/e2e/conftest.py. Tracked under specs/106-"
        "hetzner-clusters/tasks.md T078 / T080.",
    )
