from __future__ import annotations

from platform.auth.exceptions import AccountLockedError
from platform.auth.lockout import LockoutManager
from platform.auth.password import hash_password
from platform.auth.service import AuthService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer


class LockoutRepository:
    def __init__(self) -> None:
        self.user_id = uuid4()
        self.credential = SimpleNamespace(
            user_id=self.user_id,
            password_hash=hash_password("CorrectHorseBatteryStaple"),
            is_active=True,
        )
        self.roles = [SimpleNamespace(role="viewer", workspace_id=None)]
        self.auth_attempts: list[str] = []
        self.db = object()

    async def get_credential_by_email(self, email: str):
        return self.credential if email == "user@example.com" else None

    async def update_password_hash(self, user_id, new_hash: str) -> None:
        self.credential.password_hash = new_hash

    async def get_user_roles(self, user_id, workspace_id):
        return self.roles

    async def get_mfa_enrollment(self, user_id):
        return None

    async def record_auth_attempt(
        self,
        user_id,
        email: str,
        ip: str,
        user_agent: str,
        outcome: str,
    ) -> None:
        del user_id, email, ip, user_agent
        self.auth_attempts.append(outcome)


@pytest.mark.asyncio
async def test_lockout_manager_increments_and_locks_account() -> None:
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    manager = LockoutManager(redis_client, producer=producer)
    user_id = uuid4()

    attempts = await manager.increment_failure(
        user_id,
        threshold=2,
        duration=60,
        correlation_id=uuid4(),
    )

    assert attempts == 1
    assert await manager.is_locked(user_id) is False

    attempts = await manager.increment_failure(
        user_id,
        threshold=2,
        duration=60,
        correlation_id=uuid4(),
    )

    assert attempts == 2
    assert await manager.is_locked(user_id) is True
    assert producer.events[0]["event_type"] == "auth.user.locked"


@pytest.mark.asyncio
async def test_lockout_manager_resets_failure_counter() -> None:
    redis_client = FakeAsyncRedisClient()
    manager = LockoutManager(redis_client)
    user_id = uuid4()

    await manager.increment_failure(user_id, threshold=5, duration=60)
    await manager.lock_account(user_id, duration=60)
    await manager.reset_failure_counter(user_id)

    assert await manager.is_locked(user_id) is False


@pytest.mark.asyncio
async def test_lockout_integrates_with_login_flow(auth_settings) -> None:
    repository = LockoutRepository()
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    settings = auth_settings.model_copy(
        update={
            "auth": auth_settings.auth.model_copy(
                update={"lockout_threshold": 1, "lockout_duration": 60}
            )
        }
    )
    service = AuthService(repository, redis_client, settings, producer=producer)

    with pytest.raises(AccountLockedError):
        await service.login("user@example.com", "wrong-password", "127.0.0.1", "pytest")

    with pytest.raises(AccountLockedError):
        await service.login(
            "user@example.com",
            "CorrectHorseBatteryStaple",
            "127.0.0.1",
            "pytest",
        )

    assert repository.auth_attempts == ["failure_locked", "failure_locked"]
