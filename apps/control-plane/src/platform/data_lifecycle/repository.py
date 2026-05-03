"""Async SQLAlchemy repository for the data_lifecycle BC.

All queries respect the ``tenant_isolation`` RLS policy installed by
migration 111. Filters that span tenants (e.g. the platform-wide
sub-processors list) deliberately do NOT include a tenant_id predicate
because the table itself has no tenant column.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from platform.data_lifecycle.models import (
    DataExportJob,
    DeletionJob,
    DeletionPhase,
    ExportStatus,
    SubProcessor,
)


class DataLifecycleRepository:
    """Read/write helper for the three data-lifecycle tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # =========================================================================
    # data_export_jobs
    # =========================================================================

    async def create_export_job(
        self,
        *,
        tenant_id: UUID,
        scope_type: str,
        scope_id: UUID,
        requested_by_user_id: UUID | None,
        correlation_id: UUID | None = None,
    ) -> DataExportJob:
        job = DataExportJob(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            requested_by_user_id=requested_by_user_id,
            status=ExportStatus.pending.value,
            correlation_id=correlation_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_export_job(self, job_id: UUID) -> DataExportJob | None:
        return await self.session.get(DataExportJob, job_id)

    async def find_active_export_for_scope(
        self, *, scope_type: str, scope_id: UUID
    ) -> DataExportJob | None:
        """Return the in-flight job (pending|processing) for a scope, if any.

        Used by the request endpoint for idempotency: a second request for
        the same scope while a job is still pending returns the existing
        job rather than creating a new one.
        """

        stmt = (
            select(DataExportJob)
            .where(DataExportJob.scope_type == scope_type)
            .where(DataExportJob.scope_id == scope_id)
            .where(
                DataExportJob.status.in_(
                    (ExportStatus.pending.value, ExportStatus.processing.value)
                )
            )
            .order_by(desc(DataExportJob.created_at))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def count_recent_exports_for_scope(
        self,
        *,
        scope_type: str,
        scope_id: UUID,
        within: timedelta,
    ) -> int:
        """Count export jobs created in the last ``within`` window.

        Used to enforce the per-workspace 24h rate limit.
        """

        cutoff = datetime.utcnow() - within
        stmt = (
            select(func.count())
            .select_from(DataExportJob)
            .where(DataExportJob.scope_type == scope_type)
            .where(DataExportJob.scope_id == scope_id)
            .where(DataExportJob.created_at >= cutoff)
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_export_jobs_for_scope(
        self,
        *,
        scope_type: str,
        scope_id: UUID,
        status: str | None = None,
        limit: int = 20,
    ) -> list[DataExportJob]:
        stmt = (
            select(DataExportJob)
            .where(DataExportJob.scope_type == scope_type)
            .where(DataExportJob.scope_id == scope_id)
            .order_by(desc(DataExportJob.created_at))
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(DataExportJob.status == status)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_export_status(
        self,
        *,
        job_id: UUID,
        status: str,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        output_url: str | None = None,
        output_size_bytes: int | None = None,
        output_expires_at: datetime | None = None,
        error_message: str | None = None,
    ) -> None:
        values: dict[str, object] = {"status": status}
        if started_at is not None:
            values["started_at"] = started_at
        if completed_at is not None:
            values["completed_at"] = completed_at
        if output_url is not None:
            values["output_url"] = output_url
        if output_size_bytes is not None:
            values["output_size_bytes"] = output_size_bytes
        if output_expires_at is not None:
            values["output_expires_at"] = output_expires_at
        if error_message is not None:
            values["error_message"] = error_message
        await self.session.execute(
            update(DataExportJob).where(DataExportJob.id == job_id).values(**values)
        )

    # =========================================================================
    # deletion_jobs
    # =========================================================================

    async def create_deletion_job(
        self,
        *,
        tenant_id: UUID,
        scope_type: str,
        scope_id: UUID,
        requested_by_user_id: UUID | None,
        two_pa_token_id: UUID | None,
        grace_period_days: int,
        grace_ends_at: datetime,
        cancel_token_hash: bytes,
        cancel_token_expires_at: datetime,
        final_export_job_id: UUID | None = None,
        correlation_id: UUID | None = None,
    ) -> DeletionJob:
        job = DeletionJob(
            tenant_id=tenant_id,
            scope_type=scope_type,
            scope_id=scope_id,
            phase=DeletionPhase.phase_1.value,
            requested_by_user_id=requested_by_user_id,
            two_pa_token_id=two_pa_token_id,
            grace_period_days=grace_period_days,
            grace_ends_at=grace_ends_at,
            cancel_token_hash=cancel_token_hash,
            cancel_token_expires_at=cancel_token_expires_at,
            final_export_job_id=final_export_job_id,
            correlation_id=correlation_id,
        )
        self.session.add(job)
        await self.session.flush()
        return job

    async def get_deletion_job(self, job_id: UUID) -> DeletionJob | None:
        return await self.session.get(DeletionJob, job_id)

    async def find_active_deletion_for_scope(
        self, *, scope_type: str, scope_id: UUID
    ) -> DeletionJob | None:
        """Return the active job (phase_1 | phase_2) for a scope.

        The partial-unique index ``uq_deletion_jobs_active_per_scope``
        guarantees at most one such row exists at a time.
        """

        stmt = (
            select(DeletionJob)
            .where(DeletionJob.scope_type == scope_type)
            .where(DeletionJob.scope_id == scope_id)
            .where(
                DeletionJob.phase.in_(
                    (DeletionPhase.phase_1.value, DeletionPhase.phase_2.value)
                )
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_deletion_by_cancel_token_hash(
        self, *, token_hash: bytes
    ) -> DeletionJob | None:
        stmt = select(DeletionJob).where(DeletionJob.cancel_token_hash == token_hash)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_grace_expired_phase_1_jobs(
        self, *, now: datetime, limit: int = 100
    ) -> list[DeletionJob]:
        """Jobs whose grace clock has run out — fed to the cascade dispatcher."""

        stmt = (
            select(DeletionJob)
            .where(DeletionJob.phase == DeletionPhase.phase_1.value)
            .where(DeletionJob.grace_ends_at <= now)
            .order_by(DeletionJob.grace_ends_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_deletion_phase(
        self,
        *,
        job_id: UUID,
        phase: str,
        cascade_started_at: datetime | None = None,
        cascade_completed_at: datetime | None = None,
        tombstone_id: UUID | None = None,
        abort_reason: str | None = None,
    ) -> None:
        values: dict[str, object] = {"phase": phase}
        if cascade_started_at is not None:
            values["cascade_started_at"] = cascade_started_at
        if cascade_completed_at is not None:
            values["cascade_completed_at"] = cascade_completed_at
        if tombstone_id is not None:
            values["tombstone_id"] = tombstone_id
        if abort_reason is not None:
            values["abort_reason"] = abort_reason
        await self.session.execute(
            update(DeletionJob).where(DeletionJob.id == job_id).values(**values)
        )

    async def extend_grace(
        self, *, job_id: UUID, new_grace_ends_at: datetime
    ) -> None:
        await self.session.execute(
            update(DeletionJob)
            .where(DeletionJob.id == job_id)
            .values(
                grace_ends_at=new_grace_ends_at,
                cancel_token_expires_at=new_grace_ends_at,
            )
        )

    # =========================================================================
    # sub_processors (platform-level — no tenant filter)
    # =========================================================================

    async def list_sub_processors_active(self) -> list[SubProcessor]:
        stmt = (
            select(SubProcessor)
            .where(SubProcessor.is_active.is_(True))
            .order_by(SubProcessor.category.asc(), SubProcessor.name.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_sub_processors_all(self) -> list[SubProcessor]:
        stmt = select(SubProcessor).order_by(
            SubProcessor.is_active.desc(),
            SubProcessor.category.asc(),
            SubProcessor.name.asc(),
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_sub_processor(self, sub_processor_id: UUID) -> SubProcessor | None:
        return await self.session.get(SubProcessor, sub_processor_id)

    async def get_sub_processor_by_name(self, name: str) -> SubProcessor | None:
        stmt = select(SubProcessor).where(SubProcessor.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def insert_sub_processor(
        self,
        *,
        name: str,
        category: str,
        location: str,
        data_categories: list[str],
        privacy_policy_url: str | None,
        dpa_url: str | None,
        started_using_at: datetime | None,
        notes: str | None,
        updated_by_user_id: UUID | None,
    ) -> SubProcessor:
        sp = SubProcessor(
            name=name,
            category=category,
            location=location,
            data_categories=list(data_categories),
            privacy_policy_url=privacy_policy_url,
            dpa_url=dpa_url,
            started_using_at=started_using_at,
            notes=notes,
            updated_by_user_id=updated_by_user_id,
        )
        self.session.add(sp)
        await self.session.flush()
        return sp

    async def update_sub_processor(
        self,
        *,
        sub_processor_id: UUID,
        updates: dict[str, object],
        updated_by_user_id: UUID | None,
    ) -> None:
        if not updates:
            return
        values = {**updates, "updated_by_user_id": updated_by_user_id}
        await self.session.execute(
            update(SubProcessor)
            .where(SubProcessor.id == sub_processor_id)
            .values(**values)
        )

    async def soft_delete_sub_processor(
        self, *, sub_processor_id: UUID, updated_by_user_id: UUID | None
    ) -> None:
        await self.session.execute(
            update(SubProcessor)
            .where(SubProcessor.id == sub_processor_id)
            .values(is_active=False, updated_by_user_id=updated_by_user_id)
        )

    async def latest_sub_processors_change(self) -> datetime | None:
        stmt = select(func.max(SubProcessor.updated_at))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
