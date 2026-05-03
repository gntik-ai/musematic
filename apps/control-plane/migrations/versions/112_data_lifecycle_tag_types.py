"""Extend entity_tags + entity_labels CHECK constraints to accept the
three new data_lifecycle entity types.

Per constitutional rule 14, every new entity type that can carry tags
or labels MUST be registered with the polymorphic ``entity_tags`` /
``entity_labels`` substrate (UPD-082). The CHECK constraints
installed by ``065_tags_labels_saved_views`` enumerate the allowed
``entity_type`` values; this migration extends both lists with:

  - ``data_export_job``
  - ``deletion_job``
  - ``sub_processor``

Service-layer registration with ``ENTITY_TYPES`` (the Python tuple
read by tagging-substrate filters) is updated via a separate code
patch — the runtime tagging service imports ``ENTITY_TYPES`` and
forwards to filter helpers, so the source of truth for the constant
must move in lockstep with the DB CHECK constraint.

Revision ID: 112_data_lifecycle_tag_types
Revises: 111_data_lifecycle
Create Date: 2026-05-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "112_data_lifecycle_tag_types"
down_revision: str | None = "111_data_lifecycle"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PRIOR_TYPES = (
    "workspace",
    "agent",
    "fleet",
    "workflow",
    "policy",
    "certification",
    "evaluation_run",
)
NEW_TYPES = (
    "data_export_job",
    "deletion_job",
    "sub_processor",
)
ALL_TYPES = PRIOR_TYPES + NEW_TYPES


def _entity_type_check() -> str:
    """Render the CHECK clause body matching the substrate convention."""

    quoted = ",".join(f"'{t}'" for t in ALL_TYPES)
    return f"entity_type IN ({quoted})"


def upgrade() -> None:
    op.drop_constraint("ck_entity_tags_entity_type", "entity_tags", type_="check")
    op.drop_constraint(
        "ck_entity_labels_entity_type", "entity_labels", type_="check"
    )
    op.create_check_constraint(
        "ck_entity_tags_entity_type",
        "entity_tags",
        _entity_type_check(),
    )
    op.create_check_constraint(
        "ck_entity_labels_entity_type",
        "entity_labels",
        _entity_type_check(),
    )


def downgrade() -> None:
    quoted = ",".join(f"'{t}'" for t in PRIOR_TYPES)
    prior_check = f"entity_type IN ({quoted})"
    op.drop_constraint("ck_entity_tags_entity_type", "entity_tags", type_="check")
    op.drop_constraint(
        "ck_entity_labels_entity_type", "entity_labels", type_="check"
    )
    op.create_check_constraint(
        "ck_entity_tags_entity_type", "entity_tags", prior_check
    )
    op.create_check_constraint(
        "ck_entity_labels_entity_type", "entity_labels", prior_check
    )
