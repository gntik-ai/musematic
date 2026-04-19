from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.trust.models import CertificationStatus, RecertificationTriggerType
from uuid import uuid4

import pytest

from tests.trust_support import build_certification, build_trust_bundle


@pytest.mark.asyncio
async def test_recertification_create_trigger_deduplicates_pending_rows() -> None:
    bundle = build_trust_bundle()
    service = bundle.recertification_service

    created = await service.create_trigger(
        "agent-1",
        "rev-1",
        RecertificationTriggerType.revision_changed,
        {"event_type": "agent_revision.published", "event_id": "evt-1"},
    )
    duplicate = await service.create_trigger(
        "agent-1",
        "rev-1",
        RecertificationTriggerType.revision_changed,
        {"event_type": "agent_revision.published", "event_id": "evt-2"},
    )

    assert created is not None
    assert duplicate is None
    assert len(bundle.repository.triggers) == 1


@pytest.mark.asyncio
async def test_recertification_process_and_event_handlers_create_pending_certifications() -> None:
    bundle = build_trust_bundle()
    service = bundle.recertification_service
    bundle.repository.certifications.append(
        build_certification(
            status=CertificationStatus.active,
            expires_at=datetime.now(UTC) + timedelta(days=5),
        )
    )

    await service.handle_registry_event(
        {"payload": {"agent_id": "agent-1", "revision_id": "rev-2"}}
    )
    await service.handle_policy_event({"payload": {"agent_id": "agent-2", "revision_id": "rev-3"}})
    await service.handle_runtime_event({"payload": {"agent_id": "agent-3", "revision_id": "rev-4"}})
    created_from_expiry = await service.scan_expiry_approaching()
    processed = await service.process_pending_triggers()
    listed = await service.list_triggers()

    assert created_from_expiry == 1
    assert processed == 4
    assert listed.total == 4
    assert len(bundle.repository.certifications) == 5
    assert bundle.producer.events[-1]["event_type"] == "recertification.triggered"


@pytest.mark.asyncio
async def test_recertification_get_trigger_raises_for_missing_item() -> None:
    bundle = build_trust_bundle()

    with pytest.raises(LookupError):
        await bundle.recertification_service.get_trigger(uuid4())


@pytest.mark.asyncio
async def test_recertification_get_trigger_and_helper_paths() -> None:
    bundle = build_trust_bundle()
    service = bundle.recertification_service
    created = await service.create_trigger(
        "agent-helper",
        "rev-helper",
        RecertificationTriggerType.policy_changed,
        {"event_type": "", "event_id": "", "certification_id": "not-a-uuid"},
    )
    assert created is not None

    fetched = await service.get_trigger(created.id)
    await service.handle_registry_event({"payload": {"agent_id": "missing-revision"}})
    await service.handle_policy_event({"payload": {"revision_id": "missing-agent"}})
    await service.handle_runtime_event({"payload": {"agent_id": 1, "revision_id": "rev"}})

    assert fetched.id == created.id
    assert service._uuid_or_none("not-a-uuid") is None
    assert service._optional_text("") is None
