"""UPD-053 (106) US3 — DNS automation removal on tenant deletion phase 2.

Schedules a tenant for deletion, advances to phase 2, then asserts every
one of the 6 records resolves NXDOMAIN within the SC-003 deadline.

Skip-marked by default — runs only against a real Hetzner project gated
by ``RUN_J29=1``.
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


def test_remove_tenant_subdomain_clears_six_records() -> None:
    pytest.fail(
        "Body lands when the Hetzner project fixture and admin API client "
        "are wired into tests/e2e/conftest.py. Tracked under specs/106-"
        "hetzner-clusters/tasks.md T078 / T080.",
    )
