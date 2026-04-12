from __future__ import annotations

from platform.trust.models import RecertificationTriggerType
from platform.trust.router import get_recertification_trigger, list_recertification_triggers

import pytest

from tests.trust_support import admin_user, build_trust_bundle


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recertification_read_endpoints() -> None:
    bundle = build_trust_bundle()
    trigger = await bundle.recertification_service.create_trigger(
        "agent-1",
        "rev-1",
        RecertificationTriggerType.revision_changed,
        {"event_type": "agent_revision.published", "event_id": "evt-1"},
    )
    assert trigger is not None

    listed = await list_recertification_triggers(
        agent_id=None,
        current_user=admin_user(),
        recertification_service=bundle.recertification_service,
    )
    fetched = await get_recertification_trigger(
        trigger.id,
        current_user=admin_user(),
        recertification_service=bundle.recertification_service,
    )

    assert listed.total == 1
    assert fetched.id == trigger.id
