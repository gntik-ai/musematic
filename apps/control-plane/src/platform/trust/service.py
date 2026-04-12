from __future__ import annotations

from datetime import UTC, datetime
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
    InvalidStateTransitionError,
)
from platform.trust.models import (
    CertificationStatus,
    TrustCertification,
    TrustCertificationEvidenceRef,
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
