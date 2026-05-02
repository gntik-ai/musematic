from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession


async def provision_default_plans_if_missing(session: AsyncSession) -> None:
    await session.execute(
        sa.text(
            """
            WITH plan_seed(
                slug,
                display_name,
                description,
                tier,
                is_public,
                allowed_model_tier
            ) AS (
                VALUES
                  (
                    'free',
                    'Free',
                    'Free plan with hard cost-protection quotas.',
                    'free',
                    true,
                    'cheap_only'
                  ),
                  ('pro', 'Pro', 'Professional plan with opt-in overage.', 'pro', true, 'all'),
                  (
                    'enterprise',
                    'Enterprise',
                    'Enterprise plan with tenant-scoped unlimited usage.',
                    'enterprise',
                    false,
                    'all'
                  )
            ),
            inserted_plans AS (
                INSERT INTO plans (
                    slug,
                    display_name,
                    description,
                    tier,
                    is_public,
                    is_active,
                    allowed_model_tier
                )
                SELECT slug, display_name, description, tier, is_public, true, allowed_model_tier
                  FROM plan_seed
                ON CONFLICT (slug) DO NOTHING
                RETURNING id, slug
            ),
            all_plans AS (
                SELECT id, slug FROM inserted_plans
                UNION ALL
                SELECT p.id, p.slug
                  FROM plans p
                  JOIN plan_seed s ON s.slug = p.slug
            ),
            version_seed(
                slug,
                price_monthly,
                executions_per_day,
                executions_per_month,
                minutes_per_day,
                minutes_per_month,
                max_workspaces,
                max_agents_per_workspace,
                max_users_per_workspace,
                overage_price_per_minute,
                trial_days,
                quota_period_anchor
            ) AS (
                VALUES
                  ('free', 0.00, 50, 100, 30, 100, 1, 5, 3, 0.0000, 0, 'calendar_month'),
                  (
                    'pro',
                    49.00,
                    500,
                    5000,
                    240,
                    2400,
                    5,
                    50,
                    25,
                    0.1000,
                    14,
                    'subscription_anniversary'
                  ),
                  (
                    'enterprise',
                    0.00,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0.0000,
                    0,
                    'subscription_anniversary'
                  )
            )
            INSERT INTO plan_versions (
                plan_id,
                version,
                price_monthly,
                executions_per_day,
                executions_per_month,
                minutes_per_day,
                minutes_per_month,
                max_workspaces,
                max_agents_per_workspace,
                max_users_per_workspace,
                overage_price_per_minute,
                trial_days,
                quota_period_anchor,
                published_at
            )
            SELECT DISTINCT ON (p.id)
                p.id,
                1,
                v.price_monthly,
                v.executions_per_day,
                v.executions_per_month,
                v.minutes_per_day,
                v.minutes_per_month,
                v.max_workspaces,
                v.max_agents_per_workspace,
                v.max_users_per_workspace,
                v.overage_price_per_minute,
                v.trial_days,
                v.quota_period_anchor,
                now()
              FROM all_plans p
              JOIN version_seed v ON v.slug = p.slug
            ON CONFLICT (plan_id, version) DO NOTHING
            """
        )
    )
    await session.flush()
