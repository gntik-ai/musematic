"""UPD-053 (106) US4 / Journey J35 — wildcard TLS auto-renewal.

Simulates near-expiry by dialing cert-manager's ``renewBefore`` high
relative to a short-lived staging cert, then asserts:

1. cert-manager triggers renewal via the Hetzner DNS-01 webhook.
2. The new cert is written to the same Secret name (``wildcard-musematic-ai``).
3. ingress-nginx serves the new cert without dropping in-flight requests
   (TLS handshake against ``app.musematic.ai`` succeeds throughout the
   renewal window).

Skip-marked by default — runs against a sandbox Hetzner project gated
by ``RUN_J35=1``. The skip fence prevents accidental Let's Encrypt rate-
limit consumption on PR CI.
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_J35", "0") != "1",
    reason=(
        "Live wildcard TLS renewal against a sandbox Hetzner project. "
        "Set RUN_J35=1 in an operator-driven run."
    ),
)


def test_j35_wildcard_renewal_completes_without_handshake_drop() -> None:
    pytest.fail(
        "Body lands when the operator-runbook fixtures (Hetzner project + "
        "kind-cluster + sandbox-LE) are wired into tests/e2e/conftest.py. "
        "Tracked under specs/106-hetzner-clusters/tasks.md T078 / T080.",
    )
