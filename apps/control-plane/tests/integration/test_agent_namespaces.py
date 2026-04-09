from __future__ import annotations

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from platform.common.models import AgentNamespace, User, Workspace


async def _seed_workspace(session, suffix: str) -> tuple[User, Workspace]:
    user = User(email=f"{suffix}@example.com", display_name=suffix)
    session.add(user)
    await session.flush()

    workspace = Workspace(name=f"Workspace {suffix}", owner_id=user.id)
    session.add(workspace)
    await session.flush()
    return user, workspace


@pytest.mark.asyncio
async def test_namespace_unique_name_constraint(session_factory) -> None:
    async with session_factory() as session:
        first_user, first_workspace = await _seed_workspace(session, "first")
        second_user, second_workspace = await _seed_workspace(session, "second")

        session.add(
            AgentNamespace(
                name="finance-ops",
                workspace_id=first_workspace.id,
                created_by=first_user.id,
            )
        )
        await session.commit()

        session.add(
            AgentNamespace(
                name="finance-ops",
                workspace_id=second_workspace.id,
                created_by=second_user.id,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_namespace_created_with_workspace_link(session_factory) -> None:
    async with session_factory() as session:
        user, workspace = await _seed_workspace(session, "linked")
        namespace = AgentNamespace(
            name="ops-linked",
            workspace_id=workspace.id,
            created_by=user.id,
            description="Operations namespace",
        )
        session.add(namespace)
        await session.commit()

        result = await session.execute(
            select(AgentNamespace).where(AgentNamespace.id == namespace.id)
        )
        stored = result.scalar_one()

    assert stored.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_fqn_pattern_documented(async_engine) -> None:
    async with async_engine.connect() as connection:
        unique_constraints = await connection.run_sync(
            lambda sync_conn: inspect(sync_conn).get_unique_constraints("agent_namespaces")
        )

    assert any(
        constraint["column_names"] == ["name"] for constraint in unique_constraints
    )
