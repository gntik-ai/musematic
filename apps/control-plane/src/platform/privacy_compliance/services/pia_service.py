from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.events import (
    PIAPayload,
    PrivacyEventPublisher,
    PrivacyEventType,
    utcnow,
)
from platform.privacy_compliance.exceptions import PIAApprovalError
from platform.privacy_compliance.models import PIAStatus, PrivacyImpactAssessment
from platform.privacy_compliance.repository import PrivacyComplianceRepository
from uuid import UUID

DATA_CATEGORIES_REQUIRING_PIA = {"pii", "phi", "financial", "confidential"}


class PIAService:
    def __init__(
        self,
        *,
        repository: PrivacyComplianceRepository,
        event_publisher: PrivacyEventPublisher,
    ) -> None:
        self.repository = repository
        self.events = event_publisher

    async def submit_draft(
        self,
        *,
        subject_type: str,
        subject_id: UUID,
        data_categories: list[str],
        legal_basis: str,
        retention_policy: str | None,
        risks: list[dict],
        mitigations: list[dict],
        submitted_by: UUID,
    ) -> PrivacyImpactAssessment:
        pia = await self.repository.create_pia(
            PrivacyImpactAssessment(
                subject_type=subject_type,
                subject_id=subject_id,
                data_categories=data_categories,
                legal_basis=legal_basis,
                retention_policy=retention_policy,
                risks=risks,
                mitigations=mitigations,
                status=PIAStatus.draft.value,
                submitted_by=submitted_by,
            )
        )
        await self._publish(PrivacyEventType.pia_drafted, pia, submitted_by)
        return pia

    async def submit_for_review(self, pia_id: UUID, actor: UUID) -> PrivacyImpactAssessment:
        pia = await self._get(pia_id)
        pia.status = PIAStatus.under_review.value
        await self.repository.session.flush()
        await self._publish(PrivacyEventType.pia_submitted_for_review, pia, actor)
        return pia

    async def approve(self, pia_id: UUID, approver: UUID) -> PrivacyImpactAssessment:
        pia = await self._get(pia_id)
        if pia.submitted_by == approver:
            raise PIAApprovalError()
        pia.status = PIAStatus.approved.value
        pia.approved_by = approver
        pia.approved_at = datetime.now(UTC)
        await self.repository.session.flush()
        await self._publish(PrivacyEventType.pia_approved, pia, approver)
        return pia

    async def reject(
        self,
        pia_id: UUID,
        reviewer: UUID,
        feedback: str,
    ) -> PrivacyImpactAssessment:
        pia = await self._get(pia_id)
        pia.status = PIAStatus.rejected.value
        pia.rejection_feedback = feedback
        await self.repository.session.flush()
        await self._publish(PrivacyEventType.pia_rejected, pia, reviewer)
        return pia

    async def check_material_change(
        self,
        subject_type: str,
        subject_id: UUID,
        new_data_categories: list[str],
    ) -> list[PrivacyImpactAssessment]:
        current = await self.repository.get_approved_pia(subject_type, subject_id)
        if current is None or set(current.data_categories) == set(new_data_categories):
            return []
        current.status = PIAStatus.superseded.value
        await self.repository.session.flush()
        await self._publish(PrivacyEventType.pia_superseded, current, None)
        return [current]

    async def get_approved_pia(
        self,
        subject_type: str,
        subject_id: UUID,
    ) -> PrivacyImpactAssessment | None:
        return await self.repository.get_approved_pia(subject_type, subject_id)

    async def _get(self, pia_id: UUID) -> PrivacyImpactAssessment:
        pia = await self.repository.get_pia(pia_id)
        if pia is None:
            raise ValueError("PIA not found")
        return pia

    async def _publish(
        self,
        event_type: PrivacyEventType,
        pia: PrivacyImpactAssessment,
        actor: UUID | None,
    ) -> None:
        await self.events.publish(
            event_type,
            PIAPayload(
                pia_id=pia.id,
                subject_type=pia.subject_type,
                subject_id=pia.subject_id,
                status=pia.status,
                occurred_at=utcnow(),
                actor_id=actor,
            ),
            key=str(pia.subject_id),
        )

