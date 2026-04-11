from __future__ import annotations

from platform.auth.rbac import RBACEngine
from platform.auth.repository import AuthRepository
from platform.common.models.user import User
from platform.common.models.workspace import Workspace
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker


@pytest.mark.integration
@pytest.mark.asyncio
async def test_auth_rbac_flow_uses_seeded_permissions(
    session_factory: async_sessionmaker,
    redis_client,
) -> None:
    async with session_factory() as session:
        user = User(email=f"{uuid4()}@example.com", display_name="Viewer", status="active")
        session.add(user)
        await session.flush()
        workspace = Workspace(name="Workspace", owner_id=user.id, settings={})
        session.add(workspace)
        await session.flush()

        repository = AuthRepository(session)
        await repository.assign_user_role(user.id, "viewer", workspace.id)
        await session.commit()

        engine = RBACEngine()
        allowed = await engine.check_permission(
            user_id=user.id,
            resource_type="analytics",
            action="read",
            workspace_id=workspace.id,
            db=session,
            redis_client=redis_client,
        )
        denied = await engine.check_permission(
            user_id=user.id,
            resource_type="analytics",
            action="write",
            workspace_id=workspace.id,
            db=session,
            redis_client=redis_client,
        )

    assert allowed.allowed is True
    assert allowed.role == "viewer"
    assert denied.allowed is False
    assert denied.reason == "rbac_denied"
