from __future__ import annotations

from platform.trust.router import get_agent_tier, list_agent_signals

import pytest

from tests.trust_support import admin_user, build_signal, build_trust_bundle


@pytest.mark.integration
@pytest.mark.asyncio
async def test_trust_signal_listing_endpoint() -> None:
    bundle = build_trust_bundle()
    bundle.repository.signals.extend(
        [
            build_signal(source_id="sig-1"),
            build_signal(source_id="sig-2"),
        ]
    )

    listed = await list_agent_signals(
        "agent-1",
        page=1,
        page_size=10,
        current_user=admin_user(),
        trust_tier_service=bundle.trust_tier_service,
    )
    tier = await get_agent_tier(
        "agent-1",
        trust_tier_service=bundle.trust_tier_service,
    )

    assert listed.total == 2
    assert tier.agent_id == "agent-1"
