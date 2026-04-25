from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.models import (
    ConsentType,
    DSRStatus,
    PIAStatus,
    PrivacyConsentRecord,
    PrivacyDeletionTombstone,
    PrivacyDLPEvent,
    PrivacyDLPRule,
    PrivacyDSRRequest,
    PrivacyImpactAssessment,
    PrivacyResidencyConfig,
)
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession


def utcnow() -> datetime:
    return datetime.now(UTC)


class PrivacyComplianceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_dsr(self, dsr: PrivacyDSRRequest) -> PrivacyDSRRequest:
        self.session.add(dsr)
        await self.session.flush()
        return dsr

    async def get_dsr(self, dsr_id: UUID) -> PrivacyDSRRequest | None:
        return await self.session.get(PrivacyDSRRequest, dsr_id)

    async def list_dsrs(
        self,
        *,
        subject_user_id: UUID | None = None,
        request_type: str | None = None,
        status: str | None = None,
    ) -> list[PrivacyDSRRequest]:
        query = select(PrivacyDSRRequest).order_by(
            PrivacyDSRRequest.requested_at.desc(),
            PrivacyDSRRequest.id.desc(),
        )
        if subject_user_id is not None:
            query = query.where(PrivacyDSRRequest.subject_user_id == subject_user_id)
        if request_type is not None:
            query = query.where(PrivacyDSRRequest.request_type == request_type)
        if status is not None:
            query = query.where(PrivacyDSRRequest.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_due_scheduled_dsrs(self, now: datetime) -> list[PrivacyDSRRequest]:
        result = await self.session.execute(
            select(PrivacyDSRRequest)
            .where(
                PrivacyDSRRequest.status == DSRStatus.scheduled.value,
                PrivacyDSRRequest.scheduled_release_at <= now,
            )
            .order_by(PrivacyDSRRequest.scheduled_release_at.asc())
        )
        return list(result.scalars().all())

    async def update_dsr(self, dsr: PrivacyDSRRequest, **fields: Any) -> PrivacyDSRRequest:
        for key, value in fields.items():
            setattr(dsr, key, value)
        await self.session.flush()
        return dsr

    async def insert_tombstone(
        self,
        *,
        subject_user_id_hash: str,
        salt_version: int,
        entities_deleted: dict[str, int],
        cascade_log: list[dict[str, Any]],
        proof_hash: str,
        created_at: datetime | None = None,
    ) -> PrivacyDeletionTombstone:
        tombstone = PrivacyDeletionTombstone(
            subject_user_id_hash=subject_user_id_hash,
            salt_version=salt_version,
            entities_deleted=entities_deleted,
            cascade_log=cascade_log,
            proof_hash=proof_hash,
            created_at=created_at or utcnow(),
        )
        self.session.add(tombstone)
        await self.session.flush()
        return tombstone

    async def get_tombstone(self, tombstone_id: UUID) -> PrivacyDeletionTombstone | None:
        return await self.session.get(PrivacyDeletionTombstone, tombstone_id)

    async def get_residency_config(self, workspace_id: UUID) -> PrivacyResidencyConfig | None:
        result = await self.session.execute(
            select(PrivacyResidencyConfig).where(
                PrivacyResidencyConfig.workspace_id == workspace_id
            )
        )
        return result.scalar_one_or_none()

    async def upsert_residency_config(
        self,
        *,
        workspace_id: UUID,
        region_code: str,
        allowed_transfer_regions: list[str],
    ) -> PrivacyResidencyConfig:
        config = await self.get_residency_config(workspace_id)
        if config is None:
            config = PrivacyResidencyConfig(
                workspace_id=workspace_id,
                region_code=region_code,
                allowed_transfer_regions=allowed_transfer_regions,
            )
            self.session.add(config)
        else:
            config.region_code = region_code
            config.allowed_transfer_regions = allowed_transfer_regions
        await self.session.flush()
        return config

    async def delete_residency_config(self, workspace_id: UUID) -> bool:
        result = await self.session.execute(
            delete(PrivacyResidencyConfig).where(
                PrivacyResidencyConfig.workspace_id == workspace_id
            )
        )
        await self.session.flush()
        return bool(result.rowcount)

    async def create_dlp_rule(self, rule: PrivacyDLPRule) -> PrivacyDLPRule:
        self.session.add(rule)
        await self.session.flush()
        return rule

    async def get_dlp_rule(self, rule_id: UUID) -> PrivacyDLPRule | None:
        return await self.session.get(PrivacyDLPRule, rule_id)

    async def list_dlp_rules(self, workspace_id: UUID | None = None) -> list[PrivacyDLPRule]:
        query = select(PrivacyDLPRule).where(PrivacyDLPRule.enabled.is_(True))
        if workspace_id is not None:
            query = query.where(
                (PrivacyDLPRule.workspace_id.is_(None))
                | (PrivacyDLPRule.workspace_id == workspace_id)
            )
        result = await self.session.execute(query.order_by(PrivacyDLPRule.name.asc()))
        return list(result.scalars().all())

    async def update_dlp_rule(self, rule: PrivacyDLPRule, **fields: Any) -> PrivacyDLPRule:
        for key, value in fields.items():
            if value is not None:
                setattr(rule, key, value)
        await self.session.flush()
        return rule

    async def delete_dlp_rule(self, rule: PrivacyDLPRule) -> None:
        await self.session.delete(rule)
        await self.session.flush()

    async def create_dlp_event(self, event: PrivacyDLPEvent) -> PrivacyDLPEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_dlp_events(self, workspace_id: UUID | None = None) -> list[PrivacyDLPEvent]:
        query = select(PrivacyDLPEvent).order_by(PrivacyDLPEvent.created_at.desc())
        if workspace_id is not None:
            query = query.where(PrivacyDLPEvent.workspace_id == workspace_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create_pia(self, pia: PrivacyImpactAssessment) -> PrivacyImpactAssessment:
        self.session.add(pia)
        await self.session.flush()
        return pia

    async def get_pia(self, pia_id: UUID) -> PrivacyImpactAssessment | None:
        return await self.session.get(PrivacyImpactAssessment, pia_id)

    async def list_pias(
        self,
        *,
        subject_type: str | None = None,
        subject_id: UUID | None = None,
        status: str | None = None,
    ) -> list[PrivacyImpactAssessment]:
        query = select(PrivacyImpactAssessment).order_by(
            PrivacyImpactAssessment.created_at.desc()
        )
        if subject_type is not None:
            query = query.where(PrivacyImpactAssessment.subject_type == subject_type)
        if subject_id is not None:
            query = query.where(PrivacyImpactAssessment.subject_id == subject_id)
        if status is not None:
            query = query.where(PrivacyImpactAssessment.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_approved_pia(
        self,
        subject_type: str,
        subject_id: UUID,
    ) -> PrivacyImpactAssessment | None:
        result = await self.session.execute(
            select(PrivacyImpactAssessment)
            .where(
                PrivacyImpactAssessment.subject_type == subject_type,
                PrivacyImpactAssessment.subject_id == subject_id,
                PrivacyImpactAssessment.status == PIAStatus.approved.value,
            )
            .order_by(PrivacyImpactAssessment.approved_at.desc())
        )
        return result.scalars().first()

    async def upsert_consent(
        self,
        *,
        user_id: UUID,
        consent_type: str,
        granted: bool,
        workspace_id: UUID | None = None,
        now: datetime | None = None,
    ) -> PrivacyConsentRecord:
        result = await self.session.execute(
            select(PrivacyConsentRecord).where(
                PrivacyConsentRecord.user_id == user_id,
                PrivacyConsentRecord.consent_type == consent_type,
            )
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = PrivacyConsentRecord(
                user_id=user_id,
                consent_type=consent_type,
                granted=granted,
                granted_at=now or utcnow(),
                revoked_at=None if granted else now or utcnow(),
                workspace_id=workspace_id,
            )
            self.session.add(record)
        else:
            record.granted = granted
            record.granted_at = now or utcnow()
            record.revoked_at = None if granted else now or utcnow()
            record.workspace_id = workspace_id
        await self.session.flush()
        return record

    async def get_consent_records(self, user_id: UUID) -> list[PrivacyConsentRecord]:
        result = await self.session.execute(
            select(PrivacyConsentRecord)
            .where(PrivacyConsentRecord.user_id == user_id)
            .order_by(PrivacyConsentRecord.consent_type.asc())
        )
        return list(result.scalars().all())

    async def revoke_consent(
        self,
        *,
        user_id: UUID,
        consent_type: str,
        now: datetime | None = None,
    ) -> PrivacyConsentRecord:
        records = await self.get_consent_records(user_id)
        for record in records:
            if record.consent_type == consent_type:
                record.granted = False
                record.revoked_at = now or utcnow()
                await self.session.flush()
                return record
        return await self.upsert_consent(
            user_id=user_id,
            consent_type=consent_type,
            granted=False,
            now=now,
        )

    async def list_recent_revocations(self, since: datetime) -> list[PrivacyConsentRecord]:
        result = await self.session.execute(
            select(PrivacyConsentRecord).where(
                PrivacyConsentRecord.revoked_at.is_not(None),
                PrivacyConsentRecord.revoked_at >= since,
            )
        )
        return list(result.scalars().all())

    async def current_consent_state(
        self,
        user_id: UUID,
    ) -> dict[ConsentType, PrivacyConsentRecord | None]:
        consent_records = await self.get_consent_records(user_id)
        records = {ConsentType(item.consent_type): item for item in consent_records}
        return {consent_type: records.get(consent_type) for consent_type in ConsentType}
