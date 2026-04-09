from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tests.helpers import make_async_database_url, run_alembic, run_alembic_branches


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return set(await connection.run_sync(lambda sync_conn: inspect(sync_conn).get_table_names()))


async def test_upgrade_head_from_fresh_db(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "head")

    from sqlalchemy.ext.asyncio import create_async_engine

    runtime_engine = create_async_engine(database_url, future=True)
    try:
        tables = await _table_names(runtime_engine)
        assert {
            "agent_namespaces",
            "alembic_version",
            "audit_events",
            "execution_events",
            "memberships",
            "sessions",
            "users",
            "workspaces",
        }.issubset(tables)

        async with runtime_engine.connect() as connection:
            version = await connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert version == "001_initial_schema"
    finally:
        await runtime_engine.dispose()


async def test_downgrade_minus_one(postgres_container) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "head")
    run_alembic(database_url, "downgrade", "-1")

    from sqlalchemy.ext.asyncio import create_async_engine

    runtime_engine = create_async_engine(database_url, future=True)
    try:
        tables = await _table_names(runtime_engine)
        assert "users" not in tables
        # Alembic keeps the alembic_version table but empties it after a full downgrade.
        async with runtime_engine.connect() as connection:
            version_count = await connection.scalar(
                text("SELECT COUNT(*) FROM alembic_version")
            )
        assert version_count == 0
    finally:
        await runtime_engine.dispose()


async def test_append_only_audit_events(async_engine: AsyncEngine) -> None:
    async with async_engine.begin() as connection:
        event_id = await connection.scalar(
            text(
                "INSERT INTO audit_events (event_type, actor_type, action, details) "
                "VALUES ('user.login', 'user', 'login', '{\"ok\": true}'::jsonb) RETURNING id"
            )
        )
        await connection.execute(
            text("UPDATE audit_events SET action = 'mutated' WHERE id = :event_id"),
            {"event_id": event_id},
        )
        action = await connection.scalar(
            text("SELECT action FROM audit_events WHERE id = :event_id"),
            {"event_id": event_id},
        )
    assert action == "login"


async def test_append_only_execution_events(async_engine: AsyncEngine) -> None:
    async with async_engine.begin() as connection:
        event_id = await connection.scalar(
            text(
                "INSERT INTO execution_events (execution_id, event_type, payload, correlation) "
                "VALUES (gen_random_uuid(), 'step.started', '{}'::jsonb, '{}'::jsonb) RETURNING id"
            )
        )
        await connection.execute(
            text("DELETE FROM execution_events WHERE id = :event_id"),
            {"event_id": event_id},
        )
        remaining = await connection.scalar(
            text("SELECT COUNT(*) FROM execution_events WHERE id = :event_id"),
            {"event_id": event_id},
        )
    assert remaining == 1


def test_migration_chain_linear(migrated_database_url: str) -> None:
    output = run_alembic_branches(migrated_database_url)
    assert "Rev:" not in output
