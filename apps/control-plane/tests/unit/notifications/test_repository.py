from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.notifications.models import (
    AlertDeliveryOutcome,
    DeliveryMethod,
    DeliveryOutcome,
    NotificationChannelConfig,
    OutboundWebhook,
    UserAlert,
    UserAlertSettings,
    WebhookDelivery,
    WebhookDeliveryStatus,
)
from platform.notifications.repository import (
    NotificationsRepository,
    _apply_cursor,
    _decode_cursor,
    _encode_cursor,
    _items_with_cursor,
)
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import select


class ExecuteResultStub:
    def __init__(
        self,
        *,
        scalar_one=None,
        scalars_all: list[object] | None = None,
        rows: list[tuple[object, ...]] | None = None,
        rowcount: int | None = None,
    ) -> None:
        self._scalar_one = scalar_one
        self._scalars_all = list(scalars_all or [])
        self._rows = list(rows or [])
        self.rowcount = rowcount

    def scalar_one_or_none(self):
        return self._scalar_one

    def scalars(self):
        return SimpleNamespace(all=lambda: list(self._scalars_all))

    def all(self):
        return list(self._rows)


class SessionStub:
    def __init__(
        self,
        *,
        execute_results: list[ExecuteResultStub] | None = None,
        scalar_results: list[object] | None = None,
        get_results: dict[object, object] | None = None,
    ) -> None:
        self.execute_results = list(execute_results or [])
        self.scalar_results = list(scalar_results or [])
        self.get_results = dict(get_results or {})
        self.added: list[object] = []
        self.deleted: list[object] = []
        self.flush_count = 0

    async def execute(self, query):
        assert self.execute_results, f"unexpected execute call: {query}"
        return self.execute_results.pop(0)

    async def scalar(self, query):
        assert self.scalar_results, f"unexpected scalar call: {query}"
        return self.scalar_results.pop(0)

    async def get(self, model, key):
        del model
        return self.get_results.get(key)

    def add(self, value: object) -> None:
        self.added.append(value)

    async def delete(self, value: object) -> None:
        self.deleted.append(value)

    async def flush(self) -> None:
        self.flush_count += 1


def _settings(user_id):
    return UserAlertSettings(
        id=uuid4(),
        user_id=user_id,
        state_transitions=["any_to_failed"],
        delivery_method=DeliveryMethod.in_app,
        webhook_url=None,
    )


def _alert(user_id, *, read: bool = False, created_at: datetime | None = None) -> UserAlert:
    alert = UserAlert(
        id=uuid4(),
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="medium",
        read=read,
    )
    alert.created_at = created_at or datetime.now(UTC)
    alert.updated_at = alert.created_at
    return alert


def test_get_settings_and_upsert_create_when_missing() -> None:
    user_id = uuid4()
    session = SessionStub(execute_results=[ExecuteResultStub(scalar_one=None)])
    repo = NotificationsRepository(session)

    created = __import__("asyncio").run(
        repo.upsert_settings(
            user_id,
            {
                "state_transitions": ["any_to_failed"],
                "delivery_method": DeliveryMethod.webhook,
                "webhook_url": "https://hooks.example.com/alerts",
            },
        )
    )

    assert created.user_id == user_id
    assert created.delivery_method == DeliveryMethod.webhook
    assert session.added == [created]
    assert session.flush_count == 1


def test_get_settings_and_upsert_update_existing() -> None:
    user_id = uuid4()
    existing = _settings(user_id)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalar_one=existing),
            ExecuteResultStub(scalar_one=existing),
        ]
    )
    repo = NotificationsRepository(session)

    resolved = __import__("asyncio").run(repo.get_settings(user_id))
    updated = __import__("asyncio").run(
        repo.upsert_settings(
            user_id,
            {
                "state_transitions": ["working_to_pending"],
                "delivery_method": DeliveryMethod.email,
                "webhook_url": None,
            },
        )
    )

    assert resolved is existing
    assert updated is existing
    assert existing.state_transitions == ["working_to_pending"]
    assert existing.delivery_method == DeliveryMethod.email
    assert session.flush_count == 1


def test_create_alert_creates_delivery_outcome_for_non_in_app_delivery() -> None:
    session = SessionStub()
    repo = NotificationsRepository(session)

    alert = __import__("asyncio").run(
        repo.create_alert(
            user_id=uuid4(),
            interaction_id=None,
            source_reference={"type": "attention_request", "id": str(uuid4())},
            alert_type="attention_request",
            title="Attention requested",
            body="Review needed",
            urgency="high",
            delivery_method=DeliveryMethod.webhook,
        )
    )

    assert isinstance(alert.delivery_outcome, AlertDeliveryOutcome)
    assert alert.delivery_outcome.delivery_method == DeliveryMethod.webhook
    assert len(session.added) == 2
    assert session.flush_count == 2


def test_list_alerts_get_alert_mark_read_and_count_unread() -> None:
    user_id = uuid4()
    newest = _alert(user_id, created_at=datetime.now(UTC))
    older = _alert(user_id, read=True, created_at=datetime.now(UTC) - timedelta(minutes=1))
    unread = _alert(user_id, created_at=datetime.now(UTC) - timedelta(minutes=2))
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalars_all=[newest, older, unread]),
            ExecuteResultStub(scalar_one=newest),
            ExecuteResultStub(scalar_one=newest),
        ],
        scalar_results=[2, 1],
    )
    repo = NotificationsRepository(session)

    items, next_cursor, unread_total = __import__("asyncio").run(
        repo.list_alerts(user_id, "all", None, 2)
    )
    got_alert = __import__("asyncio").run(repo.get_alert(newest.id, user_id))
    marked = __import__("asyncio").run(repo.mark_read(newest.id, user_id))
    unread_count = __import__("asyncio").run(repo.get_unread_count(user_id))

    assert [item.id for item in items] == [newest.id, older.id]
    assert next_cursor is not None
    assert unread_total == 2
    assert got_alert is newest
    assert marked is newest
    assert marked.read is True
    assert unread_count == 1


def test_get_alert_by_id_pending_deliveries_update_and_delete_expired() -> None:
    user_id = uuid4()
    alert = _alert(user_id)
    outcome = AlertDeliveryOutcome(
        id=uuid4(),
        alert_id=alert.id,
        delivery_method=DeliveryMethod.webhook,
        attempt_count=1,
        outcome=DeliveryOutcome.failed,
    )
    outcome.alert = alert
    alert.delivery_outcome = outcome
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalar_one=alert),
            ExecuteResultStub(scalars_all=[outcome]),
            ExecuteResultStub(rowcount=3),
        ],
        get_results={outcome.id: outcome},
    )
    repo = NotificationsRepository(session)

    resolved = __import__("asyncio").run(repo.get_alert_by_id(alert.id))
    pending = __import__("asyncio").run(repo.get_pending_webhook_deliveries())
    updated = __import__("asyncio").run(
        repo.update_delivery_outcome(
            outcome.id,
            outcome=DeliveryOutcome.success,
            delivered_at=datetime.now(UTC),
        )
    )
    deleted = __import__("asyncio").run(repo.delete_expired_alerts(30))

    assert resolved is alert
    assert pending == [outcome]
    assert updated is outcome
    assert updated.outcome == DeliveryOutcome.success
    assert deleted == 3
    assert session.flush_count == 1


def test_cursor_helpers_round_trip() -> None:
    user_id = uuid4()
    alerts = [
        _alert(user_id, created_at=datetime.now(UTC)),
        _alert(user_id, created_at=datetime.now(UTC) - timedelta(minutes=1)),
        _alert(user_id, created_at=datetime.now(UTC) - timedelta(minutes=2)),
    ]
    page, next_cursor = _items_with_cursor(alerts, 2)

    assert [item.id for item in page] == [alerts[0].id, alerts[1].id]
    assert next_cursor is not None
    created_at, item_id = _decode_cursor(next_cursor)
    assert item_id == alerts[1].id
    assert created_at == alerts[1].created_at
    assert _encode_cursor(created_at, item_id) == next_cursor

    query = _apply_cursor(select(UserAlert), next_cursor)
    assert query is not None



def test_repository_additional_edges_cover_filters_and_missing_records() -> None:
    user_id = uuid4()
    read_alert = _alert(user_id, read=True, created_at=datetime.now(UTC))
    unread_alert = _alert(user_id, read=False, created_at=datetime.now(UTC) - timedelta(minutes=1))
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalars_all=[read_alert]),
            ExecuteResultStub(scalars_all=[unread_alert]),
            ExecuteResultStub(rowcount=None),
        ],
        scalar_results=[1, 1],
    )
    repo = NotificationsRepository(session)

    in_app_alert = __import__("asyncio").run(
        repo.create_alert(
            user_id=user_id,
            interaction_id=None,
            source_reference={"type": "attention_request", "id": str(uuid4())},
            alert_type="attention_request",
            title="Attention requested",
            body="Review needed",
            urgency="medium",
            delivery_method=DeliveryMethod.in_app,
        )
    )
    read_items, _, read_total = __import__("asyncio").run(
        repo.list_alerts(user_id, "read", None, 5)
    )
    unread_items, _, unread_total = __import__("asyncio").run(
        repo.list_alerts(user_id, "unread", None, 5)
    )
    deleted = __import__("asyncio").run(repo.delete_expired_alerts(30))

    assert in_app_alert.delivery_outcome is None
    assert [item.id for item in read_items] == [read_alert.id]
    assert [item.id for item in unread_items] == [unread_alert.id]
    assert read_total == 1
    assert unread_total == 1
    assert deleted == 0


def test_repository_mark_read_update_missing_and_cursor_helpers_edges() -> None:
    user_id = uuid4()
    already_read = _alert(user_id, read=True)
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalar_one=None),
            ExecuteResultStub(scalar_one=already_read),
        ],
        get_results={},
    )
    repo = NotificationsRepository(session)

    missing_mark = __import__("asyncio").run(repo.mark_read(uuid4(), user_id))
    marked = __import__("asyncio").run(repo.mark_read(already_read.id, user_id))
    missing_outcome = __import__("asyncio").run(repo.update_delivery_outcome(uuid4(), outcome=None))
    page, next_cursor = _items_with_cursor([already_read], 5)

    assert missing_mark is None
    assert marked is already_read
    assert missing_outcome is None
    assert page == [already_read]
    assert next_cursor is None


def test_repository_channel_config_crud_counts_and_expiry() -> None:
    user_id = uuid4()
    channel_id = uuid4()
    now = datetime.now(UTC)
    config = NotificationChannelConfig(
        id=channel_id,
        user_id=user_id,
        channel_type=DeliveryMethod.email,
        target="user@example.com",
        enabled=True,
        verified_at=now,
        verification_token_hash="hash",
        verification_expires_at=now - timedelta(minutes=1),
    )
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalars_all=[config]),
            ExecuteResultStub(scalars_all=[config]),
            ExecuteResultStub(scalar_one=config),
            ExecuteResultStub(scalars_all=[config]),
            ExecuteResultStub(scalar_one=config),
        ],
        scalar_results=[2, 1],
        get_results={channel_id: config},
    )
    repo = NotificationsRepository(session)

    enabled = __import__("asyncio").run(repo.list_enabled_channel_configs(user_id))
    listed = __import__("asyncio").run(repo.list_user_channel_configs(user_id))
    resolved = __import__("asyncio").run(repo.get_channel_config(channel_id, user_id))
    created = __import__("asyncio").run(
        repo.create_channel_config(
            user_id=user_id,
            channel_type=DeliveryMethod.sms,
            target="+34666123456",
            severity_floor="critical",
        )
    )
    updated = __import__("asyncio").run(repo.update_channel_config(channel_id, enabled=False))
    deleted = __import__("asyncio").run(repo.delete_channel_config(channel_id))
    missing_delete = __import__("asyncio").run(repo.delete_channel_config(uuid4()))
    expired = __import__("asyncio").run(repo.expire_channel_verifications(now))
    by_token = __import__("asyncio").run(repo.get_channel_config_by_token_hash("hash"))
    total = __import__("asyncio").run(repo.count_user_channels(user_id))
    sms_total = __import__("asyncio").run(repo.count_user_channels(user_id, DeliveryMethod.sms))

    assert enabled == [config]
    assert listed == [config]
    assert resolved is config
    assert created.channel_type == DeliveryMethod.sms
    assert session.added[-1] is created
    assert updated is config
    assert deleted is True
    assert missing_delete is False
    assert session.deleted == [config]
    assert expired == [config]
    assert config.enabled is False
    assert config.verification_token_hash is None
    assert by_token is config
    assert total == 2
    assert sms_total == 1


def test_repository_outbound_webhooks_deliveries_and_dead_letters() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    webhook_id = uuid4()
    delivery_id = uuid4()
    now = datetime.now(UTC)
    webhook = OutboundWebhook(
        id=webhook_id,
        workspace_id=workspace_id,
        name="CRM",
        url="https://hooks.example.com/events",
        event_types=["execution.failed"],
        signing_secret_ref="secret/ref",
        active=True,
        retry_policy={"backoff_seconds": [60]},
        created_by=actor_id,
    )
    inactive = OutboundWebhook(
        id=uuid4(),
        workspace_id=workspace_id,
        name="Inactive",
        url="https://hooks.example.com/inactive",
        event_types=["execution.failed"],
        signing_secret_ref="secret/ref/2",
        active=False,
        retry_policy={"backoff_seconds": [60]},
        created_by=actor_id,
    )
    delivery = WebhookDelivery(
        id=delivery_id,
        webhook_id=webhook_id,
        idempotency_key=uuid4(),
        event_id=uuid4(),
        event_type="execution.failed",
        payload={"ok": True},
        status=WebhookDeliveryStatus.dead_letter.value,
        failure_reason="4xx_permanent",
        attempts=3,
        dead_lettered_at=now,
    )
    delivery.webhook = webhook
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(scalars_all=[webhook, inactive]),
            ExecuteResultStub(scalars_all=[webhook, inactive]),
            ExecuteResultStub(scalar_one=delivery),
            ExecuteResultStub(scalars_all=[delivery]),
            ExecuteResultStub(scalar_one=delivery),
            ExecuteResultStub(scalars_all=[delivery]),
            ExecuteResultStub(rows=[(workspace_id, 2)]),
            ExecuteResultStub(rowcount=4),
        ],
        scalar_results=[1],
        get_results={webhook_id: webhook, delivery_id: delivery},
    )
    repo = NotificationsRepository(session)

    listed = __import__("asyncio").run(repo.list_outbound_webhooks(workspace_id))
    active = __import__("asyncio").run(
        repo.list_active_outbound_webhooks(workspace_id, "execution.failed")
    )
    created_webhook = __import__("asyncio").run(
        repo.create_outbound_webhook(
            workspace_id=workspace_id,
            name="Created",
            url="https://hooks.example.com/created",
            event_types=["execution.failed"],
            signing_secret_ref="secret/ref/new",
            created_by=actor_id,
        )
    )
    updated_webhook = __import__("asyncio").run(
        repo.update_outbound_webhook(webhook_id, active=False)
    )
    missing_webhook = __import__("asyncio").run(repo.update_outbound_webhook(uuid4(), active=True))
    resolved_webhook = __import__("asyncio").run(repo.get_outbound_webhook(webhook_id))
    by_idempotency = __import__("asyncio").run(
        repo.get_webhook_delivery_by_idempotency(webhook_id, delivery.idempotency_key)
    )
    active_count = __import__("asyncio").run(repo.count_active_webhooks(workspace_id))
    inserted_delivery = __import__("asyncio").run(
        repo.insert_delivery(
            webhook_id=webhook_id,
            idempotency_key=uuid4(),
            event_id=uuid4(),
            event_type="execution.failed",
            payload={"ok": True},
        )
    )
    due = __import__("asyncio").run(repo.list_due_deliveries(now, 10))
    updated_delivery = __import__("asyncio").run(
        repo.update_delivery_status(delivery_id, status=WebhookDeliveryStatus.delivered.value)
    )
    missing_delivery = __import__("asyncio").run(
        repo.update_delivery_status(uuid4(), status=WebhookDeliveryStatus.failed.value)
    )
    delivery_without_webhook = __import__("asyncio").run(repo.get_delivery(delivery_id))
    delivery_with_webhook = __import__("asyncio").run(
        repo.get_delivery(delivery_id, include_webhook=True)
    )
    dead_letters = __import__("asyncio").run(
        repo.list_dead_letters(
            workspace_id,
            {
                "webhook_id": webhook_id,
                "failure_reason": "4xx_permanent",
                "since": now - timedelta(hours=1),
                "until": now + timedelta(hours=1),
                "limit": 5,
            },
        )
    )
    replay = __import__("asyncio").run(
        repo.replay_dead_letter(delivery, actor_id=actor_id, now=now)
    )
    depth = __import__("asyncio").run(repo.aggregate_dead_letter_depth_by_workspace())
    deleted = __import__("asyncio").run(repo.delete_dead_letter_older_than(now))

    assert listed == [webhook, inactive]
    assert active == [webhook]
    assert created_webhook.name == "Created"
    assert updated_webhook is webhook
    assert webhook.active is False
    assert missing_webhook is None
    assert resolved_webhook is webhook
    assert by_idempotency is delivery
    assert active_count == 1
    assert inserted_delivery.event_type == "execution.failed"
    assert due == [delivery]
    assert updated_delivery is delivery
    assert delivery.status == WebhookDeliveryStatus.delivered.value
    assert missing_delivery is None
    assert delivery_without_webhook is delivery
    assert delivery_with_webhook is delivery
    assert dead_letters == [delivery]
    assert replay.replayed_from == delivery.id
    assert replay.replayed_by == actor_id
    assert depth == {workspace_id: 2}
    assert deleted == 4
