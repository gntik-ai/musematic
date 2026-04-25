from __future__ import annotations

from datetime import datetime, timedelta
from platform.audit.service import AuditChainService
from platform.common.events.producer import EventProducer
from platform.common.exceptions import AuthorizationError, NotFoundError, ValidationError
from platform.security_compliance.events import (
    SecretRotatedPayload,
    publish_security_compliance_event,
)
from platform.security_compliance.models import SecretRotationSchedule
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services._shared import append_audit, correlation, utcnow
from uuid import UUID


class SecretRotationService:
    def __init__(
        self,
        repository: SecurityComplianceRepository,
        provider: RotatableSecretProvider,
        *,
        producer: EventProducer | None = None,
        audit_chain: AuditChainService | None = None,
    ) -> None:
        self.repository = repository
        self.provider = provider
        self.producer = producer
        self.audit_chain = audit_chain

    async def create_schedule(
        self,
        *,
        secret_name: str,
        secret_type: str,
        rotation_interval_days: int,
        overlap_window_hours: int,
        vault_path: str,
        next_rotation_at: datetime | None = None,
    ) -> SecretRotationSchedule:
        if not 24 <= overlap_window_hours <= 168:
            raise ValidationError("INVALID_OVERLAP_WINDOW", "Overlap must be 24-168 hours")
        now = utcnow()
        item = await self.repository.add(
            SecretRotationSchedule(
                secret_name=secret_name,
                secret_type=secret_type,
                rotation_interval_days=rotation_interval_days,
                overlap_window_hours=overlap_window_hours,
                vault_path=vault_path,
                next_rotation_at=(
                    next_rotation_at
                    if next_rotation_at is not None
                    else now + timedelta(days=rotation_interval_days)
                ),
                rotation_state="idle",
            )
        )
        await self._emit(item)
        return item

    async def update_schedule(
        self,
        schedule_id: UUID,
        *,
        rotation_interval_days: int | None = None,
        overlap_window_hours: int | None = None,
        next_rotation_at: datetime | None = None,
    ) -> SecretRotationSchedule:
        schedule = await self._get(schedule_id)
        if rotation_interval_days is not None:
            schedule.rotation_interval_days = rotation_interval_days
        if overlap_window_hours is not None:
            if not 24 <= overlap_window_hours <= 168:
                raise ValidationError("INVALID_OVERLAP_WINDOW", "Overlap must be 24-168 hours")
            schedule.overlap_window_hours = overlap_window_hours
        if next_rotation_at is not None:
            schedule.next_rotation_at = next_rotation_at
        await self.repository.session.flush()
        return schedule

    async def trigger(
        self,
        schedule_id: UUID,
        *,
        emergency: bool = False,
        skip_overlap: bool = False,
        requester_id: UUID | None = None,
        approved_by: UUID | None = None,
    ) -> SecretRotationSchedule:
        schedule = await self._get(schedule_id)
        if emergency and skip_overlap and (approved_by is None or approved_by == requester_id):
            raise AuthorizationError(
                "TWO_PERSON_APPROVAL_REQUIRED", "Emergency skip-overlap requires 2PA"
            )
        try:
            now = utcnow()
            schedule.rotation_state = "rotating"
            await self._emit(schedule)
            current = await self.provider.get_current(schedule.secret_name)
            previous = None if skip_overlap else current
            schedule.rotation_state = "finalising" if skip_overlap else "overlap"
            schedule.overlap_ends_at = (
                None if skip_overlap else now + timedelta(hours=schedule.overlap_window_hours)
            )
            await self.provider.cache_rotation_state(
                schedule.secret_name,
                {
                    "current": current,
                    "previous": previous,
                    "overlap_ends_at": (
                        schedule.overlap_ends_at.isoformat() if schedule.overlap_ends_at else None
                    ),
                    "rotation_id": str(schedule.id),
                },
            )
            await self._emit(schedule)
            if skip_overlap:
                await self.finalise(schedule.id)
            await self.repository.session.flush()
            return schedule
        except Exception:
            schedule.rotation_state = "failed"
            await self.repository.session.flush()
            await self._emit(schedule)
            raise

    async def finalise(self, schedule_id: UUID) -> SecretRotationSchedule:
        schedule = await self._get(schedule_id)
        now = utcnow()
        schedule.rotation_state = "idle"
        schedule.last_rotated_at = now
        schedule.next_rotation_at = now + timedelta(days=schedule.rotation_interval_days)
        schedule.overlap_ends_at = None
        await self.provider.cache_rotation_state(
            schedule.secret_name,
            {"current": await self.provider.get_current(schedule.secret_name), "previous": None},
        )
        await self.repository.session.flush()
        await self._emit(schedule)
        return schedule

    async def trigger_due(self) -> list[SecretRotationSchedule]:
        results: list[SecretRotationSchedule] = []
        for schedule in await self.repository.list_due_rotations(utcnow()):
            results.append(await self.trigger(schedule.id))
        return results

    async def expire_overlaps(self) -> list[SecretRotationSchedule]:
        results: list[SecretRotationSchedule] = []
        for schedule in await self.repository.list_expired_overlaps(utcnow()):
            results.append(await self.finalise(schedule.id))
        return results

    async def list_schedules(self) -> list[SecretRotationSchedule]:
        return await self.repository.list_rotations()

    async def _get(self, schedule_id: UUID) -> SecretRotationSchedule:
        schedule = await self.repository.get_rotation(schedule_id)
        if schedule is None:
            raise NotFoundError("ROTATION_NOT_FOUND", "Rotation schedule not found")
        return schedule

    async def _emit(self, schedule: SecretRotationSchedule) -> None:
        await publish_security_compliance_event(
            "security.secret.rotated",
            SecretRotatedPayload(
                schedule_id=schedule.id,
                secret_name=schedule.secret_name,
                rotation_state=schedule.rotation_state,
                overlap_ends_at=schedule.overlap_ends_at,
            ),
            correlation(),
            self.producer,
            key=str(schedule.id),
        )
        await append_audit(
            self.audit_chain,
            schedule.id,
            "security_compliance",
            {
                "event": "secret.rotation_state",
                "schedule_id": schedule.id,
                "secret_name": schedule.secret_name,
                "rotation_state": schedule.rotation_state,
                "next_rotation_at": schedule.next_rotation_at,
                "overlap_ends_at": schedule.overlap_ends_at,
            },
        )
