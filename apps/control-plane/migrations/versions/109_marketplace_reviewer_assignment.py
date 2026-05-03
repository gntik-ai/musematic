"""Marketplace reviewer-assignment column on registry_agent_profiles.

Refresh pass on 099 baseline (spec 102, UPD-049). Adds the ability for a
platform-staff lead to assign a pending-review submission to a specific
reviewer, distinct from the existing ``reviewed_by_user_id`` column
(which 099 uses as both the in-progress claim marker and the final
reviewer on approve/reject).

Adds:

* ``assigned_reviewer_user_id`` (nullable UUID FK ``users.id`` ON DELETE
  SET NULL). NULL means "unassigned — anyone can claim". Set by
  ``MarketplaceReviewService.assign``; cleared by ``unassign``.
* Partial index ``registry_agent_profiles_assignee_pending_idx`` over
  the new column WHERE ``review_status = 'pending_review'`` so
  "submissions assigned to me" queries stay cheap.

No CHECK constraint on the column — the self-review-prevention rule
(FR-741.9) is enforced at the service + API layers (see
``contracts/self-review-prevention.md``); the column doubles as a
queue-routing dimension and may legitimately equal ``created_by`` only
for the no-op idempotent reassignment path, which the service refuses
explicitly.

Revision ID: 109_marketplace_reviewer_assign
Revises: 108_marketplace_scope_review
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "109_marketplace_reviewer_assign"
down_revision: str | None = "108_marketplace_scope_review"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "registry_agent_profiles",
        sa.Column("assigned_reviewer_user_id", PG_UUID, nullable=True),
    )
    op.create_foreign_key(
        "registry_agent_profiles_assigned_reviewer_user_fk",
        "registry_agent_profiles",
        "users",
        ["assigned_reviewer_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "registry_agent_profiles_assignee_pending_idx",
        "registry_agent_profiles",
        ["assigned_reviewer_user_id"],
        postgresql_where=sa.text("review_status = 'pending_review'"),
    )


def downgrade() -> None:
    op.drop_index(
        "registry_agent_profiles_assignee_pending_idx",
        table_name="registry_agent_profiles",
    )
    op.drop_constraint(
        "registry_agent_profiles_assigned_reviewer_user_fk",
        "registry_agent_profiles",
        type_="foreignkey",
    )
    op.drop_column("registry_agent_profiles", "assigned_reviewer_user_id")
