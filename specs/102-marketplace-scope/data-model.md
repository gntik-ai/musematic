# Data Model — UPD-049 Refresh Pass

**Phase 1 output.** Documents the additive schema change applied by Alembic migration 109 and the resulting state machine. The 099 baseline data model is documented at `specs/099-marketplace-scope/data-model.md` and is unchanged here — the refresh adds **one column** and **one partial index**.

---

## Schema delta

UPD-049 refresh is **additive** — no new tables, no dropped columns, no renamed columns. All changes target the existing `registry_agent_profiles` table.

### `registry_agent_profiles` — column added by migration 109

| Column | Type | Nullable | Default | Notes |
|---|---|---|---|---|
| `assigned_reviewer_user_id` | `UUID` | YES | NULL | FK `users.id ON DELETE SET NULL`. NULL means "unassigned — any platform-staff reviewer can claim." Set by `MarketplaceReviewService.assign`. Cleared by `MarketplaceReviewService.unassign`. Distinct from `reviewed_by_user_id` (the claim marker / final reviewer). |

### Partial index added by migration 109

| Index | Columns | Predicate | Purpose |
|---|---|---|---|
| `registry_agent_profiles_assignee_pending_idx` | `(assigned_reviewer_user_id)` | `WHERE review_status = 'pending_review'` | Cheap "submissions assigned to me" queries (typically <50 rows per reviewer). |

### Foreign keys added

| FK | Target | ON DELETE |
|---|---|---|
| `assigned_reviewer_user_id` | `users.id` | SET NULL |

### Constraints — none added

The 099 CHECK constraints (`registry_agent_profiles_marketplace_scope_check`, `registry_agent_profiles_review_status_check`, `registry_agent_profiles_public_only_default_tenant`) are preserved unchanged. No new CHECK is added because the self-review-prevention rule lives at the service layer (R9 — tenant-of-submitter and tenant-of-reviewer can be different roles, and the constraint expression depends on `created_by` which is in the same row, so a CHECK on `assigned_reviewer_user_id <> created_by` is technically possible — but rejected because reviewers may legitimately self-claim a submission they did NOT author, and the column doubles as claim marker; the cleaner rule is enforced in code).

### RLS policy — unchanged

The `agents_visibility` policy from 099 (migration 108) is preserved verbatim. The new `assigned_reviewer_user_id` column is governed by the same row-level visibility — assignment is a state of the row, not a new visibility dimension.

---

## State machine — assignment dimension (new)

The 099 review status state machine (`draft → pending_review → approved/rejected → published → deprecated`) is preserved unchanged. The refresh adds an **orthogonal** assignment dimension on rows in `pending_review`:

```text
                        ┌──────────────────────────────────────┐
                        │ assigned_reviewer_user_id IS NULL    │
                        │ (Unassigned — anyone can claim)      │
                        └──────────────────────────────────────┘
                                    │            ▲
                              assign()      unassign()
                                    │            │
                                    ▼            │
                        ┌──────────────────────────────────────┐
                        │ assigned_reviewer_user_id = R        │
                        │ (Assigned to reviewer R)             │
                        └──────────────────────────────────────┘
```

### Transitions

| From | To | Action | Constraints |
|---|---|---|---|
| Unassigned | Assigned to R | `assign(agent_id, R, assigner)` | Only platform-staff with `assign_marketplace_review`. Refused if `R == created_by` (self-review). Idempotent if already assigned to `R`. Refused with 409 if assigned to a different reviewer (lead must `unassign` first). |
| Assigned to R | Unassigned | `unassign(agent_id, assigner)` | Only platform-staff with `assign_marketplace_review`. Idempotent. |
| Assigned to R | Assigned to R' | `unassign` then `assign` | Two separate calls, each audited. No single-step reassignment endpoint by design — explicit two-step keeps the audit trail clear. |

### Interaction with claim

The 099 `claim(agent_id, reviewer_id)` semantics are preserved with one new guard:

- If `assigned_reviewer_user_id IS NULL`: claim succeeds for any platform-staff reviewer (today's behaviour).
- If `assigned_reviewer_user_id IS NOT NULL AND assigned_reviewer_user_id == reviewer_id`: claim succeeds.
- If `assigned_reviewer_user_id IS NOT NULL AND assigned_reviewer_user_id != reviewer_id`: claim raises `ReviewerAssignmentConflictError` (HTTP 409).

This prevents claim-jumping while preserving today's anyone-can-claim workflow when assignment is not used.

### Self-review guard (cross-cutting)

`SelfReviewNotAllowedError` (HTTP 403, code `self_review_not_allowed`) is raised by:

- `assign(agent_id, reviewer, assigner)` if `reviewer == created_by(agent_id)`
- `claim(agent_id, reviewer_id)` if `reviewer_id == created_by(agent_id)`
- `approve(agent_id, reviewer_id, ...)` if `reviewer_id == created_by(agent_id)`
- `reject(agent_id, reviewer_id, ...)` if `reviewer_id == created_by(agent_id)`

Each refusal emits a `marketplace.review.self_review_attempted` audit-chain entry with both user IDs and the action verb. **No Kafka event** for refusals — refusals are diagnostics, not state changes.

---

## Entities — refresh-relevant fields only

### AgentProfile (extended)

The full schema (28 columns from 099 + 1 from this refresh) lives at `apps/control-plane/src/platform/registry/models.py`. Refresh-relevant fields:

```python
class AgentProfile(Base):
    # ... existing 099 fields ...
    marketplace_scope: Mapped[str]          # 099: 'workspace' | 'tenant' | 'public_default_tenant'
    review_status: Mapped[str]              # 099: draft|pending_review|approved|rejected|published|deprecated
    reviewed_at: Mapped[datetime | None]    # 099
    reviewed_by_user_id: Mapped[UUID | None]  # 099 — claim marker / final reviewer
    review_notes: Mapped[str | None]        # 099
    forked_from_agent_id: Mapped[UUID | None]  # 099
    assigned_reviewer_user_id: Mapped[UUID | None]  # NEW (102) — queue assignment
```

### MarketplaceReviewSubmission (logical projection)

Read-model surfaced by `MarketplaceReviewService.list_queue` (already at `apps/control-plane/src/platform/marketplace/review_service.py:52`). Refresh adds these projection fields:

| Field | Source | Purpose |
|---|---|---|
| `assigned_reviewer_user_id` | `registry_agent_profiles.assigned_reviewer_user_id` | UI badge "Assigned to {name}" |
| `assigned_reviewer_email` | `users.email LEFT JOIN` | UI display |
| `is_self_authored` | computed: `created_by == current_user.id` | UI hides approve/reject for self-authored items |

### KafkaEvents (additive to 099 set)

| Event type | Topic | Producer | Consumer |
|---|---|---|---|
| `marketplace.review.assigned` | `marketplace.events` | `MarketplaceReviewService.assign` | audit, notifications (assignee inbox), analytics |
| `marketplace.review.unassigned` | `marketplace.events` | `MarketplaceReviewService.unassign` | audit, notifications (former-assignee inbox), analytics |

Self-review-attempted refusals do **not** emit a Kafka event (audit-chain only, per R9).

### AuditChainEntries (additive kinds)

| Entry kind | When emitted | Fields |
|---|---|---|
| `marketplace.review.assigned` | On `assign` | `assigner_user_id`, `assignee_user_id`, `agent_id`, `submitter_user_id`, `prior_assignee_user_id` (NULL for fresh assign) |
| `marketplace.review.unassigned` | On `unassign` | `assigner_user_id`, `prior_assignee_user_id`, `agent_id` |
| `marketplace.review.self_review_attempted` | On any refused self-review action | `actor_user_id`, `submitter_user_id`, `agent_id`, `action` (one of `assign`, `claim`, `approve`, `reject`) |

---

## Migration outline (109)

`apps/control-plane/migrations/versions/109_marketplace_reviewer_assignment.py`:

```python
"""Add reviewer-assignment column to registry_agent_profiles.

Revision ID: 109_marketplace_reviewer_assignment
Revises: 108_marketplace_scope_and_review
Create Date: 2026-05-03
"""

from alembic import op
import sqlalchemy as sa

revision = "109_marketplace_reviewer_assignment"
down_revision = "108_marketplace_scope_and_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Column
    op.add_column(
        "registry_agent_profiles",
        sa.Column(
            "assigned_reviewer_user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    # 2. FK
    op.create_foreign_key(
        "registry_agent_profiles_assigned_reviewer_user_fk",
        "registry_agent_profiles",
        "users",
        ["assigned_reviewer_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    # 3. Partial index
    op.create_index(
        "registry_agent_profiles_assignee_pending_idx",
        "registry_agent_profiles",
        ["assigned_reviewer_user_id"],
        postgresql_where=sa.text("review_status = 'pending_review'"),
    )


def downgrade() -> None:
    op.drop_index("registry_agent_profiles_assignee_pending_idx", table_name="registry_agent_profiles")
    op.drop_constraint(
        "registry_agent_profiles_assigned_reviewer_user_fk",
        "registry_agent_profiles",
        type_="foreignkey",
    )
    op.drop_column("registry_agent_profiles", "assigned_reviewer_user_id")
```

The migration is idempotent under `make migrate` and reversible under `make migrate-rollback`. RLS policy `agents_visibility` is unchanged.
