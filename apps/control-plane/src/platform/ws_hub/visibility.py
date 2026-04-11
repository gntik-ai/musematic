from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from platform.ws_hub.exceptions import ProtocolViolationError, SubscriptionAuthError
from platform.ws_hub.subscription import USER_SCOPED_CHANNELS, ChannelType
from typing import Any, Protocol
from uuid import UUID


class _WorkspaceResolver(Protocol):
    async def get_user_workspace_ids(self, user_id: UUID) -> list[UUID]: ...

    async def get_workspace_id_for_resource(
        self,
        channel: ChannelType | str,
        resource_id: UUID,
    ) -> UUID | None: ...


class VisibilityFilter:
    def __init__(
        self,
        workspaces_service_factory: Callable[
            [],
            AbstractAsyncContextManager[_WorkspaceResolver],
        ],
    ) -> None:
        self._workspaces_service_factory = workspaces_service_factory

    async def authorize_subscription(
        self,
        conn: Any,
        channel: ChannelType,
        resource_id: str,
    ) -> UUID | None:
        if channel in USER_SCOPED_CHANNELS:
            if resource_id != str(conn.user_id):
                raise SubscriptionAuthError(
                    "unauthorized",
                    "User-scoped subscriptions are limited to the connected user",
                )
            return None

        try:
            parsed_resource_id = UUID(resource_id)
        except ValueError as exc:
            raise ProtocolViolationError(
                "invalid_resource_id",
                "resource_id must be a UUID",
            ) from exc

        async with self._workspaces_service_factory() as workspaces_service:
            workspace_id = await workspaces_service.get_workspace_id_for_resource(
                channel,
                parsed_resource_id,
            )
        if workspace_id is None:
            workspace_ids = {UUID(str(item)) for item in conn.workspace_ids}
            if len(workspace_ids) == 1:
                return next(iter(workspace_ids))
            raise SubscriptionAuthError(
                "resource_not_found",
                f"Unable to resolve workspace ownership for {channel.value}:{resource_id}",
            )
        if workspace_id not in conn.workspace_ids:
            raise SubscriptionAuthError(
                "unauthorized",
                f"You are not authorized to subscribe to this {channel.value}",
            )
        return workspace_id

    def is_visible(self, envelope: dict[str, Any], conn: Any) -> bool:
        correlation = envelope.get("correlation_context") or envelope.get("correlation") or {}
        raw_workspace_id = correlation.get("workspace_id")
        if raw_workspace_id is None:
            return True
        try:
            workspace_id = UUID(str(raw_workspace_id))
        except ValueError:
            return False
        return workspace_id in conn.workspace_ids

    async def refresh_connection_memberships(self, conn: Any) -> None:
        async with self._workspaces_service_factory() as workspaces_service:
            conn.workspace_ids = set(await workspaces_service.get_user_workspace_ids(conn.user_id))
        conn.last_pong_at = datetime.now(UTC)
