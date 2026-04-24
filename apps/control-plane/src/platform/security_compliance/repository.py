from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from platform.security_compliance.models import (
    ComplianceControl,
    ComplianceEvidence,
    ComplianceEvidenceMapping,
    JitApproverPolicy,
    JitCredentialGrant,
    PenetrationTest,
    PentestFinding,
    PentestSlaPolicy,
    SecretRotationSchedule,
    SoftwareBillOfMaterials,
    VulnerabilityException,
    VulnerabilityScanResult,
)
from typing import TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

T = TypeVar("T")


class SecurityComplianceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, item: T) -> T:
        self.session.add(item)
        await self.session.flush()
        return item

    async def get_sbom(
        self,
        release_version: str,
        sbom_format: str,
    ) -> SoftwareBillOfMaterials | None:
        result = await self.session.execute(
            select(SoftwareBillOfMaterials)
            .where(SoftwareBillOfMaterials.release_version == release_version)
            .where(SoftwareBillOfMaterials.format == sbom_format)
        )
        return result.scalar_one_or_none()

    async def list_scans(self, release_version: str) -> list[VulnerabilityScanResult]:
        result = await self.session.execute(
            select(VulnerabilityScanResult)
            .where(VulnerabilityScanResult.release_version == release_version)
            .order_by(VulnerabilityScanResult.scanned_at.desc())
        )
        return list(result.scalars().all())

    async def list_active_exceptions(
        self,
        *,
        scanner: str | None = None,
        now: datetime | None = None,
    ) -> list[VulnerabilityException]:
        statement: Select[tuple[VulnerabilityException]] = select(VulnerabilityException).where(
            VulnerabilityException.expires_at > (now or datetime.now(UTC))
        )
        if scanner is not None:
            statement = statement.where(VulnerabilityException.scanner == scanner)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_rotations(self) -> list[SecretRotationSchedule]:
        result = await self.session.execute(
            select(SecretRotationSchedule).order_by(SecretRotationSchedule.secret_name.asc())
        )
        return list(result.scalars().all())

    async def get_rotation(self, schedule_id: UUID) -> SecretRotationSchedule | None:
        return await self.session.get(SecretRotationSchedule, schedule_id)

    async def list_due_rotations(self, now: datetime) -> list[SecretRotationSchedule]:
        result = await self.session.execute(
            select(SecretRotationSchedule)
            .where(SecretRotationSchedule.rotation_state == "idle")
            .where(SecretRotationSchedule.next_rotation_at <= now)
        )
        return list(result.scalars().all())

    async def list_expired_overlaps(self, now: datetime) -> list[SecretRotationSchedule]:
        result = await self.session.execute(
            select(SecretRotationSchedule)
            .where(SecretRotationSchedule.rotation_state == "overlap")
            .where(SecretRotationSchedule.overlap_ends_at <= now)
        )
        return list(result.scalars().all())

    async def get_jit_grant(self, grant_id: UUID) -> JitCredentialGrant | None:
        return await self.session.get(JitCredentialGrant, grant_id)

    async def list_jit_grants(self, user_id: UUID | None = None) -> list[JitCredentialGrant]:
        statement = select(JitCredentialGrant).order_by(JitCredentialGrant.requested_at.desc())
        if user_id is not None:
            statement = statement.where(JitCredentialGrant.user_id == user_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_jit_policies(self) -> list[JitApproverPolicy]:
        result = await self.session.execute(
            select(JitApproverPolicy).order_by(
                func.length(JitApproverPolicy.operation_pattern).desc()
            )
        )
        return list(result.scalars().all())

    async def get_pentest(self, pentest_id: UUID) -> PenetrationTest | None:
        return await self.session.get(PenetrationTest, pentest_id)

    async def list_pentests(self) -> list[PenetrationTest]:
        result = await self.session.execute(
            select(PenetrationTest).order_by(PenetrationTest.scheduled_for.desc())
        )
        return list(result.scalars().all())

    async def get_finding(self, finding_id: UUID) -> PentestFinding | None:
        return await self.session.get(PentestFinding, finding_id)

    async def list_findings(self, pentest_id: UUID) -> list[PentestFinding]:
        result = await self.session.execute(
            select(PentestFinding)
            .where(PentestFinding.pentest_id == pentest_id)
            .order_by(PentestFinding.remediation_due_date.asc())
        )
        return list(result.scalars().all())

    async def get_sla_policy(self, severity: str) -> PentestSlaPolicy | None:
        result = await self.session.execute(
            select(PentestSlaPolicy).where(PentestSlaPolicy.severity == severity)
        )
        return result.scalar_one_or_none()

    async def list_overdue_findings(self, today: date) -> list[PentestFinding]:
        result = await self.session.execute(
            select(PentestFinding)
            .where(PentestFinding.remediation_status == "open")
            .where(PentestFinding.remediation_due_date < today)
            .order_by(PentestFinding.remediation_due_date.asc())
        )
        return list(result.scalars().all())

    async def list_controls(self, framework: str | None = None) -> list[ComplianceControl]:
        statement = select(ComplianceControl).order_by(
            ComplianceControl.framework.asc(),
            ComplianceControl.control_id.asc(),
        )
        if framework is not None:
            statement = statement.where(ComplianceControl.framework == framework)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_control(self, control_id: UUID) -> ComplianceControl | None:
        return await self.session.get(ComplianceControl, control_id)

    async def list_mappings_by_evidence_type(
        self,
        evidence_type: str,
    ) -> list[ComplianceEvidenceMapping]:
        result = await self.session.execute(
            select(ComplianceEvidenceMapping).where(
                ComplianceEvidenceMapping.evidence_type == evidence_type
            )
        )
        return list(result.scalars().all())

    async def list_evidence(self, control_id: UUID | None = None) -> list[ComplianceEvidence]:
        statement = select(ComplianceEvidence).order_by(ComplianceEvidence.collected_at.desc())
        if control_id is not None:
            statement = statement.where(ComplianceEvidence.control_id == control_id)
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_evidence_for_controls(
        self,
        control_ids: Sequence[UUID],
    ) -> list[ComplianceEvidence]:
        if not control_ids:
            return []
        result = await self.session.execute(
            select(ComplianceEvidence).where(ComplianceEvidence.control_id.in_(control_ids))
        )
        return list(result.scalars().all())

    async def list_evidence_window(
        self,
        control_ids: Sequence[UUID],
        *,
        window_start: datetime,
        window_end: datetime,
    ) -> list[ComplianceEvidence]:
        if not control_ids:
            return []
        result = await self.session.execute(
            select(ComplianceEvidence)
            .where(ComplianceEvidence.control_id.in_(control_ids))
            .where(
                and_(
                    ComplianceEvidence.collected_at >= window_start,
                    ComplianceEvidence.collected_at <= window_end,
                )
            )
            .order_by(ComplianceEvidence.collected_at.asc())
        )
        return list(result.scalars().all())
