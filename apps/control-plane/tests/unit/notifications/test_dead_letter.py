from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.exceptions import AuthorizationError
from platform.notifications.exceptions import DeadLetterNotReplayableError
from platform.notifications.routers.deadletter_router import _authorize_workspace
from platform.notifications.service import AlertService
from platform.notifications.webhooks_service import OutboundWebhookService
from platform.notifications.workers.deadletter_threshold_worker import (
    run_dead_letter_threshold_scan,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _RepoStub:
    def __init__(self) -> None:
        self.workspace_id = uuid4()
        self.webhook = SimpleNamespace(id=uuid4(), workspace_id=self.workspace_id, name="CRM")
        self.dead_letter = _delivery(self.webhook, status="dead_letter")
        self.delivered = _delivery(self.webhook, status="delivered")
        self.replays: list[SimpleNamespace] = []
        self.updates: list[dict[str, object]] = []

    async def list_dead_letters(self, workspace_id, filters=None):
        assert workspace_id == self.workspace_id
        filters = filters or {}
        rows = [self.dead_letter]
        if filters.get("failure_reason") and filters["failure_reason"] != "4xx_permanent":
            return []
        return rows[: int(filters.get("limit", 100))]

    async def get_delivery(self, delivery_id, *, include_webhook=False):
        del include_webhook
        if delivery_id == self.dead_letter.id:
            return self.dead_letter
        if delivery_id == self.delivered.id:
            return self.delivered
        return None

    async def replay_dead_letter(self, original, *, actor_id, now):
        replay = _delivery(
            self.webhook,
            status="pending",
            replayed_from=original.id,
            replayed_by=actor_id,
            idempotency_key=original.idempotency_key,
        )
        replay.next_attempt_at = now
        self.replays.append(replay)
        return replay

    async def update_delivery_status(self, delivery_id, **fields):
        assert delivery_id == self.dead_letter.id
        self.updates.append(fields)
        for key, value in fields.items():
            setattr(self.dead_letter, key, value)
        return self.dead_letter


class _RetentionRepo:
    def __init__(self) -> None:
        self.cutoff = None

    async def delete_dead_letter_older_than(self, cutoff):
        self.cutoff = cutoff
        return 3


class _ThresholdRepo:
    def __init__(self, workspace_id, depth) -> None:
        self.workspace_id = workspace_id
        self.depth = depth

    async def aggregate_dead_letter_depth_by_workspace(self):
        return {self.workspace_id: self.depth}


class _RedisCooldown:
    def __init__(self) -> None:
        self.keys: set[str] = set()

    async def set(self, key, value, *, ex, nx):
        del value, ex, nx
        if key in self.keys:
            return False
        self.keys.add(key)
        return True


class _Producer:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    async def publish(self, **kwargs):
        self.events.append(kwargs)


@pytest.mark.asyncio
async def test_dead_letter_list_replay_and_resolve_paths() -> None:
    repo = _RepoStub()
    service = _service(repo)
    actor_id = uuid4()

    listed = await service.list_dead_letters(
        repo.workspace_id,
        {"failure_reason": "4xx_permanent"},
    )
    replay = await service.replay_dead_letter(repo.dead_letter.id, actor_id=actor_id)
    resolved = await service.resolve_dead_letter(
        repo.dead_letter.id,
        actor_id=actor_id,
        resolution="receiver fixed",
    )

    assert listed[0].workspace_id == repo.workspace_id
    assert replay.idempotency_key == repo.dead_letter.idempotency_key
    assert replay.replayed_from == repo.dead_letter.id
    assert repo.dead_letter.status == "dead_letter"
    assert resolved.resolution_reason == "receiver fixed"
    assert repo.updates[0]["resolved_by"] == actor_id


@pytest.mark.asyncio
async def test_dead_letter_replay_rejects_non_dead_letter_row() -> None:
    repo = _RepoStub()

    with pytest.raises(DeadLetterNotReplayableError):
        await _service(repo).replay_dead_letter(repo.delivered.id, actor_id=uuid4())


@pytest.mark.asyncio
async def test_dead_letter_batch_replay_returns_all_matching_rows() -> None:
    repo = _RepoStub()
    actor_id = uuid4()

    replayed = await _service(repo).replay_dead_letters(
        workspace_id=repo.workspace_id,
        actor_id=actor_id,
        filters={"limit": 10},
    )

    assert len(replayed) == 1
    assert replayed[0].replayed_by == actor_id


def test_dead_letter_workspace_admin_scope_is_enforced() -> None:
    workspace_id = uuid4()

    _authorize_workspace({"sub": str(uuid4()), "roles": [{"role": "superadmin"}]}, workspace_id)
    _authorize_workspace(
        {
            "sub": str(uuid4()),
            "roles": [{"role": "workspace_admin"}],
            "workspace_id": str(workspace_id),
        },
        workspace_id,
    )
    with pytest.raises(AuthorizationError):
        _authorize_workspace(
            {
                "sub": str(uuid4()),
                "roles": [{"role": "workspace_admin"}],
                "workspace_id": str(uuid4()),
            },
            workspace_id,
        )


@pytest.mark.asyncio
async def test_dead_letter_threshold_worker_emits_once_per_cooldown() -> None:
    workspace_id = uuid4()
    settings = PlatformSettings()
    settings.notifications.dead_letter_warning_threshold = 2
    producer = _Producer()
    redis = _RedisCooldown()

    first = await run_dead_letter_threshold_scan(
        repo=_ThresholdRepo(workspace_id, 3),
        redis=redis,
        settings=settings,
        producer=producer,
    )
    second = await run_dead_letter_threshold_scan(
        repo=_ThresholdRepo(workspace_id, 3),
        redis=redis,
        settings=settings,
        producer=producer,
    )

    assert first == 1
    assert second == 0
    assert producer.events[0]["event_type"] == "notifications.dlq.depth.threshold_reached"


@pytest.mark.asyncio
async def test_dead_letter_retention_gc_delegates_dead_letter_cutoff_only() -> None:
    repo = _RetentionRepo()
    settings = PlatformSettings()
    settings.notifications.dead_letter_retention_days = 7
    service = AlertService(
        repo=repo,
        accounts_repo=SimpleNamespace(),
        workspaces_service=None,
        redis=SimpleNamespace(),
        producer=None,
        settings=settings,
        email_deliverer=SimpleNamespace(),
        webhook_deliverer=SimpleNamespace(),
    )

    deleted = await service.run_dead_letter_retention_gc()

    assert deleted == 3
    assert repo.cutoff is not None
    assert 6 <= (datetime.now(UTC) - repo.cutoff).days <= 7


def _service(repo: _RepoStub) -> OutboundWebhookService:
    return OutboundWebhookService(
        repo=repo,
        settings=PlatformSettings(),
        secrets=SimpleNamespace(),
        residency_service=SimpleNamespace(),
    )


def _delivery(
    webhook: SimpleNamespace,
    *,
    status: str,
    replayed_from=None,
    replayed_by=None,
    idempotency_key=None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        webhook_id=webhook.id,
        idempotency_key=idempotency_key or uuid4(),
        event_id=uuid4(),
        event_type="execution.failed",
        payload={"event_type": "execution.failed"},
        status=status,
        failure_reason="4xx_permanent",
        attempts=3,
        last_attempt_at=now,
        last_response_status=400,
        next_attempt_at=None,
        dead_lettered_at=now - timedelta(minutes=5) if status == "dead_letter" else None,
        replayed_from=replayed_from,
        replayed_by=replayed_by,
        resolved_at=None,
        resolved_by=None,
        resolution_reason=None,
        created_at=now - timedelta(minutes=10),
        updated_at=now,
        webhook=webhook,
    )
