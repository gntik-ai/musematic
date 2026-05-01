from __future__ import annotations

from platform.ws_hub.exceptions import ProtocolViolationError, SubscriptionAuthError
from platform.ws_hub.subscription import ChannelType
from uuid import uuid4

import pytest

from tests.ws_hub_support import StaticWorkspacesService, build_connection


@pytest.mark.asyncio
async def test_visibility_authorize_subscription_allows_own_user_channels() -> None:
    conn = build_connection(user_id=uuid4())
    resource_id = str(conn.user_id)
    service = StaticWorkspacesService()
    from platform.ws_hub.visibility import VisibilityFilter

    visibility = VisibilityFilter(lambda: _factory(service))

    assert await visibility.authorize_subscription(conn, ChannelType.ALERTS, resource_id) is None
    assert await visibility.authorize_subscription(conn, ChannelType.ATTENTION, resource_id) is None


@pytest.mark.asyncio
async def test_visibility_authorize_subscription_rejects_invalid_uuid() -> None:
    conn = build_connection(user_id=uuid4(), workspace_ids={uuid4()})
    service = StaticWorkspacesService()
    from platform.ws_hub.visibility import VisibilityFilter

    visibility = VisibilityFilter(lambda: _factory(service))

    with pytest.raises(ProtocolViolationError):
        await visibility.authorize_subscription(conn, ChannelType.WORKSPACE, "not-a-uuid")


@pytest.mark.asyncio
async def test_visibility_authorize_subscription_rejects_unauthorized_workspace() -> None:
    user_id = uuid4()
    own_workspace = uuid4()
    other_workspace = uuid4()
    resource_id = uuid4()
    conn = build_connection(user_id=user_id, workspace_ids={own_workspace})
    service = StaticWorkspacesService(
        resource_workspace_map={(ChannelType.WORKSPACE.value, resource_id): other_workspace}
    )
    from platform.ws_hub.visibility import VisibilityFilter

    visibility = VisibilityFilter(lambda: _factory(service))

    with pytest.raises(SubscriptionAuthError) as exc_info:
        await visibility.authorize_subscription(conn, ChannelType.WORKSPACE, str(resource_id))

    assert exc_info.value.code == "unauthorized"


@pytest.mark.asyncio
async def test_visibility_authorize_subscription_uses_single_workspace_fallback() -> None:
    workspace_id = uuid4()
    conn = build_connection(user_id=uuid4(), workspace_ids={workspace_id})
    service = StaticWorkspacesService()
    from platform.ws_hub.visibility import VisibilityFilter

    visibility = VisibilityFilter(lambda: _factory(service))

    assert (
        await visibility.authorize_subscription(conn, ChannelType.EXECUTION, str(uuid4()))
        == workspace_id
    )


@pytest.mark.asyncio
async def test_visibility_allows_unresolved_workspace_resources_in_e2e_mode() -> None:
    conn = build_connection(user_id=uuid4(), workspace_ids=set())
    service = StaticWorkspacesService()
    from platform.ws_hub.visibility import VisibilityFilter

    visibility = VisibilityFilter(
        lambda: _factory(service),
        allow_unresolved_e2e_resources=True,
    )

    assert await visibility.authorize_subscription(
        conn,
        ChannelType.CONVERSATION,
        str(uuid4()),
    ) is None
    assert visibility.is_visible(
        {"correlation_context": {"workspace_id": str(uuid4())}},
        conn,
    ) is True


@pytest.mark.asyncio
async def test_visibility_refresh_and_event_visibility() -> None:
    workspace_id = uuid4()
    user_id = uuid4()
    conn = build_connection(user_id=user_id, workspace_ids=set())
    service = StaticWorkspacesService(workspace_ids_by_user={user_id: [workspace_id]})
    from platform.ws_hub.visibility import VisibilityFilter

    visibility = VisibilityFilter(lambda: _factory(service))
    await visibility.refresh_connection_memberships(conn)

    assert conn.workspace_ids == {workspace_id}
    assert (
        visibility.is_visible(
            {"correlation_context": {"workspace_id": str(workspace_id)}},
            conn,
        )
        is True
    )
    assert (
        visibility.is_visible(
            {"correlation_context": {"workspace_id": str(uuid4())}},
            conn,
        )
        is False
    )
    assert visibility.is_visible({"correlation_context": {"workspace_id": None}}, conn) is True
    assert visibility.is_visible({"payload": {}}, conn) is True


def _factory(service: StaticWorkspacesService):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def manager():
        yield service

    return manager()
