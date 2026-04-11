from __future__ import annotations

from datetime import UTC, datetime
from platform.common.events.registry import event_registry
from platform.connectors.dependencies import build_connectors_service, get_connectors_service
from platform.connectors.events import (
    ConnectorDeliveryRequestPayload,
    ConnectorDeliverySucceededPayload,
    ConnectorIngressPayload,
    ConnectorsEventType,
    publish_connector_ingress,
    publish_delivery_requested,
    publish_delivery_succeeded,
    register_connectors_event_types,
)
from platform.connectors.service import ConnectorsService
from types import SimpleNamespace
from uuid import uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer
from tests.connectors_support import ObjectStorageStub, build_connectors_settings, request_stub


class SessionStub:
    pass


def test_connectors_register_event_types_and_build_service(tmp_path) -> None:
    settings = build_connectors_settings(vault_file=tmp_path / "vault.json")
    register_connectors_event_types()

    assert event_registry.is_registered(ConnectorsEventType.ingress_received.value) is True
    assert event_registry.is_registered(ConnectorsEventType.delivery_requested.value) is True
    assert event_registry.is_registered(ConnectorsEventType.dead_lettered.value) is True

    service = build_connectors_service(
        session=SessionStub(),  # type: ignore[arg-type]
        settings=settings,
        producer=None,
        redis_client=FakeAsyncRedisClient(),  # type: ignore[arg-type]
        object_storage=ObjectStorageStub(),  # type: ignore[arg-type]
    )

    assert isinstance(service, ConnectorsService)
    assert service.settings.connectors.ingress_topic == "connector.ingress"


@pytest.mark.asyncio
async def test_connectors_publish_helpers_and_dependency_resolution(tmp_path) -> None:
    settings = build_connectors_settings(vault_file=tmp_path / "vault.json")
    producer = RecordingProducer()
    redis_client = FakeAsyncRedisClient()
    object_storage = ObjectStorageStub()
    request = request_stub(settings, producer, redis_client, object_storage)

    resolved = await get_connectors_service(
        request,
        session=SessionStub(),  # type: ignore[arg-type]
    )

    correlation = SimpleNamespace(correlation_id=uuid4(), workspace_id=uuid4())
    ingress = ConnectorIngressPayload(
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        connector_type_slug="slack",
        route_id=None,
        target_agent_fqn="ops:triage",
        target_workflow_id=None,
        sender_identity="U1",
        channel="#support",
        content_text="hello",
        content_structured=None,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        message_id="m1",
        original_payload={"text": "hello"},
    )
    delivery_requested = ConnectorDeliveryRequestPayload(
        delivery_id=uuid4(),
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
    )
    delivery_succeeded = ConnectorDeliverySucceededPayload(
        delivery_id=uuid4(),
        connector_instance_id=uuid4(),
        workspace_id=uuid4(),
        delivered_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    await publish_connector_ingress(producer, ingress, correlation)
    await publish_delivery_requested(producer, delivery_requested, correlation)
    await publish_delivery_succeeded(producer, delivery_succeeded, correlation)

    assert isinstance(resolved, ConnectorsService)
    assert [event["event_type"] for event in producer.events] == [
        "connector.ingress.received",
        "connector.delivery.requested",
        "connector.delivery.succeeded",
    ]
