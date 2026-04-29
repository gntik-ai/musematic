from __future__ import annotations

from platform.admin.installer_state import InstallerState, get_installer_state
from platform.admin.rbac import require_superadmin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted
from platform.common.dependencies import get_db
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/lifecycle", tags=["admin", "lifecycle"])


class VersionResponse(BaseModel):
    version: str = "unknown"
    components: dict[str, str] = {}


@router.get("/version", response_model=VersionResponse)
async def get_platform_version(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> VersionResponse:
    return VersionResponse()


@router.get("/migrations", response_model=AdminListResponse)
async def list_migrations(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminListResponse:
    return AdminListResponse(resource="migrations")


@router.post("/migrations/run", response_model=AdminActionResponse)
async def run_migrations(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("run", "migrations", affected_count=1)


@router.get("/backup", response_model=AdminListResponse)
async def list_backups(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminListResponse:
    return AdminListResponse(resource="backups")


@router.post("/backup", response_model=AdminActionResponse)
async def trigger_backup(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("trigger", "backups", affected_count=1)


@router.post("/backup/{backup_id}/restore", response_model=AdminActionResponse)
async def restore_backup(
    backup_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("restore", f"backups/{backup_id}", affected_count=1)


@router.get("/installer", response_model=InstallerState | None)
async def get_installer(
    _current_user: dict[str, Any] = Depends(require_superadmin),
    session: AsyncSession = Depends(get_db),
) -> InstallerState | None:
    return await get_installer_state(session)
