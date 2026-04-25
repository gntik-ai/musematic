from __future__ import annotations

from datetime import UTC, datetime
from platform.common.exceptions import AuthorizationError
from platform.notifications.models import DeliveryMethod
from platform.notifications.routers.channels_router import (
    ChannelVerifyRequest,
    create_channel,
    delete_channel,
    list_channels,
    resend_channel_verification,
    update_channel,
    verify_channel,
)
from platform.notifications.routers.deadletter_router import (
    _filters,
    _iso,
    get_dead_letter,
    list_dead_letters,
    replay_dead_letter,
    replay_dead_letter_batch,
    resolve_dead_letter,
)
from platform.notifications.routers.webhooks_router import (
    create_webhook,
    delete_webhook,
    get_webhook,
    list_webhooks,
    rotate_webhook_secret,
    send_test_webhook,
    update_webhook,
)
from platform.notifications.schemas import (
    ChannelConfigCreate,
    ChannelConfigRead,
    ChannelConfigUpdate,
    DeadLetterListItem,
    DeadLetterReplayBatchRequest,
    DeadLetterResolveRequest,
    OutboundWebhookCreate,
    OutboundWebhookCreateResponse,
    OutboundWebhookRead,
    OutboundWebhookUpdate,
    WebhookDeliveryRead,
)
from uuid import UUID, uuid4

import pytest


class AuditStub:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def append(self, payload: dict[str, object]) -> None:
        self.payloads.append(payload)


class ChannelServiceStub:
    def __init__(self, user_id: UUID, channel_id: UUID) -> None:
        self.user_id = user_id
        self.channel_id = channel_id
        self.deleted: list[UUID] = []

    async def list_channel_configs(self, user_id: UUID) -> list[ChannelConfigRead]:
        assert user_id == self.user_id
        return [_channel(self.user_id, self.channel_id)]

    async def get_channel_config_for_user(
        self,
        user_id: UUID,
        channel_id: UUID,
    ) -> ChannelConfigRead:
        assert user_id == self.user_id
        assert channel_id == self.channel_id
        return _channel(user_id, channel_id)

    async def create_channel_config(
        self,
        user_id: UUID,
        payload: ChannelConfigCreate,
    ) -> ChannelConfigRead:
        assert user_id == self.user_id
        return _channel(user_id, self.channel_id, channel_type=payload.channel_type)

    async def update_channel_config(
        self,
        user_id: UUID,
        channel_id: UUID,
        payload: ChannelConfigUpdate,
    ) -> ChannelConfigRead:
        assert user_id == self.user_id
        assert channel_id == self.channel_id
        return _channel(user_id, channel_id, enabled=payload.enabled is not False)

    async def delete_channel_config(self, user_id: UUID, channel_id: UUID) -> None:
        assert user_id == self.user_id
        self.deleted.append(channel_id)

    async def verify_channel_config(
        self,
        user_id: UUID,
        channel_id: UUID,
        token: str,
    ) -> ChannelConfigRead:
        assert user_id == self.user_id
        assert token == "token"
        return _channel(user_id, channel_id, verified_at=datetime.now(UTC))

    async def resend_channel_verification(
        self,
        user_id: UUID,
        channel_id: UUID,
    ) -> ChannelConfigRead:
        assert user_id == self.user_id
        return _channel(user_id, channel_id)


class WebhookServiceStub:
    def __init__(self, workspace_id: UUID, actor_id: UUID, webhook_id: UUID) -> None:
        self.workspace_id = workspace_id
        self.actor_id = actor_id
        self.webhook_id = webhook_id
        self.filters: dict[str, object] | None = None

    async def create(
        self,
        payload: OutboundWebhookCreate,
        *,
        actor_id: UUID,
    ) -> OutboundWebhookCreateResponse:
        assert actor_id == self.actor_id
        return _webhook_response(self.workspace_id, self.webhook_id, actor_id, name=payload.name)

    async def list(self, workspace_id: UUID) -> list[OutboundWebhookRead]:
        assert workspace_id == self.workspace_id
        return [_webhook(self.workspace_id, self.webhook_id, self.actor_id)]

    async def get(self, webhook_id: UUID) -> OutboundWebhookRead:
        assert webhook_id == self.webhook_id
        return _webhook(self.workspace_id, webhook_id, self.actor_id)

    async def update(
        self,
        webhook_id: UUID,
        payload: OutboundWebhookUpdate,
    ) -> OutboundWebhookRead:
        assert webhook_id == self.webhook_id
        return _webhook(
            self.workspace_id,
            webhook_id,
            self.actor_id,
            active=payload.active is not False,
        )

    async def rotate_secret(self, webhook_id: UUID) -> OutboundWebhookRead:
        assert webhook_id == self.webhook_id
        return _webhook(self.workspace_id, webhook_id, self.actor_id)

    async def deactivate(self, webhook_id: UUID) -> OutboundWebhookRead:
        assert webhook_id == self.webhook_id
        return _webhook(self.workspace_id, webhook_id, self.actor_id, active=False)

    async def send_test_event(self, webhook_id: UUID, *, actor_id: UUID) -> WebhookDeliveryRead:
        assert webhook_id == self.webhook_id
        assert actor_id == self.actor_id
        return _delivery(self.webhook_id)

    async def list_dead_letters(
        self,
        workspace_id: UUID,
        filters: dict[str, object] | None,
    ) -> list[DeadLetterListItem]:
        assert workspace_id == self.workspace_id
        self.filters = filters
        return [_dead_letter(self.workspace_id, self.webhook_id)]

    async def get_dead_letter(self, delivery_id: UUID) -> DeadLetterListItem:
        del delivery_id
        return _dead_letter(self.workspace_id, self.webhook_id)

    async def replay_dead_letter(self, delivery_id: UUID, *, actor_id: UUID) -> WebhookDeliveryRead:
        del delivery_id
        assert actor_id == self.actor_id
        return _delivery(self.webhook_id)

    async def replay_dead_letters(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        filters: dict[str, object],
    ) -> list[WebhookDeliveryRead]:
        assert workspace_id == self.workspace_id
        assert actor_id == self.actor_id
        assert filters["limit"] == 10
        return [_delivery(self.webhook_id), _delivery(self.webhook_id)]

    async def resolve_dead_letter(
        self,
        delivery_id: UUID,
        *,
        actor_id: UUID,
        resolution: str,
    ) -> WebhookDeliveryRead:
        del delivery_id
        assert actor_id == self.actor_id
        assert resolution == "fixed"
        return _delivery(self.webhook_id)


@pytest.mark.asyncio
async def test_channel_router_functions_emit_audit_payloads() -> None:
    user_id = uuid4()
    channel_id = uuid4()
    current_user = {"sub": str(user_id)}
    service = ChannelServiceStub(user_id, channel_id)
    audit = AuditStub()

    listed = await list_channels(current_user=current_user, service=service)
    created = await create_channel(
        ChannelConfigCreate(channel_type=DeliveryMethod.email, target="user@example.com"),
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    updated = await update_channel(
        channel_id,
        ChannelConfigUpdate(enabled=False),
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    await delete_channel(channel_id, current_user=current_user, service=service, audit_chain=audit)
    verified = await verify_channel(
        channel_id,
        ChannelVerifyRequest(token="token"),
        current_user=current_user,
        service=service,
    )
    resent = await resend_channel_verification(
        channel_id,
        current_user=current_user,
        service=service,
    )

    assert listed[0].id == channel_id
    assert created.channel_type == DeliveryMethod.email
    assert updated.enabled is False
    assert service.deleted == [channel_id]
    assert verified.verified_at is not None
    assert resent.id == channel_id
    assert [payload["action"] for payload in audit.payloads] == ["created", "updated", "deleted"]


@pytest.mark.asyncio
async def test_webhook_router_functions_require_admin_and_emit_audit_payloads() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    webhook_id = uuid4()
    service = WebhookServiceStub(workspace_id, actor_id, webhook_id)
    audit = AuditStub()
    current_user = {"sub": str(actor_id), "roles": [{"role": "workspace_admin"}]}

    created = await create_webhook(
        OutboundWebhookCreate(
            workspace_id=workspace_id,
            name="CRM",
            url="https://hooks.example.com/events",
            event_types=["execution.failed"],
        ),
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    listed = await list_webhooks(
        workspace_id=workspace_id,
        current_user=current_user,
        service=service,
    )
    resolved = await get_webhook(webhook_id, current_user=current_user, service=service)
    updated = await update_webhook(
        webhook_id,
        OutboundWebhookUpdate(active=False),
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    rotated = await rotate_webhook_secret(
        webhook_id,
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    deleted = await delete_webhook(
        webhook_id,
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    tested = await send_test_webhook(webhook_id, current_user=current_user, service=service)

    assert created.signing_secret == "secret"
    assert listed[0].id == webhook_id
    assert resolved.id == webhook_id
    assert updated.active is False
    assert rotated.id == webhook_id
    assert deleted.active is False
    assert tested.webhook_id == webhook_id
    assert [payload["event"] for payload in audit.payloads] == [
        "notifications.webhook.registered",
        "notifications.webhook.deactivated",
        "notifications.webhook.rotated",
        "notifications.webhook.deactivated",
    ]
    assert "signing_secret" not in audit.payloads[0]["diff"]["after"]  # type: ignore[index]

    with pytest.raises(AuthorizationError):
        await list_webhooks(
            workspace_id=workspace_id,
            current_user={"sub": str(actor_id), "roles": [{"role": "member"}]},
            service=service,
        )


@pytest.mark.asyncio
async def test_dead_letter_router_functions_authorize_filter_and_audit() -> None:
    workspace_id = uuid4()
    actor_id = uuid4()
    webhook_id = uuid4()
    delivery_id = uuid4()
    service = WebhookServiceStub(workspace_id, actor_id, webhook_id)
    audit = AuditStub()
    current_user = {"sub": str(actor_id), "roles": [{"role": "admin"}]}
    now = datetime.now(UTC)

    listed = await list_dead_letters(
        workspace_id=workspace_id,
        webhook_id=webhook_id,
        since=now,
        until=now,
        reason="4xx_permanent",
        limit=10,
        current_user=current_user,
        service=service,
    )
    resolved = await get_dead_letter(delivery_id, current_user=current_user, service=service)
    replayed = await replay_dead_letter(
        delivery_id,
        payload=None,
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    batch = await replay_dead_letter_batch(
        DeadLetterReplayBatchRequest(workspace_id=workspace_id, limit=10),
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )
    fixed = await resolve_dead_letter(
        delivery_id,
        DeadLetterResolveRequest(resolution="fixed"),
        current_user=current_user,
        service=service,
        audit_chain=audit,
    )

    assert listed[0].workspace_id == workspace_id
    assert service.filters == {
        "webhook_id": webhook_id,
        "failure_reason": "4xx_permanent",
        "since": now,
        "until": now,
        "limit": 10,
    }
    assert resolved.workspace_id == workspace_id
    assert replayed.webhook_id == webhook_id
    assert batch.replayed == 2
    assert fixed.webhook_id == webhook_id
    assert _filters(webhook_id=None, failure_reason=None, since=None, until=None, limit=5) == {
        "limit": 5
    }
    assert _iso(None) is None
    assert _iso(now) == now.isoformat()
    assert [payload["event"] for payload in audit.payloads] == [
        "notifications.dead_letter.replayed",
        "notifications.dead_letter.batch_replayed",
        "notifications.dead_letter.resolved",
    ]

    with pytest.raises(AuthorizationError):
        await list_dead_letters(
            workspace_id=workspace_id,
            current_user={
                "sub": str(actor_id),
                "roles": [{"role": "workspace_admin"}],
                "workspace_id": str(uuid4()),
            },
            service=service,
        )


def _channel(
    user_id: UUID,
    channel_id: UUID,
    *,
    channel_type: DeliveryMethod = DeliveryMethod.email,
    enabled: bool = True,
    verified_at: datetime | None = None,
) -> ChannelConfigRead:
    now = datetime.now(UTC)
    return ChannelConfigRead(
        id=channel_id,
        user_id=user_id,
        channel_type=channel_type,
        target="user@example.com",
        display_name=None,
        signing_secret_ref=None,
        enabled=enabled,
        verified_at=verified_at,
        verification_expires_at=None,
        quiet_hours=None,
        alert_type_filter=None,
        severity_floor=None,
        extra=None,
        created_at=now,
        updated_at=now,
    )


def _webhook(
    workspace_id: UUID,
    webhook_id: UUID,
    actor_id: UUID,
    *,
    active: bool = True,
) -> OutboundWebhookRead:
    now = datetime.now(UTC)
    return OutboundWebhookRead(
        id=webhook_id,
        workspace_id=workspace_id,
        name="CRM",
        url="https://hooks.example.com/events",
        event_types=["execution.failed"],
        signing_secret_ref="secret/path",
        active=active,
        retry_policy={"backoff_seconds": [60]},
        region_pinned_to=None,
        last_rotated_at=None,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )


def _webhook_response(
    workspace_id: UUID,
    webhook_id: UUID,
    actor_id: UUID,
    *,
    name: str,
) -> OutboundWebhookCreateResponse:
    data = _webhook(workspace_id, webhook_id, actor_id).model_dump()
    data["name"] = name
    return OutboundWebhookCreateResponse(**data, signing_secret="secret")


def _delivery(webhook_id: UUID) -> WebhookDeliveryRead:
    now = datetime.now(UTC)
    return WebhookDeliveryRead(
        id=uuid4(),
        webhook_id=webhook_id,
        idempotency_key=uuid4(),
        event_id=uuid4(),
        event_type="execution.failed",
        payload={"ok": True},
        status="delivered",
        failure_reason=None,
        attempts=1,
        last_attempt_at=now,
        last_response_status=200,
        next_attempt_at=None,
        dead_lettered_at=None,
        replayed_from=None,
        replayed_by=None,
        resolved_at=None,
        resolved_by=None,
        resolution_reason=None,
        created_at=now,
        updated_at=now,
    )


def _dead_letter(workspace_id: UUID, webhook_id: UUID) -> DeadLetterListItem:
    data = _delivery(webhook_id).model_dump()
    data["status"] = "dead_letter"
    data["dead_lettered_at"] = datetime.now(UTC)
    return DeadLetterListItem(**data, workspace_id=workspace_id, webhook_name="CRM")
