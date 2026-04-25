from __future__ import annotations

import os
from asyncio import gather
from datetime import UTC, datetime, timedelta
from platform.security_compliance.models import SecretRotationSchedule
from platform.security_compliance.services.secret_rotation_service import SecretRotationService
from typing import Any
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_SECRET_ROTATION_ZERO_FAILURE") != "1",
    reason="Set RUN_SECRET_ROTATION_ZERO_FAILURE=1 to run the 100 req/s rotation scenario",
)


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


class TrafficValidatorProvider:
    def __init__(self) -> None:
        self.current_value = "test-db-current"
        self.rotation_state: dict[str, dict[str, Any]] = {}

    async def get_current(self, secret_name: str) -> str:
        cached = self.rotation_state.get(secret_name, {})
        current = cached.get("current")
        return str(current) if isinstance(current, str) else self.current_value

    async def cache_rotation_state(self, secret_name: str, state: dict[str, Any]) -> None:
        self.rotation_state[secret_name] = state

    async def validate_either(self, secret_name: str, presented: str) -> bool:
        state = self.rotation_state.get(secret_name, {})
        current = state.get("current", self.current_value)
        previous = state.get("previous")
        return presented == current or (previous is not None and presented == previous)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rotation_overlap_accepts_current_and_previous_without_failures() -> None:
    repository = FakeRepository()
    provider = TrafficValidatorProvider()
    service = SecretRotationService(repository, provider)  # type: ignore[arg-type]
    schedule = await service.create_schedule(
        secret_name="test_db_password",
        secret_type="db_password",
        rotation_interval_days=90,
        overlap_window_hours=24,
        vault_path="secret/data/musematic/dev/rotating/test-db",
        next_rotation_at=datetime.now(UTC) - timedelta(minutes=1),
    )

    await service.trigger(schedule.id, requester_id=uuid4())
    provider.rotation_state["test_db_password"]["current"] = "test-db-next"
    provider.current_value = "test-db-next"

    presented = ["test-db-current", "test-db-next"]
    results = await gather(
        *(
            provider.validate_either("test_db_password", presented[index % 2])
            for index in range(100)
        )
    )

    assert all(results)
    assert results.count(False) == 0

    await service.finalise(schedule.id)

    assert await provider.validate_either("test_db_password", "test-db-next") is True
    assert await provider.validate_either("test_db_password", "test-db-current") is False
