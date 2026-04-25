"""model_catalog: catalogue, fallback, credentials, injection patterns."""

from __future__ import annotations

from uuid import UUID

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "059_model_catalog"
down_revision = "058_security_compliance"
branch_labels = None
depends_on = None

PG_UUID = postgresql.UUID(as_uuid=True)
SYSTEM_BOOTSTRAP_USER_ID = UUID("00000000-0000-0000-0000-000000000075")


def upgrade() -> None:
    _ensure_system_bootstrap_user()
    _create_catalog_table()
    _create_cards_table()
    _create_fallback_policies_table()
    _create_provider_credentials_table()
    _create_injection_patterns_table()
    _extend_agent_profiles()
    _seed_catalogue_entries()
    _seed_injection_patterns()


def downgrade() -> None:
    op.drop_column("registry_agent_profiles", "default_model_binding")
    op.drop_table("injection_defense_patterns")
    op.drop_table("model_provider_credentials")
    op.drop_table("model_fallback_policies")
    op.drop_table("model_cards")
    op.drop_table("model_catalog_entries")


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", PG_UUID, nullable=False, server_default=sa.text("gen_random_uuid()"))


def _now_column(name: str = "created_at") -> sa.Column[object]:
    return sa.Column(
        name,
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.text("now()"),
    )


def _ensure_system_bootstrap_user() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO users (id, email, display_name, status)
            VALUES (:id, 'system_bootstrap@musematic.ai', 'System Bootstrap', 'active')
            ON CONFLICT (email) DO NOTHING
            """
        ).bindparams(sa.bindparam("id", SYSTEM_BOOTSTRAP_USER_ID, type_=PG_UUID))
    )


def _create_catalog_table() -> None:
    op.create_table(
        "model_catalog_entries",
        _uuid_pk(),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_id", sa.String(length=256), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("approved_use_cases", postgresql.JSONB(), nullable=True),
        sa.Column("prohibited_use_cases", postgresql.JSONB(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("input_cost_per_1k_tokens", sa.Numeric(10, 6), nullable=False),
        sa.Column("output_cost_per_1k_tokens", sa.Numeric(10, 6), nullable=False),
        sa.Column("quality_tier", sa.String(length=16), nullable=False),
        sa.Column("approved_by", PG_UUID, nullable=False),
        sa.Column(
            "approved_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("approval_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'approved'"),
        ),
        _now_column(),
        _now_column("updated_at"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "model_id", name="uq_model_catalog_provider_model"),
        sa.CheckConstraint("context_window > 0", name="ck_model_catalog_context_window"),
        sa.CheckConstraint(
            "input_cost_per_1k_tokens >= 0",
            name="ck_model_catalog_input_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "output_cost_per_1k_tokens >= 0",
            name="ck_model_catalog_output_cost_nonnegative",
        ),
        sa.CheckConstraint(
            "quality_tier IN ('tier1', 'tier2', 'tier3')",
            name="ck_model_catalog_quality_tier",
        ),
        sa.CheckConstraint(
            "status IN ('approved', 'deprecated', 'blocked')",
            name="ck_model_catalog_status",
        ),
        sa.CheckConstraint(
            "approval_expires_at > approved_at",
            name="ck_model_catalog_approval_expiry",
        ),
    )
    op.create_index(
        "ix_model_catalog_status_expires",
        "model_catalog_entries",
        ["status", "approval_expires_at"],
    )


def _create_cards_table() -> None:
    op.create_table(
        "model_cards",
        _uuid_pk(),
        sa.Column("catalog_entry_id", PG_UUID, nullable=False),
        sa.Column("capabilities", sa.Text(), nullable=True),
        sa.Column("training_cutoff", sa.Date(), nullable=True),
        sa.Column("known_limitations", sa.Text(), nullable=True),
        sa.Column("safety_evaluations", postgresql.JSONB(), nullable=True),
        sa.Column("bias_assessments", postgresql.JSONB(), nullable=True),
        sa.Column("card_url", sa.Text(), nullable=True),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        _now_column(),
        _now_column("updated_at"),
        sa.ForeignKeyConstraint(
            ["catalog_entry_id"],
            ["model_catalog_entries.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("catalog_entry_id", name="uq_model_cards_catalog_entry_id"),
    )


def _create_fallback_policies_table() -> None:
    op.create_table(
        "model_fallback_policies",
        _uuid_pk(),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", PG_UUID, nullable=True),
        sa.Column("primary_model_id", PG_UUID, nullable=False),
        sa.Column("fallback_chain", postgresql.JSONB(), nullable=False),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="3"),
        sa.Column(
            "backoff_strategy",
            sa.String(length=32),
            nullable=False,
            server_default="exponential",
        ),
        sa.Column(
            "acceptable_quality_degradation",
            sa.String(length=16),
            nullable=False,
            server_default="tier_plus_one",
        ),
        sa.Column(
            "recovery_window_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
        _now_column(),
        sa.ForeignKeyConstraint(["primary_model_id"], ["model_catalog_entries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "scope_type IN ('global', 'workspace', 'agent')",
            name="ck_model_fallback_scope_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'global' AND scope_id IS NULL) OR "
            "(scope_type != 'global' AND scope_id IS NOT NULL)",
            name="ck_model_fallback_scope_id",
        ),
        sa.CheckConstraint("retry_count > 0 AND retry_count <= 10", name="ck_model_fallback_retry"),
        sa.CheckConstraint(
            "backoff_strategy IN ('fixed', 'linear', 'exponential')",
            name="ck_model_fallback_backoff",
        ),
        sa.CheckConstraint(
            "acceptable_quality_degradation IN "
            "('tier_equal', 'tier_plus_one', 'tier_plus_two')",
            name="ck_model_fallback_quality_degradation",
        ),
        sa.CheckConstraint(
            "recovery_window_seconds >= 30",
            name="ck_model_fallback_recovery_window",
        ),
    )
    op.create_index("ix_fallback_scope", "model_fallback_policies", ["scope_type", "scope_id"])
    op.create_index("ix_fallback_primary", "model_fallback_policies", ["primary_model_id"])


def _create_provider_credentials_table() -> None:
    op.create_table(
        "model_provider_credentials",
        _uuid_pk(),
        sa.Column("workspace_id", PG_UUID, nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("vault_ref", sa.String(length=256), nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotation_schedule_id", PG_UUID, nullable=True),
        _now_column(),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces_workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["rotation_schedule_id"],
            ["secret_rotation_schedules.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "provider",
            name="uq_model_provider_workspace_provider",
        ),
    )


def _create_injection_patterns_table() -> None:
    op.create_table(
        "injection_defense_patterns",
        _uuid_pk(),
        sa.Column("pattern_name", sa.String(length=128), nullable=False),
        sa.Column("pattern_regex", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("layer", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("seeded", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("workspace_id", PG_UUID, nullable=True),
        _now_column(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces_workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="ck_injection_pattern_severity",
        ),
        sa.CheckConstraint(
            "layer IN ('input_sanitizer', 'output_validator')",
            name="ck_injection_pattern_layer",
        ),
        sa.CheckConstraint(
            "action IN ('strip', 'quote_as_data', 'reject', 'redact', 'block')",
            name="ck_injection_pattern_action",
        ),
    )
    op.create_index(
        "ix_injection_patterns_layer",
        "injection_defense_patterns",
        ["layer", "workspace_id", "severity"],
    )


def _extend_agent_profiles() -> None:
    op.add_column(
        "registry_agent_profiles",
        sa.Column("default_model_binding", sa.String(length=128), nullable=True),
    )


def _seed_catalogue_entries() -> None:
    entries = [
        ("openai", "gpt-4o", "GPT-4o", "tier1", 128000, "0.005000", "0.015000"),
        ("openai", "gpt-4o-mini", "GPT-4o Mini", "tier2", 128000, "0.000150", "0.000600"),
        (
            "anthropic",
            "claude-opus-4-6",
            "Claude Opus 4.6",
            "tier1",
            200000,
            "0.015000",
            "0.075000",
        ),
        (
            "anthropic",
            "claude-sonnet-4-6",
            "Claude Sonnet 4.6",
            "tier1",
            200000,
            "0.003000",
            "0.015000",
        ),
        (
            "anthropic",
            "claude-haiku-4-5",
            "Claude Haiku 4.5",
            "tier2",
            200000,
            "0.000800",
            "0.004000",
        ),
        ("google", "gemini-2.0-pro", "Gemini 2.0 Pro", "tier1", 2000000, "0.002500", "0.010000"),
    ]
    values = ",\n".join(
        "('{provider}', '{model_id}', '{display_name}', '{tier}', {context}, "
        "{input_cost}, {output_cost})".format(
            provider=provider,
            model_id=model_id,
            display_name=display_name.replace("'", "''"),
            tier=tier,
            context=context,
            input_cost=input_cost,
            output_cost=output_cost,
        )
        for provider, model_id, display_name, tier, context, input_cost, output_cost in entries
    )
    op.execute(
        sa.text(
            f"""
            INSERT INTO model_catalog_entries (
                provider, model_id, display_name, quality_tier, context_window,
                input_cost_per_1k_tokens, output_cost_per_1k_tokens, approved_by,
                approved_at, approval_expires_at, approved_use_cases, prohibited_use_cases
            )
            SELECT provider, model_id, display_name, quality_tier, context_window,
                   input_cost_per_1k_tokens::numeric, output_cost_per_1k_tokens::numeric,
                   :approved_by, now(), now() + interval '90 days',
                   '["general reasoning", "agent orchestration"]'::jsonb,
                   '["credential exfiltration", "policy bypass"]'::jsonb
            FROM (VALUES
                {values}
            ) AS seed(provider, model_id, display_name, quality_tier, context_window,
                      input_cost_per_1k_tokens, output_cost_per_1k_tokens)
            ON CONFLICT (provider, model_id) DO NOTHING
            """
        ).bindparams(sa.bindparam("approved_by", SYSTEM_BOOTSTRAP_USER_ID, type_=PG_UUID))
    )


def _seed_injection_patterns() -> None:
    patterns = [
        (
            "role_reversal",
            r"(?i)ignore\s+(all\s+)?(previous|above)\s+instructions",
            "high",
            "input_sanitizer",
            "reject",
        ),
        (
            "instruction_injection",
            r"(?i)you\s+are\s+now\s+",
            "high",
            "input_sanitizer",
            "quote_as_data",
        ),
        (
            "developer_override",
            r"(?i)(system|developer)\s+message\s*:",
            "high",
            "input_sanitizer",
            "quote_as_data",
        ),
        (
            "delimiter_escape",
            r"(?i)(```|</?system>|</?assistant>)",
            "medium",
            "input_sanitizer",
            "quote_as_data",
        ),
        (
            "jailbreak_dan",
            r"(?i)do\s+anything\s+now|\\bDAN\\b",
            "high",
            "input_sanitizer",
            "reject",
        ),
        (
            "prompt_leak",
            r"(?i)(repeat|print|show)\s+(your\s+)?(system|hidden)\s+prompt",
            "high",
            "input_sanitizer",
            "reject",
        ),
        (
            "tool_exfiltration",
            r"(?i)(send|exfiltrate|upload).*(secret|token|key)",
            "critical",
            "input_sanitizer",
            "reject",
        ),
        (
            "credential_request",
            r"(?i)(api[_ -]?key|password|secret|token)\s*[:=]",
            "high",
            "input_sanitizer",
            "strip",
        ),
        (
            "base64_blob",
            r"(?i)[A-Za-z0-9+/]{80,}={0,2}",
            "medium",
            "input_sanitizer",
            "quote_as_data",
        ),
        (
            "markdown_link_exfil",
            r"(?i)\[[^]]+\]\((https?://[^)]+)\)",
            "medium",
            "input_sanitizer",
            "quote_as_data",
        ),
        (
            "jwt_detection",
            r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            "critical",
            "output_validator",
            "redact",
        ),
        ("bearer_token", r"Bearer\s+[A-Za-z0-9_\-.=]+", "critical", "output_validator", "redact"),
        ("api_key_prefix", r"msk_[A-Za-z0-9]{32,}", "critical", "output_validator", "redact"),
        ("openai_key", r"sk-[A-Za-z0-9]{32,}", "critical", "output_validator", "redact"),
        ("aws_access_key", r"AKIA[0-9A-Z]{16}", "critical", "output_validator", "redact"),
        (
            "private_key",
            r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
            "critical",
            "output_validator",
            "block",
        ),
        (
            "email_exfiltration",
            r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
            "medium",
            "output_validator",
            "redact",
        ),
        ("ssn_like", r"\b\d{3}-\d{2}-\d{4}\b", "high", "output_validator", "redact"),
        ("credit_card_like", r"\b(?:\d[ -]*?){13,19}\b", "high", "output_validator", "redact"),
        (
            "role_reversal_output",
            r"(?i)as\s+an\s+unrestricted\s+assistant",
            "high",
            "output_validator",
            "block",
        ),
        (
            "policy_bypass_output",
            r"(?i)i\s+can\s+bypass\s+the\s+policy",
            "high",
            "output_validator",
            "block",
        ),
    ]
    table = sa.table(
        "injection_defense_patterns",
        sa.column("pattern_name", sa.String),
        sa.column("pattern_regex", sa.Text),
        sa.column("severity", sa.String),
        sa.column("layer", sa.String),
        sa.column("action", sa.String),
        sa.column("seeded", sa.Boolean),
    )
    op.bulk_insert(
        table,
        [
            {
                "pattern_name": name,
                "pattern_regex": regex,
                "severity": severity,
                "layer": layer,
                "action": action,
                "seeded": True,
            }
            for name, regex, severity, layer, action in patterns
        ],
    )
