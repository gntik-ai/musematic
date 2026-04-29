from __future__ import annotations

import json
from platform.admin.audit_utils import append_admin_audit
from platform.admin.feature_flags_service import FEATURE_FLAG_DEFAULTS
from platform.admin.rbac import require_admin
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.dependencies import get_db
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/settings", tags=["admin", "settings"])


class PlatformSettingRead(BaseModel):
    key: str
    value: object
    scope: str = "global"
    scope_id: UUID | None = None


class PlatformSettingsUpdate(BaseModel):
    settings: dict[str, object] = Field(default_factory=dict)


@router.get("", response_model=list[PlatformSettingRead])
async def list_platform_settings(
    _current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> list[PlatformSettingRead]:
    result = await session.execute(
        text(
            """
            SELECT key, value, scope, scope_id
            FROM platform_settings
            WHERE scope = 'global'
              AND scope_id IS NULL
              AND NOT (key = ANY(:feature_flag_keys))
            ORDER BY key ASC
            """
        ),
        {"feature_flag_keys": list(FEATURE_FLAG_DEFAULTS)},
    )
    return [PlatformSettingRead(**dict(row)) for row in result.mappings()]


@router.put("", response_model=list[PlatformSettingRead])
async def update_platform_settings(
    payload: PlatformSettingsUpdate,
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> list[PlatformSettingRead]:
    if not payload.settings:
        return await list_platform_settings(current_user, session)
    existing = await _get_global_settings(session, payload.settings.keys())
    diffs: dict[str, dict[str, object]] = {}
    for key, value in payload.settings.items():
        previous = existing.get(key)
        diffs[key] = {"before": previous, "after": value}
        await _upsert_global_setting(session, key, value)
    await append_admin_audit(
        audit_chain,
        event_type="admin.settings.updated",
        actor=current_user,
        payload={"diff": diffs},
    )
    return await list_platform_settings(current_user, session)


async def _get_global_settings(
    session: AsyncSession,
    keys: Any,
) -> dict[str, object]:
    result = await session.execute(
        text(
            """
            SELECT key, value
            FROM platform_settings
            WHERE key = ANY(:keys)
              AND scope = 'global'
              AND scope_id IS NULL
            FOR UPDATE
            """
        ),
        {"keys": list(keys)},
    )
    return {str(row["key"]): row["value"] for row in result.mappings()}


async def _upsert_global_setting(session: AsyncSession, key: str, value: object) -> None:
    result = await session.execute(
        text(
            """
            UPDATE platform_settings
            SET value = CAST(:value AS jsonb), updated_at = now()
            WHERE key = :key
              AND scope = 'global'
              AND scope_id IS NULL
            """
        ),
        {"key": key, "value": json.dumps(value)},
    )
    if int(getattr(result, "rowcount", 0) or 0) > 0:
        return
    await session.execute(
        text(
            """
            INSERT INTO platform_settings (key, value, scope, scope_id)
            VALUES (:key, CAST(:value AS jsonb), 'global', NULL)
            """
        ),
        {"key": key, "value": json.dumps(value)},
    )
