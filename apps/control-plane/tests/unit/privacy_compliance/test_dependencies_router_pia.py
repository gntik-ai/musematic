from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import AuthorizationError
from platform.privacy_compliance import dependencies
from platform.privacy_compliance.audit_key_router import get_public_key
from platform.privacy_compliance.events import PrivacyEventPublisher
from platform.privacy_compliance.models import (
    ConsentType,
    PrivacyConsentRecord,
    PrivacyImpactAssessment,
)
from platform.privacy_compliance.router import check_residency, process_dsr
from platform.privacy_compliance.router_self_service import (
    create_own_dsr,
    get_disclosure,
    get_own_consent_history,
    get_own_consents,
    get_own_dsr,
    list_own_dsrs,
    put_own_consents,
    revoke_own_consent,
)
from platform.privacy_compliance.schemas import (
    ConsentRecordRequest,
    DSRResponse,
    DSRSelfServiceCreateRequest,
    ResidencyCheckRequest,
)
from platform.privacy_compliance.services.pia_service import PIAService
from platform.privacy_compliance.services.tombstone_signer import TombstoneSigner
from types import SimpleNamespace
from uuid import uuid4

import pytest


class FlushSession:
    def __init__(self) -> None:
        self.flushed = 0

    async def flush(self) -> None:
        self.flushed += 1


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        registry=SimpleNamespace(package_bucket="packages"),
        connectors=SimpleNamespace(dead_letter_bucket="dead"),
        privacy_compliance=SimpleNamespace(
            clickhouse_pii_tables=["events"],
            salt_vault_path="secret/path",
        ),
    )


def _request() -> SimpleNamespace:
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=_settings(),
                clients={
                    "kafka": object(),
                    "redis": object(),
                    "qdrant": object(),
                    "opensearch": object(),
                    "object_storage": object(),
                    "clickhouse": object(),
                    "audit_signer": object(),
                    "audit_chain": object(),
                },
            )
        )
    )


@pytest.mark.asyncio
async def test_privacy_dependency_builders_roles_and_request_resolvers() -> None:
    request = _request()
    session = FlushSession()

    assert dependencies._settings(request) is request.app.state.settings
    assert dependencies._producer(request) is request.app.state.clients["kafka"]
    assert dependencies._has_role({"role": "privacy_officer"}, dependencies.ADMIN_ROLES)
    assert dependencies._has_role(
        {"roles": [{"role": "auditor"}]},
        dependencies.READ_ROLES,
    )
    assert await dependencies.require_privacy_admin({"role": "service_account"})
    assert await dependencies.require_privacy_reader({"roles": ["auditor"]})
    with pytest.raises(AuthorizationError):
        await dependencies.require_privacy_admin({"role": "viewer"})
    with pytest.raises(AuthorizationError):
        await dependencies.require_privacy_reader({"roles": ["viewer"]})

    assert dependencies.build_privacy_repository(session) is not None
    assert dependencies.build_consent_service(session=session, producer=None) is not None
    assert dependencies.build_pia_service(session=session, producer=None) is not None
    assert dependencies.build_dlp_service(session=session, producer=None) is not None
    assert dependencies.build_residency_service(session=session, producer=None) is not None
    assert dependencies.build_dsr_service(
        session=session,
        settings=request.app.state.settings,
        producer=None,
        clients=request.app.state.clients,
    ) is not None
    assert await dependencies.get_consent_service(request, session=session) is not None
    assert await dependencies.get_pia_service(request, session=session) is not None
    assert await dependencies.get_dlp_service(request, session=session) is not None
    assert await dependencies.get_residency_service(request, session=session) is not None
    assert await dependencies.get_dsr_service(request, session=session) is not None


class PIARepo:
    def __init__(self) -> None:
        self.session = FlushSession()
        self.pia: PrivacyImpactAssessment | None = None

    async def create_pia(self, pia):
        pia.id = uuid4()
        self.pia = pia
        return pia

    async def get_pia(self, pia_id):
        del pia_id
        return self.pia

    async def get_approved_pia(self, subject_type, subject_id):
        if self.pia and self.pia.subject_type == subject_type and self.pia.subject_id == subject_id:
            return self.pia
        return None


class RecordingPublisher(PrivacyEventPublisher):
    def __init__(self) -> None:
        super().__init__(None)
        self.events = []

    async def publish(self, event_type, payload, *, key, correlation_ctx=None):
        del correlation_ctx
        self.events.append((event_type, payload, key))


@pytest.mark.asyncio
async def test_pia_service_full_state_machine_paths() -> None:
    repo = PIARepo()
    publisher = RecordingPublisher()
    service = PIAService(repository=repo, event_publisher=publisher)  # type: ignore[arg-type]
    submitter = uuid4()
    approver = uuid4()
    subject_id = uuid4()

    pia = await service.submit_draft(
        subject_type="agent",
        subject_id=subject_id,
        data_categories=["pii"],
        legal_basis="legitimate interest",
        retention_policy=None,
        risks=[],
        mitigations=[],
        submitted_by=submitter,
    )
    assert pia.status == "draft"
    assert (await service.submit_for_review(pia.id, submitter)).status == "under_review"
    with pytest.raises(AuthorizationError):
        await service.approve(pia.id, submitter)
    assert (await service.approve(pia.id, approver)).status == "approved"
    assert await service.get_approved_pia("agent", subject_id) is pia
    assert await service.check_material_change("agent", subject_id, ["pii"]) == []
    superseded = await service.check_material_change("agent", subject_id, ["financial"])
    assert superseded == [pia]
    assert pia.status == "superseded"
    assert (await service.reject(pia.id, approver, "needs work")).rejection_feedback == "needs work"
    repo.pia = None
    with pytest.raises(ValueError, match="PIA not found"):
        await service.submit_for_review(uuid4(), submitter)
    assert publisher.events


class SelfDsrService:
    def __init__(self, response: DSRResponse) -> None:
        self.response = response

    async def create_request(self, payload, *, requested_by):
        assert payload.subject_user_id == requested_by
        return self.response

    async def list_requests(self, **kwargs):
        del kwargs
        return [self.response]

    async def get_request(self, dsr_id):
        del dsr_id
        return self.response


class AdminDsrService(SelfDsrService):
    async def process(self, dsr_id):
        del dsr_id
        return self.response


class SelfConsentService:
    def __init__(self, record: PrivacyConsentRecord) -> None:
        self.record = record

    async def get_state(self, user_id):
        del user_id
        return {ConsentType.ai_interaction: "granted"}

    async def record_consents(self, user_id, choices, workspace_id):
        del user_id, choices, workspace_id
        return [self.record]

    async def revoke(self, user_id, consent_type):
        del user_id, consent_type
        return self.record

    async def history(self, user_id):
        del user_id
        return [self.record]


class ResidencyCheckService:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str]] = []

    async def enforce(self, workspace_id, origin_region):
        self.calls.append((workspace_id, origin_region))


@pytest.mark.asyncio
async def test_self_service_router_functions_scope_and_transform_responses() -> None:
    user_id = uuid4()
    now = datetime.now(UTC)
    response = DSRResponse(
        id=uuid4(),
        subject_user_id=user_id,
        request_type="erasure",
        requested_by=user_id,
        status="received",
        requested_at=now,
    )
    record = PrivacyConsentRecord(
        id=uuid4(),
        user_id=user_id,
        consent_type=ConsentType.ai_interaction.value,
        granted=True,
        granted_at=now,
    )
    current_user = {"sub": str(user_id)}
    dsr_service = SelfDsrService(response)
    consent_service = SelfConsentService(record)

    assert await create_own_dsr(
        DSRSelfServiceCreateRequest(request_type="erasure"),
        current_user,
        dsr_service,  # type: ignore[arg-type]
    ) == response
    assert await list_own_dsrs(current_user, dsr_service) == [response]  # type: ignore[arg-type]
    assert await get_own_dsr(response.id, current_user, dsr_service) == response  # type: ignore[arg-type]
    assert await process_dsr(response.id, current_user, AdminDsrService(response)) == response  # type: ignore[arg-type]
    audit_key_request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(clients={"audit_signer": TombstoneSigner()}))
    )
    assert "BEGIN PUBLIC KEY" in await get_public_key(audit_key_request, current_user)  # type: ignore[arg-type]
    response.subject_user_id = uuid4()
    with pytest.raises(AuthorizationError):
        await get_own_dsr(response.id, current_user, dsr_service)  # type: ignore[arg-type]

    assert (await get_own_consents(current_user, consent_service)).state  # type: ignore[arg-type]
    records = await put_own_consents(
        ConsentRecordRequest(choices={ConsentType.ai_interaction: True}),
        current_user,
        consent_service,  # type: ignore[arg-type]
    )
    assert records[0].id == record.id
    assert (await revoke_own_consent(
        ConsentType.ai_interaction,
        current_user,
        consent_service,  # type: ignore[arg-type]
    )).id == record.id
    assert (await get_own_consent_history(current_user, consent_service))[0].id == record.id  # type: ignore[arg-type]
    assert ConsentType.ai_interaction in (await get_disclosure()).required_consents


@pytest.mark.asyncio
async def test_residency_check_endpoint_uses_payload_or_header_origin() -> None:
    workspace_id = uuid4()
    service = ResidencyCheckService()
    response = await check_residency(
        workspace_id,
        ResidencyCheckRequest(origin_region="eu-central-1"),
        SimpleNamespace(headers={}),
        {"role": "auditor"},
        service,  # type: ignore[arg-type]
    )
    fallback = await check_residency(
        workspace_id,
        ResidencyCheckRequest(),
        SimpleNamespace(headers={"X-Origin-Region": "eu-west-1"}),
        {"role": "auditor"},
        service,  # type: ignore[arg-type]
    )

    assert response.allowed is True
    assert fallback.origin_region == "eu-west-1"
    assert service.calls == [
        (workspace_id, "eu-central-1"),
        (workspace_id, "eu-west-1"),
    ]
