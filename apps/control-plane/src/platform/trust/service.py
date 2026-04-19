from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.common.exceptions import ValidationError
from platform.trust.contract_schemas import (
    CertifierCreate,
    CertifierListResponse,
    CertifierResponse,
    ReassessmentCreate,
    ReassessmentListResponse,
    ReassessmentResponse,
    TrustRecertificationRequestListResponse,
    TrustRecertificationRequestResponse,
)
from platform.trust.events import (
    CertificationEventPayload,
    CertificationSupersededPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.exceptions import (
    CertificationNotFoundError,
    CertificationStateError,
    CertifierNotFoundError,
    ContractConflictError,
    InvalidStateTransitionError,
    RecertificationRequestNotFoundError,
)
from platform.trust.models import (
    CertificationStatus,
    Certifier,
    ReassessmentRecord,
    TrustCertification,
    TrustCertificationEvidenceRef,
    TrustSignal,
)
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    CertificationCreate,
    CertificationResponse,
    EvidenceRefCreate,
    EvidenceRefResponse,
)
from typing import Any
from uuid import UUID


class CertificationService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.events = TrustEventPublisher(producer)

    async def create(self, data: CertificationCreate, issuer_id: str) -> CertificationResponse:
        certification = await self.repository.create_certification(
            TrustCertification(
                agent_id=data.agent_id,
                agent_fqn=data.agent_fqn,
                agent_revision_id=data.agent_revision_id,
                status=CertificationStatus.pending,
                issued_by=str(issuer_id),
                expires_at=data.expires_at,
                created_by=self._to_uuid_or_none(issuer_id),
                updated_by=self._to_uuid_or_none(issuer_id),
            )
        )
        await self.events.publish_certification_created(
            CertificationEventPayload(
                certification_id=certification.id,
                agent_id=certification.agent_id,
                agent_fqn=certification.agent_fqn,
                agent_revision_id=certification.agent_revision_id,
                actor_id=str(issuer_id),
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return CertificationResponse.model_validate(certification)

    async def get(self, cert_id: UUID) -> CertificationResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        return CertificationResponse.model_validate(certification)

    async def list_for_agent(self, agent_id: str) -> list[CertificationResponse]:
        certifications = await self.repository.list_certifications_for_agent(agent_id)
        return [CertificationResponse.model_validate(item) for item in certifications]

    async def activate(self, cert_id: UUID, actor_id: str) -> CertificationResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        if certification.status != CertificationStatus.pending:
            raise InvalidStateTransitionError(
                certification.status.value, CertificationStatus.active.value
            )

        active = await self.repository.list_active_certifications_for_agent(certification.agent_id)
        for existing in active:
            if existing.id == certification.id:
                continue
            existing.status = CertificationStatus.superseded
            existing.superseded_by_id = certification.id
            existing.updated_by = self._to_uuid_or_none(actor_id)
            await self.events.publish_certification_superseded(
                CertificationSupersededPayload(
                    old_certification_id=existing.id,
                    new_certification_id=certification.id,
                    agent_id=certification.agent_id,
                    occurred_at=utcnow(),
                ),
                make_correlation(),
            )

        certification.status = CertificationStatus.active
        certification.updated_by = self._to_uuid_or_none(actor_id)
        await self.repository.session.flush()
        await self.events.publish_certification_activated(
            CertificationEventPayload(
                certification_id=certification.id,
                agent_id=certification.agent_id,
                agent_fqn=certification.agent_fqn,
                agent_revision_id=certification.agent_revision_id,
                actor_id=str(actor_id),
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return CertificationResponse.model_validate(certification)

    async def revoke(
        self,
        cert_id: UUID,
        reason: str,
        actor_id: str,
    ) -> CertificationResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        if certification.status != CertificationStatus.active:
            raise InvalidStateTransitionError(
                certification.status.value, CertificationStatus.revoked.value
            )
        certification.status = CertificationStatus.revoked
        certification.revoked_at = datetime.now(UTC)
        certification.revocation_reason = reason
        certification.updated_by = self._to_uuid_or_none(actor_id)
        await self.repository.session.flush()
        await self.events.publish_certification_revoked(
            CertificationEventPayload(
                certification_id=certification.id,
                agent_id=certification.agent_id,
                agent_fqn=certification.agent_fqn,
                agent_revision_id=certification.agent_revision_id,
                actor_id=str(actor_id),
                reason=reason,
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return CertificationResponse.model_validate(certification)

    async def add_evidence(
        self,
        cert_id: UUID,
        data: EvidenceRefCreate,
    ) -> EvidenceRefResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        evidence_ref = await self.repository.create_evidence_ref(
            TrustCertificationEvidenceRef(
                certification_id=certification.id,
                evidence_type=data.evidence_type,
                source_ref_type=data.source_ref_type,
                source_ref_id=data.source_ref_id,
                summary=data.summary,
                storage_ref=data.storage_ref,
            )
        )
        return EvidenceRefResponse.model_validate(evidence_ref)

    async def expire_stale(self) -> int:
        expired = await self.repository.list_stale_certifications(datetime.now(UTC))
        for certification in expired:
            certification.status = CertificationStatus.expired
            certification.updated_at = datetime.now(UTC)
            await self.events.publish_certification_expired(
                CertificationEventPayload(
                    certification_id=certification.id,
                    agent_id=certification.agent_id,
                    agent_fqn=certification.agent_fqn,
                    agent_revision_id=certification.agent_revision_id,
                    occurred_at=utcnow(),
                ),
                make_correlation(),
            )
        await self.repository.session.flush()
        return len(expired)

    async def create_certifier(
        self,
        data: CertifierCreate,
        actor_id: str,
    ) -> CertifierResponse:
        certifier = await self.repository.create_certifier(
            Certifier(
                name=data.name,
                organization=data.organization,
                credentials=data.credentials,
                permitted_scopes=data.permitted_scopes,
                is_active=True,
                created_by=self._to_uuid_or_none(actor_id),
                updated_by=self._to_uuid_or_none(actor_id),
            )
        )
        return CertifierResponse.model_validate(certifier)

    async def get_certifier(self, certifier_id: UUID) -> CertifierResponse:
        certifier = await self.repository.get_certifier(certifier_id)
        if certifier is None:
            raise CertifierNotFoundError(certifier_id)
        return CertifierResponse.model_validate(certifier)

    async def list_certifiers(self, include_inactive: bool = False) -> CertifierListResponse:
        items = await self.repository.list_certifiers(include_inactive=include_inactive)
        return CertifierListResponse(
            items=[CertifierResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def deactivate_certifier(self, certifier_id: UUID, actor_id: str) -> None:
        certifier = await self.repository.deactivate_certifier(certifier_id)
        if certifier is None:
            raise CertifierNotFoundError(certifier_id)
        certifier.updated_by = self._to_uuid_or_none(actor_id)
        await self.repository.session.flush()

    async def issue_with_certifier(
        self,
        cert_id: UUID,
        certifier_id: UUID,
        scope: str,
        actor_id: str,
    ) -> CertificationResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        certifier = await self.repository.get_certifier(certifier_id)
        if certifier is None:
            raise CertifierNotFoundError(certifier_id)
        if not certifier.is_active:
            raise ContractConflictError(
                "TRUST_CERTIFIER_INACTIVE",
                "Certifier is inactive",
                {
                    "certification_id": str(certification.id),
                    "certifier_id": str(certifier.id),
                },
            )
        if certifier.permitted_scopes and scope not in certifier.permitted_scopes:
            raise ValidationError(
                "TRUST_CERTIFIER_SCOPE_NOT_PERMITTED",
                f"Certifier scope {scope} is not permitted",
                {
                    "certification_id": str(certification.id),
                    "certifier_id": str(certifier.id),
                    "scope": scope,
                },
            )
        certification.external_certifier_id = certifier.id
        certification.updated_by = self._to_uuid_or_none(actor_id)
        await self.repository.session.flush()
        await self.events.publish_certification_updated(
            CertificationEventPayload(
                certification_id=certification.id,
                agent_id=certification.agent_id,
                agent_fqn=certification.agent_fqn,
                agent_revision_id=certification.agent_revision_id,
                actor_id=str(actor_id),
                reason=f"certifier:{scope}",
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return CertificationResponse.model_validate(certification)

    async def record_reassessment(
        self,
        cert_id: UUID,
        data: ReassessmentCreate,
        actor_id: str,
    ) -> ReassessmentResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        record = await self.repository.create_reassessment(
            certification.id,
            ReassessmentRecord(
                certification_id=certification.id,
                verdict=data.verdict,
                reassessor_id=str(actor_id),
                notes=data.notes,
                created_by=self._to_uuid_or_none(actor_id),
                updated_by=self._to_uuid_or_none(actor_id),
            ),
        )
        if data.verdict == "pass" and certification.status == CertificationStatus.suspended:
            certification.status = CertificationStatus.active
        elif data.verdict == "fail" and certification.status in {
            CertificationStatus.active,
            CertificationStatus.expiring,
        }:
            certification.status = CertificationStatus.suspended
        certification.updated_by = self._to_uuid_or_none(actor_id)
        await self.repository.session.flush()
        event_payload = CertificationEventPayload(
            certification_id=certification.id,
            agent_id=certification.agent_id,
            agent_fqn=certification.agent_fqn,
            agent_revision_id=certification.agent_revision_id,
            actor_id=str(actor_id),
            reason=f"reassessment:{data.verdict}",
            occurred_at=utcnow(),
        )
        if data.verdict == "fail" and certification.status == CertificationStatus.suspended:
            await self.events.publish_certification_suspended(event_payload, make_correlation())
        else:
            await self.events.publish_certification_updated(event_payload, make_correlation())
        return ReassessmentResponse.model_validate(record)

    async def list_reassessments(self, cert_id: UUID) -> ReassessmentListResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        items = await self.repository.list_reassessments(cert_id)
        return ReassessmentListResponse(
            items=[ReassessmentResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def dismiss_suspension(
        self,
        cert_id: UUID,
        justification: str,
        actor_id: str,
    ) -> CertificationResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        if certification.status != CertificationStatus.suspended:
            raise ContractConflictError(
                "TRUST_CERTIFICATION_NOT_SUSPENDED",
                "Only suspended certifications can be dismissed",
                {"certification_id": str(certification.id)},
            )
        certification.status = CertificationStatus.active
        certification.updated_by = self._to_uuid_or_none(actor_id)
        pending = await self.repository.list_recertification_requests(
            certification_id=certification.id,
            status="pending",
        )
        if pending:
            await self.repository.resolve_recertification_request(
                pending[0].id,
                "dismissed",
                justification,
            )
        await self.repository.create_signal(
            TrustSignal(
                agent_id=certification.agent_id,
                signal_type="certification_suspension_dismissed",
                score_contribution=Decimal("0.0000"),
                source_type="audit",
                source_id=f"{certification.id}:{actor_id}",
                workspace_id=str(
                    getattr(
                        getattr(self.settings, "trust", self.settings),
                        "default_workspace_id",
                        "00000000-0000-0000-0000-000000000000",
                    )
                ),
            )
        )
        await self.repository.session.flush()
        await self.events.publish_certification_updated(
            CertificationEventPayload(
                certification_id=certification.id,
                agent_id=certification.agent_id,
                agent_fqn=certification.agent_fqn,
                agent_revision_id=certification.agent_revision_id,
                actor_id=str(actor_id),
                reason="suspension_dismissed",
                occurred_at=utcnow(),
            ),
            make_correlation(),
        )
        return CertificationResponse.model_validate(certification)

    async def list_recertification_requests(
        self,
        *,
        certification_id: UUID | None = None,
        status: str | None = None,
    ) -> TrustRecertificationRequestListResponse:
        items = await self.repository.list_recertification_requests(
            certification_id=certification_id,
            status=status,
        )
        return TrustRecertificationRequestListResponse(
            items=[TrustRecertificationRequestResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def get_recertification_request(
        self,
        request_id: UUID,
    ) -> TrustRecertificationRequestResponse:
        item = await self.repository.get_recertification_request(request_id)
        if item is None:
            raise RecertificationRequestNotFoundError(request_id)
        return TrustRecertificationRequestResponse.model_validate(item)

    async def is_agent_certified(self, agent_id: str, revision_id: str) -> bool:
        certifications = await self.repository.list_active_certifications_for_agent(agent_id)
        return any(item.agent_revision_id == revision_id for item in certifications)

    @staticmethod
    def _to_uuid_or_none(value: str | UUID | None) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except ValueError:
            return None


def ensure_active_certification(certification: TrustCertification) -> None:
    if certification.status != CertificationStatus.active:
        raise CertificationStateError(
            "Certification must be active for this operation",
            certification_id=certification.id,
        )
