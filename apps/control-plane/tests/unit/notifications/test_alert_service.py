from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.common.exceptions import ValidationError
from platform.interactions.events import AttentionRequestedPayload, InteractionStateChangedPayload
from platform.notifications.exceptions import (
    AlertAuthorizationError,
    AlertNotFoundError,
    ChannelNotFoundError,
    ChannelVerificationError,
    QuotaExceededError,
)
from platform.notifications.models import DeliveryMethod, DeliveryOutcome
from platform.notifications.schemas import (
    ChannelConfigCreate,
    ChannelConfigUpdate,
    QuietHoursConfig,
    UserAlertSettingsRead,
    UserAlertSettingsUpdate,
)
from platform.notifications.service import AlertService
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from tests.auth_support import RecordingProducer


class RateLimitResultStub:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed


class RedisStub:
    def __init__(self, results: list[bool] | None = None) -> None:
        self.results = list(results or [True])
        self.calls: list[tuple[str, str, int, int]] = []

    async def check_rate_limit(
        self, resource: str, key: str, limit: int, window_ms: int
    ) -> RateLimitResultStub:
        self.calls.append((resource, key, limit, window_ms))
        allowed = self.results.pop(0) if self.results else True
        return RateLimitResultStub(allowed)


class AccountsRepoStub:
    def __init__(self) -> None:
        self.by_id: dict[UUID, SimpleNamespace] = {}
        self.by_email: dict[str, SimpleNamespace] = {}

    async def get_user_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        return self.by_id.get(user_id)

    async def get_user_by_email(self, email: str) -> SimpleNamespace | None:
        return self.by_email.get(email.lower())


class WorkspacesServiceStub:
    def __init__(self, member_ids: list[UUID] | None = None) -> None:
        self.member_ids = list(member_ids or [])
        self.calls: list[UUID] = []

    async def list_member_ids(self, workspace_id: UUID) -> list[UUID]:
        self.calls.append(workspace_id)
        return list(self.member_ids)


class EmailDelivererStub:
    def __init__(self, outcome: DeliveryOutcome = DeliveryOutcome.success) -> None:
        self.outcome = outcome
        self.calls: list[tuple[object, str, dict[str, object]]] = []

    async def send(
        self, alert, recipient_email: str, smtp_settings: dict[str, object]
    ) -> DeliveryOutcome:
        self.calls.append((alert, recipient_email, smtp_settings))
        return self.outcome


class WebhookDelivererStub:
    def __init__(self, responses: list[tuple[DeliveryOutcome, str | None]] | None = None) -> None:
        self.responses = list(responses or [(DeliveryOutcome.success, None)])
        self.calls: list[tuple[object, str]] = []

    async def send(self, alert, webhook_url: str) -> tuple[DeliveryOutcome, str | None]:
        self.calls.append((alert, webhook_url))
        return self.responses.pop(0) if self.responses else (DeliveryOutcome.success, None)


class SmsDelivererStub:
    def __init__(self) -> None:
        self.calls: list[tuple[object, str, object]] = []

    async def send(self, alert, target: str, config: object) -> tuple[DeliveryOutcome, str | None]:
        self.calls.append((alert, target, config))
        return DeliveryOutcome.success, None


class RepoStub:
    def __init__(self) -> None:
        self.settings_by_user: dict[UUID, object] = {}
        self.alerts: dict[UUID, SimpleNamespace] = {}
        self.outcomes: dict[UUID, SimpleNamespace] = {}
        self.created: list[SimpleNamespace] = []
        self.updated: list[tuple[UUID, dict[str, object]]] = []
        self.pending: list[SimpleNamespace] = []
        self.deleted_retention_days: list[int] = []
        self.channel_configs: dict[UUID, SimpleNamespace] = {}

    async def get_settings(self, user_id: UUID):
        return self.settings_by_user.get(user_id)

    async def upsert_settings(self, user_id: UUID, data: dict[str, object]):
        current = self.settings_by_user.get(user_id)
        now = datetime.now(UTC)
        if current is None:
            current = SimpleNamespace(
                id=uuid4(),
                user_id=user_id,
                created_at=now,
                updated_at=now,
                **data,
            )
        else:
            for key, value in data.items():
                setattr(current, key, value)
            current.updated_at = now
        self.settings_by_user[user_id] = current
        return current

    async def create_alert(
        self,
        *,
        user_id: UUID,
        interaction_id: UUID | None,
        source_reference: dict[str, object] | None,
        alert_type: str,
        title: str,
        body: str | None,
        urgency: str,
        delivery_method: DeliveryMethod | None = None,
    ):
        now = datetime.now(UTC)
        alert = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            interaction_id=interaction_id,
            source_reference=source_reference,
            alert_type=alert_type,
            title=title,
            body=body,
            urgency=urgency,
            read=False,
            created_at=now,
            updated_at=now,
            delivery_outcome=None,
        )
        if delivery_method is not None:
            outcome = SimpleNamespace(
                id=uuid4(),
                alert_id=alert.id,
                delivery_method=delivery_method,
                attempt_count=1,
                outcome=None,
                next_retry_at=None,
                error_detail=None,
                delivered_at=None,
                created_at=now,
                updated_at=now,
                alert=alert,
            )
            alert.delivery_outcome = outcome
            self.outcomes[outcome.id] = outcome
        self.alerts[alert.id] = alert
        self.created.append(alert)
        return alert

    async def get_alert_by_id(self, alert_id: UUID):
        return self.alerts.get(alert_id)

    async def list_alerts(
        self,
        user_id: UUID,
        read_filter: str,
        cursor: str | None,
        limit: int,
    ):
        del cursor
        items = [alert for alert in self.alerts.values() if alert.user_id == user_id]
        if read_filter == "read":
            items = [alert for alert in items if alert.read]
        elif read_filter == "unread":
            items = [alert for alert in items if not alert.read]
        items.sort(key=lambda alert: (alert.created_at, alert.id), reverse=True)
        unread_total = sum(
            1 for alert in self.alerts.values() if alert.user_id == user_id and not alert.read
        )
        return items[:limit], None, unread_total

    async def mark_read(self, alert_id: UUID, user_id: UUID):
        alert = self.alerts.get(alert_id)
        if alert is None or alert.user_id != user_id:
            return None
        alert.read = True
        alert.updated_at = datetime.now(UTC)
        return alert

    async def get_unread_count(self, user_id: UUID) -> int:
        return sum(
            1 for alert in self.alerts.values() if alert.user_id == user_id and not alert.read
        )

    async def get_pending_webhook_deliveries(self):
        return list(self.pending)

    async def update_delivery_outcome(self, outcome_id: UUID, **fields: object):
        outcome = self.outcomes.get(outcome_id)
        if outcome is None:
            return None
        for key, value in fields.items():
            setattr(outcome, key, value)
        self.updated.append((outcome_id, dict(fields)))
        return outcome

    async def delete_expired_alerts(self, retention_days: int) -> int:
        self.deleted_retention_days.append(retention_days)
        return 3

    async def list_user_channel_configs(self, user_id: UUID):
        return [config for config in self.channel_configs.values() if config.user_id == user_id]

    async def get_channel_config(self, channel_config_id: UUID, user_id: UUID | None = None):
        config = self.channel_configs.get(channel_config_id)
        if config is None:
            return None
        if user_id is not None and config.user_id != user_id:
            return None
        return config

    async def create_channel_config(self, **fields: object):
        now = datetime.now(UTC)
        config = SimpleNamespace(
            id=uuid4(),
            signing_secret_ref=None,
            created_at=now,
            updated_at=now,
            **fields,
        )
        self.channel_configs[config.id] = config
        return config

    async def update_channel_config(self, channel_config_id: UUID, **fields: object):
        config = self.channel_configs.get(channel_config_id)
        if config is None:
            return None
        for key, value in fields.items():
            setattr(config, key, value)
        config.updated_at = datetime.now(UTC)
        return config

    async def delete_channel_config(self, channel_config_id: UUID) -> bool:
        return self.channel_configs.pop(channel_config_id, None) is not None

    async def get_channel_config_by_token_hash(self, token_hash: str):
        for config in self.channel_configs.values():
            if config.verification_token_hash == token_hash:
                return config
        return None

    async def count_user_channels(
        self,
        user_id: UUID,
        channel_type: DeliveryMethod | None = None,
    ) -> int:
        return sum(
            1
            for config in self.channel_configs.values()
            if config.user_id == user_id
            and (channel_type is None or config.channel_type == channel_type)
        )


def _settings(
    user_id: UUID,
    *,
    transitions: list[str] | None = None,
    delivery_method: DeliveryMethod = DeliveryMethod.in_app,
    webhook_url: str | None = None,
) -> UserAlertSettingsRead:
    now = datetime.now(UTC)
    return UserAlertSettingsRead(
        id=uuid4(),
        user_id=user_id,
        state_transitions=list(
            transitions or ["working_to_pending", "any_to_complete", "any_to_failed"]
        ),
        delivery_method=delivery_method,
        webhook_url=webhook_url,
        created_at=now,
        updated_at=now,
    )


def build_service(
    *,
    repo: RepoStub | None = None,
    accounts: AccountsRepoStub | None = None,
    workspaces: WorkspacesServiceStub | None = None,
    redis: RedisStub | None = None,
    producer: RecordingProducer | None = None,
    email_deliverer: EmailDelivererStub | None = None,
    webhook_deliverer: WebhookDelivererStub | None = None,
    sms_deliverer: SmsDelivererStub | None = None,
    settings: PlatformSettings | None = None,
) -> tuple[
    AlertService,
    RepoStub,
    AccountsRepoStub,
    WorkspacesServiceStub | None,
    RedisStub,
    RecordingProducer,
]:
    repo = repo or RepoStub()
    accounts = accounts or AccountsRepoStub()
    redis = redis or RedisStub()
    producer = producer or RecordingProducer()
    service = AlertService(
        repo=repo,
        accounts_repo=accounts,
        workspaces_service=workspaces,
        redis=redis,
        producer=producer,
        settings=settings or PlatformSettings(),
        email_deliverer=email_deliverer or EmailDelivererStub(),
        webhook_deliverer=webhook_deliverer or WebhookDelivererStub(),
        sms_deliverer=sms_deliverer,
    )
    return service, repo, accounts, workspaces, redis, producer


@pytest.mark.asyncio
async def test_process_attention_request_defaults_unknown_urgency_and_publishes_in_app(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, repo, accounts, _, redis, producer = build_service()
    user_id = uuid4()
    accounts.by_email["person@example.com"] = SimpleNamespace(
        id=user_id, email="person@example.com"
    )

    with caplog.at_level("WARNING"):
        alert = await service.process_attention_request(
            AttentionRequestedPayload(
                request_id=uuid4(),
                workspace_id=uuid4(),
                source_agent_fqn="ops:reviewer",
                target_identity="person@example.com",
                urgency="urgent-now",
                related_interaction_id=uuid4(),
                related_goal_id=None,
                context_summary="Need a human decision",
            )
        )

    assert alert is not None
    assert repo.created[0].urgency == "medium"
    assert repo.created[0].body == "Need a human decision"
    assert redis.calls == [("notifications", f"ops:reviewer:{user_id}", 20, 60_000)]
    assert producer.events[-1]["event_type"] == "notifications.alert_created"
    assert "Unknown alert urgency" in caplog.text


@pytest.mark.asyncio
async def test_process_attention_request_skips_missing_target_identity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, repo, _, _, _, producer = build_service()

    with caplog.at_level("WARNING"):
        alert = await service.process_attention_request(
            AttentionRequestedPayload(
                request_id=uuid4(),
                workspace_id=uuid4(),
                source_agent_fqn="ops:reviewer",
                target_identity="missing@example.com",
                urgency="high",
                related_interaction_id=None,
                related_goal_id=None,
                context_summary=None,
            )
        )

    assert alert is None
    assert repo.created == []
    assert producer.events == []
    assert "Skipping alert creation for unknown target identity" in caplog.text


@pytest.mark.asyncio
async def test_process_attention_request_respects_rate_limit(
    caplog: pytest.LogCaptureFixture,
) -> None:
    service, repo, accounts, _, _, producer = build_service(redis=RedisStub([False]))
    user_id = uuid4()
    accounts.by_email["person@example.com"] = SimpleNamespace(
        id=user_id, email="person@example.com"
    )

    with caplog.at_level("WARNING"):
        alert = await service.process_attention_request(
            AttentionRequestedPayload(
                request_id=uuid4(),
                workspace_id=uuid4(),
                source_agent_fqn="ops:reviewer",
                target_identity="person@example.com",
                urgency="high",
                related_interaction_id=None,
                related_goal_id=None,
                context_summary=None,
            )
        )

    assert alert is None
    assert repo.created == []
    assert producer.events == []
    assert "Dropping attention alert due to rate limit" in caplog.text


@pytest.mark.asyncio
async def test_process_state_change_only_alerts_matching_members() -> None:
    workspace_id = uuid4()
    interaction_id = uuid4()
    user_match = uuid4()
    user_skip = uuid4()
    workspaces = WorkspacesServiceStub([user_match, user_skip])
    service, repo, accounts, _, redis, producer = build_service(
        workspaces=workspaces, redis=RedisStub([True, True])
    )
    accounts.by_id[user_match] = SimpleNamespace(id=user_match, email="match@example.com")
    accounts.by_id[user_skip] = SimpleNamespace(id=user_skip, email="skip@example.com")
    repo.settings_by_user[user_match] = _settings(user_match, transitions=["any_to_failed"])
    repo.settings_by_user[user_skip] = _settings(user_skip, transitions=["working_to_pending"])

    alerts = await service.process_state_change(
        InteractionStateChangedPayload(
            interaction_id=interaction_id,
            workspace_id=workspace_id,
            from_state="running",
            to_state="failed",
            occurred_at=datetime.now(UTC),
        ),
        workspace_id,
    )

    assert [alert.user_id for alert in alerts] == [user_match]
    assert producer.events[-1]["event_type"] == "notifications.alert_created"
    assert redis.calls == [("notifications", f"{interaction_id}:{user_match}", 20, 60_000)]
    assert workspaces.calls == [workspace_id]


@pytest.mark.asyncio
async def test_mark_alert_read_publishes_unread_count() -> None:
    service, repo, accounts, _, _, producer = build_service()
    user_id = uuid4()
    accounts.by_id[user_id] = SimpleNamespace(id=user_id, email="person@example.com")
    alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
    )

    result = await service.mark_alert_read(alert.id, user_id)

    assert result.read is True
    assert producer.events[-1]["event_type"] == "notifications.alert_read"
    assert producer.events[-1]["payload"]["unread_count"] == 0


@pytest.mark.asyncio
async def test_run_webhook_retry_scan_falls_back_to_in_app_without_url() -> None:
    user_id = uuid4()
    service, repo, _, _, _, producer = build_service()
    repo.settings_by_user[user_id] = _settings(
        user_id,
        delivery_method=DeliveryMethod.webhook,
        webhook_url=None,
    )
    alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "state_change", "id": str(uuid4())},
        alert_type="state_change",
        title="Interaction transitioned",
        body="running -> failed",
        urgency="medium",
        delivery_method=DeliveryMethod.webhook,
    )
    assert alert.delivery_outcome is not None
    repo.pending = [alert.delivery_outcome]

    retried = await service.run_webhook_retry_scan()

    assert retried == 1
    assert repo.updated[0][1] == {"attempt_count": 2}
    assert repo.updated[-1][1]["outcome"] == DeliveryOutcome.fallback
    assert producer.events[-1]["event_type"] == "notifications.alert_created"


@pytest.mark.asyncio
async def test_run_webhook_retry_scan_sets_next_retry_and_clears_exhausted() -> None:
    settings = PlatformSettings(NOTIFICATIONS_WEBHOOK_MAX_RETRIES=3)
    webhook_deliverer = WebhookDelivererStub([(DeliveryOutcome.timed_out, "timeout")])
    service, repo, _, _, _, _ = build_service(
        settings=settings,
        webhook_deliverer=webhook_deliverer,
    )
    active_user = uuid4()
    exhausted_user = uuid4()
    repo.settings_by_user[active_user] = _settings(
        active_user,
        delivery_method=DeliveryMethod.webhook,
        webhook_url="https://hooks.example.com/alerts",
    )
    repo.settings_by_user[exhausted_user] = _settings(
        exhausted_user,
        delivery_method=DeliveryMethod.webhook,
        webhook_url="https://hooks.example.com/alerts",
    )
    active_alert = await repo.create_alert(
        user_id=active_user,
        interaction_id=None,
        source_reference={"type": "state_change", "id": str(uuid4())},
        alert_type="state_change",
        title="Interaction transitioned",
        body="running -> failed",
        urgency="medium",
        delivery_method=DeliveryMethod.webhook,
    )
    exhausted_alert = await repo.create_alert(
        user_id=exhausted_user,
        interaction_id=None,
        source_reference={"type": "state_change", "id": str(uuid4())},
        alert_type="state_change",
        title="Interaction transitioned",
        body="running -> failed",
        urgency="medium",
        delivery_method=DeliveryMethod.webhook,
    )
    assert active_alert.delivery_outcome is not None
    assert exhausted_alert.delivery_outcome is not None
    exhausted_alert.delivery_outcome.attempt_count = 3
    exhausted_alert.delivery_outcome.next_retry_at = datetime.now(UTC) + timedelta(minutes=5)
    repo.pending = [active_alert.delivery_outcome, exhausted_alert.delivery_outcome]

    retried = await service.run_webhook_retry_scan()

    assert retried == 1
    assert repo.updated[0][1] == {"attempt_count": 2}
    retry_update = next(
        fields for _, fields in repo.updated if fields.get("outcome") == DeliveryOutcome.timed_out
    )
    assert retry_update["error_detail"] == "timeout"
    assert retry_update["next_retry_at"] is not None
    assert repo.updated[-1] == (exhausted_alert.delivery_outcome.id, {"next_retry_at": None})


@pytest.mark.asyncio
async def test_run_retention_gc_uses_configured_retention_window() -> None:
    service, repo, _, _, _, _ = build_service(
        settings=PlatformSettings(NOTIFICATIONS_ALERT_RETENTION_DAYS=45)
    )

    deleted = await service.run_retention_gc()

    assert deleted == 3
    assert repo.deleted_retention_days == [45]


@pytest.mark.asyncio
async def test_get_or_default_and_upsert_settings_cover_existing_and_validation() -> None:
    user_id = uuid4()
    service, repo, _, _, _, _ = build_service()
    repo.settings_by_user[user_id] = _settings(user_id, delivery_method=DeliveryMethod.email)

    existing = await service.get_or_default_settings(user_id)
    updated = await service.upsert_settings(
        user_id,
        UserAlertSettingsUpdate(
            state_transitions=["working_to_pending"],
            delivery_method=DeliveryMethod.email,
            webhook_url=None,
        ),
    )

    assert existing.delivery_method == DeliveryMethod.email
    assert updated.state_transitions == ["working_to_pending"]

    invalid = UserAlertSettingsUpdate.model_construct(
        state_transitions=["any_to_failed"],
        delivery_method=DeliveryMethod.webhook,
        webhook_url=None,
    )
    with pytest.raises(ValidationError) as exc_info:
        await service.upsert_settings(user_id, invalid)
    assert exc_info.value.code == "WEBHOOK_URL_REQUIRED"


@pytest.mark.asyncio
async def test_process_state_change_skips_invalid_states_and_rate_limited_members(
    caplog: pytest.LogCaptureFixture,
) -> None:
    workspace_id = uuid4()
    interaction_id = uuid4()
    user_id = uuid4()
    workspaces = WorkspacesServiceStub([user_id])
    service, repo, accounts, _, _, _ = build_service(
        workspaces=workspaces,
        redis=RedisStub([False]),
    )
    accounts.by_id[user_id] = SimpleNamespace(id=user_id, email="person@example.com")
    repo.settings_by_user[user_id] = _settings(user_id, transitions=["any_to_failed"])

    with caplog.at_level("WARNING"):
        invalid = await service.process_state_change(
            InteractionStateChangedPayload(
                interaction_id=interaction_id,
                workspace_id=workspace_id,
                from_state="mystery",
                to_state="failed",
                occurred_at=datetime.now(UTC),
            ),
            workspace_id,
        )
        limited = await service.process_state_change(
            InteractionStateChangedPayload(
                interaction_id=interaction_id,
                workspace_id=workspace_id,
                from_state="running",
                to_state="failed",
                occurred_at=datetime.now(UTC),
            ),
            workspace_id,
        )

    assert invalid == []
    assert limited == []
    assert "Skipping state change alert for unrecognized states" in caplog.text
    assert "Dropping state-change alert due to rate limit" in caplog.text


@pytest.mark.asyncio
async def test_process_state_change_skips_members_without_resolved_user() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    service, repo, _, _, _, _ = build_service(
        workspaces=WorkspacesServiceStub([user_id]),
        redis=RedisStub([True]),
    )
    repo.settings_by_user[user_id] = _settings(user_id, transitions=["any_to_failed"])

    alerts = await service.process_state_change(
        InteractionStateChangedPayload(
            interaction_id=uuid4(),
            workspace_id=workspace_id,
            from_state="running",
            to_state="failed",
            occurred_at=datetime.now(UTC),
        ),
        workspace_id,
    )

    assert alerts == []


@pytest.mark.asyncio
async def test_list_get_mark_and_unread_count_raise_expected_errors() -> None:
    user_id = uuid4()
    other_user = uuid4()
    service, repo, _, _, _, _ = build_service()
    alert = await repo.create_alert(
        user_id=other_user,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
    )

    response = await service.list_alerts(user_id, read_filter="all", cursor=None, limit=5)
    unread = await service.get_unread_count(user_id)
    assert response.items == []
    assert unread.count == 0

    with pytest.raises(AlertNotFoundError) as missing_alert:
        await service.get_alert(uuid4(), user_id)
    assert missing_alert.value.code == "ALERT_NOT_FOUND"

    with pytest.raises(AlertAuthorizationError) as forbidden_alert:
        await service.get_alert(alert.id, user_id)
    assert forbidden_alert.value.code == "ALERT_FORBIDDEN"

    with pytest.raises(AlertNotFoundError) as missing_mark:
        await service.mark_alert_read(uuid4(), user_id)
    assert missing_mark.value.code == "ALERT_NOT_FOUND"

    with pytest.raises(AlertAuthorizationError) as forbidden_mark:
        await service.mark_alert_read(alert.id, user_id)
    assert forbidden_mark.value.code == "ALERT_FORBIDDEN"


@pytest.mark.asyncio
async def test_email_and_webhook_success_paths_and_helpers() -> None:
    user_id = uuid4()
    settings = PlatformSettings(NOTIFICATIONS_WEBHOOK_MAX_RETRIES=3)
    email_deliverer = EmailDelivererStub(DeliveryOutcome.success)
    webhook_deliverer = WebhookDelivererStub([(DeliveryOutcome.success, None)])
    service, repo, accounts, _, _, producer = build_service(
        settings=settings,
        email_deliverer=email_deliverer,
        webhook_deliverer=webhook_deliverer,
    )
    accounts.by_id[user_id] = SimpleNamespace(id=user_id, email="person@example.com")

    email_alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
        delivery_method=DeliveryMethod.email,
    )
    assert email_alert.delivery_outcome is not None
    service.settings = SimpleNamespace(
        notifications=settings.notifications,
        SMTP_HOST="smtp.example.com",
        SMTP_PORT=587,
        SMTP_USERNAME="mailer@example.com",
        SMTP_PASSWORD="secret",
        SMTP_FROM="alerts@example.com",
    )
    await service._dispatch_for_settings(
        email_alert,
        _settings(user_id, delivery_method=DeliveryMethod.email),
        accounts.by_id[user_id],
    )

    webhook_alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "state_change", "id": str(uuid4())},
        alert_type="state_change",
        title="Interaction transitioned",
        body="running -> completed",
        urgency="medium",
        delivery_method=DeliveryMethod.webhook,
    )
    assert webhook_alert.delivery_outcome is not None
    await service._dispatch_webhook(
        webhook_alert,
        _settings(
            user_id,
            delivery_method=DeliveryMethod.webhook,
            webhook_url="https://hooks.example.com/alerts",
        ),
        webhook_alert.delivery_outcome,
    )
    await service._dispatch_webhook(
        webhook_alert,
        _settings(
            user_id,
            delivery_method=DeliveryMethod.webhook,
            webhook_url="https://hooks.example.com/alerts",
        ),
        None,
    )

    assert email_deliverer.calls[0][1] == "person@example.com"
    assert repo.updated[0][1]["outcome"] == DeliveryOutcome.success
    success_update = next(
        fields
        for _, fields in repo.updated
        if fields.get("outcome") == DeliveryOutcome.success and "delivered_at" in fields
    )
    assert success_update["delivered_at"] is not None
    assert webhook_deliverer.calls == [(webhook_alert, "https://hooks.example.com/alerts")]
    assert producer.events == []

    assert await service._resolve_user(str(user_id)) == accounts.by_id[user_id]
    accounts.by_email["person@example.com"] = accounts.by_id[user_id]
    assert await service._resolve_user("person@example.com") == accounts.by_id[user_id]
    assert await service._list_workspace_member_ids(uuid4()) == []
    service.workspaces_service = SimpleNamespace()
    assert await service._list_workspace_member_ids(uuid4()) == []
    assert service._normalize_urgency("high") == "high"
    smtp_settings = service._smtp_settings()
    assert smtp_settings["hostname"] == "smtp.example.com"


@pytest.mark.asyncio
async def test_alert_service_additional_success_and_retry_edges() -> None:
    user_id = uuid4()
    service, repo, accounts, _, _, _ = build_service()
    accounts.by_id[user_id] = SimpleNamespace(id=user_id, email="person@example.com")
    alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
    )
    detail = await service.get_alert(alert.id, user_id)
    assert detail.id == alert.id

    email_alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
    )
    await service._dispatch_for_settings(
        email_alert,
        _settings(
            user_id, delivery_method=DeliveryMethod.webhook, webhook_url="https://hooks.example.com"
        ),
        accounts.by_id[user_id],
    )

    no_outcome = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
    )
    await service._dispatch_email(no_outcome, accounts.by_id[user_id])

    settings = PlatformSettings(NOTIFICATIONS_WEBHOOK_MAX_RETRIES=3)
    retry_service, retry_repo, _, _, _, _ = build_service(settings=settings)
    retry_user = uuid4()
    retry_repo.settings_by_user[retry_user] = _settings(
        retry_user,
        delivery_method=DeliveryMethod.webhook,
        webhook_url="https://hooks.example.com/alerts",
    )
    exhausted = await retry_repo.create_alert(
        user_id=retry_user,
        interaction_id=None,
        source_reference={"type": "state_change", "id": str(uuid4())},
        alert_type="state_change",
        title="Interaction transitioned",
        body="running -> failed",
        urgency="medium",
        delivery_method=DeliveryMethod.webhook,
    )
    assert exhausted.delivery_outcome is not None
    exhausted.delivery_outcome.attempt_count = settings.notifications.webhook_max_retries
    retry_repo.pending = [exhausted.delivery_outcome]

    retried = await retry_service.run_webhook_retry_scan()
    assert retried == 0


@pytest.mark.asyncio
async def test_dispatch_webhook_exhausted_attempts_do_not_schedule_retry() -> None:
    settings = PlatformSettings(NOTIFICATIONS_WEBHOOK_MAX_RETRIES=2)
    webhook_deliverer = WebhookDelivererStub([(DeliveryOutcome.failed, "permanent failure")])
    service, repo, _, _, _, _ = build_service(
        settings=settings,
        webhook_deliverer=webhook_deliverer,
    )
    user_id = uuid4()
    alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "state_change", "id": str(uuid4())},
        alert_type="state_change",
        title="Interaction transitioned",
        body="running -> failed",
        urgency="medium",
        delivery_method=DeliveryMethod.webhook,
    )
    assert alert.delivery_outcome is not None
    alert.delivery_outcome.attempt_count = settings.notifications.webhook_max_retries

    await service._dispatch_webhook(
        alert,
        _settings(
            user_id,
            delivery_method=DeliveryMethod.webhook,
            webhook_url="https://hooks.example.com/alerts",
        ),
        alert.delivery_outcome,
    )

    assert repo.updated[-1][1]["outcome"] == DeliveryOutcome.failed
    assert repo.updated[-1][1]["next_retry_at"] is None
    assert repo.updated[-1][1]["error_detail"] == "permanent failure"


@pytest.mark.asyncio
async def test_channel_config_crud_verification_and_quota_edges() -> None:
    user_id = uuid4()
    other_user = uuid4()
    sms_deliverer = SmsDelivererStub()
    service, repo, _, _, _, _ = build_service(sms_deliverer=sms_deliverer)

    created = await service.create_channel_config(
        user_id,
        ChannelConfigCreate(
            channel_type=DeliveryMethod.sms,
            target="+34666123456",
            quiet_hours=QuietHoursConfig(start="23:00", end="06:00", timezone="UTC"),
        ),
    )
    listed = await service.list_channel_configs(user_id)
    resolved = await service.get_channel_config_for_user(user_id, created.id)
    updated = await service.update_channel_config(
        user_id,
        created.id,
        ChannelConfigUpdate(
            display_name="Critical SMS",
            quiet_hours=QuietHoursConfig(start="22:00", end="07:00", timezone="UTC"),
        ),
    )
    resent = await service.resend_channel_verification(user_id, created.id)

    assert created.severity_floor == service.settings.notifications.sms_default_severity_floor
    assert listed[0].id == created.id
    assert resolved.id == created.id
    assert updated.display_name == "Critical SMS"
    assert updated.quiet_hours == {"start": "22:00", "end": "07:00", "timezone": "UTC"}
    assert resent.verification_expires_at is not None
    assert len(sms_deliverer.calls) == 2

    with pytest.raises(ChannelVerificationError):
        await service.verify_channel_config(user_id, created.id, "wrong-token")

    token = "valid-token"
    config = repo.channel_configs[created.id]
    config.verification_token_hash = service._hash_token(token)
    config.verification_expires_at = datetime.now(UTC) + timedelta(minutes=5)
    verified = await service.verify_channel_config(user_id, created.id, token)
    assert verified.verified_at is not None
    assert repo.channel_configs[created.id].verification_token_hash is None

    config.verification_token_hash = service._hash_token(token)
    config.verification_expires_at = datetime.now(UTC) - timedelta(minutes=1)
    with pytest.raises(ChannelVerificationError, match="expired"):
        await service.verify_channel_config(user_id, created.id, token)

    with pytest.raises(AlertAuthorizationError):
        await service.get_channel_config_for_user(other_user, created.id)
    with pytest.raises(ChannelNotFoundError):
        await service.get_channel_config_for_user(user_id, uuid4())

    await service.delete_channel_config(user_id, created.id)
    assert created.id not in repo.channel_configs

    quota_settings = PlatformSettings(NOTIFICATIONS_CHANNELS_PER_USER_MAX=0)
    quota_service, _, _, _, _, _ = build_service(settings=quota_settings)
    with pytest.raises(QuotaExceededError):
        await quota_service.create_channel_config(
            user_id,
            ChannelConfigCreate(channel_type=DeliveryMethod.email, target="user@example.com"),
        )


@pytest.mark.asyncio
async def test_channel_dispatch_uses_router_and_verification_email_noop_paths() -> None:
    user_id = uuid4()
    routed: list[tuple[object, object, object, str]] = []

    class ChannelRouterStub:
        async def route(self, alert, user, *, workspace_id=None, severity="medium"):
            routed.append((alert, user, workspace_id, severity))

    settings = PlatformSettings()
    settings.notifications.multi_channel_enabled = True
    email_deliverer = EmailDelivererStub()
    service, repo, accounts, _, _, _ = build_service(
        settings=settings,
        email_deliverer=email_deliverer,
    )
    service.channel_router = ChannelRouterStub()  # type: ignore[assignment]
    accounts.by_id[user_id] = SimpleNamespace(id=user_id, email="person@example.com")
    alert = await repo.create_alert(
        user_id=user_id,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="critical",
    )

    await service._dispatch_for_settings(
        alert,
        _settings(user_id),
        accounts.by_id[user_id],
        workspace_id=uuid4(),
    )

    now = datetime.now(UTC)
    email_config = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        channel_type=DeliveryMethod.email,
        target="person@example.com",
        created_at=now,
        updated_at=now,
    )
    webhook_config = SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        channel_type=DeliveryMethod.webhook,
        target="https://hooks.example.com",
        created_at=now,
        updated_at=now,
    )
    await service._send_channel_verification(email_config, "email-token")
    await service._send_channel_verification(webhook_config, "webhook-token")
    raw, token_hash, _expires_at = service._verification_challenge(DeliveryMethod.email)

    assert routed[0][0] is alert
    assert routed[0][3] == "critical"
    assert email_deliverer.calls[0][1] == "person@example.com"
    assert raw
    assert token_hash == service._hash_token(raw)


@pytest.mark.asyncio
async def test_process_export_ready_creates_alert_with_localized_template() -> None:
    """T038 — UPD-051 export-ready notification routes via the user's
    delivery preference and renders the localized export_ready template."""
    user_id = uuid4()
    job_id = uuid4()
    service, repo, accounts, _, _, producer = build_service()
    accounts.by_id[user_id] = SimpleNamespace(id=user_id, email="owner@example.com")
    repo.settings_by_user[user_id] = _settings(user_id, delivery_method=DeliveryMethod.in_app)

    alert = await service.process_export_ready(
        user_id=user_id,
        job_id=job_id,
        output_size_bytes=15 * 1024 * 1024,  # 15 MiB
        expires_at=datetime(2026, 5, 10, 12, 0, tzinfo=UTC),
    )

    assert alert is not None
    assert alert.user_id == user_id
    assert alert.alert_type == "export_ready"
    assert alert.title == "Your data export is ready"
    assert "15 MB" in (alert.body or "")
    assert "2026-05-10" in (alert.body or "")
    assert alert.source_reference == {"type": "data_export_job", "id": str(job_id)}
    # An in-app alert publishes through the in-app dispatcher.
    assert producer.events[-1]["event_type"] == "notifications.alert_created"


@pytest.mark.asyncio
async def test_process_export_ready_skips_when_user_missing() -> None:
    user_id = uuid4()
    service, _repo, _accounts, _, _, _producer = build_service()
    # accounts repo intentionally has no entry for user_id
    alert = await service.process_export_ready(
        user_id=user_id,
        job_id=uuid4(),
        output_size_bytes=1024,
        expires_at=None,
    )
    assert alert is None
