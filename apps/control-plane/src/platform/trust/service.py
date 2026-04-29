from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from platform.audit.repository import AuditChainRepository
from platform.audit.service import AuditChainService
from platform.common.audit_hook import audit_chain_hook
from platform.common.exceptions import ValidationError
from platform.common.tagging.filter_extension import TagLabelFilterParams
from platform.common.tagging.listing import resolve_filtered_entity_ids
from platform.evaluation.repository import EvaluationRepository
from platform.model_catalog.models import ModelCard, ModelCatalogEntry
from platform.registry.models import AgentProfile
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
    CertificationBlockedError,
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
    TrustRecertificationRequest,
    TrustSignal,
)
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    CertificationCreate,
    CertificationResponse,
    EvidenceRefCreate,
    EvidenceRefResponse,
)
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select


class CertificationService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
        fairness_gate: Any | None = None,
        tag_service: Any | None = None,
        label_service: Any | None = None,
        tagging_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.events = TrustEventPublisher(producer)
        self.fairness_gate = fairness_gate
        self.tag_service = tag_service
        self.label_service = label_service
        self.tagging_service = tagging_service

    async def create(self, data: CertificationCreate, issuer_id: str) -> CertificationResponse:
        await self._assert_pia_gate(data)
        await self._ensure_bound_model_has_card(data.agent_id)
        await self._assert_fairness_gate(data)
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
        persisted = await self.repository.get_certification(certification.id)
        if persisted is None:
            raise CertificationNotFoundError(certification.id)
        return CertificationResponse.model_validate(persisted)

    async def get(self, cert_id: UUID) -> CertificationResponse:
        certification = await self.repository.get_certification(cert_id)
        if certification is None:
            raise CertificationNotFoundError(cert_id)
        return CertificationResponse.model_validate(certification)

    async def _assert_pia_gate(self, data: CertificationCreate) -> None:
        if not data.data_categories:
            return
        from platform.privacy_compliance.repository import PrivacyComplianceRepository
        from platform.privacy_compliance.services.pia_service import DATA_CATEGORIES_REQUIRING_PIA

        categories = {category.casefold() for category in data.data_categories}
        if categories.isdisjoint(DATA_CATEGORIES_REQUIRING_PIA):
            return
        try:
            subject_id = UUID(data.agent_id)
        except ValueError:
            return
        pia = await PrivacyComplianceRepository(self.repository.session).get_approved_pia(
            "agent",
            subject_id,
        )
        if pia is None:
            raise CertificationBlockedError(
                "pia_required",
                f"Agent {data.agent_id} declares privacy-sensitive data categories.",
            )

    async def _assert_fairness_gate(self, data: CertificationCreate) -> None:
        high_impact = data.high_impact_use or "high_impact_use" in {
            item.casefold() for item in data.data_categories
        }
        if not high_impact:
            return
        try:
            agent_id = UUID(data.agent_id)
        except ValueError:
            return
        staleness_days = int(
            getattr(self.settings.content_moderation, "default_fairness_staleness_days", 90)
        )
        if self.fairness_gate is not None:
            latest = await self.fairness_gate.get_latest_passing_evaluation(
                agent_id=agent_id,
                agent_revision_id=data.agent_revision_id,
                staleness_days=staleness_days,
            )
            stale_latest = (
                None
                if latest is not None
                else await self._get_stale_fairness_gate_result(agent_id, data.agent_revision_id)
            )
        else:
            cutoff = datetime.now(UTC) - timedelta(days=staleness_days)
            evaluation_repo = EvaluationRepository(self.repository.session)
            latest = await evaluation_repo.get_latest_passing_fairness_evaluation(
                agent_id,
                data.agent_revision_id,
                cutoff,
            )
            stale_latest = await evaluation_repo.get_latest_passing_fairness_evaluation_any_age(
                agent_id,
                data.agent_revision_id,
            )
        if latest is not None:
            await self._append_fairness_gate_audit(data, "passed")
            return
        reason = (
            "fairness_evaluation_stale"
            if stale_latest is not None
            else "fairness_evaluation_required"
        )
        await self._append_fairness_gate_audit(data, reason)
        if stale_latest is not None:
            raise CertificationBlockedError(
                "fairness_evaluation_stale",
                "High-impact agents require a non-stale passing fairness evaluation.",
            )
        if latest is None:
            raise CertificationBlockedError(
                "fairness_evaluation_required",
                "High-impact agents require a recent passing fairness evaluation.",
            )

    async def _get_stale_fairness_gate_result(
        self,
        agent_id: UUID,
        agent_revision_id: str,
    ) -> object | None:
        getter = getattr(self.fairness_gate, "get_latest_passing_evaluation_any_age", None)
        if getter is None:
            return None
        result = await getter(agent_id=agent_id, agent_revision_id=agent_revision_id)
        return cast(object | None, result)

    async def _append_fairness_gate_audit(
        self,
        data: CertificationCreate,
        outcome: str,
    ) -> None:
        if not hasattr(self.settings, "audit") or not callable(
            getattr(self.repository.session, "execute", None)
        ):
            return
        audit_chain = AuditChainService(
            AuditChainRepository(self.repository.session),
            self.settings,
            producer=getattr(self.events, "producer", None),
        )
        await audit_chain_hook(
            audit_chain,
            None,
            "trust.certification.fairness_gate",
            {
                "agent_id": data.agent_id,
                "agent_revision_id": data.agent_revision_id,
                "high_impact_use": data.high_impact_use,
                "outcome": outcome,
                "occurred_at": datetime.now(UTC),
            },
        )

    async def list_for_agent(
        self,
        agent_id: str,
        tag_label_filters: TagLabelFilterParams | None = None,
    ) -> list[CertificationResponse]:
        all_certifications = await self.repository.list_certifications_for_agent(agent_id)
        allowed_ids = await resolve_filtered_entity_ids(
            entity_type="certification",
            visible_entity_ids={certification.id for certification in all_certifications},
            filters=tag_label_filters,
            tag_service=self.tag_service,
            label_service=self.label_service,
        )
        certifications = (
            all_certifications
            if allowed_ids is None
            else [
                certification
                for certification in all_certifications
                if certification.id in allowed_ids
            ]
        )
        return [CertificationResponse.model_validate(item) for item in certifications]

    async def list_visible_certifications(self, requester: UUID | dict[str, Any]) -> set[UUID]:
        agent_id = (
            str(requester.get("agent_id") or requester.get("agent_profile_id") or "")
            if isinstance(requester, dict)
            else str(requester)
        )
        if not agent_id:
            return set()
        return {
            certification.id
            for certification in await self.repository.list_certifications_for_agent(agent_id)
        }

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
        if self.tagging_service is not None:
            await self.tagging_service.cascade_on_entity_deletion(
                "certification",
                certification.id,
            )
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

    async def flag_affected_certifications_for_rereview(self, catalog_entry_id: UUID) -> int:
        entry = await self.repository.session.get(ModelCatalogEntry, catalog_entry_id)
        if entry is None:
            return 0
        binding = f"{entry.provider}:{entry.model_id}"
        result = await self.repository.session.execute(
            select(AgentProfile).where(AgentProfile.default_model_binding == binding)
        )
        flagged = 0
        for profile in result.scalars().all():
            certifications = await self.repository.get_active_or_expiring_certifications_for_agent(
                str(profile.id),
            )
            for certification in certifications:
                await self.repository.create_recertification_request(
                    TrustRecertificationRequest(
                        certification_id=certification.id,
                        trigger_type="model_card_material_change",
                        trigger_reference=str(catalog_entry_id),
                        resolution_status="pending",
                    )
                )
                flagged += 1
        await self.repository.session.flush()
        return flagged

    async def _ensure_bound_model_has_card(self, agent_id: str) -> None:
        try:
            agent_uuid = UUID(str(agent_id))
        except ValueError:
            return
        profile = await self.repository.session.get(AgentProfile, agent_uuid)
        binding = getattr(profile, "default_model_binding", None)
        if not isinstance(binding, str) or ":" not in binding:
            return
        provider, model_id = binding.split(":", 1)
        result = await self.repository.session.execute(
            select(ModelCatalogEntry)
            .where(ModelCatalogEntry.provider == provider)
            .where(ModelCatalogEntry.model_id == model_id)
        )
        entry = result.scalar_one_or_none()
        if entry is None:
            return
        card_result = await self.repository.session.execute(
            select(ModelCard).where(ModelCard.catalog_entry_id == entry.id)
        )
        if card_result.scalar_one_or_none() is None:
            raise ValidationError(
                "CERTIFICATION_BLOCKED",
                "Certification blocked because the bound model is missing a model card.",
                {"reason": "model_card_missing", "catalog_entry_id": str(entry.id)},
            )

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
