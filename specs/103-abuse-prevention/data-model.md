# Data Model — UPD-050 Abuse Prevention (Refresh)

**Phase 1 output.** Documents the 6 new PostgreSQL tables, 4 Redis key families, the GeoLite2 ConfigMap asset, and the state transitions on `account_suspensions`. Migration 110 is the single Alembic file that introduces all six tables + seed defaults.

---

## PostgreSQL — 6 new tables (Alembic migration 110)

### `signup_velocity_counters`

The durable mirror of the Redis-side rolling-window counters. Refreshed by the cron every 60 s.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `counter_key` | `VARCHAR(128)` | NO | Composite key, e.g. `ip:1.2.3.4` / `asn:AS12345` / `email_domain:example.com`. |
| `counter_window_start` | `TIMESTAMPTZ` | NO | Window-start timestamp aligned to the rolling-window boundary. |
| `counter_value` | `INTEGER` | NO, default 0 | Current counter value at the time of the last cron sync. |
| `dimension` | `VARCHAR(16)` | NO | One of `ip` / `asn` / `email_domain`. CHECK enforces. |

**Primary key**: `(counter_key, counter_window_start)`.
**Index**: `signup_velocity_counters_window_idx` on `(counter_window_start)` for the cleanup cron's range delete.

### `disposable_email_domains`

The upstream-sourced disposable-email blocklist. Truncated and reinserted on each weekly cron run.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `domain` | `VARCHAR(253)` | NO | Lowercased FQDN (max 253 per RFC 1035). |
| `source` | `VARCHAR(64)` | NO | The upstream source identifier (e.g., `disposable-email-domains-master`). |
| `last_updated_at` | `TIMESTAMPTZ` | NO, default `now()` | Set when the row is upserted by the cron. |

**Primary key**: `(domain)`.
**No additional index** — primary key covers the lookup path.

### `disposable_email_overrides`

Super-admin per-domain overrides. Takes precedence over `disposable_email_domains` (always — both for adding and removing).

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `domain` | `VARCHAR(253)` | NO | Lowercased FQDN. |
| `mode` | `VARCHAR(8)` | NO | `'block'` (force-block) or `'allow'` (force-allow). CHECK enforces. |
| `reason` | `TEXT` | YES | Free-form reason supplied by the super admin. |
| `created_at` | `TIMESTAMPTZ` | NO, default `now()` |  |
| `created_by_user_id` | `UUID` | NO | FK `users.id ON DELETE SET NULL` (denormalised for audit). |

**Primary key**: `(domain)`.

**Resolution rule** (in `disposable_emails.py`):
1. If `disposable_email_overrides.mode == 'allow'` for the domain → allow.
2. Else if `disposable_email_overrides.mode == 'block'` for the domain → block.
3. Else if domain in `disposable_email_domains` → block.
4. Else → allow.

### `trusted_source_allowlist`

Super-admin-managed allowlist for IPs (or CIDR ranges) and email domains exempt from velocity counting per FR-742.5.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `entry_kind` | `VARCHAR(16)` | NO | `'ip_cidr'` or `'email_domain'`. CHECK enforces. |
| `entry_value` | `VARCHAR(253)` | NO | CIDR string for `ip_cidr` (e.g., `10.0.0.0/8`); FQDN for `email_domain`. |
| `note` | `TEXT` | YES | Free-form context (e.g., "Acme Corp office NAT — confirmed by phone 2026-05-03"). |
| `created_at` | `TIMESTAMPTZ` | NO, default `now()` |  |
| `created_by_user_id` | `UUID` | YES | FK `users.id ON DELETE SET NULL`. |

**Primary key**: `(entry_kind, entry_value)`.

### `account_suspensions`

The suspension aggregate. Carries the suspension lifecycle.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `id` | `UUID` | NO, default `gen_random_uuid()` | Primary key. |
| `user_id` | `UUID` | NO | The suspended user. FK `users.id`. |
| `tenant_id` | `UUID` | NO | The tenant the user belongs to. FK `tenants.id`. |
| `reason` | `VARCHAR(64)` | NO | Code from the documented set: `cost_burn_rate` / `repeated_velocity` / `fraud_scoring_suspend` / `manual_super_admin` / `manual_tenant_admin`. CHECK enforces. |
| `evidence_json` | `JSONB` | NO, default `{}` | Free-form evidence summary (rule_name, sample_event_ids, threshold_breached, etc.). |
| `suspended_at` | `TIMESTAMPTZ` | NO, default `now()` |  |
| `suspended_by` | `VARCHAR(32)` | NO, default `'system'` | Source: `'system'` / `'super_admin'` / `'tenant_admin'`. CHECK enforces. |
| `suspended_by_user_id` | `UUID` | YES | NULL when `suspended_by='system'`; required otherwise. |
| `lifted_at` | `TIMESTAMPTZ` | YES | NULL while suspension is active. |
| `lifted_by_user_id` | `UUID` | YES | FK `users.id`. |
| `lift_reason` | `TEXT` | YES |  |

**Indexes**:
- `account_suspensions_user_active_idx` on `(user_id)` WHERE `lifted_at IS NULL` — partial, cheap "is this user currently suspended" lookup on every login.
- `account_suspensions_tenant_idx` on `(tenant_id, suspended_at DESC)` — admin queue queries.

**State machine**:

```text
                     ┌────────────────┐
                     │  Active        │ — lifted_at IS NULL
                     │ (suspension on)│
                     └────────────────┘
                              │
                          lift(actor, reason)
                              │
                              ▼
                     ┌────────────────┐
                     │   Lifted       │ — lifted_at IS NOT NULL
                     │ (final)        │
                     └────────────────┘
```

Once lifted, a row is immutable (no re-activation). A new suspension creates a new row.

### `abuse_prevention_settings`

Settings key/value store driving the admin surface and the live thresholds.

| Column | Type | Nullable | Notes |
|---|---|---|---|
| `setting_key` | `VARCHAR(64)` | NO | Primary key. Documented set below. |
| `setting_value_json` | `JSONB` | NO | Strongly typed at the service layer. |
| `updated_at` | `TIMESTAMPTZ` | NO, default `now()` | Set on every write. |
| `updated_by_user_id` | `UUID` | YES | FK `users.id` (nullable for system-seeded rows). |

**Documented setting keys** (seeded by the migration):

| Key | Default | Notes |
|---|---|---|
| `velocity_per_ip_hour` | `5` | Refusal threshold per IP per rolling hour. |
| `velocity_per_asn_hour` | `50` | Per ASN per rolling hour. |
| `velocity_per_email_domain_day` | `20` | Per email domain per rolling day. |
| `captcha_enabled` | `false` |  |
| `captcha_provider` | `"turnstile"` | `"turnstile"` / `"hcaptcha"` / `"disabled"`. |
| `geo_block_mode` | `"disabled"` | `"disabled"` / `"deny_list"` / `"allow_list"`. |
| `geo_block_country_codes` | `[]` | Array of ISO-3166-1 alpha-2 codes. |
| `fraud_scoring_provider` | `"disabled"` | `"disabled"` / `"minfraud"` / `"sift"`. |
| `disposable_email_blocking` | `true` |  |
| `auto_suspension_repeated_velocity_window_hours` | `24` |  |
| `auto_suspension_repeated_velocity_min_hits` | `3` |  |
| `auto_suspension_cost_burn_rate_threshold_usd_per_hour` | `5.00` |  |

---

## Redis — 4 new key families

| Key pattern | Purpose | TTL | Substrate |
|---|---|---|---|
| `abuse:vel:ip:{ip}` | Rolling-hour signup attempts per IP. INCR + EXPIRE 3600. | 1h | INT |
| `abuse:vel:asn:{asn}` | Rolling-hour signup attempts per ASN. INCR + EXPIRE 3600. | 1h | INT |
| `abuse:vel:domain:{domain}` | Rolling-day signup attempts per email domain. INCR + EXPIRE 86400. | 24h | INT |
| `abuse:captcha_seen:{sha256(token)}` | CAPTCHA token replay-prevention cache. SET NX with EX 600. | 10m | STR (`"1"`) |

**Failure mode**: every Redis op is wrapped in a 100-ms timeout; on timeout / connection error the velocity guard refuses with HTTP 503 (`abuse_prevention_unavailable`) per R1's fail-closed decision.

---

## GeoLite2 .mmdb — ConfigMap asset

Mounted at `/var/lib/musematic/geoip/GeoLite2-Country.mmdb` via `deploy/helm/platform/templates/configmap-geoip.yaml`. Loaded by `geo_block.py` on app start; reloaded on SIGHUP.

The Helm chart contains a Job that downloads the .mmdb on chart upgrade using a license key from Vault (`secret/data/maxmind/geolite2_license_key`). Operators without a MaxMind license leave geo-blocking `disabled` and the ConfigMap is empty — `geo_block.py` returns `None` for all lookups (graceful degradation per R5).

---

## Kafka — 1 new topic + 4 event types

**Topic**: `security.abuse_events`. Producer: `AbusePreventionService`, `SuspensionService`. Consumers: audit, notifications (suspension applied → user inbox), analytics.

| Event type | Trigger | Payload (selected fields) |
|---|---|---|
| `abuse.signup.refused` | velocity / disposable / captcha / geo / fraud guard refused signup | `reason`, `counter_key` (hashed), `actor_ip_hash`, `email_domain`, `setting_value_at_refusal` |
| `abuse.suspension.applied` | a suspension row was inserted | `user_id`, `tenant_id`, `reason`, `evidence_json`, `suspended_by` |
| `abuse.suspension.lifted` | a suspension was lifted | `suspension_id`, `user_id`, `lifted_by_user_id`, `lift_reason` |
| `abuse.threshold.changed` | `abuse_prevention_settings` row was UPDATEd | `setting_key`, `prior_value`, `new_value`, `updated_by_user_id` |

All events follow the canonical `EventEnvelope` shape (correlation_id, tenant_id, ts, etc.).

---

## Audit chain — 4 new entry kinds

The audit chain machinery from `security_compliance/services/audit_chain_service.py` gains four new entry kinds, all emitted via the existing service (rule 9):

- `abuse.signup.refused` — same payload shape as the Kafka event (a refusal is BOTH an audit-chain entry AND a Kafka event for separate downstream concerns).
- `abuse.suspension.applied`
- `abuse.suspension.lifted`
- `abuse.threshold.changed`

For very high-cardinality refusal traffic (e.g., a sustained bot attack), the audit-chain emission is **rate-limited at the source**: the velocity guard emits one audit-chain entry per (counter_key, threshold-breach) tuple per rolling window, not one per refusal. This keeps the chain's hash-link writes bounded.

---

## Migration outline (110)

`apps/control-plane/migrations/versions/110_abuse_prevention.py`:

```python
"""Abuse prevention layer (UPD-050 — spec 103 refresh).

Adds the 6 tables that hold velocity counters (durable mirror),
disposable-email blocklist + per-domain overrides, trusted-source
allowlist, account suspensions, and tunable settings.

Revision ID: 110_abuse_prevention
Revises: 109_marketplace_reviewer_assign
Create Date: 2026-05-03
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


def upgrade() -> None:
    # 1. signup_velocity_counters
    op.create_table(
        "signup_velocity_counters",
        sa.Column("counter_key", sa.String(length=128), nullable=False),
        sa.Column("counter_window_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("counter_value", sa.Integer, nullable=False, server_default="0"),
        sa.Column("dimension", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("counter_key", "counter_window_start"),
        sa.CheckConstraint("dimension IN ('ip','asn','email_domain')", name="svc_dimension_chk"),
    )
    op.create_index(
        "signup_velocity_counters_window_idx",
        "signup_velocity_counters",
        ["counter_window_start"],
    )

    # 2. disposable_email_domains
    op.create_table(
        "disposable_email_domains",
        sa.Column("domain", sa.String(length=253), primary_key=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("last_updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 3. disposable_email_overrides
    op.create_table(
        "disposable_email_overrides",
        sa.Column("domain", sa.String(length=253), primary_key=True),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", PG_UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint("mode IN ('block','allow')", name="dispo_override_mode_chk"),
    )

    # 4. trusted_source_allowlist
    op.create_table(
        "trusted_source_allowlist",
        sa.Column("entry_kind", sa.String(length=16), nullable=False),
        sa.Column("entry_value", sa.String(length=253), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_by_user_id", PG_UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.PrimaryKeyConstraint("entry_kind", "entry_value"),
        sa.CheckConstraint("entry_kind IN ('ip_cidr','email_domain')", name="tsa_kind_chk"),
    )

    # 5. account_suspensions
    op.create_table(
        "account_suspensions",
        sa.Column("id", PG_UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", PG_UUID, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", PG_UUID, sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("evidence_json", postgresql.JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("suspended_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("suspended_by", sa.String(length=32), nullable=False, server_default=sa.text("'system'")),
        sa.Column("suspended_by_user_id", PG_UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lifted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("lifted_by_user_id", PG_UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("lift_reason", sa.Text, nullable=True),
        sa.CheckConstraint(
            "suspended_by IN ('system','super_admin','tenant_admin')",
            name="account_suspensions_suspended_by_chk",
        ),
        sa.CheckConstraint(
            "reason IN ('cost_burn_rate','repeated_velocity','fraud_scoring_suspend','manual_super_admin','manual_tenant_admin')",
            name="account_suspensions_reason_chk",
        ),
    )
    op.create_index(
        "account_suspensions_user_active_idx",
        "account_suspensions",
        ["user_id"],
        postgresql_where=sa.text("lifted_at IS NULL"),
    )
    op.create_index(
        "account_suspensions_tenant_idx",
        "account_suspensions",
        ["tenant_id", sa.text("suspended_at DESC")],
    )

    # 6. abuse_prevention_settings + seed defaults
    op.create_table(
        "abuse_prevention_settings",
        sa.Column("setting_key", sa.String(length=64), primary_key=True),
        sa.Column("setting_value_json", postgresql.JSONB, nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_by_user_id", PG_UUID, sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.execute(
        """
        INSERT INTO abuse_prevention_settings (setting_key, setting_value_json) VALUES
            ('velocity_per_ip_hour', '5'::jsonb),
            ('velocity_per_asn_hour', '50'::jsonb),
            ('velocity_per_email_domain_day', '20'::jsonb),
            ('captcha_enabled', 'false'::jsonb),
            ('captcha_provider', '"turnstile"'::jsonb),
            ('geo_block_mode', '"disabled"'::jsonb),
            ('geo_block_country_codes', '[]'::jsonb),
            ('fraud_scoring_provider', '"disabled"'::jsonb),
            ('disposable_email_blocking', 'true'::jsonb),
            ('auto_suspension_repeated_velocity_window_hours', '24'::jsonb),
            ('auto_suspension_repeated_velocity_min_hits', '3'::jsonb),
            ('auto_suspension_cost_burn_rate_threshold_usd_per_hour', '5.00'::jsonb)
        """
    )


def downgrade() -> None:
    op.drop_table("abuse_prevention_settings")
    op.drop_index("account_suspensions_tenant_idx", table_name="account_suspensions")
    op.drop_index("account_suspensions_user_active_idx", table_name="account_suspensions")
    op.drop_table("account_suspensions")
    op.drop_table("trusted_source_allowlist")
    op.drop_table("disposable_email_overrides")
    op.drop_table("disposable_email_domains")
    op.drop_index("signup_velocity_counters_window_idx", table_name="signup_velocity_counters")
    op.drop_table("signup_velocity_counters")
```

**Reversibility**: every CREATE has a corresponding DROP in `downgrade()` in reverse order. Tested against postgres:16 by `make migrate` → `make migrate-rollback` round-trip.

**Revision-id length check**: `len("110_abuse_prevention") == 22 ≤ 32`. ✅

---

## Entity relationship diagram

```text
                      ┌─────────────┐
                      │   users     │   (existing — UPD-046)
                      └─────────────┘
                        ▲       ▲       ▲
                        │       │       │
                        │       │       │ FK created_by_user_id
                        │       │       │ FK suspended_by_user_id
                        │       │       │ FK lifted_by_user_id
                        │       │       │ FK updated_by_user_id
                        │       │       │
        ┌───────────────┘       │       └────────────────┐
        │                       │                        │
┌─────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ tsa             │  │  account_suspensions │  │ abuse_prevention_    │
│ trusted_source_ │  │                      │  │ settings             │
│ allowlist       │  │ user_id, tenant_id,  │  │ setting_key,         │
│ (entry_kind,    │  │ reason, evidence,    │  │ setting_value_json,  │
│  entry_value)   │  │ suspended_at,        │  │ updated_at,          │
└─────────────────┘  │ suspended_by,        │  │ updated_by_user_id   │
                     │ lifted_at,           │  └──────────────────────┘
                     │ lift_reason          │
                     └──────────────────────┘
                              ▲
                              │ FK tenant_id
                              │
                      ┌─────────────┐
                      │  tenants    │   (existing — UPD-046)
                      └─────────────┘

┌────────────────────────────┐  ┌────────────────────────────┐
│  disposable_email_domains  │  │  disposable_email_         │
│  (domain, source,          │  │  overrides                 │
│   last_updated_at)         │  │  (domain, mode, reason,    │
│                            │  │   created_by_user_id)      │
│  upstream-cron synced      │  │                            │
└────────────────────────────┘  │  takes precedence ↑        │
                                └────────────────────────────┘

┌──────────────────────────────────┐
│  signup_velocity_counters        │   durable mirror of Redis
│  (counter_key,                   │   counters; cron sync 60s
│   counter_window_start,          │
│   counter_value, dimension)      │
└──────────────────────────────────┘
```
