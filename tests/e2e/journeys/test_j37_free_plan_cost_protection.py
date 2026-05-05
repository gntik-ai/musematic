"""J37 Free Plan Cost Protection — UPD-054 (FR-807).

Three Free-tier rejection paths: premium model, oversize context, hard
cap on small executions. Verifies zero overage cost is incurred.

Cross-BC links: governance/ (premium-model gate) ↔ workspaces/
(quota counter) ↔ analytics/ (cost ledger).
"""
from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.journey,
    pytest.mark.j37,
    pytest.mark.skipif(
        os.environ.get("RUN_J37", "0") != "1",
        reason="Requires dev kind cluster + plans + ClickHouse cost-events.",
    ),
    pytest.mark.timeout(480),
]


@pytest.mark.asyncio
async def test_j37_free_user_premium_model_rejected(http_client) -> None:
    """Free user invokes premium model -> `quota_exceeded` BEFORE any
    model-router invocation (zero `model_router_invocations_total`
    metric increment).
    """
    pytest.skip("Scaffold — body lands during US3 implementation.")


@pytest.mark.asyncio
async def test_j37_free_user_oversize_context_rejected(http_client) -> None:
    """Free user requests context window above the Free tier cap ->
    rejected with `quota_exceeded`.
    """
    pytest.skip("Scaffold — body lands during US3 implementation.")


@pytest.mark.asyncio
async def test_j37_free_user_hard_cap_402(http_client) -> None:
    """Free user runs many small executions until quota -> HTTP 402;
    period total cost in ClickHouse is exactly 0 cents.
    """
    pytest.skip("Scaffold — body lands during US3 implementation.")
