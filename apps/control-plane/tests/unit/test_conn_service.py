from __future__ import annotations

import json
import platform.connectors.service as service_module
from datetime import UTC, datetime
from platform.connectors.exceptions import (
    ConnectorConfigError,
    ConnectorDisabledError,
    ConnectorNotFoundError,
    ConnectorTypeDeprecatedError,
    ConnectorTypeNotFoundError,
    DeadLetterAlreadyResolvedError,
    DeadLetterNotFoundError,
    DeliveryError,
    DeliveryPermanentError,
)
from platform.connectors.models import (
    ConnectorCredentialRef,
    ConnectorHealthStatus,
    ConnectorInstanceStatus,
    ConnectorType,
    DeadLetterResolution,
    DeliveryStatus,
)
from platform.connectors.plugin import HealthCheckResult, InboundMessage
from platform.connectors.security import compute_hmac_sha256
from platform.connectors.schemas import (
    ConnectorInstanceCreate,
    ConnectorInstanceUpdate,
    ConnectorRouteCreate,
    ConnectorRouteUpdate,
    DeadLetterDiscardRequest,
    DeadLetterRedeliverRequest,
    OutboundDeliveryCreate,
)
from platform.connectors.service import ConnectorsService
from uuid import UUID, uuid4

import pytest

from tests.auth_support import FakeAsyncRedisClient, RecordingProducer
from tests.connectors_support import (
    ObjectStorageStub,
    build_connector_instance,
    build_connectors_settings,
    build_dead_letter,
    build_delivery,
    build_route,
    write_mock_vault,
)


class FakeConnector:
    def __init__(
        self,
        *,
        health_result: HealthCheckResult | None = None,
        inbound_result: InboundMessage | None = None,
        deliver_error: Exception | None = None,
    ) -> None:
        self.health_result = health_result or HealthCheckResult(
            status=ConnectorHealthStatus.healthy,
            latency_ms=5.0,
        )
        self.inbound_result = inbound_result
        self.deliver_error = deliver_error
        self.validated: list[tuple[dict[str, object], dict[str, str]]] = []
        self.deliveries: list[tuple[object, dict[str, object]]] = []

    async def validate_config(
        self,
        config: dict[str, object],
        credential_refs: dict[str, str],
    ) -> None:
        self.validated.append((config, credential_refs))

    async def normalize_inbound(self, **kwargs) -> InboundMessage:
        del kwargs
        assert self.inbound_result is not None
        return self.inbound_result

    async def deliver_outbound(self, request, config: dict[str, object]) -> None:
        self.deliveries.append((request, config))
        if self.deliver_error is not None:
            raise self.deliver_error

    async def health_check(self, config: dict[str, object]) -> HealthCheckResult:
        self.last_health_config = config
        return self.health_result


class FakeConnectorsRepository:
    def __init__(self, *, connector_type: ConnectorType, instance) -> None:
        self.connector_type = connector_type
        self.instances: dict[UUID, object] = {instance.id: instance}
        self.routes: dict[UUID, object] = {}
        self.deliveries: dict[UUID, object] = {}
        self.dead_letters: dict[UUID, object] = {}
        self.pending_retries: list[object] = []
        self.raise_integrity = False

    async def list_connector_types(self):
        return [self.connector_type]

    async def get_connector_type(self, type_slug: str):
        return self.connector_type if self.connector_type.slug == type_slug else None

    async def create_connector_instance(self, **kwargs):
        if self.raise_integrity:
            raise type("IntegrityError", (Exception,), {})()
        created = build_connector_instance(
            workspace_id=kwargs["workspace_id"],
            connector_type=self.connector_type,
            name=kwargs["name"],
            config=kwargs["config"],
            status=kwargs["status"],
        )
        created.messages_sent = 0
        created.messages_failed = 0
        created.messages_retried = 0
        created.messages_dead_lettered = 0
        created.created_at = datetime.now(UTC)
        created.updated_at = created.created_at
        self.instances[created.id] = created
        return created

    async def upsert_credential_refs(self, connector_instance_id: UUID, workspace_id: UUID, credential_refs: dict[str, str]):
        refs = [
            ConnectorCredentialRef(
                connector_instance_id=connector_instance_id,
                workspace_id=workspace_id,
                credential_key=key,
                vault_path=value,
            )
            for key, value in sorted(credential_refs.items())
        ]
        self.instances[connector_instance_id].credential_refs = refs
        return refs

    async def get_connector_instance(self, connector_id: UUID, workspace_id: UUID):
        instance = self.instances.get(connector_id)
        if instance is None or instance.workspace_id != workspace_id or instance.deleted_at is not None:
            return None
        return instance

    async def get_connector_instance_public(self, connector_id: UUID):
        instance = self.instances.get(connector_id)
        if instance is None or instance.deleted_at is not None:
            return None
        return instance

    async def list_connector_instances(self, workspace_id: UUID):
        items = [item for item in self.instances.values() if item.workspace_id == workspace_id and item.deleted_at is None]
        return items, len(items)

    async def update_connector_instance(self, instance, **kwargs):
        if self.raise_integrity:
            raise type("IntegrityError", (Exception,), {})()
        if kwargs.get("name") is not None:
            instance.name = kwargs["name"]
        if kwargs.get("config") is not None:
            instance.config_json = kwargs["config"]
        if kwargs.get("status") is not None:
            instance.status = kwargs["status"]
        if kwargs.get("health_status") is not None:
            instance.health_status = kwargs["health_status"]
        if "health_check_error" in kwargs:
            instance.health_check_error = kwargs["health_check_error"]
        if kwargs.get("last_health_check_at") is not None:
            instance.last_health_check_at = kwargs["last_health_check_at"]
        return instance

    async def soft_delete_connector_instance(self, instance):
        instance.deleted_at = datetime.now(UTC)
        return instance

    async def create_route(self, **kwargs):
        route = build_route(
            workspace_id=kwargs["workspace_id"],
            connector_instance_id=kwargs["connector_instance_id"],
            name=kwargs["name"],
            channel_pattern=kwargs["channel_pattern"],
            sender_pattern=kwargs["sender_pattern"],
            conditions=kwargs["conditions"],
            target_agent_fqn=kwargs["target_agent_fqn"],
            priority=kwargs["priority"],
            is_enabled=kwargs["is_enabled"],
        )
        route.target_workflow_id = kwargs["target_workflow_id"]
        route.created_at = datetime.now(UTC)
        route.updated_at = route.created_at
        self.routes[route.id] = route
        return route

    async def get_route(self, route_id: UUID, workspace_id: UUID):
        route = self.routes.get(route_id)
        if route is None or route.workspace_id != workspace_id or route.deleted_at is not None:
            return None
        return route

    async def list_routes(self, workspace_id: UUID, connector_instance_id: UUID):
        items = [
            route
            for route in self.routes.values()
            if route.workspace_id == workspace_id
            and route.connector_instance_id == connector_instance_id
            and route.deleted_at is None
        ]
        return items, len(items)

    async def update_route(self, route, **kwargs):
        for key, value in kwargs.items():
            if value is not None:
                setattr(route, key if key != "conditions" else "conditions_json", value)
        return route

    async def delete_route(self, route):
        route.deleted_at = datetime.now(UTC)
        return route

    async def get_routes_for_instance(self, connector_instance_id: UUID, workspace_id: UUID):
        routes = [
            route
            for route in self.routes.values()
            if route.connector_instance_id == connector_instance_id
            and route.workspace_id == workspace_id
            and route.deleted_at is None
        ]
        return sorted(routes, key=lambda item: (item.priority, item.created_at))

    async def create_outbound_delivery(self, **kwargs):
        delivery = build_delivery(
            workspace_id=kwargs["workspace_id"],
            connector_instance_id=kwargs["connector_instance_id"],
            destination=kwargs["destination"],
            max_attempts=kwargs["max_attempts"],
        )
        delivery.content_json = kwargs["content"]
        delivery.priority = kwargs["priority"]
        delivery.source_interaction_id = kwargs["source_interaction_id"]
        delivery.source_execution_id = kwargs["source_execution_id"]
        delivery.created_at = datetime.now(UTC)
        delivery.updated_at = delivery.created_at
        self.deliveries[delivery.id] = delivery
        return delivery

    async def get_outbound_delivery(self, delivery_id: UUID, workspace_id: UUID | None = None):
        delivery = self.deliveries.get(delivery_id)
        if delivery is None:
            return None
        if workspace_id is not None and delivery.workspace_id != workspace_id:
            return None
        return delivery

    async def list_outbound_deliveries(self, workspace_id: UUID, connector_instance_id: UUID | None = None):
        items = [
            delivery
            for delivery in self.deliveries.values()
            if delivery.workspace_id == workspace_id
            and (connector_instance_id is None or delivery.connector_instance_id == connector_instance_id)
        ]
        return items, len(items)

    async def update_delivery_status(self, delivery, **kwargs):
        delivery.status = kwargs["status"]
        if kwargs.get("attempt_count") is not None:
            delivery.attempt_count = kwargs["attempt_count"]
        delivery.next_retry_at = kwargs.get("next_retry_at")
        delivery.delivered_at = kwargs.get("delivered_at")
        return delivery

    async def append_error_history(self, delivery, error_record):
        delivery.error_history = [*delivery.error_history, error_record]
        return delivery

    async def get_pending_retries(self, *, limit: int):
        del limit
        return list(self.pending_retries)

    async def create_dead_letter_entry(self, **kwargs):
        entry = build_dead_letter(
            workspace_id=kwargs["workspace_id"],
            connector_instance_id=kwargs["connector_instance_id"],
            delivery=self.deliveries[kwargs["outbound_delivery_id"]],
        )
        entry.dead_lettered_at = kwargs["dead_lettered_at"]
        entry.resolved_at = None
        entry.archive_path = None
        self.dead_letters[entry.id] = entry
        return entry

    async def increment_connector_metrics(self, connector_instance_id: UUID, *, sent_delta: int = 0, failed_delta: int = 0, retried_delta: int = 0, dead_lettered_delta: int = 0):
        instance = self.instances[connector_instance_id]
        instance.messages_sent += sent_delta
        instance.messages_failed += failed_delta
        instance.messages_retried += retried_delta
        instance.messages_dead_lettered += dead_lettered_delta

    async def list_dead_letter_entries(self, workspace_id: UUID, *, connector_instance_id: UUID | None = None, resolution_status: DeadLetterResolution | None = None):
        items = [
            entry
            for entry in self.dead_letters.values()
            if entry.workspace_id == workspace_id
            and (connector_instance_id is None or entry.connector_instance_id == connector_instance_id)
            and (resolution_status is None or entry.resolution_status == resolution_status)
        ]
        return items, len(items)

    async def get_dead_letter_entry(self, entry_id: UUID, workspace_id: UUID):
        entry = self.dead_letters.get(entry_id)
        if entry is None or entry.workspace_id != workspace_id:
            return None
        return entry

    async def update_dead_letter_resolution(self, entry, **kwargs):
        entry.resolution_status = kwargs["resolution_status"]
        entry.resolved_at = kwargs["resolved_at"]
        entry.resolution_note = kwargs["resolution_note"]
        entry.archive_path = kwargs.get("archive_path")
        return entry

    async def list_enabled_connector_instances_by_type(self, type_slug: str):
        return [
            instance
            for instance in self.instances.values()
            if instance.connector_type.slug == type_slug
            and instance.status is ConnectorInstanceStatus.enabled
            and instance.deleted_at is None
        ]


def _service(tmp_path):
    workspace_id = uuid4()
    connector_type = ConnectorType(
        id=uuid4(),
        slug="slack",
        display_name="Slack",
        description="Slack",
        config_schema={},
        is_deprecated=False,
        deprecated_at=None,
        deprecation_note=None,
    )
    instance = build_connector_instance(
        workspace_id=workspace_id,
        connector_type=connector_type,
        config={"bot_token": {"$ref": "bot_token"}, "signing_secret": {"$ref": "signing_secret"}},
        status=ConnectorInstanceStatus.enabled,
    )
    instance.messages_sent = 0
    instance.messages_failed = 0
    instance.messages_retried = 0
    instance.messages_dead_lettered = 0
    instance.created_at = datetime.now(UTC)
    instance.updated_at = instance.created_at
    instance.credential_refs = [
        ConnectorCredentialRef(
            connector_instance_id=instance.id,
            workspace_id=workspace_id,
            credential_key="bot_token",
            vault_path="vault/bot_token",
        ),
        ConnectorCredentialRef(
            connector_instance_id=instance.id,
            workspace_id=workspace_id,
            credential_key="signing_secret",
            vault_path="vault/signing_secret",
        ),
    ]
    settings = build_connectors_settings(vault_file=tmp_path / "vault.json")
    write_mock_vault(
        tmp_path / "vault.json",
        {"vault/bot_token": "bot-secret", "vault/signing_secret": "signing-secret"},
    )
    repo = FakeConnectorsRepository(connector_type=connector_type, instance=instance)
    redis_client = FakeAsyncRedisClient()
    producer = RecordingProducer()
    object_storage = ObjectStorageStub()
    service = ConnectorsService(
        repository=repo,  # type: ignore[arg-type]
        settings=settings,
        producer=producer,
        redis_client=redis_client,  # type: ignore[arg-type]
        object_storage=object_storage,  # type: ignore[arg-type]
    )
    return service, repo, instance, settings, producer, redis_client, object_storage


@pytest.mark.asyncio
async def test_service_connector_instance_lifecycle_and_health(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, instance, settings, producer, redis_client, object_storage = _service(tmp_path)
    del producer, redis_client, object_storage
    fake_connector = FakeConnector(
        health_result=HealthCheckResult(
            status=ConnectorHealthStatus.degraded,
            latency_ms=3.0,
            error="failed with signing-secret",
        )
    )
    monkeypatch.setattr(service_module, "get_connector", lambda slug: fake_connector)

    types_response = await service.list_connector_types()
    assert types_response.total == 1
    assert (await service.get_connector_type("slack")).slug == "slack"
    with pytest.raises(ConnectorTypeNotFoundError):
        await service.get_connector_type("missing")

    created = await service.create_connector_instance(
        instance.workspace_id,
        ConnectorInstanceCreate.model_validate(
            {
                "connector_type_slug": "slack",
                "name": " Support ",
                "config": {
                    "bot_token": {"$ref": "bot_token"},
                    "signing_secret": {"$ref": "signing_secret"},
                },
                "credential_refs": {
                    "bot_token": "vault/bot_token",
                    "signing_secret": "vault/signing_secret",
                },
            }
        ),
    )
    assert created.name == "Support"
    assert fake_connector.validated[-1][0]["bot_token"] == {"$ref": "bot_token"}

    repo.connector_type.is_deprecated = True
    with pytest.raises(ConnectorTypeDeprecatedError):
        await service.create_connector_instance(
            instance.workspace_id,
            ConnectorInstanceCreate.model_validate(
                {
                    "connector_type_slug": "slack",
                    "name": "Deprecated",
                    "config": {
                        "bot_token": {"$ref": "bot_token"},
                        "signing_secret": {"$ref": "signing_secret"},
                    },
                    "credential_refs": {
                        "bot_token": "vault/bot_token",
                        "signing_secret": "vault/signing_secret",
                    },
                }
            ),
        )
    repo.connector_type.is_deprecated = False

    repo.raise_integrity = True
    with pytest.raises(Exception) as excinfo:
        await service.create_connector_instance(
            instance.workspace_id,
            ConnectorInstanceCreate.model_validate(
                {
                    "connector_type_slug": "slack",
                    "name": "Conflict",
                    "config": {
                        "bot_token": {"$ref": "bot_token"},
                        "signing_secret": {"$ref": "signing_secret"},
                    },
                    "credential_refs": {
                        "bot_token": "vault/bot_token",
                        "signing_secret": "vault/signing_secret",
                    },
                }
            ),
        )
    assert excinfo.type.__name__ == "ConnectorNameConflictError"
    repo.raise_integrity = False

    with pytest.raises(ConnectorConfigError):
        await service.create_connector_instance(
            instance.workspace_id,
            ConnectorInstanceCreate.model_validate(
                {
                    "connector_type_slug": "slack",
                    "name": "Broken",
                    "config": {"bot_token": {"$ref": "bot_token"}},
                    "credential_refs": {},
                }
            ),
        )

    listed = await service.list_connector_instances(instance.workspace_id)
    assert listed.total >= 1
    fetched = await service.get_connector_instance(instance.workspace_id, instance.id)
    assert fetched.id == instance.id

    updated = await service.update_connector_instance(
        instance.workspace_id,
        instance.id,
        ConnectorInstanceUpdate.model_validate(
            {
                "name": "Renamed",
                "status": "disabled",
                "credential_refs": {
                    "bot_token": "vault/bot_token",
                    "signing_secret": "vault/signing_secret",
                },
            }
        ),
    )
    assert updated.name == "Renamed"
    assert instance.status is ConnectorInstanceStatus.disabled

    instance.status = ConnectorInstanceStatus.enabled
    health = await service.run_health_check(instance.workspace_id, instance.id)
    assert health.status is ConnectorHealthStatus.degraded
    assert health.error == "failed with [REDACTED]"

    await service.delete_connector_instance(instance.workspace_id, instance.id)
    with pytest.raises(ConnectorNotFoundError):
        await service.get_connector_instance(instance.workspace_id, instance.id)

    repo.instances[instance.id] = instance
    instance.deleted_at = None
    assert settings.connectors.ingress_topic == "connector.ingress"


@pytest.mark.asyncio
async def test_service_routing_verification_and_inbound_flow(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, instance, settings, producer, redis_client, object_storage = _service(tmp_path)
    del settings, object_storage
    inbound_message = InboundMessage(
        connector_instance_id=instance.id,
        workspace_id=instance.workspace_id,
        sender_identity="U123",
        sender_display="alice",
        channel="#support-prod",
        content_text="hello",
        content_structured={"text": "hello"},
        timestamp=datetime.now(UTC),
        original_payload={"severity": "high"},
        message_id="m-1",
    )
    fake_connector = FakeConnector(inbound_result=inbound_message)
    monkeypatch.setattr(service_module, "get_connector", lambda slug: fake_connector)

    route = await service.create_route(
        instance.workspace_id,
        instance.id,
        ConnectorRouteCreate.model_validate(
            {
                "name": "route",
                "channel_pattern": "#support*",
                "conditions": {"severity": "high"},
                "target_agent_fqn": "ops:triage",
            }
        ),
    )
    fetched_route = await service.get_route(instance.workspace_id, route.id)
    assert fetched_route.id == route.id
    listed_routes = await service.list_routes(instance.workspace_id, instance.id)
    assert listed_routes.total == 1
    updated_route = await service.update_route(
        instance.workspace_id,
        route.id,
        ConnectorRouteUpdate.model_validate({"target_agent_fqn": "ops:lead", "priority": 5}),
    )
    assert updated_route.target_agent_fqn == "ops:lead"
    with pytest.raises(ConnectorConfigError):
        await service.update_route(
            instance.workspace_id,
            route.id,
            ConnectorRouteUpdate.model_validate({"target_agent_fqn": None}),
        )

    raw = b'{"event":"ok"}'
    webhook_signature = "sha256=" + compute_hmac_sha256("signing-secret", raw)
    await service.verify_webhook_request(instance.id, raw, {"x-hub-signature-256": webhook_signature})
    timestamp = "12345"
    slack_signature = "v0=" + compute_hmac_sha256(
        "signing-secret",
        f"v0:{timestamp}:".encode() + raw,
    )
    await service.verify_slack_request(
        instance.id,
        raw,
        {"x-slack-signature": slack_signature, "x-slack-request-timestamp": timestamp},
    )

    matched = await service.match_route(instance.workspace_id, instance.id, inbound_message)
    assert matched is not None
    cache_key = f"connector:routes:{instance.workspace_id}:{instance.id}"
    assert await redis_client.get(cache_key) is not None

    routed = await service.process_inbound(
        instance.id,
        payload={"severity": "high"},
        raw_body=raw,
        headers={},
        path="/hooks/slack",
    )
    assert routed["routed"] is True
    assert producer.events[-1]["event_type"] == "connector.ingress.received"

    fake_connector.inbound_result = InboundMessage(
        connector_instance_id=instance.id,
        workspace_id=instance.workspace_id,
        sender_identity="U123",
        sender_display=None,
        channel="#other",
        content_text="hello",
        content_structured=None,
        timestamp=datetime.now(UTC),
        original_payload={},
        message_id=None,
    )
    unrouted = await service.process_inbound(
        instance.id,
        payload={},
        raw_body=raw,
        headers={},
        path="/hooks/slack",
    )
    assert unrouted == {"ok": True, "routed": False}

    challenge = await service.process_inbound(
        instance.id,
        payload={"type": "url_verification", "challenge": "abc"},
        raw_body=raw,
        headers={},
        path="/hooks/slack",
    )
    assert challenge == {"ok": True, "challenge": "abc"}

    instance.status = ConnectorInstanceStatus.disabled
    with pytest.raises(ConnectorDisabledError):
        await service.process_inbound(instance.id, payload={}, raw_body=raw, headers={}, path=None)
    instance.status = ConnectorInstanceStatus.enabled

    small_settings = build_connectors_settings(
        vault_file=tmp_path / "small-vault.json",
        database_url="postgresql+asyncpg://user:pass@localhost:5432/test",
    )
    write_mock_vault(
        tmp_path / "small-vault.json",
        {"vault/bot_token": "bot-secret", "vault/signing_secret": "signing-secret"},
    )
    small_settings.connectors.max_payload_size_bytes = 1
    tiny_service = ConnectorsService(
        repository=repo,  # type: ignore[arg-type]
        settings=small_settings,
        producer=producer,
        redis_client=redis_client,  # type: ignore[arg-type]
        object_storage=ObjectStorageStub(),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(service_module, "get_connector", lambda slug: fake_connector)
    with pytest.raises(ConnectorConfigError):
        await tiny_service.process_inbound(instance.id, payload={}, raw_body=b"too-big", headers={}, path=None)

    await service.delete_route(instance.workspace_id, route.id)
    with pytest.raises(ConnectorNotFoundError):
        await service.get_route(instance.workspace_id, route.id)


@pytest.mark.asyncio
async def test_service_delivery_dead_letter_and_polling_paths(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, instance, settings, producer, redis_client, object_storage = _service(tmp_path)
    del settings
    delivery_connector = FakeConnector()
    monkeypatch.setattr(service_module, "get_connector", lambda slug: delivery_connector)

    created = await service.create_delivery(
        instance.workspace_id,
        OutboundDeliveryCreate.model_validate(
            {
                "connector_instance_id": instance.id,
                "destination": "C123",
                "content_text": "hello",
            }
        ),
    )
    assert created.destination == "C123"
    delivery_id = created.id
    assert (await service.get_delivery(instance.workspace_id, delivery_id)).id == delivery_id
    assert (await service.list_deliveries(instance.workspace_id)).total == 1

    delivered = await service.execute_delivery(delivery_id)
    assert delivered.status is DeliveryStatus.delivered
    assert repo.instances[instance.id].messages_sent == 1

    failure_delivery = await repo.create_outbound_delivery(
        workspace_id=instance.workspace_id,
        connector_instance_id=instance.id,
        destination="C999",
        content={"content_text": "hello", "content_structured": None, "metadata": {}},
        priority=1,
        max_attempts=3,
        source_interaction_id=None,
        source_execution_id=None,
    )
    delivery_connector.deliver_error = DeliveryError("secret bot-secret down")
    failed = await service.execute_delivery(failure_delivery.id)
    assert failed.status is DeliveryStatus.failed
    assert failed.error_history[-1]["error"] == "secret [REDACTED] down"

    dead_letter_delivery = await repo.create_outbound_delivery(
        workspace_id=instance.workspace_id,
        connector_instance_id=instance.id,
        destination="C777",
        content={"content_text": "hello", "content_structured": None, "metadata": {}},
        priority=1,
        max_attempts=1,
        source_interaction_id=None,
        source_execution_id=None,
    )
    delivery_connector.deliver_error = DeliveryPermanentError("permanent bot-secret")
    dead_lettered = await service.execute_delivery(dead_letter_delivery.id)
    assert dead_lettered.status is DeliveryStatus.dead_lettered
    assert repo.instances[instance.id].messages_dead_lettered == 1
    assert producer.events[-1]["event_type"] == "connector.delivery.dead_lettered"

    delivered_again = await service.execute_delivery(delivery_id)
    assert delivered_again.status is DeliveryStatus.delivered

    repo.pending_retries = [failure_delivery]
    delivery_connector.deliver_error = None
    await service.retry_pending_deliveries()

    dead_letter_entry = next(iter(repo.dead_letters.values()))
    listed_dead_letters = await service.list_dead_letter_entries(instance.workspace_id)
    assert listed_dead_letters.total == 1
    assert (await service.get_dead_letter_entry(instance.workspace_id, dead_letter_entry.id)).id == dead_letter_entry.id

    redelivered = await service.redeliver_dead_letter(
        instance.workspace_id,
        dead_letter_entry.id,
        DeadLetterRedeliverRequest.model_validate({"resolution_note": "retry"}),
    )
    assert redelivered.destination == dead_letter_entry.outbound_delivery.destination
    assert dead_letter_entry.resolution_status is DeadLetterResolution.redelivered

    pending_delivery = build_delivery(
        workspace_id=instance.workspace_id,
        connector_instance_id=instance.id,
    )
    pending_delivery.created_at = datetime.now(UTC)
    pending_delivery.updated_at = pending_delivery.created_at
    pending_entry = build_dead_letter(
        workspace_id=instance.workspace_id,
        connector_instance_id=instance.id,
        delivery=pending_delivery,
    )
    repo.dead_letters[pending_entry.id] = pending_entry
    discarded = await service.discard_dead_letter(
        instance.workspace_id,
        pending_entry.id,
        DeadLetterDiscardRequest.model_validate({"resolution_note": "archive"}),
    )
    assert discarded.archive_path is not None
    assert object_storage.objects

    with pytest.raises(DeadLetterAlreadyResolvedError):
        await service.redeliver_dead_letter(
            instance.workspace_id,
            dead_letter_entry.id,
            DeadLetterRedeliverRequest.model_validate({}),
        )
    with pytest.raises(DeadLetterNotFoundError):
        await service.get_dead_letter_entry(instance.workspace_id, uuid4())

    email_type = ConnectorType(
        id=uuid4(),
        slug="email",
        display_name="Email",
        description="Email",
        config_schema={},
        is_deprecated=False,
        deprecated_at=None,
        deprecation_note=None,
    )
    email_instance = build_connector_instance(
        workspace_id=instance.workspace_id,
        connector_type=email_type,
        config={"imap_host": {"nested": "bad"}},
        status=ConnectorInstanceStatus.enabled,
    )
    email_instance.config_json = {
        "imap_host": "imap.example.com",
        "imap_port": 993,
        "email_address": "ops@example.com",
        "imap_password": {"$ref": "imap_password"},
        "inbox_folder": "INBOX",
    }
    email_instance.messages_sent = 0
    email_instance.messages_failed = 0
    email_instance.messages_retried = 0
    email_instance.messages_dead_lettered = 0
    email_instance.created_at = datetime.now(UTC)
    email_instance.updated_at = email_instance.created_at
    email_instance.credential_refs = [
        ConnectorCredentialRef(
            connector_instance_id=email_instance.id,
            workspace_id=email_instance.workspace_id,
            credential_key="imap_password",
            vault_path="vault/imap_password",
        )
    ]
    repo.instances[email_instance.id] = email_instance
    write_mock_vault(
        tmp_path / "vault.json",
        {
            "vault/bot_token": "bot-secret",
            "vault/signing_secret": "signing-secret",
            "vault/imap_password": "imap-secret",
        },
    )

    raw_message = (
        "From: alerts@example.com\r\n"
        "To: ops@example.com\r\n"
        "Subject: Incident\r\n"
        "Content-Type: text/plain; charset=utf-8\r\n\r\n"
        "Paged\r\n"
    ).encode("utf-8")

    class ImapStub:
        def __init__(self, host: str, port: int) -> None:
            self.host = host
            self.port = port
            self.seen: list[str] = []

        async def wait_hello_from_server(self) -> None:
            return None

        async def login(self, username: str, password: str) -> None:
            self.username = username
            self.password = password

        async def select(self, folder: str) -> None:
            self.folder = folder

        async def search(self, query: str):
            del query
            return "OK", [b"1 2"]

        async def fetch(self, message_id: str, flags: str):
            del flags
            return "OK", [b"RFC822", raw_message if message_id == "1" else b"RFC822", b"ignored"]

        async def store(self, message_id: str, action: str, flag: str) -> None:
            self.seen.append(message_id + action + flag)

        async def logout(self) -> None:
            return None

    monkeypatch.setattr(
        service_module,
        "__import__",
        lambda name: type("ImapModule", (), {"IMAP4_SSL": ImapStub}),
        raising=False,
    )
    email_connector = FakeConnector(
        inbound_result=InboundMessage(
            connector_instance_id=email_instance.id,
            workspace_id=email_instance.workspace_id,
            sender_identity="alerts@example.com",
            sender_display=None,
            channel="ops@example.com",
            content_text="Paged",
            content_structured=None,
            timestamp=datetime.now(UTC),
            original_payload={"message_id": "1"},
            message_id="1",
        )
    )
    repo.routes.clear()
    email_route = await repo.create_route(
        workspace_id=email_instance.workspace_id,
        connector_instance_id=email_instance.id,
        name="email route",
        channel_pattern="ops@example.com",
        sender_pattern=None,
        conditions={},
        target_agent_fqn="ops:triage",
        target_workflow_id=None,
        priority=1,
        is_enabled=True,
    )
    monkeypatch.setattr(service_module, "get_connector", lambda slug: email_connector if slug == "email" else delivery_connector)
    await service.poll_email_connectors()
    assert producer.events[-1]["payload"]["route_id"] == str(email_route.id)

    assert service._parse_search_ids(("OK", [b"1 2"])) == ["1", "2"]
    assert service._parse_search_ids(("OK", ["3 4"])) == ["3", "4"]
    assert service._extract_email_payload(("OK", [b"RFC822", raw_message])) == raw_message
    assert service._extract_email_payload(("OK", [])) is None
    assert service._dead_letter_depth_key(instance.workspace_id).startswith("connector:dead-letter-depth:")
    assert service._route_cache_key(instance.workspace_id, instance.id).startswith("connector:routes:")
    assert service._extract_config_refs({"a": [{"$ref": "token"}], "b": {"$ref": "secret"}}) == {"token", "secret"}
    assert service._route_to_cache(email_route)["target_agent_fqn"] == "ops:triage"


@pytest.mark.asyncio
async def test_service_not_found_disabled_and_helper_edges(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    service, repo, instance, settings, producer, redis_client, object_storage = _service(tmp_path)
    del settings, producer, object_storage
    fake_connector = FakeConnector(
        inbound_result=InboundMessage(
            connector_instance_id=instance.id,
            workspace_id=instance.workspace_id,
            sender_identity="sender-1",
            sender_display=None,
            channel="#ops",
            content_text="hello",
            content_structured=None,
            timestamp=datetime.now(UTC),
            original_payload={"severity": "high"},
            message_id=None,
        ),
        deliver_error=RuntimeError("boom"),
    )
    monkeypatch.setattr(service_module, "get_connector", lambda slug: fake_connector)

    with pytest.raises(ConnectorTypeNotFoundError):
        await service.create_connector_instance(
            instance.workspace_id,
            ConnectorInstanceCreate.model_validate(
                {
                    "connector_type_slug": "telegram",
                    "name": "Missing type",
                    "config": {"bot_token": {"$ref": "bot_token"}},
                    "credential_refs": {"bot_token": "vault/bot_token"},
                }
            ),
        )

    missing_id = uuid4()
    with pytest.raises(ConnectorNotFoundError):
        await service.get_connector_instance(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.update_connector_instance(
            instance.workspace_id,
            missing_id,
            ConnectorInstanceUpdate.model_validate({"name": "x"}),
        )
    with pytest.raises(ConnectorNotFoundError):
        await service.delete_connector_instance(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.run_health_check(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.create_route(
            instance.workspace_id,
            missing_id,
            ConnectorRouteCreate.model_validate({"name": "r", "target_agent_fqn": "ops:triage"}),
        )
    with pytest.raises(ConnectorNotFoundError):
        await service.list_routes(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.get_route(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.delete_route(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.verify_webhook_request(missing_id, b"{}", {})
    with pytest.raises(ConnectorNotFoundError):
        await service.verify_slack_request(missing_id, b"{}", {})

    with pytest.raises(ConnectorNotFoundError):
        await service.create_delivery(
            instance.workspace_id,
            OutboundDeliveryCreate.model_validate(
                {
                    "connector_instance_id": missing_id,
                    "destination": "C123",
                    "content_text": "hello",
                }
            ),
        )
    instance.status = ConnectorInstanceStatus.disabled
    with pytest.raises(ConnectorDisabledError):
        await service.create_delivery(
            instance.workspace_id,
            OutboundDeliveryCreate.model_validate(
                {
                    "connector_instance_id": instance.id,
                    "destination": "C123",
                    "content_text": "hello",
                }
            ),
        )
    instance.status = ConnectorInstanceStatus.enabled
    with pytest.raises(ConnectorNotFoundError):
        await service.get_delivery(instance.workspace_id, missing_id)
    with pytest.raises(ConnectorNotFoundError):
        await service.execute_delivery(missing_id)

    delivery = await repo.create_outbound_delivery(
        workspace_id=instance.workspace_id,
        connector_instance_id=instance.id,
        destination="C1",
        content={"content_text": "hi", "content_structured": None, "metadata": {}},
        priority=1,
        max_attempts=2,
        source_interaction_id=None,
        source_execution_id=None,
    )
    instance.status = ConnectorInstanceStatus.disabled
    with pytest.raises(ConnectorDisabledError):
        await service.execute_delivery(delivery.id)
    instance.status = ConnectorInstanceStatus.enabled

    repo.instances.pop(instance.id)
    with pytest.raises(ConnectorNotFoundError):
        await service.execute_delivery(delivery.id)
    repo.instances[instance.id] = instance

    generic_failed = await service.execute_delivery(delivery.id)
    assert generic_failed.status is DeliveryStatus.failed

    await redis_client.set(
        service._route_cache_key(instance.workspace_id, instance.id),
        b'{"invalid":"cache"}',
    )
    assert await service._load_routes_for_matching(instance.workspace_id, instance.id) == []

    inbound = InboundMessage(
        connector_instance_id=instance.id,
        workspace_id=instance.workspace_id,
        sender_identity="sender-1",
        sender_display=None,
        channel="#ops",
        content_text="hi",
        content_structured=None,
        timestamp=datetime.now(UTC),
        original_payload={"severity": "high"},
        message_id=None,
    )
    assert service._conditions_match({"severity": "high"}, inbound) is True
    assert service._conditions_match({"severity": "low"}, inbound) is False

    existing_dead = await repo.create_outbound_delivery(
        workspace_id=instance.workspace_id,
        connector_instance_id=instance.id,
        destination="C2",
        content={"content_text": "hi", "content_structured": None, "metadata": {}},
        priority=1,
        max_attempts=1,
        source_interaction_id=None,
        source_execution_id=None,
    )
    existing_dead.error_history = [{"attempt": 1, "error": "boom"}]
    response = await service._dead_letter_delivery(existing_dead, instance.id, 1, "boom", [])
    assert response.status is DeliveryStatus.dead_lettered

    with pytest.raises(DeadLetterNotFoundError):
        await service.redeliver_dead_letter(
            instance.workspace_id,
            missing_id,
            DeadLetterRedeliverRequest.model_validate({}),
        )
    with pytest.raises(DeadLetterNotFoundError):
        await service.discard_dead_letter(
            instance.workspace_id,
            missing_id,
            DeadLetterDiscardRequest.model_validate({}),
        )
