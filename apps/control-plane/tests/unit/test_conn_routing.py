from __future__ import annotations

from datetime import UTC, datetime
from platform.connectors.plugin import InboundMessage
from platform.connectors.service import ConnectorsService
from uuid import UUID, uuid4

import pytest

from tests.auth_support import RecordingProducer
from tests.connectors_support import ObjectStorageStub, build_connectors_settings, build_route


class RouteRepositoryStub:
    def __init__(self, routes: list[object]) -> None:
        self.routes = routes
        self.calls: list[tuple[UUID, UUID]] = []

    async def get_routes_for_instance(
        self,
        connector_instance_id: UUID,
        workspace_id: UUID,
    ) -> list[object]:
        self.calls.append((connector_instance_id, workspace_id))
        return list(self.routes)


class RedisCacheStub:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, ttl: int | None = None) -> bool:
        del ttl
        self.values[key] = value
        return True

    async def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)


def _service_for_routes(routes: list[object]) -> tuple[ConnectorsService, RouteRepositoryStub]:
    repository = RouteRepositoryStub(routes)
    service = ConnectorsService(
        repository=repository,  # type: ignore[arg-type]
        settings=build_connectors_settings(),
        producer=RecordingProducer(),
        redis_client=RedisCacheStub(),
        object_storage=ObjectStorageStub(),
    )
    return service, repository


def _inbound_message(
    *,
    connector_instance_id: UUID,
    workspace_id: UUID,
    channel: str = "#support-general",
    sender_identity: str = "user-1",
    metadata: dict[str, str] | None = None,
) -> InboundMessage:
    return InboundMessage(
        connector_instance_id=connector_instance_id,
        workspace_id=workspace_id,
        sender_identity=sender_identity,
        sender_display=None,
        channel=channel,
        content_text="hello",
        content_structured=None,
        timestamp=datetime.now(UTC),
        original_payload={},
        metadata=metadata or {},
    )


@pytest.mark.asyncio
async def test_match_route_prefers_first_matching_priority_and_tiebreaker_order() -> None:
    workspace_id = uuid4()
    connector_instance_id = uuid4()
    earlier_route = build_route(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
        name="Earlier",
        channel_pattern="#support*",
        priority=10,
    )
    later_route = build_route(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
        name="Later",
        channel_pattern="#support*",
        priority=10,
    )
    lower_priority_number = build_route(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
        name="Priority winner",
        channel_pattern="#support*",
        priority=5,
    )
    service, repository = _service_for_routes(
        [lower_priority_number, earlier_route, later_route]
    )

    matched = await service.match_route(
        workspace_id,
        connector_instance_id,
        _inbound_message(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
        ),
    )

    assert matched is not None
    assert matched["id"] == str(lower_priority_number.id)
    assert repository.calls == [(connector_instance_id, workspace_id)]


@pytest.mark.asyncio
async def test_match_route_supports_globs_and_skips_disabled_routes() -> None:
    workspace_id = uuid4()
    connector_instance_id = uuid4()
    disabled_route = build_route(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
        name="Disabled",
        channel_pattern="#support*",
        priority=10,
        is_enabled=False,
    )
    sender_route = build_route(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
        name="Sender match",
        sender_pattern="agent-*",
        priority=20,
    )
    service, _repository = _service_for_routes([disabled_route, sender_route])

    matched = await service.match_route(
        workspace_id,
        connector_instance_id,
        _inbound_message(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
            channel="#support-escalations",
            sender_identity="agent-42",
        ),
    )

    assert matched is not None
    assert matched["id"] == str(sender_route.id)


@pytest.mark.asyncio
async def test_match_route_requires_conditions_and_returns_none_without_match() -> None:
    workspace_id = uuid4()
    connector_instance_id = uuid4()
    conditional_route = build_route(
        workspace_id=workspace_id,
        connector_instance_id=connector_instance_id,
        name="Conditional",
        conditions={"intent": "billing"},
    )
    service, _repository = _service_for_routes([conditional_route])

    missing_metadata = await service.match_route(
        workspace_id,
        connector_instance_id,
        _inbound_message(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
        ),
    )
    original_payload_match = await service.match_route(
        workspace_id,
        connector_instance_id,
        InboundMessage(
            connector_instance_id=connector_instance_id,
            workspace_id=workspace_id,
            sender_identity="user-1",
            sender_display=None,
            channel="#support-general",
            content_text="hello",
            content_structured=None,
            timestamp=datetime.now(UTC),
            original_payload={"intent": "billing"},
        ),
    )

    assert missing_metadata is None
    assert original_payload_match is not None
    assert original_payload_match["id"] == str(conditional_route.id)
