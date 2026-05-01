from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_103_billing_schema_tables_seed_and_rls(async_engine: AsyncEngine) -> None:
    async with async_engine.connect() as connection:
        table_names = set(
            await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        )
        assert {
            "plans",
            "plan_versions",
            "subscriptions",
            "usage_records",
            "overage_authorizations",
            "processed_event_ids",
        }.issubset(table_names)

        columns = {
            table: {
                column["name"]
                for column in await connection.run_sync(
                    lambda sync, table=table: inspect(sync).get_columns(table)
                )
            }
            for table in {
                "plans",
                "plan_versions",
                "subscriptions",
                "usage_records",
                "overage_authorizations",
                "processed_event_ids",
            }
        }
        assert {"slug", "tier", "is_public", "allowed_model_tier"}.issubset(
            columns["plans"]
        )
        assert {"plan_id", "version", "published_at", "deprecated_at"}.issubset(
            columns["plan_versions"]
        )
        assert {"tenant_id", "scope_type", "scope_id", "plan_id", "plan_version"}.issubset(
            columns["subscriptions"]
        )
        assert {"tenant_id", "workspace_id", "subscription_id", "metric"}.issubset(
            columns["usage_records"]
        )

        rls_rows = (
            await connection.execute(
                text(
                    """
                    SELECT relname, relrowsecurity, relforcerowsecurity
                      FROM pg_class
                     WHERE relname IN (
                        'subscriptions',
                        'usage_records',
                        'overage_authorizations'
                     )
                    """
                )
            )
        ).mappings()
        assert {
            row["relname"]: (row["relrowsecurity"], row["relforcerowsecurity"])
            for row in rls_rows
        } == {
            "subscriptions": (True, True),
            "usage_records": (True, True),
            "overage_authorizations": (True, True),
        }

        seeded_slugs = set(
            (
                await connection.execute(
                    text(
                        """
                        SELECT p.slug
                          FROM plans p
                          JOIN plan_versions pv ON pv.plan_id = p.id
                         WHERE pv.version = 1 AND pv.published_at IS NOT NULL
                        """
                    )
                )
            ).scalars()
        )
        assert seeded_slugs == {"free", "pro", "enterprise"}

        default_workspace_count = await connection.scalar(
            text(
                """
                SELECT count(*)
                  FROM workspaces_workspaces w
                  JOIN tenants t ON t.id = w.tenant_id
                 WHERE t.kind = 'default'
                """
            )
        )
        backfilled_count = await connection.scalar(
            text(
                """
                SELECT count(*)
                  FROM subscriptions s
                  JOIN tenants t ON t.id = s.tenant_id
                 WHERE t.kind = 'default' AND s.scope_type = 'workspace'
                """
            )
        )
        assert backfilled_count == default_workspace_count
