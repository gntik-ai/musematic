from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.trust.models import (
    CertificationStatus,
    ReassessmentRecord,
    TrustRecertificationRequest,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.trust_support import build_certification, build_trust_bundle


class _ManagerStub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, str, object]] = []

    def subscribe(self, topic: str, group: str, handler) -> None:
        self.subscriptions.append((topic, group, handler))


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


def test_surveillance_registers_topics_and_schedule_helper() -> None:
    bundle = build_trust_bundle()
    service = bundle.surveillance_service
    manager = _ManagerStub()
    now = datetime.now(UTC)

    service.register(manager)

    assert manager.subscriptions == [
        (
            "policy.events",
            "platform.trust-surveillance-material-change",
            service.handle_material_change,
        ),
        (
            "trust.events",
            "platform.trust-surveillance-revision-signals",
            service.handle_material_change,
        ),
    ]
    assert service._is_reassessment_due("@always", now, now) is True
    assert service._is_reassessment_due("@daily", now - timedelta(days=2), now) is True
    assert service._is_reassessment_due("@weekly", now - timedelta(days=8), now) is True
    assert service._is_reassessment_due("@monthly", now - timedelta(days=31), now) is True
    assert service._is_reassessment_due("@daily", now, now) is False
    assert service._is_reassessment_due("custom", now, now) is False


@pytest.mark.asyncio
async def test_surveillance_handles_agent_fqn_and_missing_targets() -> None:
    bundle = build_trust_bundle(TRUST_RECERTIFICATION_GRACE_PERIOD_DAYS=3)
    service = bundle.surveillance_service
    certification = build_certification(
        agent_id="agent-fqn",
        status=CertificationStatus.expiring,
        expires_at=datetime.now(UTC) + timedelta(days=5),
    )
    bundle.repository.certifications.append(certification)

    await service.handle_material_change(
        SimpleNamespace(
            event_type="trust.signal.changed",
            payload={"agent_fqn": "agent-fqn", "source_id": "src-1"},
        )
    )
    await service.handle_material_change(
        SimpleNamespace(event_type="trust.signal.changed", payload={})
    )

    missing_request = await bundle.repository.create_recertification_request(
        TrustRecertificationRequest(
            certification_id=uuid4(),
            trigger_type="signal",
            trigger_reference="missing-cert",
            deadline=datetime.now(UTC) - timedelta(minutes=1),
            resolution_status="pending",
        )
    )
    await service.check_grace_period_expiry()

    assert certification.status == CertificationStatus.suspended
    assert bundle.repository.recertification_requests[0].trigger_type == "signal"
    assert bundle.repository.recertification_requests[0].trigger_reference == "src-1"
    assert missing_request.resolution_status == "pending"

    silent_bundle = build_trust_bundle()
    silent_bundle.surveillance_service.events.producer = None
    await silent_bundle.surveillance_service._publish_alert(
        "trust.certification.expired",
        certification,
        {"reason": "none"},
    )
    assert silent_bundle.producer.events == []


@pytest.mark.asyncio
async def test_surveillance_covers_execute_branch_and_non_due_schedule() -> None:
    class _ExecuteResult:
        def __init__(self, items):
            self._items = items

        def scalars(self):
            return self

        def all(self):
            return self._items

    class _SessionWithExecute:
        def __init__(self, items):
            self._items = items
            self.flush_count = 0

        async def execute(self, statement):
            del statement
            return _ExecuteResult(self._items)

        async def flush(self) -> None:
            self.flush_count += 1

    bundle = build_trust_bundle()
    service = bundle.surveillance_service
    scheduled = build_certification(
        agent_id="agent-noop",
        status=CertificationStatus.active,
        expires_at=datetime.now(UTC) + timedelta(days=10),
    )
    scheduled.reassessment_schedule = "@daily"
    bundle.repository.certifications.append(scheduled)
    await bundle.repository.create_reassessment(
        scheduled.id,
        ReassessmentRecord(
            certification_id=scheduled.id,
            verdict="action_required",
            reassessor_id="automated",
            notes="recent run",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    )
    session = _SessionWithExecute([scheduled])
    service.repository.session = session

    candidates = await service._list_surveillance_candidates()
    await service.run_surveillance_cycle()

    assert candidates == [scheduled]
    assert len(bundle.repository.reassessments) == 1
    assert session.flush_count == 1
