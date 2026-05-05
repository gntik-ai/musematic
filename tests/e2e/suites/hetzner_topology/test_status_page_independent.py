"""UPD-053 (106) US5 — status page operational independence (rule 49).

Asserts that scaling the in-cluster ingress controller to zero replicas
does NOT take down ``https://status.musematic.ai/``: external requests
must still return 200 because the page is served by Cloudflare Pages.

Skip-marked by default — runs only against a real Hetzner project gated
by ``RUN_J29=1`` because it (a) exercises the live Cloudflare Pages push
pipeline and (b) requires the operator's Cloudflare project to be
configured.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_J29", "0") != "1",
    reason=(
        "Requires a sandbox Hetzner project + a Cloudflare Pages project "
        "for status.musematic.ai. Set RUN_J29=1 in an operator-driven run."
    ),
)


def test_status_page_remains_reachable_when_ingress_scaled_to_zero() -> None:
    pytest.fail(
        "Body lands when the kubectl-driven scale-to-zero helper and the "
        "external HTTP poller are wired into tests/e2e/conftest.py. Tracked "
        "under specs/106-hetzner-clusters/tasks.md T078 / T080.",
    )
