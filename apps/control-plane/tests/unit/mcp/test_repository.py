from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.mcp.models import (
    MCPExposedTool,
    MCPInvocationAuditRecord,
    MCPInvocationDirection,
    MCPInvocationOutcome,
)
from platform.mcp.repository import MCPRepository
from uuid import uuid4

from tests.mcp_support import build_catalog_cache, build_exposed_tool, build_server
from tests.registry_support import ExecuteResultStub, SessionStub


async def test_repository_crud_and_listing_paths() -> None:
    workspace_id = uuid4()
    server = build_server(workspace_id=workspace_id)
    other = build_server(workspace_id=workspace_id, display_name="Other")
    cache = build_catalog_cache(server_id=server.id)
    audit = MCPInvocationAuditRecord(
        agent_id=uuid4(),
        tool_identifier="mcp:test:search",
        direction=MCPInvocationDirection.outbound,
        outcome=MCPInvocationOutcome.allowed,
    )
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=server),
            ExecuteResultStub(one=server),
            ExecuteResultStub(many=[server, other]),
            ExecuteResultStub(many=[server, other]),
            ExecuteResultStub(many=[server]),
            ExecuteResultStub(one=cache),
            ExecuteResultStub(many=[audit]),
        ]
    )
    repo = MCPRepository(session)  # type: ignore[arg-type]

    created = await repo.create_server(server)
    fetched = await repo.get_server(server.id, workspace_id)
    by_url = await repo.get_server_by_url(workspace_id, server.endpoint_url)
    listed, total = await repo.list_servers(workspace_id, limit=20)
    by_ids = await repo.list_servers_by_ids(workspace_id, [server.id])
    updated = await repo.update_server(server, display_name="Updated")
    cache_result = await repo.get_catalog_cache(server.id)
    audit_result = await repo.list_audit_records_by_agent(audit.agent_id)

    assert created is server
    assert fetched is server
    assert by_url is server
    assert total == 2
    assert listed == [server, other]
    assert by_ids == [server]
    assert updated.display_name == "Updated"
    assert cache_result is cache
    assert audit_result == [audit]


async def test_repository_upserts_exposed_tools_catalog_cache_and_refresh_requests() -> None:
    workspace_id = uuid4()
    tool = build_exposed_tool(workspace_id=workspace_id, tool_fqn="finance:lookup")
    existing_tool = build_exposed_tool(
        id=tool.id,
        workspace_id=workspace_id,
        tool_fqn=tool.tool_fqn,
        mcp_tool_name="lookup",
        mcp_description="Old",
        is_exposed=False,
    )
    cache = build_catalog_cache(server_id=uuid4())
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(one=None),
            ExecuteResultStub(one=existing_tool),
            ExecuteResultStub(one=None),
            ExecuteResultStub(one=cache),
            ExecuteResultStub(many=[cache]),
            ExecuteResultStub(one=cache),
        ]
    )
    repo = MCPRepository(session)  # type: ignore[arg-type]

    created_tool, created_flag = await repo.upsert_exposed_tool(tool)
    updated_tool, updated_flag = await repo.upsert_exposed_tool(
        MCPExposedTool(
            id=uuid4(),
            workspace_id=workspace_id,
            tool_fqn=tool.tool_fqn,
            mcp_tool_name="lookup-renamed",
            mcp_description="New",
            mcp_input_schema={"type": "object"},
            is_exposed=True,
            created_by=uuid4(),
        )
    )
    created_cache = await repo.upsert_catalog_cache(
        cache.server_id,
        tools_catalog=[{"name": "search", "inputSchema": {}}],
        fetched_at=datetime.now(UTC),
        version_snapshot="v1",
        is_stale=False,
        next_refresh_at=datetime.now(UTC) + timedelta(minutes=30),
    )
    updated_cache = await repo.upsert_catalog_cache(
        cache.server_id,
        tools_catalog=[{"name": "search", "inputSchema": {}}],
        fetched_at=datetime.now(UTC),
        version_snapshot="v2",
        is_stale=True,
        next_refresh_at=datetime.now(UTC) + timedelta(minutes=45),
    )
    due = await repo.list_due_catalog_refresh(now=datetime.now(UTC) + timedelta(days=1))
    marked = await repo.mark_refresh_requested(cache.server_id, datetime.now(UTC))

    assert created_flag is True
    assert created_tool is tool
    assert updated_flag is False
    assert updated_tool.mcp_tool_name == "lookup-renamed"
    assert created_cache.version_snapshot == "v1"
    assert updated_cache.version_snapshot == "v2"
    assert updated_cache.is_stale is True
    assert due == [cache]
    assert marked is cache



async def test_repository_handles_global_tools_empty_server_ids_and_missing_refresh() -> None:
    workspace_id = uuid4()
    scoped_tool = build_exposed_tool(workspace_id=workspace_id, tool_fqn="finance:lookup")
    global_tool = build_exposed_tool(
        workspace_id=None,
        tool_fqn="global:search",
        mcp_tool_name="global-search",
    )
    audit = MCPInvocationAuditRecord(
        agent_id=uuid4(),
        tool_identifier="mcp:global:search",
        direction=MCPInvocationDirection.inbound,
        outcome=MCPInvocationOutcome.denied,
    )
    session = SessionStub(
        execute_results=[
            ExecuteResultStub(many=[scoped_tool, global_tool]),
            ExecuteResultStub(many=[scoped_tool, global_tool]),
            ExecuteResultStub(many=[global_tool]),
            ExecuteResultStub(many=[global_tool]),
            ExecuteResultStub(many=[global_tool]),
            ExecuteResultStub(many=[global_tool]),
            ExecuteResultStub(one=None),
        ]
    )
    repo = MCPRepository(session)  # type: ignore[arg-type]

    scoped_items, scoped_total = await repo.get_exposed_tools(
        workspace_id,
        is_exposed=True,
        limit=10,
    )
    global_items, global_total = await repo.get_exposed_tools(None, is_exposed=None, limit=10)
    by_fqn = await repo.get_exposed_tool_by_fqn(global_tool.tool_fqn, None)
    by_name = await repo.get_exposed_tool_by_name(global_tool.mcp_tool_name, None)
    empty_servers = await repo.list_servers_by_ids(workspace_id, [])
    missing_mark = await repo.mark_refresh_requested(uuid4(), datetime.now(UTC))
    created_audit = await repo.create_audit_record(audit)

    assert scoped_total == 2
    assert scoped_items == [scoped_tool, global_tool]
    assert global_total == 1
    assert global_items == [global_tool]
    assert by_fqn is global_tool
    assert by_name is global_tool
    assert empty_servers == []
    assert missing_mark is None
    assert created_audit is audit
