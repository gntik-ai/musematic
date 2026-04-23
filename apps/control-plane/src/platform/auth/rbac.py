from __future__ import annotations

from collections.abc import Iterable
from platform.auth.events import PermissionDeniedPayload, publish_auth_event
from platform.auth.purpose import check_purpose_bound
from platform.auth.repository import AuthRepository
from platform.auth.schemas import PermissionCheckResponse, RoleType
from platform.common.clients.redis import AsyncRedisClient
from platform.common.events.producer import EventProducer
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession


class RBACEngine:
    def __init__(self) -> None:
        self._permissions: dict[str, set[tuple[str, str, str]]] = {}
        self._loaded = False

    async def load_permissions(self, repository: AuthRepository) -> None:
        rows = await repository.get_all_role_permissions()
        permissions: dict[str, set[tuple[str, str, str]]] = {}
        for row in rows:
            permissions.setdefault(row.role, set()).add((row.resource_type, row.action, row.scope))
        self._permissions = permissions
        self._loaded = True

    async def check_permission(
        self,
        user_id: UUID,
        resource_type: str,
        action: str,
        workspace_id: UUID | None,
        db: AsyncSession,
        redis_client: AsyncRedisClient,
        *,
        producer: EventProducer | None = None,
        correlation_id: UUID | None = None,
        identity_type: str = "user",
        agent_purpose: str | None = None,
    ) -> PermissionCheckResponse:
        del redis_client
        repository = AuthRepository(db)
        if not self._loaded:
            await self.load_permissions(repository)

        roles = await repository.get_user_roles(user_id, workspace_id)
        if not roles:
            return await self._deny(
                user_id,
                resource_type,
                action,
                producer,
                correlation_id,
                "rbac_denied",
            )

        for user_role in roles:
            if user_role.role == RoleType.SUPERADMIN.value:
                return PermissionCheckResponse(
                    allowed=True,
                    role=user_role.role,
                    resource_type=resource_type,
                    action=action,
                    scope="global",
                )

            for permission in self._permissions.get(user_role.role, set()):
                permission_resource, permission_action, scope = permission
                if not self._matches(permission_resource, resource_type):
                    continue
                if not self._matches(permission_action, action):
                    continue
                if not self._workspace_matches(user_role.workspace_id, workspace_id, scope):
                    continue
                await check_purpose_bound(
                    identity_type,
                    agent_purpose,
                    resource_type,
                    action,
                    producer,
                    correlation_id or uuid4(),
                    identity_id=user_id,
                )
                return PermissionCheckResponse(
                    allowed=True,
                    role=user_role.role,
                    resource_type=resource_type,
                    action=action,
                    scope=scope,
                )

        return await self._deny(
            user_id,
            resource_type,
            action,
            producer,
            correlation_id,
            "rbac_denied",
        )

    async def revoke_connector_sourced_roles(
        self,
        repository: AuthRepository,
        *,
        user_id: UUID,
        connector_id: UUID,
        keep_assignments: Iterable[tuple[str, UUID | None]],
    ) -> int:
        preserved = set(keep_assignments)
        revoked = 0
        assignments = await repository.get_user_roles_by_source_connector(
            user_id,
            connector_id,
        )
        for assignment in assignments:
            key = (assignment.role, assignment.workspace_id)
            if key in preserved:
                continue
            await repository.revoke_user_role(assignment.id)
            revoked += 1
        return revoked

    async def _deny(
        self,
        user_id: UUID,
        resource_type: str,
        action: str,
        producer: EventProducer | None,
        correlation_id: UUID | None,
        reason: str,
    ) -> PermissionCheckResponse:
        await publish_auth_event(
            "auth.permission.denied",
            PermissionDeniedPayload(
                user_id=user_id,
                resource_type=resource_type,
                action=action,
                reason=reason,
            ),
            correlation_id or uuid4(),
            producer,
        )
        return PermissionCheckResponse(
            allowed=False,
            role="",
            resource_type=resource_type,
            action=action,
            scope="",
            reason=reason,
        )

    @staticmethod
    def _matches(expected: str, actual: str) -> bool:
        return expected in {"*", actual}

    @staticmethod
    def _workspace_matches(
        assignment_workspace_id: UUID | None,
        requested_workspace_id: UUID | None,
        scope: str,
    ) -> bool:
        if scope == "global":
            return assignment_workspace_id is None
        if requested_workspace_id is None:
            return assignment_workspace_id is None
        if assignment_workspace_id is None:
            return True
        return assignment_workspace_id == requested_workspace_id


rbac_engine = RBACEngine()
