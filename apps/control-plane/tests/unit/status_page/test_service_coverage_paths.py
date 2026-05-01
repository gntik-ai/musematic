from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.notifications.models import DeliveryOutcome
from platform.status_page.exceptions import ConfirmationTokenInvalidError, SubscriptionNotFoundError
from platform.status_page.schemas import OverallState, SourceKind, UptimeSummary
from platform.status_page.service import (
    CURRENT_SNAPSHOT_KEY,
    LAST_GOOD_SNAPSHOT_KEY,
    SnapshotWithSource,
    StatusPageService,
    _affected_components,
    _delivery_outcome,
    _event_id,
    _hash_token,
    _normalise_scope,
    _optional_workspace_id,
    _render_template,
    _unsubscribe_url,
)
from types import SimpleNamespace
from uuid import uuid4

import pytest


class _RedisCompatStub:
    def __init__(self) -> None:
        self.values: dict[str, tuple[bytes, int | None]] = {}

    async def get(self, key: str) -> bytes | None:
        item = self.values.get(key)
        return item[0] if item else None

    async def set(self, key: str, value: bytes, *, ex: int) -> None:
        self.values[key] = (value, ex)


class _EmailStub:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, str]] = []

    async def send(self, alert: SimpleNamespace, email: str, _settings: object) -> None:
        self.sent.append((email, alert.title, alert.body))


class _WebhookStub:
    def __init__(self, outcome: DeliveryOutcome = DeliveryOutcome.success) -> None:
        self.outcome = outcome
        self.calls: list[dict[str, object]] = []

    async def send_signed(self, **kwargs) -> tuple[DeliveryOutcome, str | None, str]:
        self.calls.append(kwargs)
        error = None if self.outcome == DeliveryOutcome.success else "delivery failed"
        return self.outcome, error, "idem-1"


class _SlackStub:
    async def send(self, _alert: object, _target: str) -> tuple[DeliveryOutcome, str | None]:
        return DeliveryOutcome.timed_out, "timeout"


class _RepoFullStub:
    def __init__(self) -> None:
        self.rows: list[SimpleNamespace] = []
        self.current_row: SimpleNamespace | None = None
        self.active_incidents: list[SimpleNamespace] = []
        self.resolved_incidents: list[SimpleNamespace] = []
        self.scheduled_maintenance: list[SimpleNamespace] = []
        self.active_maintenance: list[SimpleNamespace] = []
        self.uptime: dict[str, object] = {}
        self.component_history: list[dict[str, object]] = []
        self.subscriptions: list[SimpleNamespace] = []
        self.dispatches: list[dict[str, object]] = []
        self.confirmation_hash: bytes | None = None
        self.unsubscribe_hash: bytes | None = None
        self.existing_subscription: SimpleNamespace | None = None

    async def list_active_incidents(self) -> list[SimpleNamespace]:
        return self.active_incidents

    async def list_recent_resolved_incidents(self, *, days: int = 7) -> list[SimpleNamespace]:
        assert days == 7
        return self.resolved_incidents

    async def list_scheduled_maintenance(self, *, days: int = 30) -> list[SimpleNamespace]:
        assert days == 30
        return self.scheduled_maintenance

    async def list_active_maintenance(self) -> list[SimpleNamespace]:
        return self.active_maintenance

    async def get_uptime_30d(self) -> dict[str, object]:
        return self.uptime

    async def insert_snapshot(self, **kwargs) -> SimpleNamespace:
        row = SimpleNamespace(
            id=uuid4(),
            generated_at=kwargs["generated_at"],
            overall_state=kwargs["overall_state"],
            payload=kwargs["payload"],
            source_kind=kwargs["source_kind"],
        )
        self.rows.append(row)
        self.current_row = row
        return row

    async def get_current_snapshot(self) -> SimpleNamespace | None:
        return self.current_row

    async def get_component_history(
        self,
        _component_id: str,
        *,
        days: int = 30,
    ) -> list[dict[str, object]]:
        assert days == 30
        return self.component_history

    async def create_subscription(self, **kwargs) -> SimpleNamespace:
        subscription = SimpleNamespace(
            id=uuid4(),
            created_at=datetime.now(UTC),
            **kwargs,
        )
        self.subscriptions.append(subscription)
        return subscription

    async def get_subscription_by_confirmation_hash(
        self,
        token_hash: bytes,
    ) -> SimpleNamespace | None:
        return self.subscriptions[0] if token_hash == self.confirmation_hash else None

    async def get_subscription_by_unsubscribe_hash(
        self,
        token_hash: bytes,
    ) -> SimpleNamespace | None:
        return self.subscriptions[0] if token_hash == self.unsubscribe_hash else None

    async def confirm_subscription(self, subscription: SimpleNamespace) -> SimpleNamespace:
        subscription.confirmed_at = datetime.now(UTC)
        subscription.health = "healthy"
        return subscription

    async def mark_unsubscribed(self, subscription: SimpleNamespace) -> SimpleNamespace:
        subscription.health = "unsubscribed"
        return subscription

    async def rotate_unsubscribe_token(
        self,
        subscription: SimpleNamespace,
        token_hash: bytes,
    ) -> SimpleNamespace:
        subscription.unsubscribe_token_hash = token_hash
        return subscription

    async def list_confirmed_subscriptions_for_event(
        self,
        *,
        affected_components: list[str],
    ) -> list[SimpleNamespace]:
        affected = set(affected_components)
        return [
            item
            for item in self.subscriptions
            if not affected
            or not item.scope_components
            or affected.intersection(item.scope_components)
        ]

    async def insert_dispatch(self, **kwargs) -> SimpleNamespace:
        self.dispatches.append(kwargs)
        return SimpleNamespace(id=uuid4(), **kwargs)

    async def list_user_subscriptions(self, **_kwargs) -> list[SimpleNamespace]:
        return self.subscriptions

    async def update_user_subscription(
        self,
        *,
        values: dict[str, object],
        **_kwargs,
    ) -> SimpleNamespace | None:
        if not self.subscriptions:
            return None
        for key, value in values.items():
            setattr(self.subscriptions[0], key, value)
        return self.subscriptions[0]

    async def get_user_subscription(self, **_kwargs) -> SimpleNamespace | None:
        return self.subscriptions[0] if self.subscriptions else None

    async def get_subscription(self, _subscription_id) -> SimpleNamespace | None:
        return self.existing_subscription


def _incident(*, resolved: bool = False) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        title="Workflow execution outage",
        severity="high",
        description="Execution queue is failing",
        triggered_at=now - timedelta(minutes=15),
        resolved_at=now if resolved else None,
        alert_rule_class="workflow",
        runbook_scenario="execution",
        condition_fingerprint="workflow-execution",
    )


def _maintenance(*, active: bool = True) -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        announcement_text="" if active else "Scheduled database upgrade",
        reason="Emergency patch",
        starts_at=now - timedelta(minutes=5),
        ends_at=now + timedelta(minutes=30),
        blocks_writes=active,
    )


def _current_user(**overrides: str) -> dict[str, str]:
    return {"sub": str(uuid4()), "workspace_id": str(uuid4()), **overrides}


@pytest.mark.asyncio
async def test_public_snapshot_component_and_incident_paths() -> None:
    repo = _RepoFullStub()
    redis = _RedisCompatStub()
    repo.active_incidents = [_incident()]
    repo.resolved_incidents = [_incident(resolved=True)]
    repo.scheduled_maintenance = [_maintenance(active=False)]
    repo.active_maintenance = [_maintenance()]
    repo.uptime = {
        "control-plane-api": UptimeSummary(pct=98.5, incidents=2),
        "web-app": {"pct": 99.0, "incidents": 1},
        "ignored": "bad",
    }
    service = StatusPageService(repository=repo, redis_client=redis)

    snapshot = await service.compose_current_snapshot(
        component_health=None,
        source_kind=SourceKind.kafka,
    )
    assert snapshot.overall_state is OverallState.maintenance
    assert redis.values[CURRENT_SNAPSHOT_KEY][1] == 90
    assert redis.values[LAST_GOOD_SNAPSHOT_KEY][1] == 24 * 60 * 60

    cached = await service.get_public_snapshot()
    assert cached.source == "redis"

    redis.values.clear()
    postgres = await service.get_public_snapshot()
    assert postgres.source == "postgres"
    assert LAST_GOOD_SNAPSHOT_KEY not in redis.values

    repo.component_history = [{"at": datetime.now(UTC), "state": "degraded"}]
    detail = await service.get_component_detail("control-plane-api")
    assert detail.history_30d[0].state is OverallState.degraded
    with pytest.raises(KeyError):
        await service.get_component_detail("missing")

    assert len((await service.list_public_incidents(status="active")).incidents) == 1
    assert len((await service.list_public_incidents(status="resolved")).incidents) == 1
    assert len((await service.list_public_incidents()).incidents) == 2
    assert (await service.get_my_platform_status(_current_user())).active_maintenance is not None


@pytest.mark.asyncio
async def test_public_snapshot_fallback_and_normalisation_edges() -> None:
    repo = _RepoFullStub()
    service = StatusPageService(repository=repo, redis_client=object())

    fallback = await service.get_public_snapshot()
    assert fallback.source == "fallback"
    assert fallback.snapshot.overall_state is OverallState.operational

    generated_at = datetime.now(UTC)
    components = service._normalise_components(
        [
            {"id": " ", "state": "operational"},
            {"id": "api", "state": "down"},
            {"id": "db", "state": "mystery", "last_check_at": generated_at},
        ],
        generated_at=generated_at,
        uptime={"api": UptimeSummary(pct=97, incidents=1)},
    )
    assert [component.state for component in components] == [
        OverallState.partial_outage,
        OverallState.degraded,
    ]
    assert SnapshotWithSource(fallback.snapshot, "test").age_seconds >= 0


@pytest.mark.asyncio
async def test_subscription_lifecycle_and_delivery_paths(monkeypatch) -> None:
    repo = _RepoFullStub()
    email = _EmailStub()
    webhook = _WebhookStub()
    service = StatusPageService(
        repository=repo,
        redis_client=_RedisCompatStub(),
        email_deliverer=email,
        webhook_deliverer=webhook,
        slack_deliverer=_SlackStub(),
    )
    monkeypatch.setenv("FEATURE_E2E_MODE", "true")

    response = await service.submit_email_subscription(
        email=" Dev@Example.TEST ",
        scope_components=[" web-app ", "", "web-app"],
    )
    assert "confirmation link" in response.message
    assert repo.subscriptions[0].target == "dev@example.test"
    assert email.sent
    assert _normalise_scope([" b ", "a", "a", ""]) == ["a", "b"]

    with pytest.raises(ConfirmationTokenInvalidError):
        await service.confirm_email_subscription("bad-token")
    with pytest.raises(SubscriptionNotFoundError):
        await service.unsubscribe("bad-token")

    repo.confirmation_hash = _hash_token("confirm")
    repo.unsubscribe_hash = _hash_token("unsubscribe")
    assert (await service.confirm_email_subscription("confirm")).status == "confirmed"
    assert (await service.unsubscribe("unsubscribe")).status == "unsubscribed"

    webhook_response = await service.submit_webhook_subscription(
        url="https://hooks.example.test/status",
        scope_components=["control-plane-api"],
    )
    assert webhook_response.verification_state == "healthy"
    assert webhook_response.signing_secret_hint is not None
    failed_webhook = StatusPageService(
        repository=repo,
        webhook_deliverer=_WebhookStub(DeliveryOutcome.failed),
    )
    assert (
        await failed_webhook.submit_webhook_subscription(
            url="https://hooks.example.test/fail",
            scope_components=[],
        )
    ).verification_state == "failed"
    slack_response = await service.submit_slack_subscription(
        webhook_url="https://slack",
        scope_components=[],
    )
    assert slack_response.verification_state == "healthy"

    user = _current_user()
    with pytest.raises(ValidationError):
        await service.create_my_subscription(user, channel="rss", target="x", scope_components=[])
    mine = await service.create_my_subscription(
        user,
        channel="webhook",
        target="https://hooks.example.test/me",
        scope_components=["api"],
    )
    assert mine.channel == "webhook"
    assert len(await service.list_my_subscriptions(user)) >= 1
    updated = await service.update_my_subscription(
        user,
        repo.subscriptions[0].id,
        target="new@example.test",
        scope_components=["control-plane-api"],
    )
    assert updated.target == "new@example.test"
    deleted = await service.delete_my_subscription(user, repo.subscriptions[0].id)
    assert deleted.status == "unsubscribed"


@pytest.mark.asyncio
async def test_delivery_outcomes_and_forbidden_subscription_paths() -> None:
    repo = _RepoFullStub()
    repo.subscriptions = [
        SimpleNamespace(
            id=uuid4(),
            channel="email",
            target="dev@example.test",
            scope_components=[],
            health="healthy",
            confirmed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            user_id=uuid4(),
            workspace_id=None,
            webhook_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            channel="slack",
            target="https://slack",
            scope_components=["control-plane-api"],
            health="healthy",
            confirmed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            user_id=uuid4(),
            workspace_id=None,
            webhook_id=None,
        ),
        SimpleNamespace(
            id=uuid4(),
            channel="webhook",
            target="https://hooks.example.test",
            scope_components=["control-plane-api"],
            health="healthy",
            confirmed_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
            user_id=uuid4(),
            workspace_id=None,
            webhook_id=None,
        ),
    ]
    service = StatusPageService(
        repository=repo,
        email_deliverer=_EmailStub(),
        slack_deliverer=_SlackStub(),
        webhook_deliverer=_WebhookStub(DeliveryOutcome.failed),
    )

    sent = await service.dispatch_event(
        "incident.created",
        {
            "incident_id": str(uuid4()),
            "title": "API degraded",
            "severity": "critical",
            "components_affected": ["control-plane-api"],
            "public_status_base_url": "https://status.example.test",
        },
    )
    assert sent == 1
    assert [item["outcome"] for item in repo.dispatches] == [
        "sent",
        "retrying",
        "dead_lettered",
    ]
    assert _delivery_outcome(DeliveryOutcome.success) == "sent"
    assert _delivery_outcome(DeliveryOutcome.timed_out) == "retrying"
    assert _delivery_outcome(DeliveryOutcome.failed) == "dead_lettered"

    other_user = uuid4()
    repo.subscriptions.clear()
    repo.existing_subscription = SimpleNamespace(user_id=other_user)
    with pytest.raises(AuthorizationError):
        await service.update_my_subscription(_current_user(), uuid4(), target="missing")
    repo.existing_subscription = None
    with pytest.raises(SubscriptionNotFoundError):
        await service.delete_my_subscription(_current_user(), uuid4())


def test_status_page_helper_edges() -> None:
    event_id = uuid4()
    assert _event_id({"event_id": str(event_id)}) == event_id
    assert _event_id({"event_id": "not-a-uuid", "window_id": str(event_id)}) == event_id
    assert _affected_components({"affected_components": [1, "api"]}) == ["1", "api"]
    assert _affected_components({"components": "api"}) == []
    assert _unsubscribe_url("tok", {"base_url": "https://status.example.test/"}) == (
        "https://status.example.test/api/v1/public/subscribe/email/unsubscribe?token=tok"
    )
    assert _optional_workspace_id({"workspace": str(event_id)}) == event_id
    assert "unknown.kind" in _render_template(
        "missing-template.txt",
        event_kind="unknown.kind",
        payload={},
    )
    with pytest.raises(KeyError):
        _render_template("missing-template.txt", payload={})
