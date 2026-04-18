"""Backfill registry FQNs and flag short-purpose profiles for reindexing."""

from __future__ import annotations

from alembic import op

revision = "041_fqn_backfill"
down_revision = "040_simulation_digital_twins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO registry_namespaces (
            id,
            workspace_id,
            name,
            created_by,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            legacy.workspace_id,
            'default',
            MIN(legacy.created_by::text)::uuid,
            now(),
            now()
        FROM registry_agent_profiles AS legacy
        WHERE legacy.namespace_id IS NULL
          AND legacy.deleted_at IS NULL
        GROUP BY legacy.workspace_id
        ON CONFLICT (workspace_id, name) DO NOTHING
        """
    )

    op.execute(
        """
        WITH default_namespaces AS (
            SELECT id, workspace_id
            FROM registry_namespaces
            WHERE name = 'default'
        ),
        legacy_candidates AS (
            SELECT
                profile.id AS agent_id,
                profile.workspace_id,
                namespace.id AS default_namespace_id,
                COALESCE(
                    NULLIF(
                        btrim(
                            regexp_replace(
                                lower(
                                    COALESCE(
                                        NULLIF(profile.display_name, ''),
                                        NULLIF(profile.local_name, ''),
                                        'agent'
                                    )
                                ),
                                '[^a-z0-9]+',
                                '-',
                                'g'
                            )
                        ),
                        ''
                    ),
                    'agent'
                ) AS base_slug,
                ROW_NUMBER() OVER (
                    PARTITION BY profile.workspace_id,
                    COALESCE(
                        NULLIF(
                            btrim(
                                regexp_replace(
                                    lower(
                                        COALESCE(
                                            NULLIF(profile.display_name, ''),
                                            NULLIF(profile.local_name, ''),
                                            'agent'
                                        )
                                    ),
                                    '[^a-z0-9]+',
                                    '-',
                                    'g'
                                )
                            ),
                            ''
                        ),
                        'agent'
                    )
                    ORDER BY profile.created_at, profile.id
                ) AS duplicate_rank
            FROM registry_agent_profiles AS profile
            JOIN default_namespaces AS namespace
              ON namespace.workspace_id = profile.workspace_id
            WHERE profile.namespace_id IS NULL
              AND profile.deleted_at IS NULL
        ),
        existing_counts AS (
            SELECT
                profile.workspace_id,
                profile.local_name,
                COUNT(*) AS existing_count
            FROM registry_agent_profiles AS profile
            JOIN default_namespaces AS namespace
              ON namespace.workspace_id = profile.workspace_id
             AND profile.namespace_id = namespace.id
            WHERE profile.deleted_at IS NULL
              AND profile.id NOT IN (SELECT agent_id FROM legacy_candidates)
            GROUP BY profile.workspace_id, profile.local_name
        ),
        ranked_candidates AS (
            SELECT
                legacy.agent_id,
                legacy.default_namespace_id,
                CASE
                    WHEN COALESCE(existing.existing_count, 0) + legacy.duplicate_rank = 1
                        THEN legacy.base_slug
                    ELSE legacy.base_slug
                        || '-'
                        || (
                            COALESCE(existing.existing_count, 0) + legacy.duplicate_rank
                        )::text
                END AS final_local_name
            FROM legacy_candidates AS legacy
            LEFT JOIN existing_counts AS existing
              ON existing.workspace_id = legacy.workspace_id
             AND existing.local_name = legacy.base_slug
        )
        UPDATE registry_agent_profiles AS profile
        SET
            namespace_id = ranked.default_namespace_id,
            local_name = ranked.final_local_name,
            fqn = 'default:' || ranked.final_local_name,
            updated_at = now()
        FROM ranked_candidates AS ranked
        WHERE profile.id = ranked.agent_id
        """
    )

    op.execute(
        """
        UPDATE registry_agent_profiles
        SET
            needs_reindex = true,
            updated_at = now()
        WHERE COALESCE(length(btrim(purpose)), 0) < 50
          AND deleted_at IS NULL
          AND needs_reindex = false
        """
    )


def downgrade() -> None:
    pass
