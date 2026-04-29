from __future__ import annotations

from platform.admin.feature_flags_service import (
    FeatureFlagRecord,
    FeatureFlagScope,
    FeatureFlagsService,
)
from platform.admin.rbac import require_admin
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.dependencies import get_db
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/feature-flags", tags=["admin", "feature-flags"])


class FeatureFlagRead(BaseModel):
    key: str
    enabled: bool
    scope: FeatureFlagScope
    scope_id: UUID | None
    inherited: bool


class FeatureFlagUpdate(BaseModel):
    enabled: bool
    scope: FeatureFlagScope = "global"
    scope_id: UUID | None = None


def _read(record: FeatureFlagRecord) -> FeatureFlagRead:
    return FeatureFlagRead(
        key=record.key,
        enabled=record.enabled,
        scope=record.scope,
        scope_id=record.scope_id,
        inherited=record.inherited,
    )


def _service(session: AsyncSession, audit_chain: AuditChainService) -> FeatureFlagsService:
    return FeatureFlagsService(session, audit_chain)


@router.get("", response_model=list[FeatureFlagRead])
async def list_feature_flags(
    scope: FeatureFlagScope = Query(default="global"),
    scope_id: UUID | None = Query(default=None),
    _current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> list[FeatureFlagRead]:
    records = await _service(session, audit_chain).list_flags(scope=scope, scope_id=scope_id)
    return [_read(record) for record in records]


@router.put("/{key}", response_model=FeatureFlagRead)
async def update_feature_flag(
    key: str,
    payload: FeatureFlagUpdate,
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> FeatureFlagRead:
    record = await _service(session, audit_chain).set_flag(
        key=key,
        enabled=payload.enabled,
        scope=payload.scope,
        scope_id=payload.scope_id,
        actor=current_user,
    )
    return _read(record)


@router.delete("/{key}", status_code=204)
async def delete_feature_flag_override(
    key: str,
    scope: FeatureFlagScope = Query(default="global"),
    scope_id: UUID | None = Query(default=None),
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> None:
    await _service(session, audit_chain).delete_override(
        key=key,
        scope=scope,
        scope_id=scope_id,
        actor=current_user,
    )
