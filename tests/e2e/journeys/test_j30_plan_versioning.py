"""J30 Plan Versioning — UPD-054 (FR-800).

Super-admin publishes a new plan version; existing subscribers stay on
their version; new signups land on the new version; edits to a
published version are rejected; opt-in upgrades emit a prorated invoice.

Cross-BC links: billing/plans ↔ billing/subscriptions ↔ admin/.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j30,
    pytest.mark.skipif(
        os.environ.get("RUN_J30", "0") != "1",
        reason="Requires dev kind cluster + plans + Stripe test mode.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j30_publish_v2_existing_subscribers_stay_on_v1(
    super_admin_client, stripe_client,
) -> None:
    """Pro plan v2 (59 EUR) published; v1 (49 EUR) subscribers continue at 49 EUR."""
    pytest.skip("Scaffold — body lands during US3 implementation.")


@pytest.mark.asyncio
async def test_j30_published_version_is_immutable(super_admin_client) -> None:
    """Edit attempt against published v1 returns HTTP 409 `version_immutable`."""
    pytest.skip("Scaffold — body lands during US3 implementation.")


@pytest.mark.asyncio
async def test_j30_opt_in_upgrade_emits_prorated_invoice(
    super_admin_client, stripe_client,
) -> None:
    """V1 subscriber opts in to v2 mid-cycle; Stripe issues a prorated
    invoice line that reconciles to the documented formula within +/-1 cent.
    """
    pytest.skip("Scaffold — body lands during US3 implementation.")
