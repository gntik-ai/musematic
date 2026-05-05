"""J26 Abuse Prevention — UPD-054 (FR-796).

Four sub-scenarios: signup velocity, disposable-email rejection,
suspended-account login block + super-admin lift, Free-tier cost
protection rejection.

Cross-BC links: abuse_prevention/ ↔ accounts/ ↔ admin/ ↔ governance/.
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j26,
    pytest.mark.skipif(
        os.environ.get("RUN_J26", "0") != "1",
        reason="Requires dev kind cluster + abuse-prevention BC + accounts.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j26_signup_velocity_block(http_client) -> None:
    """10 signups same IP -> velocity block at #10 with `signup_velocity_exceeded`."""
    pytest.skip("Scaffold — body lands during US4 implementation.")


@pytest.mark.asyncio
async def test_j26_disposable_email_rejected(http_client) -> None:
    """Signup with a disposable-email address (e.g. @tempmail.com) is rejected
    pre-creation with HTTP 400 and `disposable_email`.
    """
    pytest.skip("Scaffold — body lands during US4 implementation.")


@pytest.mark.asyncio
async def test_j26_suspended_account_blocked_then_lifted(super_admin_client) -> None:
    """A previously-suspended account cannot login; super-admin lifts the
    suspension; user can re-login successfully.
    """
    pytest.skip("Scaffold — body lands during US4 implementation.")


@pytest.mark.asyncio
async def test_j26_free_tier_cost_protection_rejection(http_client) -> None:
    """Free user attempting premium model + long-execution combo is
    rejected pre-dispatch with `quota_exceeded` (cross-check with J37).
    """
    pytest.skip("Scaffold — body lands during US4 implementation.")
