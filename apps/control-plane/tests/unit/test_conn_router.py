from __future__ import annotations

from datetime import UTC, datetime
from platform.connectors.dependencies import get_connectors_service
from platform.connectors.models import ConnectorHealthStatus, ConnectorInstanceStatus, DeadLetterResolution, DeliveryStatus
from platform.connectors.router import router
from platform.connectors.schemas import (
    ConnectorInstanceListResponse,
    ConnectorInstanceResponse,
    ConnectorRouteListResponse,
    ConnectorRouteResponse,
    ConnectorTypeListResponse,
    ConnectorTypeResponse,
    DeadLetterEntryListResponse,
    DeadLetterEntryResponse,
    HealthCheckResponse,
    OutboundDeliveryListResponse,
    OutboundDeliveryResponse,
)
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from platform.common.dependencies import get_current_user


def _connector_instance_response(workspace_id, connector_id) -> ConnectorInstanceResponse:
    now = datetime.now(UTC)
    return ConnectorInstanceResponse(
        id=connector_id,
        workspace_id=workspace_id,
        connector_type_id=uuid4(),
        connector_type_slug="slack",
        name="Slack",
        config={"bot_token": {"$ref": "bot_token"}},
        status=ConnectorInstanceStatus.enabled,
        health_status=ConnectorHealthStatus.healthy,
        last_health_check_at=None,
        health_check_error=None,
        messages_sent=1,
        messages_failed=0,
        messages_retried=0,
        messages_dead_lettered=0,
        credential_keys=["bot_token"],
        created_at=now,
        updated_at=now,
    )


def _route_response(workspace_id, connector_id, route_id) -> ConnectorRouteResponse:
    now = datetime.now(UTC)
    return ConnectorRouteResponse(
        id=route_id,
        workspace_id=workspace_id,
        connector_instance_id=connector_id,
        name="Route",
        channel_pattern="#support*",
        sender_pattern=None,
        conditions={},
        target_agent_fqn="ops:triage",
        target_workflow_id=None,
        priority=10,
        is_enabled=True,
        created_at=now,
        updated_at=now,
    )


def _delivery_response(workspace_id, connector_id, delivery_id) -> OutboundDeliveryResponse:
    now = datetime.now(UTC)
    return OutboundDeliveryResponse(
        id=delivery_id,
        workspace_id=workspace_id,
        connector_instance_id=connector_id,
        destination="C123",
        content_text="hello",
        content_structured=None,
        metadata={},
        priority=1,
        status=DeliveryStatus.delivered,
        attempt_count=1,
        max_attempts=3,
        next_retry_at=None,
        delivered_at=now,
        error_history=[],
        source_interaction_id=None,
        source_execution_id=None,
        created_at=now,
        updated_at=now,
    )


def _dead_letter_response(workspace_id, connector_id, delivery_id, entry_id) -> DeadLetterEntryResponse:
    now = datetime.now(UTC)
    return DeadLetterEntryResponse(
        id=entry_id,
        workspace_id=workspace_id,
        outbound_delivery_id=delivery_id,
        connector_instance_id=connector_id,
        resolution_status=DeadLetterResolution.pending,
        dead_lettered_at=now,
        resolved_at=None,
        resolution_note=None,
        archive_path=None,
        error_history=[{"error": "boom"}],
        delivery=_delivery_response(workspace_id, connector_id, delivery_id),
    )


class ServiceStub:
    def __init__(self, workspace_id, connector_id, route_id, delivery_id, entry_id) -> None:
        self.workspace_id = workspace_id
        self.connector_id = connector_id
        self.route_id = route_id
        self.delivery_id = delivery_id
        self.entry_id = entry_id
        self.calls: list[tuple[str, tuple, dict]] = []

    async def list_connector_types(self):
        self.calls.append(("list_connector_types", (), {}))
        return ConnectorTypeListResponse(
            items=[
                ConnectorTypeResponse(
                    id=uuid4(),
                    slug="slack",
                    display_name="Slack",
                    description="Slack",
                    config_schema={},
                    is_deprecated=False,
                    deprecated_at=None,
                    deprecation_note=None,
                )
            ],
            total=1,
        )

    async def get_connector_type(self, type_slug: str):
        self.calls.append(("get_connector_type", (type_slug,), {}))
        return (await self.list_connector_types()).items[0]

    async def create_connector_instance(self, workspace_id, payload):
        self.calls.append(("create_connector_instance", (workspace_id, payload), {}))
        return _connector_instance_response(workspace_id, self.connector_id)

    async def list_connector_instances(self, workspace_id):
        self.calls.append(("list_connector_instances", (workspace_id,), {}))
        return ConnectorInstanceListResponse(
            items=[_connector_instance_response(workspace_id, self.connector_id)],
            total=1,
        )

    async def get_connector_instance(self, workspace_id, connector_id):
        self.calls.append(("get_connector_instance", (workspace_id, connector_id), {}))
        return _connector_instance_response(workspace_id, connector_id)

    async def update_connector_instance(self, workspace_id, connector_id, payload):
        self.calls.append(("update_connector_instance", (workspace_id, connector_id, payload), {}))
        return _connector_instance_response(workspace_id, connector_id)

    async def delete_connector_instance(self, workspace_id, connector_id):
        self.calls.append(("delete_connector_instance", (workspace_id, connector_id), {}))

    async def run_health_check(self, workspace_id, connector_id):
        self.calls.append(("run_health_check", (workspace_id, connector_id), {}))
        return HealthCheckResponse(status=ConnectorHealthStatus.healthy, latency_ms=5.0, error=None)

    async def create_route(self, workspace_id, connector_id, payload):
        self.calls.append(("create_route", (workspace_id, connector_id, payload), {}))
        return _route_response(workspace_id, connector_id, self.route_id)

    async def list_routes(self, workspace_id, connector_id):
        self.calls.append(("list_routes", (workspace_id, connector_id), {}))
        return ConnectorRouteListResponse(
            items=[_route_response(workspace_id, connector_id, self.route_id)],
            total=1,
        )

    async def get_route(self, workspace_id, route_id):
        self.calls.append(("get_route", (workspace_id, route_id), {}))
        return _route_response(workspace_id, self.connector_id, route_id)

    async def update_route(self, workspace_id, route_id, payload):
        self.calls.append(("update_route", (workspace_id, route_id, payload), {}))
        return _route_response(workspace_id, self.connector_id, route_id)

    async def delete_route(self, workspace_id, route_id):
        self.calls.append(("delete_route", (workspace_id, route_id), {}))

    async def verify_webhook_request(self, connector_instance_id, raw_body, headers):
        self.calls.append(("verify_webhook_request", (connector_instance_id, raw_body, headers), {}))

    async def verify_slack_request(self, connector_instance_id, raw_body, headers):
        self.calls.append(("verify_slack_request", (connector_instance_id, raw_body, headers), {}))

    async def process_inbound(self, connector_instance_id, **kwargs):
        self.calls.append(("process_inbound", (connector_instance_id,), kwargs))
        return {"ok": True, "routed": True, "route_id": str(self.route_id)}

    async def create_delivery(self, workspace_id, payload):
        self.calls.append(("create_delivery", (workspace_id, payload), {}))
        return _delivery_response(workspace_id, self.connector_id, self.delivery_id)

    async def list_deliveries(self, workspace_id, connector_instance_id=None):
        self.calls.append(("list_deliveries", (workspace_id,), {"connector_instance_id": connector_instance_id}))
        return OutboundDeliveryListResponse(
            items=[_delivery_response(workspace_id, self.connector_id, self.delivery_id)],
            total=1,
        )

    async def get_delivery(self, workspace_id, delivery_id):
        self.calls.append(("get_delivery", (workspace_id, delivery_id), {}))
        return _delivery_response(workspace_id, self.connector_id, delivery_id)

    async def list_dead_letter_entries(self, workspace_id, **kwargs):
        self.calls.append(("list_dead_letter_entries", (workspace_id,), kwargs))
        return DeadLetterEntryListResponse(
            items=[_dead_letter_response(workspace_id, self.connector_id, self.delivery_id, self.entry_id)],
            total=1,
        )

    async def get_dead_letter_entry(self, workspace_id, entry_id):
        self.calls.append(("get_dead_letter_entry", (workspace_id, entry_id), {}))
        return _dead_letter_response(workspace_id, self.connector_id, self.delivery_id, entry_id)

    async def redeliver_dead_letter(self, workspace_id, entry_id, payload):
        self.calls.append(("redeliver_dead_letter", (workspace_id, entry_id, payload), {}))
        return _delivery_response(workspace_id, self.connector_id, self.delivery_id)

    async def discard_dead_letter(self, workspace_id, entry_id, payload):
        self.calls.append(("discard_dead_letter", (workspace_id, entry_id, payload), {}))
        return _dead_letter_response(workspace_id, self.connector_id, self.delivery_id, entry_id)


@pytest.mark.asyncio
async def test_connectors_router_covers_all_endpoints() -> None:
    workspace_id = uuid4()
    connector_id = uuid4()
    route_id = uuid4()
    delivery_id = uuid4()
    entry_id = uuid4()
    service = ServiceStub(workspace_id, connector_id, route_id, delivery_id, entry_id)

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: {"sub": "user"}
    app.dependency_overrides[get_connectors_service] = lambda: service

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        assert (await client.get("/api/v1/connectors/types")).status_code == 200
        assert (await client.get("/api/v1/connectors/types/slack")).status_code == 200

        create_payload = {
            "connector_type_slug": "slack",
            "name": "Slack",
            "config": {"bot_token": {"$ref": "bot_token"}},
            "credential_refs": {"bot_token": "vault/bot_token"},
        }
        assert (
            await client.post(f"/api/v1/workspaces/{workspace_id}/connectors", json=create_payload)
        ).status_code == 201
        assert (await client.get(f"/api/v1/workspaces/{workspace_id}/connectors")).status_code == 200
        assert (
            await client.get(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}")
        ).status_code == 200
        assert (
            await client.put(
                f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}",
                json={"name": "Updated"},
            )
        ).status_code == 200
        assert (
            await client.delete(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}")
        ).status_code == 204
        assert (
            await client.post(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}/health-check")
        ).status_code == 200

        route_payload = {"name": "Route", "target_agent_fqn": "ops:triage"}
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}/routes",
                json=route_payload,
            )
        ).status_code == 201
        assert (
            await client.get(f"/api/v1/workspaces/{workspace_id}/connectors/{connector_id}/routes")
        ).status_code == 200
        assert (await client.get(f"/api/v1/workspaces/{workspace_id}/routes/{route_id}")).status_code == 200
        assert (
            await client.put(
                f"/api/v1/workspaces/{workspace_id}/routes/{route_id}",
                json={"target_agent_fqn": "ops:lead"},
            )
        ).status_code == 200
        assert (await client.delete(f"/api/v1/workspaces/{workspace_id}/routes/{route_id}")).status_code == 204

        assert (
            await client.post(
                f"/api/v1/inbound/slack/{connector_id}",
                json={"type": "event_callback"},
                headers={
                    "x-slack-signature": "sig",
                    "x-slack-request-timestamp": "1",
                },
            )
        ).status_code == 200
        assert (
            await client.post(f"/api/v1/inbound/telegram/{connector_id}", json={"update_id": 1})
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/inbound/webhook/{connector_id}",
                json={"event": "ok"},
                headers={"x-hub-signature-256": "sha256=sig"},
            )
        ).status_code == 200

        delivery_payload = {
            "connector_instance_id": str(connector_id),
            "destination": "C123",
            "content_text": "hello",
        }
        assert (
            await client.post(f"/api/v1/workspaces/{workspace_id}/deliveries", json=delivery_payload)
        ).status_code == 201
        assert (
            await client.get(
                f"/api/v1/workspaces/{workspace_id}/deliveries",
                params={"connector_instance_id": str(connector_id)},
            )
        ).status_code == 200
        assert (
            await client.get(f"/api/v1/workspaces/{workspace_id}/deliveries/{delivery_id}")
        ).status_code == 200

        assert (
            await client.get(
                f"/api/v1/workspaces/{workspace_id}/dead-letter",
                params={
                    "connector_instance_id": str(connector_id),
                    "resolution_status": DeadLetterResolution.pending.value,
                },
            )
        ).status_code == 200
        assert (
            await client.get(f"/api/v1/workspaces/{workspace_id}/dead-letter/{entry_id}")
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/dead-letter/{entry_id}/redeliver",
                json={"resolution_note": "retry"},
            )
        ).status_code == 200
        assert (
            await client.post(
                f"/api/v1/workspaces/{workspace_id}/dead-letter/{entry_id}/discard",
                json={"resolution_note": "archive"},
            )
        ).status_code == 200

    called = {name for name, _, _ in service.calls}
    assert "verify_slack_request" in called
    assert "verify_webhook_request" in called
    assert "process_inbound" in called
    assert "discard_dead_letter" in called
