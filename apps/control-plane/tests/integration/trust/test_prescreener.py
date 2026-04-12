from __future__ import annotations

from platform.trust.router import (
    activate_prescreener_rule_set,
    create_prescreener_rule_set,
    prescreen,
)
from platform.trust.schemas import PreScreenRequest

import pytest

from tests.trust_support import (
    admin_user,
    build_rule_set_create,
    build_trust_bundle,
    service_account_user,
)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_prescreener_endpoints() -> None:
    bundle = build_trust_bundle()
    created = await create_prescreener_rule_set(
        build_rule_set_create(),
        current_user=admin_user(),
        prescreener_service=bundle.prescreener_service,
    )
    activated = await activate_prescreener_rule_set(
        created.id,
        current_user=admin_user(),
        prescreener_service=bundle.prescreener_service,
    )
    screened = await prescreen(
        PreScreenRequest(content="this is a jailbreak", context_type="input"),
        current_user=service_account_user(),
        prescreener_service=bundle.prescreener_service,
    )

    assert created.version == 1
    assert activated.is_active is True
    assert screened.blocked is True
