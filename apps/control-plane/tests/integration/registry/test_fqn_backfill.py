from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from helpers import make_async_database_url, run_alembic


async def test_fqn_backfill_migration_is_idempotent_and_marks_short_purposes(
    postgres_container,
) -> None:
    database_url = make_async_database_url(postgres_container.get_connection_url())
    run_alembic(database_url, "upgrade", "040_simulation_digital_twins")

    engine = create_async_engine(database_url, future=True)
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    ALTER TABLE registry_agent_profiles
                    ALTER COLUMN namespace_id DROP NOT NULL,
                    ALTER COLUMN local_name DROP NOT NULL,
                    ALTER COLUMN fqn DROP NOT NULL
                    """
                )
            )

            workspace_id = await connection.scalar(text("SELECT gen_random_uuid()"))
            creator_id = await connection.scalar(text("SELECT gen_random_uuid()"))
            finance_namespace_id = await connection.scalar(text("SELECT gen_random_uuid()"))
            legacy_one_id = await connection.scalar(text("SELECT gen_random_uuid()"))
            legacy_two_id = await connection.scalar(text("SELECT gen_random_uuid()"))
            existing_agent_id = await connection.scalar(text("SELECT gen_random_uuid()"))

            await connection.execute(
                text(
                    """
                    INSERT INTO registry_namespaces (
                        id,
                        workspace_id,
                        name,
                        created_by
                    ) VALUES (
                        :namespace_id,
                        :workspace_id,
                        'finance',
                        :creator_id
                    )
                    """
                ),
                {
                    "namespace_id": finance_namespace_id,
                    "workspace_id": workspace_id,
                    "creator_id": creator_id,
                },
            )

            for agent_id, display_name, purpose in (
                (
                    legacy_one_id,
                    "old agent",
                    "This legacy purpose is intentionally long enough to avoid reindexing.",
                ),
                (
                    legacy_two_id,
                    "old agent",
                    "too short",
                ),
            ):
                await connection.execute(
                    text(
                        """
                        INSERT INTO registry_agent_profiles (
                            id,
                            workspace_id,
                            namespace_id,
                            local_name,
                            fqn,
                            display_name,
                            purpose,
                            role_types,
                            visibility_agents,
                            visibility_tools,
                            tags,
                            created_by
                        ) VALUES (
                            :agent_id,
                            :workspace_id,
                            NULL,
                            NULL,
                            NULL,
                            :display_name,
                            :purpose,
                            '[]'::jsonb,
                            '[]'::jsonb,
                            '[]'::jsonb,
                            '[]'::jsonb,
                            :creator_id
                        )
                        """
                    ),
                    {
                        "agent_id": agent_id,
                        "workspace_id": workspace_id,
                        "display_name": display_name,
                        "purpose": purpose,
                        "creator_id": creator_id,
                    },
                )

            await connection.execute(
                text(
                    """
                    INSERT INTO registry_agent_profiles (
                        id,
                        workspace_id,
                        namespace_id,
                        local_name,
                        fqn,
                        display_name,
                        purpose,
                        role_types,
                        visibility_agents,
                        visibility_tools,
                        tags,
                        created_by
                    ) VALUES (
                        :agent_id,
                        :workspace_id,
                        :namespace_id,
                        'existing-agent',
                        'finance:existing-agent',
                        'Existing Agent',
                        'This existing agent already has a valid namespace and fqn assigned.',
                        '[]'::jsonb,
                        '[]'::jsonb,
                        '[]'::jsonb,
                        '[]'::jsonb,
                        :creator_id
                    )
                    """
                ),
                {
                    "agent_id": existing_agent_id,
                    "workspace_id": workspace_id,
                    "namespace_id": finance_namespace_id,
                    "creator_id": creator_id,
                },
            )

        run_alembic(database_url, "upgrade", "041_fqn_backfill")

        async with engine.connect() as connection:
            default_namespace_count = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM registry_namespaces
                    WHERE workspace_id = :workspace_id
                      AND name = 'default'
                    """
                ),
                {"workspace_id": workspace_id},
            )
            backfilled_rows = (
                await connection.execute(
                        text(
                            """
                            SELECT display_name, purpose, namespace_id, local_name, fqn, needs_reindex
                            FROM registry_agent_profiles
                            WHERE id IN (:legacy_one_id, :legacy_two_id)
                            ORDER BY display_name, local_name
                            """
                    ),
                    {
                        "legacy_one_id": legacy_one_id,
                        "legacy_two_id": legacy_two_id,
                    },
                )
            ).mappings().all()
            existing_row = (
                await connection.execute(
                    text(
                        """
                        SELECT namespace_id, local_name, fqn
                        FROM registry_agent_profiles
                        WHERE id = :agent_id
                        """
                    ),
                    {"agent_id": existing_agent_id},
                )
            ).mappings().one()

        assert default_namespace_count == 1
        assert [row["local_name"] for row in backfilled_rows] == ["old-agent", "old-agent-2"]
        assert [row["fqn"] for row in backfilled_rows] == [
            "default:old-agent",
            "default:old-agent-2",
        ]
        assert all(row["namespace_id"] is not None for row in backfilled_rows)
        needs_reindex_by_purpose = {row["purpose"]: row["needs_reindex"] for row in backfilled_rows}
        assert (
            needs_reindex_by_purpose[
                "This legacy purpose is intentionally long enough to avoid reindexing."
            ]
            is False
        )
        assert needs_reindex_by_purpose["too short"] is True
        assert existing_row["namespace_id"] == finance_namespace_id
        assert existing_row["local_name"] == "existing-agent"
        assert existing_row["fqn"] == "finance:existing-agent"

        run_alembic(database_url, "upgrade", "041_fqn_backfill")

        async with engine.connect() as connection:
            namespace_count_after_second_run = await connection.scalar(
                text(
                    """
                    SELECT COUNT(*)
                    FROM registry_namespaces
                    WHERE workspace_id = :workspace_id
                      AND name = 'default'
                    """
                ),
                {"workspace_id": workspace_id},
            )
        assert namespace_count_after_second_run == 1
    finally:
        await engine.dispose()
