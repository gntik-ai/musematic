from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.orm.exc import StaleDataError

from platform.common.models import Membership, User, Workspace


async def _create_user(session, email: str = "user@example.com") -> User:
    user = User(email=email, display_name="User")
    session.add(user)
    await session.flush()
    return user


async def _create_workspace(session, owner: User, name: str = "Workspace") -> Workspace:
    workspace = Workspace(name=name, owner_id=owner.id)
    session.add(workspace)
    await session.flush()
    return workspace


@pytest.mark.asyncio
async def test_uuid_auto_generation_after_flush(session_factory) -> None:
    async with session_factory() as session:
        user = await _create_user(session)
        assert user.id is not None


@pytest.mark.asyncio
async def test_created_at_set_on_insert(session_factory) -> None:
    async with session_factory() as session:
        user = await _create_user(session, "created@example.com")
        assert user.created_at is not None


@pytest.mark.asyncio
async def test_updated_at_changes_on_update_while_created_at_stays_fixed(session_factory) -> None:
    async with session_factory() as session:
        user = await _create_user(session, "updated@example.com")
        created_at = user.created_at
        updated_at = user.updated_at
        user.display_name = "Changed"
        await session.flush()
        assert user.created_at == created_at
        assert user.updated_at >= updated_at


@pytest.mark.asyncio
async def test_is_deleted_false_when_deleted_at_is_none(session_factory) -> None:
    async with session_factory() as session:
        user = await _create_user(session, "active@example.com")
        assert user.is_deleted is False


@pytest.mark.asyncio
async def test_is_deleted_true_after_soft_deletion(session_factory) -> None:
    async with session_factory() as session:
        user = await _create_user(session, "deleted@example.com")
        user.deleted_at = datetime.now(timezone.utc)
        assert user.is_deleted is True


@pytest.mark.asyncio
async def test_filter_deleted_excludes_deleted_records_from_query(session_factory) -> None:
    async with session_factory() as session:
        active_user = await _create_user(session, "kept@example.com")
        deleted_user = await _create_user(session, "gone@example.com")
        deleted_user.deleted_at = datetime.now(timezone.utc)
        await session.flush()

        result = await session.execute(select(User).where(User.filter_deleted()))
        emails = {user.email for user in result.scalars()}

    assert active_user.email in emails
    assert deleted_user.email not in emails


@pytest.mark.asyncio
async def test_filter_deleted_includes_active_records(session_factory) -> None:
    async with session_factory() as session:
        active_user = await _create_user(session, "visible@example.com")
        result = await session.execute(select(User).where(User.filter_deleted()))
        assert active_user in result.scalars().all()


@pytest.mark.asyncio
async def test_version_increments_from_one_to_two_on_update(session_factory) -> None:
    async with session_factory() as session:
        owner = await _create_user(session, "owner@example.com")
        workspace = await _create_workspace(session, owner)
        await session.commit()

    async with session_factory() as session:
        loaded = await session.get(Workspace, workspace.id)
        assert loaded.version == 1
        loaded.name = "Workspace v2"
        await session.commit()
        assert loaded.version == 2


@pytest.mark.asyncio
async def test_stale_data_error_raised_for_concurrent_updates(session_factory) -> None:
    async with session_factory() as session:
        owner = await _create_user(session, "stale@example.com")
        workspace = await _create_workspace(session, owner, "Concurrency")
        await session.commit()

    async with session_factory() as session_one, session_factory() as session_two:
        record_one = await session_one.get(Workspace, workspace.id)
        record_two = await session_two.get(Workspace, workspace.id)

        record_one.name = "First"
        await session_one.commit()

        record_two.name = "Second"
        with pytest.raises(StaleDataError):
            await session_two.commit()


@pytest.mark.asyncio
async def test_records_are_filterable_by_workspace_id(session_factory) -> None:
    async with session_factory() as session:
        owner = await _create_user(session, "scope@example.com")
        workspace = await _create_workspace(session, owner, "Scoped")
        membership = Membership(workspace_id=workspace.id, user_id=owner.id)
        session.add(membership)
        await session.flush()

        result = await session.execute(
            select(Membership).where(Membership.workspace_id == workspace.id)
        )
        memberships = result.scalars().all()

    assert membership in memberships


@pytest.mark.asyncio
async def test_created_by_and_updated_by_nullable_for_bootstrap(session_factory) -> None:
    async with session_factory() as session:
        user = User(email="bootstrap@example.com", display_name="Bootstrap")
        session.add(user)
        await session.flush()
        assert user.created_by is None
        assert user.updated_by is None

