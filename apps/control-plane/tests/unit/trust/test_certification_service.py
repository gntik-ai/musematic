from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import ValidationError
from platform.trust.contract_schemas import ReassessmentCreate
from platform.trust.exceptions import (
    CertificationBlockedError,
    CertificationNotFoundError,
    CertificationStateError,
    CertifierNotFoundError,
    ContractConflictError,
    InvalidStateTransitionError,
    RecertificationRequestNotFoundError,
)
from platform.trust.models import CertificationStatus, TrustRecertificationRequest
from platform.trust.schemas import EvidenceRefCreate
from platform.trust.service import CertificationService, ensure_active_certification
from typing import Any
from uuid import uuid4

import pytest

from tests.trust_support import (
    build_certification,
    build_certification_create,
    build_certifier_create,
    build_trust_bundle,
)


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


class FairnessGateStub:
    def __init__(self, latest: object | None, any_age: object | None = None) -> None:
        self.latest = latest
        self.any_age = any_age
        self.calls: list[dict[str, Any]] = []

    async def get_latest_passing_evaluation(self, **kwargs: Any) -> object | None:
        self.calls.append(kwargs)
        return self.latest

    async def get_latest_passing_evaluation_any_age(self, **kwargs: Any) -> object | None:
        self.calls.append({"any_age": True, **kwargs})
        return self.any_age


@pytest.mark.asyncio
async def test_certification_fairness_gate_blocks_high_impact_without_eval() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    gate = FairnessGateStub(None)
    service.fairness_gate = gate
    agent_id = uuid4()

    with pytest.raises(CertificationBlockedError) as exc_info:
        await service._assert_fairness_gate(
            build_certification_create().model_copy(
                update={
                    "agent_id": str(agent_id),
                    "agent_revision_id": "rev-fairness",
                    "high_impact_use": True,
                }
            )
        )

    assert exc_info.value.details["reason"] == "fairness_evaluation_required"
    assert gate.calls[0]["agent_id"] == agent_id
    assert gate.calls[0]["agent_revision_id"] == "rev-fairness"


@pytest.mark.asyncio
async def test_certification_fairness_gate_passes_with_recent_eval() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    gate = FairnessGateStub(object())
    service.fairness_gate = gate
    agent_id = uuid4()

    await service._assert_fairness_gate(
        build_certification_create().model_copy(
            update={
                "agent_id": str(agent_id),
                "agent_revision_id": "rev-fairness",
                "high_impact_use": True,
            }
        )
    )
    await service._assert_fairness_gate(
        build_certification_create().model_copy(update={"high_impact_use": False})
    )

    assert len(gate.calls) == 1


@pytest.mark.asyncio
async def test_certification_fairness_gate_blocks_stale_eval() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    gate = FairnessGateStub(None, any_age=object())
    service.fairness_gate = gate
    agent_id = uuid4()

    with pytest.raises(CertificationBlockedError) as exc_info:
        await service._assert_fairness_gate(
            build_certification_create().model_copy(
                update={
                    "agent_id": str(agent_id),
                    "agent_revision_id": "rev-fairness",
                    "high_impact_use": True,
                }
            )
        )

    assert exc_info.value.details["reason"] == "fairness_evaluation_stale"


@pytest.mark.asyncio
async def test_certification_service_certifier_management_and_scope_validation() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    actor_id = str(uuid4())
    created = await service.create(build_certification_create(), actor_id)

    certifier = await service.create_certifier(build_certifier_create(), actor_id)
    fetched = await service.get_certifier(certifier.id)
    listed = await service.list_certifiers()
    issued = await service.issue_with_certifier(
        created.id,
        certifier.id,
        "financial_calculations",
        actor_id,
    )

    assert fetched.id == certifier.id
    assert listed.total == 1
    assert issued.external_certifier_id == certifier.id
    assert bundle.producer.events[-1]["event_type"] == "trust.certification.updated"

    scoped = await service.create_certifier(build_certifier_create(), actor_id)
    with pytest.raises(ValidationError):
        await service.issue_with_certifier(created.id, scoped.id, "other_scope", actor_id)

    await service.deactivate_certifier(certifier.id, actor_id)
    active_only = await service.list_certifiers()
    include_inactive = await service.list_certifiers(include_inactive=True)

    assert active_only.total == 1
    assert include_inactive.total == 2
    assert any(
        item.id == certifier.id and item.is_active is False
        for item in include_inactive.items
    )

    with pytest.raises(CertifierNotFoundError):
        await service.get_certifier(uuid4())
    with pytest.raises(CertifierNotFoundError):
        await service.deactivate_certifier(uuid4(), actor_id)
    with pytest.raises(CertificationNotFoundError):
        await service.issue_with_certifier(uuid4(), scoped.id, "financial_calculations", actor_id)


@pytest.mark.asyncio
async def test_certification_service_reassessment_and_recertification_flows() -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    actor_id = str(uuid4())

    created = await service.create(build_certification_create(), actor_id)
    await service.activate(created.id, actor_id)
    failed = await service.record_reassessment(
        created.id,
        ReassessmentCreate(verdict="fail", notes="threshold breach"),
        actor_id,
    )
    listed = await service.list_reassessments(created.id)

    assert failed.verdict == "fail"
    assert listed.total == 1
    stored = await bundle.repository.get_certification(created.id)
    assert stored is not None
    assert stored.status == CertificationStatus.suspended
    assert bundle.producer.events[-1]["event_type"] == "trust.certification.suspended"

    request = await bundle.repository.create_recertification_request(
        TrustRecertificationRequest(
            certification_id=created.id,
            trigger_type="signal",
            trigger_reference="evt-1",
            deadline=datetime.now(UTC) + timedelta(days=1),
            resolution_status="pending",
        )
    )
    dismissed = await service.dismiss_suspension(
        created.id,
        "Operator validated mitigation",
        actor_id,
    )
    requests = await service.list_recertification_requests(status="dismissed")
    fetched_request = await service.get_recertification_request(request.id)

    assert dismissed.status == CertificationStatus.active
    assert requests.total == 1
    assert fetched_request.id == request.id
    assert request.resolution_status == "dismissed"
    assert bundle.repository.signals[-1].signal_type == "certification_suspension_dismissed"
    assert bundle.producer.events[-1]["event_type"] == "trust.certification.updated"

    pass_cert = await service.create(
        build_certification_create().model_copy(
            update={
                "agent_id": "agent-pass",
                "agent_fqn": "fleet:agent-pass",
                "agent_revision_id": "rev-pass",
            }
        ),
        actor_id,
    )
    await service.activate(pass_cert.id, actor_id)
    pass_model = await bundle.repository.get_certification(pass_cert.id)
    assert pass_model is not None
    pass_model.status = CertificationStatus.suspended
    passed = await service.record_reassessment(
        pass_cert.id,
        ReassessmentCreate(verdict="pass", notes="all good"),
        actor_id,
    )

    action_cert = await service.create(
        build_certification_create().model_copy(
            update={
                "agent_id": "agent-action",
                "agent_fqn": "fleet:agent-action",
                "agent_revision_id": "rev-action",
            }
        ),
        actor_id,
    )
    await service.activate(action_cert.id, actor_id)
    action_required = await service.record_reassessment(
        action_cert.id,
        ReassessmentCreate(verdict="action_required", notes="manual follow-up"),
        actor_id,
    )

    assert passed.verdict == "pass"
    assert pass_model.status == CertificationStatus.active
    assert action_required.verdict == "action_required"
    assert bundle.producer.events[-1]["event_type"] == "trust.certification.updated"

    with pytest.raises(ContractConflictError):
        await service.dismiss_suspension(action_cert.id, "Nothing to dismiss", actor_id)
    with pytest.raises(RecertificationRequestNotFoundError):
        await service.get_recertification_request(uuid4())


@pytest.mark.asyncio
async def test_certification_service_covers_remaining_not_found_and_self_supersede_paths(
    monkeypatch,
) -> None:
    bundle = build_trust_bundle()
    service = bundle.certification_service
    actor_id = str(uuid4())
    created = await service.create(build_certification_create(), actor_id)
    stored = await bundle.repository.get_certification(created.id)
    assert stored is not None

    async def _active_rows(_agent_id: str):
        return [stored]

    monkeypatch.setattr(bundle.repository, "list_active_certifications_for_agent", _active_rows)
    activated = await service.activate(created.id, actor_id)

    inactive = await service.create_certifier(build_certifier_create(), actor_id)
    await service.deactivate_certifier(inactive.id, actor_id)

    assert activated.status == CertificationStatus.active
    assert CertificationService._to_uuid_or_none(stored.id) == stored.id

    with pytest.raises(CertificationNotFoundError):
        await service.revoke(uuid4(), "missing", actor_id)
    with pytest.raises(CertifierNotFoundError):
        await service.issue_with_certifier(created.id, uuid4(), "financial_calculations", actor_id)
    with pytest.raises(ContractConflictError):
        await service.issue_with_certifier(
            created.id,
            inactive.id,
            "financial_calculations",
            actor_id,
        )
    with pytest.raises(CertificationNotFoundError):
        await service.record_reassessment(
            uuid4(),
            ReassessmentCreate(verdict="pass", notes="missing"),
            actor_id,
        )
    with pytest.raises(CertificationNotFoundError):
        await service.list_reassessments(uuid4())
    with pytest.raises(CertificationNotFoundError):
        await service.dismiss_suspension(uuid4(), "missing certification", actor_id)
