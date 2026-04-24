from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.security_compliance.models import SecretRotationSchedule
from platform.security_compliance.services.secret_rotation_service import SecretRotationService
from uuid import UUID, uuid4

import pytest


class FakeRepository:
    def __init__(self) -> None:
        self.session = self
        self.rotations: dict[UUID, SecretRotationSchedule] = {}

    async def flush(self) -> None:
        return None

    async def add(self, item: SecretRotationSchedule) -> SecretRotationSchedule:
        item.id = uuid4()
        self.rotations[item.id] = item
        return item

    async def get_rotation(self, schedule_id: UUID) -> SecretRotationSchedule | None:
        return self.rotations.get(schedule_id)

    async def list_rotations(self) -> list[SecretRotationSchedule]:
        return list(self.rotations.values())

    async def list_due_rotations(self, now: datetime) -> list[SecretRotationSchedule]:
        return [
            item
            for item in self.rotations.values()
            if item.rotation_state == "idle" and item.next_rotation_at <= now
        ]

    async def list_expired_overlaps(self, now: datetime) -> list[SecretRotationSchedule]:
        return [
            item
            for item in self.rotations.values()
            if item.rotation_state == "overlap" and item.overlap_ends_at <= now
        ]


class FakeProvider:
    def __init__(self) -> None:
        self.state: dict[str, dict[str, object]] = {}

    async def get_current(self, secret_name: str) -> str:
        return f"{secret_name}-current"

    async def cache_rotation_state(self, secret_name: str, state: dict[str, object]) -> None:
        self.state[secret_name] = state


class FailingProvider(FakeProvider):
    async def get_current(self, secret_name: str) -> str:
        del secret_name
        raise RuntimeError("vault unavailable")


def _service() -> SecretRotationService:
    return SecretRotationService(FakeRepository(), FakeProvider())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_rotation_schedule_and_trigger_overlap() -> None:
    service = _service()
    schedule = await service.create_schedule(
        secret_name="jwt",
        secret_type="jwt",
        rotation_interval_days=90,
        overlap_window_hours=24,
        vault_path="secret/jwt",
        next_rotation_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    result = await service.trigger(schedule.id, requester_id=uuid4())

    assert result.rotation_state == "overlap"
    assert result.overlap_ends_at is not None
    assert result.next_rotation_at <= datetime.now(UTC)


@pytest.mark.asyncio
async def test_emergency_skip_overlap_requires_peer_approval() -> None:
    service = _service()
    requester = uuid4()
    schedule = await service.create_schedule(
        secret_name="db",
        secret_type="password",
        rotation_interval_days=30,
        overlap_window_hours=24,
        vault_path="secret/db",
    )

    with pytest.raises(AuthorizationError):
        await service.trigger(
            schedule.id,
            emergency=True,
            skip_overlap=True,
            requester_id=requester,
            approved_by=requester,
        )


@pytest.mark.asyncio
async def test_overlap_expirer_finalises_rotation() -> None:
    service = _service()
    schedule = await service.create_schedule(
        secret_name="api",
        secret_type="api_key",
        rotation_interval_days=30,
        overlap_window_hours=24,
        vault_path="secret/api",
    )
    schedule.rotation_state = "overlap"
    schedule.overlap_ends_at = datetime.now(UTC) - timedelta(seconds=1)

    [result] = await service.expire_overlaps()

    assert result.rotation_state == "idle"
    assert result.overlap_ends_at is None
    assert result.last_rotated_at is not None


@pytest.mark.asyncio
async def test_rotation_update_due_listing_and_skip_overlap_paths() -> None:
    service = _service()
    with pytest.raises(ValidationError):
        await service.create_schedule(
            secret_name="bad",
            secret_type="api_key",
            rotation_interval_days=30,
            overlap_window_hours=1,
            vault_path="secret/bad",
        )
    schedule = await service.create_schedule(
        secret_name="jwt",
        secret_type="jwt",
        rotation_interval_days=30,
        overlap_window_hours=24,
        vault_path="secret/jwt",
        next_rotation_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    updated = await service.update_schedule(
        schedule.id,
        rotation_interval_days=45,
        overlap_window_hours=48,
        next_rotation_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    due = await service.trigger_due()
    listed = await service.list_schedules()

    assert updated.rotation_interval_days == 45
    assert due == [schedule]
    assert listed == [schedule]

    skip = await service.create_schedule(
        secret_name="db",
        secret_type="password",
        rotation_interval_days=30,
        overlap_window_hours=24,
        vault_path="secret/db",
    )
    result = await service.trigger(
        skip.id,
        emergency=True,
        skip_overlap=True,
        requester_id=uuid4(),
        approved_by=uuid4(),
    )
    assert result.rotation_state == "idle"


@pytest.mark.asyncio
async def test_rotation_trigger_marks_failure_when_provider_fails() -> None:
    repository = FakeRepository()
    service = SecretRotationService(repository, FailingProvider())  # type: ignore[arg-type]
    schedule = await service.create_schedule(
        secret_name="broken",
        secret_type="api_key",
        rotation_interval_days=30,
        overlap_window_hours=24,
        vault_path="secret/broken",
    )

    with pytest.raises(RuntimeError):
        await service.trigger(schedule.id)

    assert repository.rotations[schedule.id].rotation_state == "failed"
