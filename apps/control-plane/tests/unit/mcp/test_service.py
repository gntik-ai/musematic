from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common.clients.redis import RateLimitResult
from platform.mcp.exceptions import (
    MCPDuplicateRegistrationError,
    MCPInsecureTransportError,
    MCPServerNotFoundError,
    MCPServerSuspendedError,
)
from platform.mcp.models import MCPInvocationDirection, MCPInvocationOutcome, MCPServerStatus
from platform.mcp.schemas import (
    MCPExposedToolUpsertRequest,
    MCPServerPatch,
    MCPServerRegisterRequest,
)
from platform.mcp.service import MCPService
from uuid import uuid4

import pytest
from tests.mcp_support import (
    FakeMCPRepository,
    FakeRedisClient,
    RecordingProducer,
    build_catalog_cache,
    build_server,
    build_settings,
)


class ToolRegistryStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    async def refresh_server_catalog(self, server_id, *, force_refresh: bool = False):
        self.calls.append((str(server_id), force_refresh))
        return {"server_id": str(server_id)}


def _service(
    *,
    repository: FakeMCPRepository | None = None,
    redis_client: FakeRedisClient | None = None,
    producer: RecordingProducer | None = None,
) -> tuple[MCPService, FakeMCPRepository, FakeRedisClient, RecordingProducer]:
    repo = repository or FakeMCPRepository()
    redis = redis_client or FakeRedisClient()
    events = producer or RecordingProducer()
    service = MCPService(
        repository=repo,
        settings=build_settings(),
        producer=events,
        redis_client=redis,
    )
    return service, repo, redis, events


@pytest.mark.asyncio
async def test_register_server_validates_https_and_duplicates() -> None:
    service, repo, _redis, producer = _service()
    workspace_id = uuid4()
    created_by = uuid4()

    with pytest.raises(MCPInsecureTransportError):
        await service.register_server(
            workspace_id,
            MCPServerRegisterRequest(
                display_name="Local",
                endpoint_url="http://mcp.example.com",
                auth_config={},
            ),
            created_by,
        )

    existing = build_server(workspace_id=workspace_id, endpoint_url="https://mcp.example.com")
    repo.servers[existing.id] = existing
    with pytest.raises(MCPDuplicateRegistrationError):
        await service.register_server(
            workspace_id,
            MCPServerRegisterRequest(
                display_name="Duplicate",
                endpoint_url=existing.endpoint_url,
                auth_config={},
            ),
            created_by,
        )

    assert producer.events == []
    assert repo.session.commit_calls == 0


@pytest.mark.asyncio
async def test_service_registers_updates_and_deregisters_servers() -> None:
    service, repo, _redis, producer = _service()
    workspace_id = uuid4()
    created_by = uuid4()

    registered = await service.register_server(
        workspace_id,
        MCPServerRegisterRequest(
            display_name="Finance MCP",
            endpoint_url="https://mcp.example.com",
            auth_config={"type": "api_key", "value": "secret"},
            catalog_ttl_seconds=120,
        ),
        created_by,
    )
    server_id = registered.server_id

    suspended = await service.update_server(
        workspace_id,
        server_id,
        MCPServerPatch(status=MCPServerStatus.suspended, display_name="Finance MCP v2"),
    )
    deregistered = await service.deregister_server(workspace_id, server_id)

    assert registered.status is MCPServerStatus.active
    assert suspended.display_name == "Finance MCP v2"
    assert deregistered.status is MCPServerStatus.deregistered
    assert repo.session.commit_calls == 3
    assert [event["event_type"] for event in producer.events] == [
        "mcp.server.registered",
        "mcp.server.suspended",
        "mcp.server.deregistered",
    ]

    with pytest.raises(MCPServerSuspendedError):
        await service.update_server(
            workspace_id,
            server_id,
            MCPServerPatch(display_name="should fail"),
        )


@pytest.mark.asyncio
async def test_service_exposed_tools_catalog_refresh_health_and_audit_paths() -> None:
    repo = FakeMCPRepository()
    redis = FakeRedisClient(
        rate_limit_results=[
            RateLimitResult(False, 0, 250),
            RateLimitResult(True, 5, 0),
        ]
    )
    service, _repo, _redis, producer = _service(repository=repo, redis_client=redis)
    workspace_id = uuid4()
    server = build_server(workspace_id=workspace_id)
    repo.servers[server.id] = server
    repo.catalog_caches[server.id] = build_catalog_cache(
        server_id=server.id,
        next_refresh_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    tool = await service.toggle_exposure(
        workspace_id,
        "finance:lookup",
        MCPExposedToolUpsertRequest(
            mcp_tool_name="lookup",
            mcp_description="Lookup a record",
            mcp_input_schema={"type": "object"},
            is_exposed=True,
        ),
        created_by=uuid4(),
    )
    catalog = await service.get_catalog(workspace_id, server.id)
    forced = await service.force_refresh(workspace_id, server.id)
    service.tool_registry = ToolRegistryStub()
    refreshed = await service.refresh_due_catalogs()
    denied_limit = await service.check_rate_limit(uuid4())
    allowed_limit = await service.check_rate_limit(uuid4())

    await service.update_health(server.id, ok=False, classification="transient")
    degraded = await service.get_server_health(server.id)
    await service.update_health(server.id, ok=True)
    healthy = await service.get_server_health(server.id)
    audit = await service.create_audit_record(
        workspace_id=workspace_id,
        principal_id=uuid4(),
        agent_id=None,
        agent_fqn=None,
        server_id=server.id,
        tool_identifier="mcp:test:lookup",
        direction=MCPInvocationDirection.outbound,
        outcome=MCPInvocationOutcome.denied,
        error_code="rate_limit",
    )
    listed = await service.list_exposed_tools(workspace_id, is_exposed=True, page=1, page_size=10)

    assert tool.mcp_tool_name == "lookup"
    assert catalog.tool_count == 1
    assert forced["refresh_scheduled"] is True
    assert refreshed == 1
    assert denied_limit.allowed is False
    assert allowed_limit.allowed is True
    assert degraded.status == "degraded"
    assert healthy.status == "healthy"
    assert audit.error_code == "rate_limit"
    assert listed.total == 1
    assert redis.deleted == [f"cache:mcp_exposed_tools:{workspace_id}"]
    assert repo.session.commit_calls == 3
    assert producer.events == []


@pytest.mark.asyncio
async def test_service_falls_back_to_cache_and_raises_not_found() -> None:
    service, repo, redis, _producer = _service()
    server = build_server()
    repo.servers[server.id] = server
    repo.catalog_caches[server.id] = build_catalog_cache(server_id=server.id, is_stale=True)

    health = await service.get_server_health(server.id)
    assert health.status == "degraded"

    with pytest.raises(MCPServerNotFoundError):
        await service.get_catalog(server.workspace_id, uuid4())

    redis.hashes[service._health_key(server.id)] = {
        "status": "unhealthy",
        "error_count_5m": "2",
        "last_success_at": datetime.now(UTC).isoformat(),
    }
    health_from_redis = await service.get_server_health(server.id)
    assert health_from_redis.status == "unhealthy"
    assert health_from_redis.error_count_5m == 2


@pytest.mark.asyncio
async def test_service_covers_direct_get_ttl_patch_missing_catalog_and_parse_helpers() -> None:
    repo = FakeMCPRepository()
    service, _repo, _redis, producer = _service(repository=repo)
    workspace_id = uuid4()
    server = build_server(workspace_id=workspace_id)
    repo.servers[server.id] = server

    fetched = await service.get_server(workspace_id, server.id)
    updated = await service.update_server(
        workspace_id,
        server.id,
        MCPServerPatch(catalog_ttl_seconds=30),
    )

    with pytest.raises(MCPServerNotFoundError):
        await service.get_catalog(workspace_id, server.id)

    forced = await service.force_refresh(workspace_id, server.id)

    class SessionWithoutCommit:
        pass

    service_without_commit = MCPService(
        repository=type('RepoStub', (), {'session': SessionWithoutCommit()})(),
        settings=build_settings(),
        producer=None,
        redis_client=FakeRedisClient(),
    )

    now = datetime.now(UTC)
    assert fetched.server_id == server.id
    assert updated.catalog_ttl_seconds == 30
    assert forced['refresh_scheduled'] is True
    assert repo.catalog_caches[server.id].is_stale is True
    assert service._parse_datetime(now) == now
    await service_without_commit._commit()
    assert producer.events == []



@pytest.mark.asyncio
async def test_service_lists_servers_and_handles_refresh_and_rate_limit_edge_cases() -> None:
    repo = FakeMCPRepository()
    service, _repo, _redis, _producer = _service(repository=repo)
    workspace_id = uuid4()
    server = build_server(workspace_id=workspace_id)
    repo.servers[server.id] = server

    listed = await service.list_servers(workspace_id, status=None, page=1, page_size=10)
    unchanged = await service.update_server(
        workspace_id,
        server.id,
        MCPServerPatch(),
    )
    no_registry_refresh = await service.refresh_due_catalogs()

    repo.catalog_caches[server.id] = build_catalog_cache(
        server_id=server.id,
        next_refresh_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    class FailingRegistry:
        async def refresh_server_catalog(self, server_id, *, force_refresh: bool = False):
            del server_id, force_refresh
            raise RuntimeError("boom")

    service.tool_registry = FailingRegistry()
    swallowed_refresh = await service.refresh_due_catalogs()

    service_without_checker = MCPService(
        repository=repo,
        settings=build_settings(),
        producer=None,
        redis_client=object(),
    )
    fallback_limit = await service_without_checker.check_rate_limit(uuid4())

    assert listed.total == 1
    assert unchanged.server_id == server.id
    assert no_registry_refresh == 0
    assert swallowed_refresh == 0
    assert fallback_limit.allowed is True
    assert (
        fallback_limit.remaining
        == service_without_checker.settings.MCP_RATE_LIMIT_PER_PRINCIPAL_PER_MINUTE
    )
