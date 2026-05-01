"""Link cost attributions to billing subscriptions.

Revision ID: 104_cost_attributions_subscription_id
Revises: 103_billing_plans_subscriptions_usage_overage
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "104_cost_attributions_subscription_id"
down_revision: str | None = "103_billing_plans_subscriptions_usage_overage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cost_attributions",
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "cost_attributions_subscription_idx",
        "cost_attributions",
        ["subscription_id"],
    )


def downgrade() -> None:
    op.drop_index("cost_attributions_subscription_idx", table_name="cost_attributions")
    op.drop_column("cost_attributions", "subscription_id")
