from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.trust.exceptions import (
    CertificationNotFoundError,
    CertificationStateError,
    InvalidStateTransitionError,
)
from platform.trust.models import CertificationStatus
from platform.trust.schemas import EvidenceRefCreate
from platform.trust.service import CertificationService, ensure_active_certification
from uuid import uuid4

import pytest

from tests.trust_support import build_certification, build_certification_create, build_trust_bundle


@pytest.mark.asyncio
async def test_certification_service_create_activate_supersede_and_revoke() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    issuer_id = str(uuid4())

    created = await service.create(build_certification_create(), issuer_id)
    evidence = await service.add_evidence(
        created.id,
        EvidenceRefCreate(
            evidence_type="test_results",
            source_ref_type="suite",
            source_ref_id="suite-1",
            summary="passed",
        ),
    )
    activated = await service.activate(created.id, issuer_id)

    newer = await service.create(
        build_certification_create().model_copy(update={"agent_revision_id": "rev-2"}),
        issuer_id,
    )
    activated_newer = await service.activate(newer.id, issuer_id)
    revoked = await service.revoke(activated_newer.id, "manual review", issuer_id)
    listed = await service.list_for_agent(created.agent_id)

    previous = await bundle.repository.get_certification(created.id)
    assert created.status == CertificationStatus.pending
    assert evidence.source_ref_id == "suite-1"
    assert activated.status == CertificationStatus.active
    assert previous is not None
    assert previous.status == CertificationStatus.superseded
    assert previous.superseded_by_id == activated_newer.id
    assert revoked.status == CertificationStatus.revoked
    assert revoked.revocation_reason == "manual review"
    assert len(listed) == 2
    assert [event["event_type"] for event in bundle.producer.events] == [
        "certification.created",
        "certification.activated",
        "certification.created",
        "certification.superseded",
        "certification.activated",
        "certification.revoked",
    ]


@pytest.mark.asyncio
async def test_certification_service_get_missing_and_ensure_active_guard() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service

    with pytest.raises(CertificationNotFoundError):
        await service.get(uuid4())

    created = await service.create(build_certification_create(), str(uuid4()))
    certification = await bundle.repository.get_certification(created.id)
    assert certification is not None

    with pytest.raises(CertificationStateError):
        ensure_active_certification(certification)


@pytest.mark.asyncio
async def test_certification_service_expire_stale_marks_expired_and_emits_events() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    issuer_id = str(uuid4())
    created = await service.create(
        build_certification_create().model_copy(
            update={"expires_at": datetime.now(UTC) - timedelta(hours=2)}
        ),
        issuer_id,
    )
    await service.activate(created.id, issuer_id)

    expired_count = await service.expire_stale()
    stored = await bundle.repository.get_certification(created.id)

    assert expired_count == 1
    assert stored is not None
    assert stored.status == CertificationStatus.expired
    assert bundle.producer.events[-1]["event_type"] == "certification.expired"


@pytest.mark.asyncio
async def test_certification_service_rejects_invalid_transitions_and_missing_resources() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    issuer_id = str(uuid4())
    created = await service.create(build_certification_create(), issuer_id)

    with pytest.raises(CertificationNotFoundError):
        await service.activate(uuid4(), issuer_id)
    with pytest.raises(InvalidStateTransitionError):
        await service.revoke(created.id, "not active", issuer_id)
    with pytest.raises(CertificationNotFoundError):
        await service.add_evidence(
            uuid4(),
            EvidenceRefCreate(
                evidence_type="test_results",
                source_ref_type="suite",
                source_ref_id="suite-404",
            ),
        )

    await service.activate(created.id, issuer_id)
    with pytest.raises(InvalidStateTransitionError):
        await service.activate(created.id, issuer_id)


@pytest.mark.asyncio
async def test_certification_service_certified_checks_and_uuid_coercion() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    issuer_id = str(uuid4())
    created = await service.create(build_certification_create(), issuer_id)

    assert await service.is_agent_certified(created.agent_id, created.agent_revision_id) is False

    await service.activate(created.id, issuer_id)

    assert await service.is_agent_certified(created.agent_id, created.agent_revision_id) is True
    assert await service.is_agent_certified(created.agent_id, "other-revision") is False
    assert CertificationService._to_uuid_or_none(None) is None
    assert CertificationService._to_uuid_or_none("not-a-uuid") is None
    parsed = CertificationService._to_uuid_or_none(issuer_id)
    assert parsed is not None
    assert str(parsed) == issuer_id


def test_ensure_active_certification_accepts_active_state() -> None:
    ensure_active_certification(build_certification(status=CertificationStatus.active))
