from __future__ import annotations

import json
from datetime import UTC, datetime
from fnmatch import fnmatch
from platform.common.events.envelope import CorrelationContext
from platform.common.logging import get_logger
from platform.connectors.events import (
    ConnectorDeadLetteredPayload,
    ConnectorDeliveryFailedPayload,
    ConnectorDeliveryRequestPayload,
    ConnectorDeliverySucceededPayload,
    ConnectorIngressPayload,
    publish_connector_ingress,
    publish_dead_lettered,
    publish_delivery_failed,
    publish_delivery_requested,
    publish_delivery_succeeded,
)
from platform.connectors.exceptions import (
    ConnectorConfigError,
    ConnectorDisabledError,
    ConnectorNameConflictError,
    ConnectorNotFoundError,
    ConnectorTypeDeprecatedError,
    ConnectorTypeNotFoundError,
    DeadLetterAlreadyResolvedError,
    DeadLetterNotFoundError,
    DeliveryError,
    DeliveryPermanentError,
)
from platform.connectors.implementations.registry import get_connector
from platform.connectors.models import (
    ConnectorInstance,
    ConnectorInstanceStatus,
    ConnectorRoute,
    DeadLetterEntry,
    DeadLetterResolution,
    DeliveryStatus,
    OutboundDelivery,
)
from platform.connectors.plugin import DeliveryRequest, InboundMessage
from platform.connectors.repository import ConnectorsRepository
from platform.connectors.retry import compute_next_retry_at
from platform.connectors.schemas import (
    ConnectorInstanceCreate,
    ConnectorInstanceListResponse,
    ConnectorInstanceResponse,
    ConnectorInstanceUpdate,
    ConnectorRouteCreate,
    ConnectorRouteListResponse,
    ConnectorRouteResponse,
    ConnectorRouteUpdate,
    ConnectorTypeListResponse,
    ConnectorTypeResponse,
    DeadLetterDiscardRequest,
    DeadLetterEntryListResponse,
    DeadLetterEntryResponse,
    DeadLetterRedeliverRequest,
    HealthCheckResponse,
    OutboundDeliveryCreate,
    OutboundDeliveryListResponse,
    OutboundDeliveryResponse,
    TestConnectivityRequest,
    TestConnectivityResponse,
)
from platform.connectors.security import (
    VaultResolver,
    assert_slack_signature,
    assert_webhook_signature,
    payload_to_json,
    resolve_connector_secret,
    scrub_secret_text,
)
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm.attributes import set_committed_value


class ConnectorsService:
    def __init__(
        self,
        *,
        repository: ConnectorsRepository,
        settings: Any,
        producer: Any | None,
        redis_client: Any,
        object_storage: Any,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.producer = producer
        self.redis_client = redis_client
        self.object_storage = object_storage
        self.vault = VaultResolver(settings)
        self.logger = get_logger(__name__)

    async def list_connector_types(self) -> ConnectorTypeListResponse:
        items = await self.repository.list_connector_types()
        return ConnectorTypeListResponse(
            items=[self._connector_type_response(item) for item in items],
            total=len(items),
        )

    async def get_connector_type(self, type_slug: str) -> ConnectorTypeResponse:
        item = await self.repository.get_connector_type(type_slug)
        if item is None:
            raise ConnectorTypeNotFoundError(type_slug)
        return self._connector_type_response(item)

    async def create_connector_instance(
        self,
        workspace_id: UUID,
        payload: ConnectorInstanceCreate,
    ) -> ConnectorInstanceResponse:
        connector_type = await self.repository.get_connector_type(payload.connector_type_slug.value)
        if connector_type is None:
            raise ConnectorTypeNotFoundError(payload.connector_type_slug.value)
        if connector_type.is_deprecated:
            raise ConnectorTypeDeprecatedError(connector_type.slug)
        await self._validate_connector_config(
            connector_type.slug,
            payload.config,
            payload.credential_refs,
        )
        try:
            instance = await self.repository.create_connector_instance(
                workspace_id=workspace_id,
                connector_type_id=connector_type.id,
                name=payload.name,
                config=payload.config,
                status=payload.status,
            )
            refs = await self.repository.upsert_credential_refs(
                instance.id,
                workspace_id,
                payload.credential_refs,
            )
            set_committed_value(instance, "connector_type", connector_type)
            set_committed_value(instance, "credential_refs", refs)
            return self._connector_instance_response(instance)
        except Exception as exc:
            if exc.__class__.__name__ == "IntegrityError":
                raise ConnectorNameConflictError(payload.name) from exc
            raise

    async def get_connector_instance(
        self,
        workspace_id: UUID,
        connector_id: UUID,
    ) -> ConnectorInstanceResponse:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        return self._connector_instance_response(instance)

    async def list_connector_instances(self, workspace_id: UUID) -> ConnectorInstanceListResponse:
        items, total = await self.repository.list_connector_instances(workspace_id)
        return ConnectorInstanceListResponse(
            items=[self._connector_instance_response(item) for item in items],
            total=total,
        )

    async def update_connector_instance(
        self,
        workspace_id: UUID,
        connector_id: UUID,
        payload: ConnectorInstanceUpdate,
    ) -> ConnectorInstanceResponse:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        next_config = payload.config if payload.config is not None else instance.config_json
        next_refs = (
            payload.credential_refs
            if payload.credential_refs is not None
            else {item.credential_key: item.vault_path for item in instance.credential_refs}
        )
        await self._validate_connector_config(
            instance.connector_type.slug,
            next_config,
            next_refs,
        )
        try:
            await self.repository.update_connector_instance(
                instance,
                name=payload.name,
                config=payload.config,
                status=payload.status,
            )
        except Exception as exc:
            if exc.__class__.__name__ == "IntegrityError":
                raise ConnectorNameConflictError(payload.name or instance.name) from exc
            raise
        if payload.credential_refs is not None:
            instance.credential_refs = await self.repository.upsert_credential_refs(
                instance.id,
                workspace_id,
                payload.credential_refs,
            )
        await self._invalidate_route_cache(workspace_id, instance.id)
        return self._connector_instance_response(instance)

    async def delete_connector_instance(self, workspace_id: UUID, connector_id: UUID) -> None:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        await self.repository.soft_delete_connector_instance(instance)
        await self._invalidate_route_cache(workspace_id, connector_id)

    async def run_health_check(
        self,
        workspace_id: UUID,
        connector_id: UUID,
    ) -> HealthCheckResponse:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        connector = get_connector(instance.connector_type.slug)
        resolved_config, secrets = await self._resolve_runtime_config(instance)
        # SECURITY: credential value is local-only, not logged
        result = await connector.health_check(resolved_config)
        error = scrub_secret_text(result.error, secrets)
        await self.repository.update_connector_instance(
            instance,
            health_status=result.status,
            health_check_error=error,
            last_health_check_at=datetime.now(UTC),
        )
        return HealthCheckResponse(status=result.status, latency_ms=result.latency_ms, error=error)

    async def test_connectivity(
        self,
        workspace_id: UUID,
        connector_id: UUID,
        payload: TestConnectivityRequest,
    ) -> TestConnectivityResponse:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        connector = get_connector(instance.connector_type.slug)
        config = payload.config if payload.config is not None else instance.config_json
        credential_refs = (
            payload.credential_refs
            if payload.credential_refs
            else {item.credential_key: item.vault_path for item in instance.credential_refs}
        )
        await self._validate_connector_config(instance.connector_type.slug, config, credential_refs)
        resolved_config, secrets = self._resolve_config(config, credential_refs)
        result = await connector.test_connectivity(resolved_config, credential_refs)
        return TestConnectivityResponse(
            connector_instance_id=instance.id,
            connector_type_slug=instance.connector_type.slug,
            result=result.model_copy(
                update={"diagnostic": scrub_secret_text(result.diagnostic, secrets)}
            ),
        )

    async def create_route(
        self,
        workspace_id: UUID,
        connector_id: UUID,
        payload: ConnectorRouteCreate,
    ) -> ConnectorRouteResponse:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        route = await self.repository.create_route(
            workspace_id=workspace_id,
            connector_instance_id=connector_id,
            name=payload.name,
            channel_pattern=payload.channel_pattern,
            sender_pattern=payload.sender_pattern,
            conditions=payload.conditions,
            target_agent_fqn=payload.target_agent_fqn,
            target_workflow_id=payload.target_workflow_id,
            priority=payload.priority,
            is_enabled=payload.is_enabled,
        )
        await self._invalidate_route_cache(workspace_id, connector_id)
        return self._route_response(route)

    async def list_routes(
        self,
        workspace_id: UUID,
        connector_id: UUID,
    ) -> ConnectorRouteListResponse:
        instance = await self.repository.get_connector_instance(connector_id, workspace_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        items, total = await self.repository.list_routes(workspace_id, connector_id)
        return ConnectorRouteListResponse(
            items=[self._route_response(item) for item in items],
            total=total,
        )

    async def get_route(self, workspace_id: UUID, route_id: UUID) -> ConnectorRouteResponse:
        route = await self.repository.get_route(route_id, workspace_id)
        if route is None:
            raise ConnectorNotFoundError(route_id)
        return self._route_response(route)

    async def update_route(
        self,
        workspace_id: UUID,
        route_id: UUID,
        payload: ConnectorRouteUpdate,
    ) -> ConnectorRouteResponse:
        route = await self.repository.get_route(route_id, workspace_id)
        if route is None:
            raise ConnectorNotFoundError(route_id)
        target_agent_fqn = route.target_agent_fqn
        target_workflow_id = route.target_workflow_id
        if "target_agent_fqn" in payload.model_fields_set:
            target_agent_fqn = payload.target_agent_fqn
        if "target_workflow_id" in payload.model_fields_set:
            target_workflow_id = payload.target_workflow_id
        if target_agent_fqn is None and target_workflow_id is None:
            raise ConnectorConfigError("At least one route target must be provided")
        await self.repository.update_route(
            route,
            name=payload.name,
            channel_pattern=payload.channel_pattern,
            sender_pattern=payload.sender_pattern,
            conditions=payload.conditions,
            target_agent_fqn=target_agent_fqn,
            target_workflow_id=target_workflow_id,
            priority=payload.priority,
            is_enabled=payload.is_enabled,
        )
        await self._invalidate_route_cache(workspace_id, route.connector_instance_id)
        return self._route_response(route)

    async def delete_route(self, workspace_id: UUID, route_id: UUID) -> None:
        route = await self.repository.get_route(route_id, workspace_id)
        if route is None:
            raise ConnectorNotFoundError(route_id)
        await self.repository.delete_route(route)
        await self._invalidate_route_cache(workspace_id, route.connector_instance_id)

    async def verify_webhook_request(
        self,
        connector_id: UUID,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> None:
        instance = await self.repository.get_connector_instance_public(connector_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        resolved_config, _secrets = await self._resolve_runtime_config(instance)
        assert_webhook_signature(
            str(resolved_config["signing_secret"]),
            raw_body,
            headers.get("x-hub-signature-256"),
        )

    async def verify_slack_request(
        self,
        connector_id: UUID,
        raw_body: bytes,
        headers: dict[str, str],
    ) -> None:
        instance = await self.repository.get_connector_instance_public(connector_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        resolved_config, _secrets = await self._resolve_runtime_config(instance)
        assert_slack_signature(
            str(resolved_config["signing_secret"]),
            raw_body,
            headers.get("x-slack-signature"),
            headers.get("x-slack-request-timestamp"),
        )

    async def process_inbound(
        self,
        connector_id: UUID,
        *,
        payload: dict[str, Any],
        raw_body: bytes,
        headers: dict[str, str],
        path: str | None = None,
    ) -> dict[str, Any]:
        if len(raw_body) > self.settings.connectors.max_payload_size_bytes:
            raise ConnectorConfigError("Inbound payload exceeds the configured size limit.")
        instance = await self.repository.get_connector_instance_public(connector_id)
        if instance is None:
            raise ConnectorNotFoundError(connector_id)
        if instance.status is ConnectorInstanceStatus.disabled:
            raise ConnectorDisabledError(connector_id)
        resolved_config, _secrets = await self._resolve_runtime_config(instance)
        if (
            instance.connector_type.slug == "slack"
            and payload.get("type") == "url_verification"
            and isinstance(payload.get("challenge"), str)
        ):
            return {"ok": True, "challenge": payload["challenge"]}
        connector = get_connector(instance.connector_type.slug)
        inbound = await connector.normalize_inbound(
            connector_instance_id=instance.id,
            workspace_id=instance.workspace_id,
            config=resolved_config,
            payload=payload,
            raw_body=raw_body if raw_body else payload_to_json(payload),
            headers=headers,
            path=path,
        )
        matched = await self.match_route(instance.workspace_id, instance.id, inbound)
        if matched is None:
            self.logger.info(
                "Unrouted connector inbound message",
                extra={
                    "connector_instance_id": str(instance.id),
                    "workspace_id": str(instance.workspace_id),
                },
            )
            return {"ok": True, "routed": False}
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=instance.workspace_id,
        )
        route_id = UUID(str(matched["id"])) if matched.get("id") else None
        target_workflow_id = (
            UUID(str(matched["target_workflow_id"])) if matched.get("target_workflow_id") else None
        )
        await publish_connector_ingress(
            self.producer,
            ConnectorIngressPayload(
                connector_instance_id=instance.id,
                workspace_id=instance.workspace_id,
                connector_type_slug=instance.connector_type.slug,
                route_id=route_id,
                target_agent_fqn=matched.get("target_agent_fqn"),
                target_workflow_id=target_workflow_id,
                sender_identity=inbound.sender_identity,
                channel=inbound.channel,
                content_text=inbound.content_text,
                content_structured=inbound.content_structured,
                timestamp=inbound.timestamp,
                message_id=inbound.message_id,
                original_payload=inbound.original_payload,
            ),
            correlation,
            topic=self.settings.connectors.ingress_topic,
        )
        return {"ok": True, "routed": True, "route_id": matched["id"]}

    async def create_delivery(
        self,
        workspace_id: UUID,
        payload: OutboundDeliveryCreate,
    ) -> OutboundDeliveryResponse:
        instance = await self.repository.get_connector_instance(
            payload.connector_instance_id,
            workspace_id,
        )
        if instance is None:
            raise ConnectorNotFoundError(payload.connector_instance_id)
        if instance.status is ConnectorInstanceStatus.disabled:
            raise ConnectorDisabledError(instance.id)
        delivery = await self.repository.create_outbound_delivery(
            workspace_id=workspace_id,
            connector_instance_id=payload.connector_instance_id,
            destination=payload.destination,
            content={
                "content_text": payload.content_text,
                "content_structured": payload.content_structured,
                "metadata": payload.metadata,
            },
            priority=payload.priority,
            max_attempts=payload.max_attempts,
            source_interaction_id=payload.source_interaction_id,
            source_execution_id=payload.source_execution_id,
        )
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            interaction_id=payload.source_interaction_id,
            execution_id=payload.source_execution_id,
        )
        await publish_delivery_requested(
            self.producer,
            ConnectorDeliveryRequestPayload(
                delivery_id=delivery.id,
                connector_instance_id=delivery.connector_instance_id,
                workspace_id=delivery.workspace_id,
            ),
            correlation,
            topic=self.settings.connectors.delivery_topic,
        )
        return self._delivery_response(delivery)

    async def get_delivery(
        self,
        workspace_id: UUID,
        delivery_id: UUID,
    ) -> OutboundDeliveryResponse:
        delivery = await self.repository.get_outbound_delivery(delivery_id, workspace_id)
        if delivery is None:
            raise ConnectorNotFoundError(delivery_id)
        return self._delivery_response(delivery)

    async def list_deliveries(
        self,
        workspace_id: UUID,
        connector_instance_id: UUID | None = None,
    ) -> OutboundDeliveryListResponse:
        items, total = await self.repository.list_outbound_deliveries(
            workspace_id,
            connector_instance_id,
        )
        return OutboundDeliveryListResponse(
            items=[self._delivery_response(item) for item in items],
            total=total,
        )

    async def execute_delivery(self, delivery_id: UUID) -> OutboundDeliveryResponse:
        delivery = await self.repository.get_outbound_delivery(delivery_id)
        if delivery is None:
            raise ConnectorNotFoundError(delivery_id)
        if delivery.status in {DeliveryStatus.delivered, DeliveryStatus.dead_lettered}:
            return self._delivery_response(delivery)
        instance = await self.repository.get_connector_instance_public(
            delivery.connector_instance_id
        )
        if instance is None:
            raise ConnectorNotFoundError(delivery.connector_instance_id)
        if instance.status is ConnectorInstanceStatus.disabled:
            raise ConnectorDisabledError(instance.id)
        connector = get_connector(instance.connector_type.slug)
        resolved_config, secrets = await self._resolve_runtime_config(instance)
        attempt = delivery.attempt_count + 1
        request = DeliveryRequest(
            connector_instance_id=delivery.connector_instance_id,
            workspace_id=delivery.workspace_id,
            destination=delivery.destination,
            content_text=delivery.content_json.get("content_text"),
            content_structured=delivery.content_json.get("content_structured"),
            metadata=dict(delivery.content_json.get("metadata", {})),
        )
        try:
            await self.repository.update_delivery_status(
                delivery,
                status=DeliveryStatus.in_flight,
            )
            # SECURITY: credential value is local-only, not logged
            await connector.deliver_outbound(request, resolved_config)
            await self.repository.update_delivery_status(
                delivery,
                status=DeliveryStatus.delivered,
                attempt_count=attempt,
                delivered_at=datetime.now(UTC),
            )
            await self.repository.increment_connector_metrics(
                instance.id,
                sent_delta=1,
            )
            await publish_delivery_succeeded(
                self.producer,
                ConnectorDeliverySucceededPayload(
                    delivery_id=delivery.id,
                    connector_instance_id=delivery.connector_instance_id,
                    workspace_id=delivery.workspace_id,
                    delivered_at=delivery.delivered_at or datetime.now(UTC),
                ),
                CorrelationContext(
                    correlation_id=uuid4(),
                    workspace_id=delivery.workspace_id,
                    interaction_id=delivery.source_interaction_id,
                    execution_id=delivery.source_execution_id,
                ),
                topic=self.settings.connectors.delivery_topic,
            )
            return self._delivery_response(delivery)
        except DeliveryPermanentError as exc:
            return await self._dead_letter_delivery(
                delivery,
                instance.id,
                attempt,
                str(exc),
                secrets,
            )
        except DeliveryError as exc:
            return await self._handle_failed_delivery(
                delivery,
                instance.id,
                attempt,
                str(exc),
                secrets,
            )
        except Exception as exc:
            return await self._handle_failed_delivery(
                delivery,
                instance.id,
                attempt,
                str(exc),
                secrets,
            )

    async def retry_pending_deliveries(self, limit: int = 100) -> None:
        for delivery in await self.repository.get_pending_retries(limit=limit):
            await self.execute_delivery(delivery.id)

    async def list_dead_letter_entries(
        self,
        workspace_id: UUID,
        *,
        connector_instance_id: UUID | None = None,
        resolution_status: DeadLetterResolution | None = None,
    ) -> DeadLetterEntryListResponse:
        items, total = await self.repository.list_dead_letter_entries(
            workspace_id,
            connector_instance_id=connector_instance_id,
            resolution_status=resolution_status,
        )
        return DeadLetterEntryListResponse(
            items=[self._dead_letter_response(item) for item in items],
            total=total,
        )

    async def get_dead_letter_entry(
        self,
        workspace_id: UUID,
        entry_id: UUID,
    ) -> DeadLetterEntryResponse:
        entry = await self.repository.get_dead_letter_entry(entry_id, workspace_id)
        if entry is None:
            raise DeadLetterNotFoundError(entry_id)
        return self._dead_letter_response(entry)

    async def redeliver_dead_letter(
        self,
        workspace_id: UUID,
        entry_id: UUID,
        payload: DeadLetterRedeliverRequest,
    ) -> OutboundDeliveryResponse:
        entry = await self.repository.get_dead_letter_entry(entry_id, workspace_id)
        if entry is None:
            raise DeadLetterNotFoundError(entry_id)
        if entry.resolution_status is not DeadLetterResolution.pending:
            raise DeadLetterAlreadyResolvedError(entry_id)
        delivery = entry.outbound_delivery
        new_delivery = await self.repository.create_outbound_delivery(
            workspace_id=workspace_id,
            connector_instance_id=entry.connector_instance_id,
            destination=delivery.destination,
            content=delivery.content_json,
            priority=delivery.priority,
            max_attempts=delivery.max_attempts,
            source_interaction_id=delivery.source_interaction_id,
            source_execution_id=delivery.source_execution_id,
        )
        await self.repository.update_dead_letter_resolution(
            entry,
            resolution_status=DeadLetterResolution.redelivered,
            resolved_at=datetime.now(UTC),
            resolution_note=payload.resolution_note,
        )
        await self._update_dead_letter_depth(workspace_id, delta=-1)
        correlation = CorrelationContext(
            correlation_id=uuid4(),
            workspace_id=workspace_id,
            interaction_id=delivery.source_interaction_id,
            execution_id=delivery.source_execution_id,
        )
        await publish_delivery_requested(
            self.producer,
            ConnectorDeliveryRequestPayload(
                delivery_id=new_delivery.id,
                connector_instance_id=new_delivery.connector_instance_id,
                workspace_id=new_delivery.workspace_id,
            ),
            correlation,
            topic=self.settings.connectors.delivery_topic,
        )
        return self._delivery_response(new_delivery)

    async def discard_dead_letter(
        self,
        workspace_id: UUID,
        entry_id: UUID,
        payload: DeadLetterDiscardRequest,
    ) -> DeadLetterEntryResponse:
        entry = await self.repository.get_dead_letter_entry(entry_id, workspace_id)
        if entry is None:
            raise DeadLetterNotFoundError(entry_id)
        if entry.resolution_status is not DeadLetterResolution.pending:
            raise DeadLetterAlreadyResolvedError(entry_id)
        archive_key = f"{workspace_id}/{entry.id}.json"
        archive_payload = {
            "entry_id": str(entry.id),
            "workspace_id": str(workspace_id),
            "connector_instance_id": str(entry.connector_instance_id),
            "delivery": self._delivery_response(entry.outbound_delivery).model_dump(mode="json"),
        }
        await self.object_storage.create_bucket_if_not_exists(
            self.settings.connectors.dead_letter_bucket
        )
        await self.object_storage.upload_object(
            self.settings.connectors.dead_letter_bucket,
            archive_key,
            json.dumps(archive_payload).encode("utf-8"),
            content_type="application/json",
        )
        await self.repository.update_dead_letter_resolution(
            entry,
            resolution_status=DeadLetterResolution.discarded,
            resolved_at=datetime.now(UTC),
            resolution_note=payload.resolution_note,
            archive_path=archive_key,
        )
        await self._update_dead_letter_depth(workspace_id, delta=-1)
        return self._dead_letter_response(entry)

    async def poll_email_connectors(self) -> None:
        instances = await self.repository.list_enabled_connector_instances_by_type("email")
        for instance in instances:
            try:
                await self._poll_email_connector(instance)
            except Exception as exc:  # pragma: no cover - defensive worker logging
                self.logger.warning(
                    "Email polling failed for connector %s: %s",
                    instance.id,
                    exc,
                )

    async def match_route(
        self,
        workspace_id: UUID,
        connector_instance_id: UUID,
        inbound: InboundMessage,
    ) -> dict[str, Any] | None:
        routes = await self._load_routes_for_matching(workspace_id, connector_instance_id)
        for route in routes:
            if not route.get("is_enabled", True):
                continue
            channel_pattern = route.get("channel_pattern")
            if channel_pattern and not fnmatch(inbound.channel, str(channel_pattern)):
                continue
            sender_pattern = route.get("sender_pattern")
            if sender_pattern and not fnmatch(inbound.sender_identity, str(sender_pattern)):
                continue
            conditions = route.get("conditions", {})
            if isinstance(conditions, dict):
                if not self._conditions_match(conditions, inbound):
                    continue
            return route
        return None

    async def _validate_connector_config(
        self,
        type_slug: str,
        config: dict[str, Any],
        credential_refs: dict[str, str],
    ) -> None:
        refs_in_config = self._extract_config_refs(config)
        missing = sorted(refs_in_config.difference(credential_refs))
        if missing:
            raise ConnectorConfigError(f"Missing credential_refs for keys: {', '.join(missing)}.")
        connector = get_connector(type_slug)
        await connector.validate_config(config, credential_refs)

    async def _resolve_runtime_config(
        self,
        instance: ConnectorInstance,
    ) -> tuple[dict[str, Any], list[str]]:
        refs = {item.credential_key: item.vault_path for item in instance.credential_refs}
        return self._resolve_config(instance.config_json, refs)

    def _resolve_config(
        self,
        config: dict[str, Any],
        refs: dict[str, str],
    ) -> tuple[dict[str, Any], list[str]]:
        secrets: list[str] = []

        def _resolve(value: Any) -> Any:
            if isinstance(value, dict):
                if "$ref" in value:
                    key = str(value["$ref"])
                    secret = resolve_connector_secret(self.vault, refs[key], key)
                    secrets.append(secret)
                    return secret
                return {name: _resolve(item) for name, item in value.items()}
            if isinstance(value, list):
                return [_resolve(item) for item in value]
            return value

        resolved = _resolve(config)
        if not isinstance(resolved, dict):
            raise ConnectorConfigError("Connector config must resolve to an object.")
        return resolved, secrets

    async def _invalidate_route_cache(self, workspace_id: UUID, connector_id: UUID) -> None:
        await self.redis_client.delete(self._route_cache_key(workspace_id, connector_id))

    async def _load_routes_for_matching(
        self,
        workspace_id: UUID,
        connector_instance_id: UUID,
    ) -> list[dict[str, Any]]:
        cache_key = self._route_cache_key(workspace_id, connector_instance_id)
        cached = await self.redis_client.get(cache_key)
        if cached is not None:
            decoded = json.loads(cached.decode("utf-8"))
            if not isinstance(decoded, list):
                return []
            return [item for item in decoded if isinstance(item, dict)]
        routes = await self.repository.get_routes_for_instance(connector_instance_id, workspace_id)
        payload = [self._route_to_cache(item) for item in routes]
        await self.redis_client.set(
            cache_key,
            json.dumps(payload).encode("utf-8"),
            ttl=self.settings.connectors.route_cache_ttl_seconds,
        )
        return payload

    def _conditions_match(self, conditions: dict[str, Any], inbound: InboundMessage) -> bool:
        for key, expected in conditions.items():
            actual = inbound.metadata.get(key)
            if actual is None:
                actual = inbound.original_payload.get(key)
            if actual != expected:
                return False
        return True

    async def _handle_failed_delivery(
        self,
        delivery: OutboundDelivery,
        connector_instance_id: UUID,
        attempt: int,
        error: str,
        secrets: list[str],
    ) -> OutboundDeliveryResponse:
        scrubbed = scrub_secret_text(error, secrets) or "Delivery failed."
        await self.repository.append_error_history(
            delivery,
            {
                "attempt": attempt,
                "error": scrubbed,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
        if attempt >= delivery.max_attempts:
            return await self._dead_letter_delivery(
                delivery,
                connector_instance_id,
                attempt,
                scrubbed,
                secrets,
            )
        retry_at = compute_next_retry_at(attempt)
        await self.repository.update_delivery_status(
            delivery,
            status=DeliveryStatus.failed,
            attempt_count=attempt,
            next_retry_at=retry_at,
        )
        await self.repository.increment_connector_metrics(
            connector_instance_id,
            failed_delta=1,
            retried_delta=1,
        )
        await publish_delivery_failed(
            self.producer,
            ConnectorDeliveryFailedPayload(
                delivery_id=delivery.id,
                connector_instance_id=delivery.connector_instance_id,
                workspace_id=delivery.workspace_id,
                attempt_count=attempt,
                retry_at=retry_at,
                error=scrubbed,
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=delivery.workspace_id,
                interaction_id=delivery.source_interaction_id,
                execution_id=delivery.source_execution_id,
            ),
            topic=self.settings.connectors.delivery_topic,
        )
        return self._delivery_response(delivery)

    async def _dead_letter_delivery(
        self,
        delivery: OutboundDelivery,
        connector_instance_id: UUID,
        attempt: int,
        error: str,
        secrets: list[str],
    ) -> OutboundDeliveryResponse:
        scrubbed = scrub_secret_text(error, secrets) or "Delivery failed."
        if not delivery.error_history or delivery.error_history[-1].get("attempt") != attempt:
            await self.repository.append_error_history(
                delivery,
                {
                    "attempt": attempt,
                    "error": scrubbed,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
            )
        await self.repository.update_delivery_status(
            delivery,
            status=DeliveryStatus.dead_lettered,
            attempt_count=attempt,
            next_retry_at=None,
        )
        entry = await self.repository.create_dead_letter_entry(
            workspace_id=delivery.workspace_id,
            outbound_delivery_id=delivery.id,
            connector_instance_id=delivery.connector_instance_id,
            dead_lettered_at=datetime.now(UTC),
        )
        await self.repository.increment_connector_metrics(
            connector_instance_id,
            failed_delta=1,
            dead_lettered_delta=1,
        )
        await self._update_dead_letter_depth(delivery.workspace_id, delta=1)
        await publish_dead_lettered(
            self.producer,
            ConnectorDeadLetteredPayload(
                delivery_id=delivery.id,
                dead_letter_entry_id=entry.id,
                connector_instance_id=delivery.connector_instance_id,
                workspace_id=delivery.workspace_id,
                attempt_count=attempt,
                error=scrubbed,
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=delivery.workspace_id,
                interaction_id=delivery.source_interaction_id,
                execution_id=delivery.source_execution_id,
            ),
            topic=self.settings.connectors.delivery_topic,
        )
        delivery.dead_letter_entry = entry
        return self._delivery_response(delivery)

    async def _update_dead_letter_depth(self, workspace_id: UUID, *, delta: int) -> None:
        key = self._dead_letter_depth_key(workspace_id)
        current_bytes = await self.redis_client.get(key)
        current = int(current_bytes.decode("utf-8")) if current_bytes is not None else 0
        next_value = max(current + delta, 0)
        await self.redis_client.set(key, str(next_value).encode("utf-8"))

    async def _poll_email_connector(self, instance: ConnectorInstance) -> None:
        aioimaplib = __import__("aioimaplib")
        connector = get_connector("email")
        resolved_config, _secrets = await self._resolve_runtime_config(instance)
        client = aioimaplib.IMAP4_SSL(
            resolved_config["imap_host"],
            int(resolved_config["imap_port"]),
        )
        await client.wait_hello_from_server()
        try:
            await client.login(resolved_config["email_address"], resolved_config["imap_password"])
            await client.select(resolved_config.get("inbox_folder", "INBOX"))
            search_response = await client.search("UNSEEN")
            for message_id in self._parse_search_ids(search_response):
                fetch_response = await client.fetch(message_id, "(RFC822)")
                raw_message = self._extract_email_payload(fetch_response)
                if raw_message is None:
                    continue
                inbound = await connector.normalize_inbound(
                    connector_instance_id=instance.id,
                    workspace_id=instance.workspace_id,
                    config=resolved_config,
                    payload={"source": "imap", "message_id": message_id},
                    raw_body=raw_message,
                    headers={},
                )
                route = await self.match_route(instance.workspace_id, instance.id, inbound)
                if route is not None:
                    await publish_connector_ingress(
                        self.producer,
                        ConnectorIngressPayload(
                            connector_instance_id=instance.id,
                            workspace_id=instance.workspace_id,
                            connector_type_slug="email",
                            route_id=UUID(str(route["id"])),
                            target_agent_fqn=route.get("target_agent_fqn"),
                            target_workflow_id=(
                                UUID(str(route["target_workflow_id"]))
                                if route.get("target_workflow_id")
                                else None
                            ),
                            sender_identity=inbound.sender_identity,
                            channel=inbound.channel,
                            content_text=inbound.content_text,
                            content_structured=inbound.content_structured,
                            timestamp=inbound.timestamp,
                            message_id=inbound.message_id,
                            original_payload=inbound.original_payload,
                        ),
                        CorrelationContext(
                            correlation_id=uuid4(),
                            workspace_id=instance.workspace_id,
                        ),
                        topic=self.settings.connectors.ingress_topic,
                    )
                await client.store(message_id, "+FLAGS", "\\Seen")
        finally:
            await client.logout()

    def _parse_search_ids(self, response: Any) -> list[str]:
        if isinstance(response, tuple) and len(response) >= 2:
            data = response[1]
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, bytes):
                        return [value for value in item.decode("utf-8").split() if value]
                    if isinstance(item, str):
                        return [value for value in item.split() if value]
        return []

    def _extract_email_payload(self, response: Any) -> bytes | None:
        if isinstance(response, tuple) and len(response) >= 2:
            data = response[1]
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, bytes) and b"RFC822" not in item:
                        return item
        return None

    def _connector_type_response(self, item: Any) -> ConnectorTypeResponse:
        return ConnectorTypeResponse.model_validate(item, from_attributes=True)

    def _connector_instance_response(self, item: ConnectorInstance) -> ConnectorInstanceResponse:
        return ConnectorInstanceResponse(
            id=item.id,
            workspace_id=item.workspace_id,
            connector_type_id=item.connector_type_id,
            connector_type_slug=item.connector_type.slug,
            name=item.name,
            config=item.config_json,
            status=item.status,
            health_status=item.health_status,
            last_health_check_at=item.last_health_check_at,
            health_check_error=item.health_check_error,
            messages_sent=item.messages_sent,
            messages_failed=item.messages_failed,
            messages_retried=item.messages_retried,
            messages_dead_lettered=item.messages_dead_lettered,
            credential_keys=[ref.credential_key for ref in item.credential_refs],
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _route_response(self, item: ConnectorRoute) -> ConnectorRouteResponse:
        return ConnectorRouteResponse(
            id=item.id,
            workspace_id=item.workspace_id,
            connector_instance_id=item.connector_instance_id,
            name=item.name,
            channel_pattern=item.channel_pattern,
            sender_pattern=item.sender_pattern,
            conditions=item.conditions_json,
            target_agent_fqn=item.target_agent_fqn,
            target_workflow_id=item.target_workflow_id,
            priority=item.priority,
            is_enabled=item.is_enabled,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _delivery_response(self, item: OutboundDelivery) -> OutboundDeliveryResponse:
        return OutboundDeliveryResponse(
            id=item.id,
            workspace_id=item.workspace_id,
            connector_instance_id=item.connector_instance_id,
            destination=item.destination,
            content_text=item.content_json.get("content_text"),
            content_structured=item.content_json.get("content_structured"),
            metadata=dict(item.content_json.get("metadata", {})),
            priority=item.priority,
            status=item.status,
            attempt_count=item.attempt_count,
            max_attempts=item.max_attempts,
            next_retry_at=item.next_retry_at,
            delivered_at=item.delivered_at,
            error_history=item.error_history,
            source_interaction_id=item.source_interaction_id,
            source_execution_id=item.source_execution_id,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _dead_letter_response(self, item: DeadLetterEntry) -> DeadLetterEntryResponse:
        return DeadLetterEntryResponse(
            id=item.id,
            workspace_id=item.workspace_id,
            outbound_delivery_id=item.outbound_delivery_id,
            connector_instance_id=item.connector_instance_id,
            resolution_status=item.resolution_status,
            dead_lettered_at=item.dead_lettered_at,
            resolved_at=item.resolved_at,
            resolution_note=item.resolution_note,
            archive_path=item.archive_path,
            error_history=item.outbound_delivery.error_history,
            delivery=self._delivery_response(item.outbound_delivery),
        )

    def _route_cache_key(self, workspace_id: UUID, connector_id: UUID) -> str:
        return f"connector:routes:{workspace_id}:{connector_id}"

    def _dead_letter_depth_key(self, workspace_id: UUID) -> str:
        return f"connector:dead-letter-depth:{workspace_id}"

    def _extract_config_refs(self, config: Any) -> set[str]:
        refs: set[str] = set()
        if isinstance(config, dict):
            if "$ref" in config and isinstance(config["$ref"], str):
                refs.add(config["$ref"])
            for value in config.values():
                refs.update(self._extract_config_refs(value))
        elif isinstance(config, list):
            for item in config:
                refs.update(self._extract_config_refs(item))
        return refs

    def _route_to_cache(self, route: ConnectorRoute) -> dict[str, Any]:
        return {
            "id": str(route.id),
            "channel_pattern": route.channel_pattern,
            "sender_pattern": route.sender_pattern,
            "conditions": route.conditions_json,
            "target_agent_fqn": route.target_agent_fqn,
            "target_workflow_id": (
                str(route.target_workflow_id) if route.target_workflow_id is not None else None
            ),
            "priority": route.priority,
            "is_enabled": route.is_enabled,
        }
