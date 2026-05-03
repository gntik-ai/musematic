"""Abuse-prevention layer (UPD-050) — settings, disposable-email registry,
trusted source allowlist, velocity counters, account suspensions.

Adds 6 new tables that back the abuse-prevention bounded context per
``specs/100-abuse-prevention/data-model.md``:

* ``abuse_prevention_settings`` (key/value with 12 seed rows)
* ``disposable_email_domains`` (curated list, seeded with the small inline
  sample below; the full ~1500-domain seed is loaded asynchronously by the
  weekly sync cron the first time it runs)
* ``disposable_email_overrides`` (super-admin exceptions)
* ``trusted_source_allowlist`` (IP/ASN bypass)
* ``signup_velocity_counters`` (durable snapshot of Redis counters)
* ``account_suspensions`` (suspension lifecycle aggregate)

The ``account_suspensions.reason`` and ``suspended_by`` columns each
carry CHECK constraints over a documented enum-of-strings (data-model.md
Reason enum). The ``as_user_active_idx`` partial index keeps the
login-path point lookup cheap.

Revision ID: 110_abuse_prevention
Revises: 109_marketplace_reviewer_assign
Create Date: 2026-05-02
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "110_abuse_prevention"
down_revision: str | None = "109_marketplace_reviewer_assign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PG_UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB(astext_type=sa.Text())

REASON_ENUM_VALUES = (
    "velocity_repeat",
    "fraud_score",
    "cost_burn_rate",
    "disposable_email_pattern",
    "captcha_replay",
    "geo_violation",
    "manual",
    "tenant_admin",
)
SUSPENDED_BY_VALUES = ("system", "super_admin", "tenant_admin")
TRUSTED_KIND_VALUES = ("ip", "asn")

# Seed values for `abuse_prevention_settings`. Mirrored from
# specs/100-abuse-prevention/data-model.md.
SEED_SETTINGS = (
    ("velocity_per_ip_hour", "5"),
    ("velocity_per_asn_hour", "50"),
    ("velocity_per_email_domain_day", "20"),
    ("captcha_enabled", "false"),
    ('captcha_provider', '"turnstile"'),
    ('geo_block_mode', '"disabled"'),
    ("geo_block_country_codes", "[]"),
    ('fraud_scoring_provider', '"disabled"'),
    ("fraud_scoring_threshold", "75.0"),
    ("disposable_email_blocking", "true"),
    ("auto_suspension_cost_burn_multiplier", "1.5"),
    ("auto_suspension_velocity_repeat_threshold", "3"),
)

# Initial inline seed of disposable-email domains. Small sample — the
# weekly sync cron pulls the full ~1500-domain list from the upstream
# `disposable-email-domains` GitHub project on first run. Keeping this
# inline list small keeps the migration cheap; even with the cron
# disabled, these provide useful day-1 coverage of the most common
# disposable providers.
INITIAL_DISPOSABLE_DOMAINS = (
    "10minutemail.com",
    "guerrillamail.com",
    "guerrillamail.net",
    "mailinator.com",
    "tempmail.com",
    "throwawaymail.com",
    "yopmail.com",
    "trashmail.com",
    "trashmail.net",
    "fakeinbox.com",
    "discard.email",
    "sharklasers.com",
    "spam4.me",
    "tempinbox.com",
    "dispostable.com",
)


def upgrade() -> None:
    # --- 1. abuse_prevention_settings ----------------------------------------
    op.create_table(
        "abuse_prevention_settings",
        sa.Column("setting_key", sa.String(length=64), primary_key=True),
        sa.Column("setting_value_json", JSONB, nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    for key, value_json in SEED_SETTINGS:
        op.execute(
            sa.text(
                "INSERT INTO abuse_prevention_settings (setting_key, setting_value_json) "
                "VALUES (:key, CAST(:value AS jsonb))"
            ).bindparams(key=key, value=value_json)
        )

    # --- 2. disposable_email_domains -----------------------------------------
    op.create_table(
        "disposable_email_domains",
        sa.Column("domain", sa.String(length=253), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column(
            "last_updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "pending_removal_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    for domain in INITIAL_DISPOSABLE_DOMAINS:
        op.execute(
            sa.text(
                "INSERT INTO disposable_email_domains (domain, source) "
                "VALUES (:domain, 'seed')"
            ).bindparams(domain=domain)
        )

    # --- 3. disposable_email_overrides ---------------------------------------
    op.create_table(
        "disposable_email_overrides",
        sa.Column("domain", sa.String(length=253), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
    )

    # --- 4. trusted_source_allowlist -----------------------------------------
    op.create_table(
        "trusted_source_allowlist",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("value", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("kind", "value", name="trusted_source_allowlist_unique"),
    )
    op.create_check_constraint(
        "trusted_source_allowlist_kind_check",
        "trusted_source_allowlist",
        "kind IN ('" + "', '".join(TRUSTED_KIND_VALUES) + "')",
    )

    # --- 5. signup_velocity_counters -----------------------------------------
    op.create_table(
        "signup_velocity_counters",
        sa.Column("counter_key", sa.String(length=128), nullable=False),
        sa.Column(
            "counter_window_start", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column("counter_value", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint(
            "counter_key", "counter_window_start", name="signup_velocity_counters_pkey"
        ),
    )
    op.create_index(
        "svc_window_idx",
        "signup_velocity_counters",
        ["counter_window_start"],
    )

    # --- 6. account_suspensions ----------------------------------------------
    op.create_table(
        "account_suspensions",
        sa.Column(
            "id",
            PG_UUID,
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            PG_UUID,
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            PG_UUID,
            sa.ForeignKey("tenants.id"),
            nullable=False,
        ),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column(
            "evidence_json",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "suspended_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "suspended_by",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column(
            "suspended_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lifted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "lifted_by_user_id",
            PG_UUID,
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("lift_reason", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "account_suspensions_reason_check",
        "account_suspensions",
        "reason IN ('" + "', '".join(REASON_ENUM_VALUES) + "')",
    )
    op.create_check_constraint(
        "account_suspensions_suspended_by_check",
        "account_suspensions",
        "suspended_by IN ('" + "', '".join(SUSPENDED_BY_VALUES) + "')",
    )
    # Partial index for the login-path "active suspension?" point lookup.
    op.create_index(
        "as_user_active_idx",
        "account_suspensions",
        ["user_id"],
        postgresql_where=sa.text("lifted_at IS NULL"),
    )


def downgrade() -> None:
    # Reverse order — drop tables that other tables depend on last.
    op.drop_index("as_user_active_idx", table_name="account_suspensions")
    op.drop_constraint(
        "account_suspensions_suspended_by_check",
        "account_suspensions",
        type_="check",
    )
    op.drop_constraint(
        "account_suspensions_reason_check",
        "account_suspensions",
        type_="check",
    )
    op.drop_table("account_suspensions")
    op.drop_index(
        "svc_window_idx", table_name="signup_velocity_counters"
    )
    op.drop_table("signup_velocity_counters")
    op.drop_constraint(
        "trusted_source_allowlist_kind_check",
        "trusted_source_allowlist",
        type_="check",
    )
    op.drop_table("trusted_source_allowlist")
    op.drop_table("disposable_email_overrides")
    op.drop_table("disposable_email_domains")
    op.drop_table("abuse_prevention_settings")
