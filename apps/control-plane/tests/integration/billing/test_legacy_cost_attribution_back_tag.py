from __future__ import annotations

from tests.integration.billing.test_cost_attribution_subscription_link import (
    test_cost_attribution_write_and_legacy_read_are_subscription_tagged,
)


async def test_legacy_cost_attribution_back_tag() -> None:
    await test_cost_attribution_write_and_legacy_read_are_subscription_tagged()
