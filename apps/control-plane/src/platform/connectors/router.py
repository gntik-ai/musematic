from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.connectors.dependencies import get_connectors_service
from platform.connectors.models import DeadLetterResolution
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
from platform.connectors.service import ConnectorsService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status

router = APIRouter(prefix="/api/v1", tags=["connectors"])


def _headers(request: Request) -> dict[str, str]:
    return {key.lower(): value for key, value in request.headers.items()}


async def _verify_webhook_signature(
    request: Request,
    connector_instance_id: UUID,
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> None:
    await connectors_service.verify_webhook_request(
        connector_instance_id,
        await request.body(),
        _headers(request),
    )


async def _verify_slack_signature(
    request: Request,
    connector_instance_id: UUID,
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> None:
    await connectors_service.verify_slack_request(
        connector_instance_id,
        await request.body(),
        _headers(request),
    )


@router.get("/connectors/types", response_model=ConnectorTypeListResponse)
async def list_connector_types(
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorTypeListResponse:
    del current_user
    return await connectors_service.list_connector_types()


@router.get("/connectors/types/{type_slug}", response_model=ConnectorTypeResponse)
async def get_connector_type(
    type_slug: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorTypeResponse:
    del current_user
    return await connectors_service.get_connector_type(type_slug)


@router.post(
    "/workspaces/{workspace_id}/connectors",
    response_model=ConnectorInstanceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connector_instance(
    workspace_id: UUID,
    payload: ConnectorInstanceCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorInstanceResponse:
    del current_user
    return await connectors_service.create_connector_instance(workspace_id, payload)


@router.get(
    "/workspaces/{workspace_id}/connectors",
    response_model=ConnectorInstanceListResponse,
)
async def list_connector_instances(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorInstanceListResponse:
    del current_user
    return await connectors_service.list_connector_instances(workspace_id)


@router.get(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}",
    response_model=ConnectorInstanceResponse,
)
async def get_connector_instance(
    workspace_id: UUID,
    connector_instance_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorInstanceResponse:
    del current_user
    return await connectors_service.get_connector_instance(workspace_id, connector_instance_id)


@router.put(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}",
    response_model=ConnectorInstanceResponse,
)
async def update_connector_instance(
    workspace_id: UUID,
    connector_instance_id: UUID,
    payload: ConnectorInstanceUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorInstanceResponse:
    del current_user
    return await connectors_service.update_connector_instance(
        workspace_id,
        connector_instance_id,
        payload,
    )


@router.delete(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connector_instance(
    workspace_id: UUID,
    connector_instance_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> Response:
    del current_user
    await connectors_service.delete_connector_instance(workspace_id, connector_instance_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}/health-check",
    response_model=HealthCheckResponse,
)
async def health_check_connector(
    workspace_id: UUID,
    connector_instance_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> HealthCheckResponse:
    del current_user
    return await connectors_service.run_health_check(workspace_id, connector_instance_id)


@router.post(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}/test-connectivity",
    response_model=TestConnectivityResponse,
)
async def run_connector_connectivity_test(
    workspace_id: UUID,
    connector_instance_id: UUID,
    payload: TestConnectivityRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> TestConnectivityResponse:
    del current_user
    return await connectors_service.test_connectivity(workspace_id, connector_instance_id, payload)


@router.post(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}/routes",
    response_model=ConnectorRouteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_connector_route(
    workspace_id: UUID,
    connector_instance_id: UUID,
    payload: ConnectorRouteCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorRouteResponse:
    del current_user
    return await connectors_service.create_route(workspace_id, connector_instance_id, payload)


@router.get(
    "/workspaces/{workspace_id}/connectors/{connector_instance_id}/routes",
    response_model=ConnectorRouteListResponse,
)
async def list_connector_routes(
    workspace_id: UUID,
    connector_instance_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorRouteListResponse:
    del current_user
    return await connectors_service.list_routes(workspace_id, connector_instance_id)


@router.get("/workspaces/{workspace_id}/routes/{route_id}", response_model=ConnectorRouteResponse)
async def get_connector_route(
    workspace_id: UUID,
    route_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorRouteResponse:
    del current_user
    return await connectors_service.get_route(workspace_id, route_id)


@router.put("/workspaces/{workspace_id}/routes/{route_id}", response_model=ConnectorRouteResponse)
async def update_connector_route(
    workspace_id: UUID,
    route_id: UUID,
    payload: ConnectorRouteUpdate,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> ConnectorRouteResponse:
    del current_user
    return await connectors_service.update_route(workspace_id, route_id, payload)


@router.delete(
    "/workspaces/{workspace_id}/routes/{route_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_connector_route(
    workspace_id: UUID,
    route_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> Response:
    del current_user
    await connectors_service.delete_route(workspace_id, route_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/inbound/slack/{connector_instance_id}",
    dependencies=[Depends(_verify_slack_signature)],
)
async def inbound_slack(
    connector_instance_id: UUID,
    request: Request,
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> dict[str, Any]:
    raw = await request.body()
    payload = await request.json()
    return await connectors_service.process_inbound(
        connector_instance_id,
        payload=payload,
        raw_body=raw,
        headers=_headers(request),
        path=str(request.url.path),
    )


@router.post("/inbound/telegram/{connector_instance_id}")
async def inbound_telegram(
    connector_instance_id: UUID,
    request: Request,
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> dict[str, Any]:
    raw = await request.body()
    payload = await request.json()
    return await connectors_service.process_inbound(
        connector_instance_id,
        payload=payload,
        raw_body=raw,
        headers=_headers(request),
        path=str(request.url.path),
    )


@router.post(
    "/inbound/webhook/{connector_instance_id}",
    dependencies=[Depends(_verify_webhook_signature)],
)
async def inbound_webhook(
    connector_instance_id: UUID,
    request: Request,
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> dict[str, Any]:
    raw = await request.body()
    payload = await request.json()
    return await connectors_service.process_inbound(
        connector_instance_id,
        payload=payload,
        raw_body=raw,
        headers=_headers(request),
        path=str(request.url.path),
    )


@router.post(
    "/workspaces/{workspace_id}/deliveries",
    response_model=OutboundDeliveryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_delivery(
    workspace_id: UUID,
    payload: OutboundDeliveryCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> OutboundDeliveryResponse:
    del current_user
    return await connectors_service.create_delivery(workspace_id, payload)


@router.get("/workspaces/{workspace_id}/deliveries", response_model=OutboundDeliveryListResponse)
async def list_deliveries(
    workspace_id: UUID,
    connector_instance_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> OutboundDeliveryListResponse:
    del current_user
    return await connectors_service.list_deliveries(
        workspace_id,
        connector_instance_id=connector_instance_id,
    )


@router.get(
    "/workspaces/{workspace_id}/deliveries/{delivery_id}",
    response_model=OutboundDeliveryResponse,
)
async def get_delivery(
    workspace_id: UUID,
    delivery_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> OutboundDeliveryResponse:
    del current_user
    return await connectors_service.get_delivery(workspace_id, delivery_id)


@router.get("/workspaces/{workspace_id}/dead-letter", response_model=DeadLetterEntryListResponse)
async def list_dead_letter_entries(
    workspace_id: UUID,
    connector_instance_id: UUID | None = Query(default=None),
    resolution_status: DeadLetterResolution | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> DeadLetterEntryListResponse:
    del current_user
    return await connectors_service.list_dead_letter_entries(
        workspace_id,
        connector_instance_id=connector_instance_id,
        resolution_status=resolution_status,
    )


@router.get(
    "/workspaces/{workspace_id}/dead-letter/{entry_id}",
    response_model=DeadLetterEntryResponse,
)
async def get_dead_letter_entry(
    workspace_id: UUID,
    entry_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> DeadLetterEntryResponse:
    del current_user
    return await connectors_service.get_dead_letter_entry(workspace_id, entry_id)


@router.post(
    "/workspaces/{workspace_id}/dead-letter/{entry_id}/redeliver",
    response_model=OutboundDeliveryResponse,
)
async def redeliver_dead_letter(
    workspace_id: UUID,
    entry_id: UUID,
    payload: DeadLetterRedeliverRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> OutboundDeliveryResponse:
    del current_user
    return await connectors_service.redeliver_dead_letter(workspace_id, entry_id, payload)


@router.post(
    "/workspaces/{workspace_id}/dead-letter/{entry_id}/discard",
    response_model=DeadLetterEntryResponse,
)
async def discard_dead_letter(
    workspace_id: UUID,
    entry_id: UUID,
    payload: DeadLetterDiscardRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    connectors_service: ConnectorsService = Depends(get_connectors_service),
) -> DeadLetterEntryResponse:
    del current_user
    return await connectors_service.discard_dead_letter(workspace_id, entry_id, payload)
