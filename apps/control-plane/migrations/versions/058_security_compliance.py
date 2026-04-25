"""security_compliance: hash chain and compliance substrate."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
import yaml
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "058_security_compliance"
down_revision = "057_api_governance"
branch_labels = None
depends_on = None


UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    _create_audit_chain_table()
    _create_sbom_table()
    _create_vuln_scan_tables()
    _create_pentest_tables()
    _create_rotation_table()
    _create_jit_tables()
    _create_compliance_tables()
    _install_audit_chain_trigger()
    _revoke_mutation_perms()
    _seed_pentest_sla_policies()
    _seed_jit_approver_policies()
    _seed_compliance_frameworks()


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_chain_entries_append_only ON audit_chain_entries")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_chain_mutation()")
    for table in (
        "compliance_evidence",
        "compliance_evidence_mappings",
        "compliance_controls",
        "jit_approver_policies",
        "jit_credential_grants",
        "secret_rotation_schedules",
        "pentest_sla_policies",
        "pentest_findings",
        "penetration_tests",
        "vulnerability_exceptions",
        "vulnerability_scan_results",
        "software_bills_of_materials",
        "audit_chain_entries",
    ):
        op.drop_table(table)


def _uuid_pk() -> sa.Column[object]:
    return sa.Column("id", UUID, nullable=False, server_default=sa.text("gen_random_uuid()"))


def _now_column(name: str = "created_at") -> sa.Column[object]:
    return sa.Column(
        name, sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
    )


def _create_audit_chain_table() -> None:
    op.create_table(
        "audit_chain_entries",
        _uuid_pk(),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("entry_hash", sa.String(length=64), nullable=False),
        sa.Column("audit_event_id", UUID, nullable=True),
        sa.Column("audit_event_source", sa.String(length=64), nullable=False),
        sa.Column("canonical_payload_hash", sa.String(length=64), nullable=False),
        _now_column(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sequence_number", name="uq_audit_chain_entries_sequence_number"),
        sa.UniqueConstraint("entry_hash", name="uq_audit_chain_entries_entry_hash"),
    )
    op.create_index(
        "ix_audit_chain_source_time", "audit_chain_entries", ["audit_event_source", "created_at"]
    )


def _create_sbom_table() -> None:
    op.create_table(
        "software_bills_of_materials",
        _uuid_pk(),
        sa.Column("release_version", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("release_version", "format", name="uq_sbom_release_format"),
        sa.CheckConstraint("format IN ('spdx', 'cyclonedx')", name="ck_sbom_format"),
    )


def _create_vuln_scan_tables() -> None:
    op.create_table(
        "vulnerability_scan_results",
        _uuid_pk(),
        sa.Column("scanner", sa.String(length=64), nullable=False),
        sa.Column("release_version", sa.String(length=64), nullable=False),
        sa.Column("findings", postgresql.JSONB(), nullable=False),
        sa.Column("max_severity", sa.String(length=32), nullable=True),
        sa.Column(
            "scanned_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("gating_result", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "scanner IN "
            "('trivy','grype','pip_audit','npm_audit','govulncheck','bandit','gosec','gitleaks')",
            name="ck_vuln_scan_scanner",
        ),
        sa.CheckConstraint(
            "max_severity IS NULL OR max_severity IN ('critical','high','medium','low','info')",
            name="ck_vuln_scan_max_severity",
        ),
        sa.CheckConstraint("gating_result IN ('passed','blocked')", name="ck_vuln_scan_gate"),
    )
    op.create_index(
        "ix_vuln_scan_release", "vulnerability_scan_results", ["release_version", "scanned_at"]
    )
    op.create_index(
        "ix_vuln_scan_severity", "vulnerability_scan_results", ["max_severity", "gating_result"]
    )
    op.create_table(
        "vulnerability_exceptions",
        _uuid_pk(),
        sa.Column("scanner", sa.String(length=64), nullable=False),
        sa.Column("vulnerability_id", sa.String(length=128), nullable=False),
        sa.Column("component_pattern", sa.String(length=256), nullable=False),
        sa.Column("justification", sa.Text(), nullable=False),
        sa.Column("approved_by", UUID, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        _now_column(),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(justification) >= 20", name="ck_vuln_exception_justification"),
    )
    op.create_index(
        "ix_vuln_exception_active",
        "vulnerability_exceptions",
        ["scanner", "vulnerability_id", "expires_at"],
    )


def _create_pentest_tables() -> None:
    op.create_table(
        "penetration_tests",
        _uuid_pk(),
        sa.Column("scheduled_for", sa.Date(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("firm", sa.String(length=256), nullable=True),
        sa.Column("report_url", sa.Text(), nullable=True),
        sa.Column("attestation_hash", sa.String(length=64), nullable=True),
        _now_column(),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "pentest_findings",
        _uuid_pk(),
        sa.Column("pentest_id", UUID, nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "remediation_status", sa.String(length=32), nullable=False, server_default="open"
        ),
        sa.Column("remediation_due_date", sa.Date(), nullable=False),
        sa.Column("remediated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("remediation_notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["pentest_id"], ["penetration_tests.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low')", name="ck_pentest_finding_severity"
        ),
        sa.CheckConstraint(
            "remediation_status IN ('open','in_progress','remediated','accepted','wont_fix')",
            name="ck_pentest_finding_status",
        ),
    )
    op.create_index(
        "ix_pentest_overdue",
        "pentest_findings",
        ["remediation_status", "remediation_due_date"],
        postgresql_where=sa.text("remediation_status = 'open'"),
    )
    op.create_table(
        "pentest_sla_policies",
        _uuid_pk(),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("max_days", sa.Integer(), nullable=False),
        sa.Column("ceiling_days", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("severity", name="uq_pentest_sla_severity"),
        sa.CheckConstraint(
            "severity IN ('critical','high','medium','low')", name="ck_pentest_sla_severity"
        ),
        sa.CheckConstraint("max_days > 0", name="ck_pentest_sla_max_days"),
    )


def _create_rotation_table() -> None:
    op.create_table(
        "secret_rotation_schedules",
        _uuid_pk(),
        sa.Column("secret_name", sa.String(length=256), nullable=False),
        sa.Column("secret_type", sa.String(length=64), nullable=False),
        sa.Column("rotation_interval_days", sa.Integer(), nullable=False, server_default="90"),
        sa.Column("overlap_window_hours", sa.Integer(), nullable=False, server_default="24"),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_rotation_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overlap_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotation_state", sa.String(length=32), nullable=False, server_default="idle"),
        sa.Column("vault_path", sa.String(length=512), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("secret_name", name="uq_secret_rotation_secret_name"),
        sa.CheckConstraint(
            "rotation_interval_days > 0 AND rotation_interval_days <= 365",
            name="ck_rotation_interval_days",
        ),
        sa.CheckConstraint(
            "overlap_window_hours >= 24 AND overlap_window_hours <= 168",
            name="ck_rotation_overlap_hours",
        ),
        sa.CheckConstraint(
            "rotation_state IN ('idle','rotating','overlap','finalising','failed')",
            name="ck_rotation_state",
        ),
    )
    op.create_index(
        "ix_rotation_due",
        "secret_rotation_schedules",
        ["next_rotation_at"],
        postgresql_where=sa.text("rotation_state = 'idle'"),
    )


def _create_jit_tables() -> None:
    op.create_table(
        "jit_credential_grants",
        _uuid_pk(),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("operation", sa.String(length=256), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("approved_by", UUID, nullable=True),
        _now_column("requested_at"),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_by", UUID, nullable=True),
        sa.Column(
            "usage_audit", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["revoked_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(purpose) >= 20", name="ck_jit_purpose_length"),
        sa.CheckConstraint(
            "status IN ('pending','approved','rejected','expired','revoked')", name="ck_jit_status"
        ),
        sa.CheckConstraint(
            "approved_by IS NULL OR approved_by != user_id", name="ck_jit_no_self_approval"
        ),
    )
    op.create_index(
        "ix_jit_user_status", "jit_credential_grants", ["user_id", "status", "expires_at"]
    )
    op.create_index(
        "ix_jit_pending",
        "jit_credential_grants",
        ["status", "requested_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "jit_approver_policies",
        _uuid_pk(),
        sa.Column("operation_pattern", sa.String(length=256), nullable=False),
        sa.Column("required_roles", postgresql.JSONB(), nullable=False),
        sa.Column("min_approvers", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_expiry_minutes", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("operation_pattern", name="uq_jit_policy_operation_pattern"),
        sa.CheckConstraint(
            "min_approvers > 0 AND min_approvers <= 5", name="ck_jit_policy_min_approvers"
        ),
        sa.CheckConstraint(
            "max_expiry_minutes > 0 AND max_expiry_minutes <= 1440", name="ck_jit_policy_max_expiry"
        ),
    )


def _create_compliance_tables() -> None:
    op.create_table(
        "compliance_controls",
        _uuid_pk(),
        sa.Column("framework", sa.String(length=32), nullable=False),
        sa.Column("control_id", sa.String(length=64), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence_requirements", postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "framework", "control_id", name="uq_compliance_controls_framework_control"
        ),
        sa.CheckConstraint(
            "framework IN ('soc2','iso27001','hipaa','pci_dss')", name="ck_compliance_framework"
        ),
    )
    op.create_table(
        "compliance_evidence_mappings",
        _uuid_pk(),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("control_id", UUID, nullable=False),
        sa.Column("filter_expression", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["control_id"], ["compliance_controls.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mapping_by_evidence", "compliance_evidence_mappings", ["evidence_type"])
    op.create_table(
        "compliance_evidence",
        _uuid_pk(),
        sa.Column("control_id", UUID, nullable=False),
        sa.Column("evidence_type", sa.String(length=64), nullable=False),
        sa.Column("evidence_ref", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("collected_by", UUID, nullable=True),
        sa.ForeignKeyConstraint(["control_id"], ["compliance_controls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["collected_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_by_control", "compliance_evidence", ["control_id", "collected_at"])


def _install_audit_chain_trigger() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_chain_mutation()
        RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'audit_chain_entries is append-only';
            END IF;

            IF NEW.id IS DISTINCT FROM OLD.id
                OR NEW.sequence_number IS DISTINCT FROM OLD.sequence_number
                OR NEW.previous_hash IS DISTINCT FROM OLD.previous_hash
                OR NEW.entry_hash IS DISTINCT FROM OLD.entry_hash
                OR NEW.audit_event_source IS DISTINCT FROM OLD.audit_event_source
                OR NEW.canonical_payload_hash IS DISTINCT FROM OLD.canonical_payload_hash
                OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
                RAISE EXCEPTION 'audit_chain_entries is append-only';
            END IF;

            IF OLD.audit_event_id IS NULL OR NEW.audit_event_id IS NOT NULL THEN
                RAISE EXCEPTION 'audit_chain_entries only allows RTBF nulling of audit_event_id';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_chain_entries_append_only
        BEFORE UPDATE OR DELETE ON audit_chain_entries
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_chain_mutation();
        """
    )


def _revoke_mutation_perms() -> None:
    op.execute("REVOKE UPDATE, DELETE ON audit_chain_entries FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'musematic') THEN
                REVOKE UPDATE, DELETE ON audit_chain_entries FROM musematic;
            END IF;
        END
        $$;
        """
    )


def _seed_pentest_sla_policies() -> None:
    table = sa.table(
        "pentest_sla_policies",
        sa.column("id"),
        sa.column("severity"),
        sa.column("max_days"),
        sa.column("ceiling_days"),
    )
    rows = [
        {"id": uuid4(), "severity": "critical", "max_days": 7, "ceiling_days": 7},
        {"id": uuid4(), "severity": "high", "max_days": 30, "ceiling_days": 30},
        {"id": uuid4(), "severity": "medium", "max_days": 90, "ceiling_days": 90},
        {"id": uuid4(), "severity": "low", "max_days": 180, "ceiling_days": 180},
    ]
    op.bulk_insert(table, rows)


def _seed_jit_approver_policies() -> None:
    table = sa.table(
        "jit_approver_policies",
        sa.column("id"),
        sa.column("operation_pattern"),
        sa.column("required_roles", postgresql.JSONB()),
        sa.column("min_approvers"),
        sa.column("max_expiry_minutes"),
    )
    rows = [
        {
            "id": uuid4(),
            "operation_pattern": "db:prod:*",
            "required_roles": ["platform_admin"],
            "min_approvers": 1,
            "max_expiry_minutes": 60,
        },
        {
            "id": uuid4(),
            "operation_pattern": "infra:prod:*",
            "required_roles": ["platform_admin"],
            "min_approvers": 1,
            "max_expiry_minutes": 60,
        },
        {
            "id": uuid4(),
            "operation_pattern": "customer_data:*",
            "required_roles": ["platform_admin", "trust_reviewer"],
            "min_approvers": 2,
            "max_expiry_minutes": 30,
        },
        {
            "id": uuid4(),
            "operation_pattern": "*",
            "required_roles": ["platform_admin"],
            "min_approvers": 1,
            "max_expiry_minutes": 1440,
        },
    ]
    op.bulk_insert(table, rows)


def _seed_compliance_frameworks() -> None:
    frameworks_dir = (
        Path(__file__).resolve().parents[2] / "src/platform/security_compliance/frameworks"
    )
    control_rows: list[dict[str, object]] = []
    control_ids: dict[str, object] = {}
    for name in ("soc2", "iso27001", "hipaa", "pci_dss"):
        payload = yaml.safe_load((frameworks_dir / f"{name}.yaml").read_text(encoding="utf-8"))
        for item in payload["controls"]:
            row_id = uuid4()
            key = f"{name}:{item['control_id']}"
            control_ids[key] = row_id
            control_rows.append(
                {
                    "id": row_id,
                    "framework": name,
                    "control_id": item["control_id"],
                    "description": item["description"],
                    "evidence_requirements": item.get("evidence_requirements"),
                }
            )
    controls = sa.table(
        "compliance_controls",
        sa.column("id"),
        sa.column("framework"),
        sa.column("control_id"),
        sa.column("description"),
        sa.column("evidence_requirements", postgresql.JSONB()),
    )
    op.bulk_insert(controls, control_rows)

    mappings_payload = yaml.safe_load(
        (frameworks_dir / "mappings.yaml").read_text(encoding="utf-8")
    )
    mapping_rows: list[dict[str, object]] = []
    for mapping in mappings_payload["mappings"]:
        for control_ref in mapping["controls"]:
            mapping_rows.append(
                {
                    "id": uuid4(),
                    "evidence_type": mapping["evidence_type"],
                    "control_id": control_ids[control_ref],
                    "filter_expression": mapping.get("filter_expression"),
                }
            )
    mappings = sa.table(
        "compliance_evidence_mappings",
        sa.column("id"),
        sa.column("evidence_type"),
        sa.column("control_id"),
        sa.column("filter_expression"),
    )
    op.bulk_insert(mappings, mapping_rows)
