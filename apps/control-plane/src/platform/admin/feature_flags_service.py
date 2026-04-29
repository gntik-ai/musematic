from __future__ import annotations

import json
from dataclasses import dataclass
from platform.admin.audit_utils import append_admin_audit
from platform.audit.service import AuditChainService
from platform.common.exceptions import NotFoundError, ValidationError
from typing import Any, Final, Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

FeatureFlagScope = Literal["global", "tenant", "workspace", "user"]

FEATURE_FLAG_DEFAULTS: Final[dict[str, bool]] = {
    "FEATURE_SIGNUP_ENABLED": True,
    "FEATURE_SIGNUP_REQUIRES_APPROVAL": False,
    "FEATURE_SOCIAL_LOGIN_ENABLED": True,
    "FEATURE_MAINTENANCE_MODE": False,
    "FEATURE_API_RATE_LIMITING": True,
    "FEATURE_DLP_ENABLED": True,
    "FEATURE_COST_HARD_CAPS": True,
    "FEATURE_CONTENT_MODERATION": True,
    "FEATURE_IMPERSONATION_ENABLED": True,
    "FEATURE_TWO_PERSON_AUTHORIZATION": True,
    "FEATURE_READ_ONLY_ADMIN_MODE": True,
}


@dataclass(frozen=True, slots=True)
class FeatureFlagRecord:
    key: str
    enabled: bool
    scope: FeatureFlagScope
    scope_id: UUID | None
    inherited: bool


class FeatureFlagsService:
    def __init__(self, session: AsyncSession, audit_chain: AuditChainService) -> None:
        self.session = session
        self.audit_chain = audit_chain

    async def list_flags(
        self,
        *,
        scope: FeatureFlagScope = "global",
        scope_id: UUID | None = None,
    ) -> list[FeatureFlagRecord]:
        self._validate_scope(scope, scope_id)
        rows = await self._list_scope_rows(scope, scope_id)
        global_rows = rows if scope == "global" else await self._list_scope_rows("global", None)
        explicit = {str(row["key"]): bool((row["value"] or {}).get("enabled")) for row in rows}
        global_values = {
            str(row["key"]): bool((row["value"] or {}).get("enabled")) for row in global_rows
        }
        records: list[FeatureFlagRecord] = []
        for key, default in FEATURE_FLAG_DEFAULTS.items():
            if key in explicit:
                enabled = explicit[key]
                inherited = False
            else:
                enabled = global_values.get(key, default)
                inherited = scope != "global"
            records.append(
                FeatureFlagRecord(
                    key=key,
                    enabled=enabled,
                    scope=scope,
                    scope_id=scope_id,
                    inherited=inherited,
                )
            )
        return records

    async def set_flag(
        self,
        *,
        key: str,
        enabled: bool,
        scope: FeatureFlagScope,
        scope_id: UUID | None,
        actor: dict[str, Any],
    ) -> FeatureFlagRecord:
        self._validate_flag_key(key)
        self._validate_scope(scope, scope_id)
        old_row = await self._get_row(key, scope, scope_id)
        old_enabled = (
            bool((old_row["value"] or {}).get("enabled")) if old_row is not None else None
        )
        value = {"enabled": enabled}
        if old_row is None:
            await self.session.execute(
                text(
                    """
                    INSERT INTO platform_settings (key, value, scope, scope_id)
                    VALUES (:key, CAST(:value AS jsonb), :scope, :scope_id)
                    """
                ),
                {
                    "key": key,
                    "value": json.dumps(value),
                    "scope": scope,
                    "scope_id": scope_id,
                },
            )
        else:
            await self.session.execute(
                text(
                    """
                    UPDATE platform_settings
                    SET value = CAST(:value AS jsonb), updated_at = now()
                    WHERE id = :id
                    """
                ),
                {"id": old_row["id"], "value": json.dumps(value)},
            )
        await append_admin_audit(
            self.audit_chain,
            event_type="admin.feature_flag.updated",
            actor=actor,
            payload={
                "feature_flag": key,
                "scope": scope,
                "scope_id": None if scope_id is None else str(scope_id),
                "diff": {"enabled": {"before": old_enabled, "after": enabled}},
            },
        )
        return FeatureFlagRecord(
            key=key,
            enabled=enabled,
            scope=scope,
            scope_id=scope_id,
            inherited=False,
        )

    async def delete_override(
        self,
        *,
        key: str,
        scope: FeatureFlagScope,
        scope_id: UUID | None,
        actor: dict[str, Any],
    ) -> None:
        self._validate_flag_key(key)
        self._validate_scope(scope, scope_id)
        row = await self._get_row(key, scope, scope_id)
        if row is None:
            raise NotFoundError(
                "FEATURE_FLAG_OVERRIDE_NOT_FOUND",
                "Feature flag override not found",
            )
        await self.session.execute(
            text("DELETE FROM platform_settings WHERE id = :id"),
            {"id": row["id"]},
        )
        await append_admin_audit(
            self.audit_chain,
            event_type="admin.feature_flag.deleted",
            actor=actor,
            payload={
                "feature_flag": key,
                "scope": scope,
                "scope_id": None if scope_id is None else str(scope_id),
                "diff": {"enabled": {"before": (row["value"] or {}).get("enabled"), "after": None}},
            },
        )

    async def _list_scope_rows(
        self,
        scope: FeatureFlagScope,
        scope_id: UUID | None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT id, key, value, scope, scope_id
            FROM platform_settings
            WHERE key = ANY(:keys)
              AND scope = :scope
              AND ((:scope_id IS NULL AND scope_id IS NULL) OR scope_id = :scope_id)
        """
        result = await self.session.execute(
            text(query),
            {"keys": list(FEATURE_FLAG_DEFAULTS), "scope": scope, "scope_id": scope_id},
        )
        return [dict(row) for row in result.mappings()]

    async def _get_row(
        self,
        key: str,
        scope: FeatureFlagScope,
        scope_id: UUID | None,
    ) -> dict[str, Any] | None:
        result = await self.session.execute(
            text(
                """
                SELECT id, key, value, scope, scope_id
                FROM platform_settings
                WHERE key = :key
                  AND scope = :scope
                  AND ((:scope_id IS NULL AND scope_id IS NULL) OR scope_id = :scope_id)
                LIMIT 1
                FOR UPDATE
                """
            ),
            {"key": key, "scope": scope, "scope_id": scope_id},
        )
        row = result.mappings().first()
        return None if row is None else dict(row)

    @staticmethod
    def _validate_flag_key(key: str) -> None:
        if key not in FEATURE_FLAG_DEFAULTS:
            raise ValidationError("UNKNOWN_FEATURE_FLAG", f"Unsupported feature flag: {key}")

    @staticmethod
    def _validate_scope(scope: str, scope_id: UUID | None) -> None:
        if scope not in {"global", "tenant", "workspace", "user"}:
            raise ValidationError("INVALID_FEATURE_FLAG_SCOPE", "Invalid feature flag scope")
        if scope == "global" and scope_id is not None:
            raise ValidationError("INVALID_FEATURE_FLAG_SCOPE", "Global flags cannot have scope_id")
        if scope != "global" and scope_id is None:
            raise ValidationError("INVALID_FEATURE_FLAG_SCOPE", "Scoped flags require scope_id")
