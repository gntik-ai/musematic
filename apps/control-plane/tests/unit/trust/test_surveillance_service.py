from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.trust.models import CertificationStatus
from types import SimpleNamespace

import pytest

from tests.trust_support import build_certification, build_trust_bundle


@pytest.mark.asyncio
async def test_surveillance_cycle_transitions_and_creates_reassessments() -> None:
    bundle = build_trust_bundle(TRUST_SURVEILLANCE_WARNING_WINDOW_DAYS=7)
    service = bundle.surveillance_service
    far = build_certification(
        agent_id="agent-far",
        status=CertificationStatus.active,
        expires_at=datetime.now(UTC) + timedelta(days=30),
    )
    warning = build_certification(
        agent_id="agent-warning",
        status=CertificationStatus.active,
        expires_at=datetime.now(UTC) + timedelta(days=2),
    )
    expired = build_certification(
        agent_id="agent-expired",
        status=CertificationStatus.expiring,
        expires_at=datetime.now(UTC) - timedelta(days=1),
    )
    scheduled = build_certification(
        agent_id="agent-scheduled",
        status=CertificationStatus.active,
        expires_at=datetime.now(UTC) + timedelta(days=15),
    )
    scheduled.reassessment_schedule = "@daily"
    bundle.repository.certifications.extend([far, warning, expired, scheduled])

    await service.run_surveillance_cycle()

    assert far.status.value == "active"
    assert warning.status.value == "expiring"
    assert expired.status.value == "expired"
    assert len(bundle.repository.reassessments) == 1
    reassessment = bundle.repository.reassessments[0]
    assert reassessment.certification_id == scheduled.id
    assert reassessment.verdict == "action_required"
    event_types = [event["event_type"] for event in bundle.producer.events]
    assert "trust.certification.expiring" in event_types
    assert "certification.expired" in event_types
    assert "trust.reassessment.required" in event_types


@pytest.mark.asyncio
async def test_surveillance_handles_material_change_and_grace_period_expiry() -> None:
    bundle = build_trust_bundle(TRUST_RECERTIFICATION_GRACE_PERIOD_DAYS=14)
    service = bundle.surveillance_service
    certification = build_certification(
        agent_id="agent-material",
        status=CertificationStatus.active,
        expires_at=datetime.now(UTC) + timedelta(days=10),
    )
    bundle.repository.certifications.append(certification)

    now = datetime.now(UTC)
    await service.handle_material_change(
        SimpleNamespace(
            event_type="policy.updated",
            payload={"agent_id": "agent-material", "event_id": "evt-1"},
        )
    )

    assert certification.status.value == "suspended"
    assert len(bundle.repository.recertification_requests) == 1
    request = bundle.repository.recertification_requests[0]
    assert request.trigger_type == "policy"
    assert now + timedelta(days=13, hours=23) <= request.deadline
    assert request.deadline <= now + timedelta(days=14, minutes=1)

    request.deadline = datetime.now(UTC) - timedelta(minutes=5)
    await service.check_grace_period_expiry()

    assert certification.status.value == "revoked"
    assert certification.revocation_reason == "recertification timeout"
    assert request.resolution_status == "revoked"
    event_types = [event["event_type"] for event in bundle.producer.events]
    assert "trust.certification.suspended" in event_types
    assert "certification.revoked" in event_types
