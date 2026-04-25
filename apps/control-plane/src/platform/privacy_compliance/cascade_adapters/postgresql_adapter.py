from __future__ import annotations

from datetime import UTC, datetime
from platform.privacy_compliance.cascade_adapters.base import (
    CascadeAdapter,
    CascadePlan,
    CascadeResult,
)
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DELETED_SUBJECT_UUID = "00000000-0000-0000-0000-000000000000"

USER_IDENTITY_COLUMNS: dict[str, list[str]] = {
    "users": ["id"],
    "agent_namespaces": ["created_by"],
    "debug_logging_sessions": ["requested_by"],
    "memberships": ["user_id"],
    "sessions": ["user_id"],
    "workspaces": ["owner_id"],
    "user_credentials": ["user_id"],
    "mfa_enrollments": ["user_id"],
    "oauth_audit_entries": ["user_id"],
    "oauth_links": ["user_id"],
    "user_roles": ["user_id"],
    "auth_attempts": ["user_id"],
    "accounts_users": ["user_id", "suspended_by", "blocked_by", "archived_by"],
    "invitations": ["user_id", "inviter_id", "consumed_by_user_id", "revoked_by"],
    "approval_requests": ["user_id", "reviewer_id"],
    "workspaces_workspaces": ["owner_id"],
    "workspaces_memberships": ["user_id"],
    "workspaces_goals": ["created_by"],
    "interactions_conversations": ["created_by"],
    "interactions_interactions": ["participant_user_id"],
    "execution_executions": ["created_by"],
    "execution_reprioritization_triggers": ["created_by"],
    "evaluation_eval_sets": ["created_by"],
    "evaluation_rubrics": ["created_by"],
    "evaluation_calibration_runs": ["created_by"],
    "evaluation_ate_configs": ["created_by"],
    "evaluation_human_ai_grades": ["reviewer_id"],
    "registry_namespaces": ["created_by"],
    "registry_agent_profiles": ["created_by"],
    "policies_policy_versions": ["created_by"],
    "policies_attachments": ["created_by"],
    "mcp_server_registrations": ["created_by"],
    "mcp_exposed_tools": ["created_by"],
    "memory_knowledge_nodes": ["created_by"],
    "composition_requests": ["requested_by"],
    "fleet_learning_cross_fleet_transfers": ["approved_by"],
    "agentops_cicd_gate_results": ["requested_by"],
    "agentops_adaptation_proposals": ["revoked_by"],
    "marketplace_ratings": ["user_id"],
    "marketplace_recommendations": ["user_id"],
    "notifications_user_alerts": ["user_id"],
    "notifications_alert_settings": ["user_id"],
    "notification_channel_configs": ["user_id"],
    "outbound_webhooks": ["created_by"],
    "webhook_deliveries": ["replayed_by", "resolved_by"],
    "user_alerts": ["user_id"],
    "user_alert_settings": ["user_id"],
    "vulnerability_exceptions": ["approved_by"],
    "jit_credential_grants": ["user_id", "approved_by", "revoked_by"],
    "compliance_evidence": ["uploaded_by"],
    "model_catalog_entries": ["approved_by"],
    "privacy_dsr_requests": ["subject_user_id", "requested_by"],
    "privacy_impact_assessments": ["submitted_by", "approved_by"],
    "privacy_consent_records": ["user_id"],
    "a2a_external_endpoints": ["created_by"],
}


DELETE_ROW_COLUMNS = {"id", "user_id", "participant_user_id"}


class PostgreSQLCascadeAdapter(CascadeAdapter):
    store_name = "postgresql"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._column_cache: dict[str, set[str]] = {}

    async def dry_run(self, subject_user_id: UUID) -> CascadePlan:
        estimates: dict[str, int] = {}
        for table, columns in USER_IDENTITY_COLUMNS.items():
            available_columns = await self._available_columns(table, columns)
            estimates[table] = (
                await self._count_table(table, available_columns, subject_user_id)
                if available_columns
                else 0
            )
        return CascadePlan(
            store_name=self.store_name,
            estimated_count=sum(estimates.values()),
            per_target_estimates=estimates,
        )

    async def execute(self, subject_user_id: UUID) -> CascadeResult:
        started = datetime.now(UTC)
        counts: dict[str, int] = {}
        errors: list[str] = []
        await self._ensure_sentinel_user()
        for table, columns in reversed(list(USER_IDENTITY_COLUMNS.items())):
            try:
                available_columns = await self._available_columns(table, columns)
                counts[table] = (
                    await self._mutate_table(table, available_columns, subject_user_id)
                    if available_columns
                    else 0
                )
            except Exception as exc:
                errors.append(f"{table}: {exc}")
                counts[table] = 0
        await self.session.flush()
        return CascadeResult(
            store_name=self.store_name,
            started_at=started,
            completed_at=datetime.now(UTC),
            affected_count=sum(counts.values()),
            per_target_counts=counts,
            errors=errors,
        )

    async def _available_columns(self, table: str, columns: list[str]) -> list[str]:
        if table not in self._column_cache:
            result = await self.session.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                    AND table_name = :table
                    """
                ),
                {"table": table},
            )
            self._column_cache[table] = {str(column) for column in result.scalars().all()}
        existing = self._column_cache[table]
        return [column for column in columns if column in existing]

    async def _ensure_sentinel_user(self) -> None:
        await self.session.execute(
            text(
                """
                INSERT INTO users (id, email, display_name, status)
                VALUES (:id, :email, :display_name, :status)
                ON CONFLICT (id) DO NOTHING
                """
            ),
            {
                "id": DELETED_SUBJECT_UUID,
                "email": "deleted-subject@musematic.local",
                "display_name": "Deleted subject",
                "status": "archived",
            },
        )

    async def _count_table(self, table: str, columns: list[str], subject_user_id: UUID) -> int:
        predicates = " OR ".join(f"{column} = :uid" for column in columns)
        result = await self.session.execute(
            text(f"SELECT count(*) FROM {table} WHERE {predicates}"),
            {"uid": str(subject_user_id)},
        )
        return int(result.scalar_one())

    async def _mutate_table(self, table: str, columns: list[str], subject_user_id: UUID) -> int:
        delete_columns = [column for column in columns if column in DELETE_ROW_COLUMNS]
        if delete_columns:
            predicates = " OR ".join(f"{column} = :uid" for column in delete_columns)
            result = await self.session.execute(
                text(f"DELETE FROM {table} WHERE {predicates}"),
                {"uid": str(subject_user_id)},
            )
            return _rowcount(result)

        assignments = ", ".join(f"{column} = :sentinel" for column in columns)
        predicates = " OR ".join(f"{column} = :uid" for column in columns)
        result = await self.session.execute(
            text(f"UPDATE {table} SET {assignments} WHERE {predicates}"),
            {"uid": str(subject_user_id), "sentinel": DELETED_SUBJECT_UUID},
        )
        return _rowcount(result)


def _rowcount(result: object) -> int:
    value = getattr(result, "rowcount", 0)
    return int(value or 0)
