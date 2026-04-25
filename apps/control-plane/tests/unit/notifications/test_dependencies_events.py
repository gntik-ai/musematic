from __future__ import annotations

from datetime import UTC, datetime
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.registry import event_registry
from platform.notifications.dependencies import (
    AllowAllDlpService,
    AllowAllResidencyService,
    InMemorySecretProvider,
    NoopAuditChainService,
    _get_producer,
    _get_redis,
    _get_settings,
    build_notifications_service,
    get_audit_chain_service,
    get_channel_router,
    get_deliverer_registry,
    get_dlp_service,
    get_notifications_service,
    get_outbound_webhook_service,
    get_residency_service,
    get_secret_provider,
)
from platform.notifications.events import (
    AlertCreatedPayload,
    AlertReadPayload,
    DeliveryAttemptedPayload,
    NotificationsEventType,
    WebhookDeactivatedPayload,
    WebhookRegisteredPayload,
    WebhookSecretRotatedPayload,
    publish_alert_created,
    publish_alert_read,
    publish_delivery_attempted,
    publish_webhook_deactivated,
    publish_webhook_registered,
    publish_webhook_secret_rotated,
    register_notifications_event_types,
)
from platform.notifications.exceptions import AlertAuthorizationError, AlertNotFoundError
from platform.notifications.models import DeliveryMethod
from platform.notifications.service import AlertService
from types import SimpleNamespace
from uuid import uuid4

import pytest
from pydantic import ValidationError
from tests.auth_support import RecordingProducer


@pytest.mark.asyncio
async def test_dependencies_build_service_and_get_dependency() -> None:
    settings = SimpleNamespace(notifications=SimpleNamespace())
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"redis": object(), "kafka": None},
            )
        )
    )
    session = object()
    workspaces_service = object()

    built = build_notifications_service(
        session=session,  # type: ignore[arg-type]
        settings=settings,  # type: ignore[arg-type]
        redis_client=request.app.state.clients["redis"],  # type: ignore[arg-type]
        producer=None,
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
    )
    resolved = await get_notifications_service(
        request,
        session=session,  # type: ignore[arg-type]
        workspaces_service=workspaces_service,  # type: ignore[arg-type]
    )

    assert isinstance(built, AlertService)
    assert isinstance(resolved, AlertService)


@pytest.mark.asyncio
async def test_dependency_fallback_services_and_factories() -> None:
    settings = PlatformSettings()
    redis_client = object()
    producer = object()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                clients={"redis": redis_client, "kafka": producer},
            )
        )
    )

    assert _get_settings(request) is settings  # type: ignore[arg-type]
    assert _get_redis(request) is redis_client  # type: ignore[arg-type]
    assert _get_producer(request) is producer  # type: ignore[arg-type]

    audit = get_audit_chain_service(request)  # type: ignore[arg-type]
    dlp = get_dlp_service(request)  # type: ignore[arg-type]
    residency = get_residency_service(request)  # type: ignore[arg-type]
    secrets = get_secret_provider(request)  # type: ignore[arg-type]
    registry = get_deliverer_registry(request, secrets)  # type: ignore[arg-type]

    assert isinstance(audit, NoopAuditChainService)
    assert isinstance(dlp, AllowAllDlpService)
    assert isinstance(residency, AllowAllResidencyService)
    assert isinstance(secrets, InMemorySecretProvider)
    assert registry.get(DeliveryMethod.email) is not None

    await audit.append({"event": "noop"})
    assert await dlp.scan_outbound(payload={}, workspace_id=None, channel_type="email") == {
        "action": "allow"
    }
    assert await residency.resolve_region_for_url("https://hooks.example.com") is None
    assert await residency.check_egress(object(), None) is True
    assert await secrets.read_secret("secret/path") == {}
    await secrets.write_secret("secret/path", {"value": "redacted"})

    custom_audit = NoopAuditChainService()
    custom_dlp = AllowAllDlpService()
    custom_residency = AllowAllResidencyService()
    custom_secrets = InMemorySecretProvider()
    request.app.state.audit_chain_service = custom_audit
    request.app.state.dlp_service = custom_dlp
    request.app.state.residency_service = custom_residency
    request.app.state.secret_provider = custom_secrets
    assert get_audit_chain_service(request) is custom_audit  # type: ignore[arg-type]
    assert get_dlp_service(request) is custom_dlp  # type: ignore[arg-type]
    assert get_residency_service(request) is custom_residency  # type: ignore[arg-type]
    assert get_secret_provider(request) is custom_secrets  # type: ignore[arg-type]

    channel_router = await get_channel_router(
        request,  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        workspaces_service=object(),  # type: ignore[arg-type]
        audit_chain=custom_audit,
        dlp_service=custom_dlp,
        residency_service=custom_residency,
        secret_provider=custom_secrets,
        deliverers=registry,
    )
    outbound = await get_outbound_webhook_service(
        request,  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        dlp_service=custom_dlp,
        residency_service=custom_residency,
        secret_provider=custom_secrets,
    )
    notifications = await get_notifications_service(
        request,  # type: ignore[arg-type]
        session=object(),  # type: ignore[arg-type]
        workspaces_service=object(),  # type: ignore[arg-type]
        channel_router=channel_router,
        secret_provider=custom_secrets,
    )

    assert channel_router.settings is settings
    assert outbound.settings is settings
    assert notifications.channel_router is channel_router


@pytest.mark.asyncio
async def test_notifications_events_register_and_publish_helpers() -> None:
    register_notifications_event_types()
    assert event_registry.is_registered(NotificationsEventType.alert_created.value) is True
    assert event_registry.is_registered(NotificationsEventType.alert_read.value) is True

    producer = RecordingProducer()
    correlation = CorrelationContext(correlation_id=uuid4())
    created_payload = AlertCreatedPayload(
        id=uuid4(),
        user_id=uuid4(),
        alert_type="attention_request",
        title="Attention requested",
        body="Review needed",
        urgency="high",
        read=False,
        interaction_id=None,
        source_reference={"type": "attention_request", "id": str(uuid4())},
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    read_payload = AlertReadPayload(
        alert_id=uuid4(), user_id=created_payload.user_id, unread_count=1
    )

    await publish_alert_created(producer, created_payload, correlation)
    await publish_alert_read(producer, read_payload, correlation)
    await publish_webhook_registered(
        producer,
        WebhookRegisteredPayload(
            webhook_id=uuid4(),
            workspace_id=uuid4(),
            event_types=["execution.failed"],
            actor_id=uuid4(),
            occurred_at=datetime.now(UTC),
        ),
        correlation,
    )
    await publish_webhook_deactivated(
        producer,
        WebhookDeactivatedPayload(
            webhook_id=uuid4(),
            workspace_id=uuid4(),
            actor_id=uuid4(),
            occurred_at=datetime.now(UTC),
        ),
        correlation,
    )
    await publish_webhook_secret_rotated(
        producer,
        WebhookSecretRotatedPayload(
            webhook_id=uuid4(),
            workspace_id=uuid4(),
            actor_id=uuid4(),
            occurred_at=datetime.now(UTC),
        ),
        correlation,
    )
    await publish_delivery_attempted(
        producer,
        DeliveryAttemptedPayload(
            webhook_id=uuid4(),
            channel_type="webhook",
            outcome="success",
            occurred_at=datetime.now(UTC),
        ),
        correlation,
    )
    await publish_alert_created(None, created_payload, correlation)

    assert [event["event_type"] for event in producer.events] == [
        "notifications.alert_created",
        "notifications.alert_read",
        "notifications.webhook.registered",
        "notifications.webhook.deactivated",
        "notifications.webhook.rotated",
        "notifications.delivery.attempted",
    ]
    assert producer.events[0]["topic"] == "notifications.alerts"


def test_notifications_exceptions_and_schema_validator() -> None:
    missing = AlertNotFoundError("alert-1")
    forbidden = AlertAuthorizationError()

    assert missing.code == "ALERT_NOT_FOUND"
    assert forbidden.code == "ALERT_FORBIDDEN"

    from platform.notifications.schemas import UserAlertSettingsUpdate

    with pytest.raises(ValidationError, match="webhook_url is required"):
        UserAlertSettingsUpdate(
            state_transitions=["any_to_failed"],
            delivery_method="webhook",
            webhook_url=None,
        )
