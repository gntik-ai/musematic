from __future__ import annotations

import json
from platform.admin.rbac import require_admin, require_superadmin
from platform.admin.responses import (
    AdminActionResponse,
    AdminDetailResponse,
    AdminListResponse,
    accepted,
    empty_detail,
    empty_list,
)
from platform.common.dependencies import get_db
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["admin", "auth"])


class ChecklistStateUpdate(BaseModel):
    state: dict[str, Any] = Field(default_factory=dict)


class ReadOnlyModeUpdate(BaseModel):
    enabled: bool


@router.get("/users", response_model=AdminListResponse)
async def list_users(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("users", current_user)


@router.get("/users/{user_id}", response_model=AdminDetailResponse)
async def get_user(
    user_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("users", user_id)


@router.post("/users/{user_id}/suspend", response_model=AdminActionResponse)
async def suspend_user(
    user_id: str,
    preview: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("suspend", f"users/{user_id}", preview=preview, affected_count=1)


@router.post("/users/{user_id}/reactivate", response_model=AdminActionResponse)
async def reactivate_user(
    user_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("reactivate", f"users/{user_id}", affected_count=1)


@router.post("/users/{user_id}/force-mfa-enrollment", response_model=AdminActionResponse)
async def force_mfa_enrollment(
    user_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("force_mfa_enrollment", f"users/{user_id}", affected_count=1)


@router.post("/users/{user_id}/force-password-reset", response_model=AdminActionResponse)
async def force_password_reset(
    user_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("force_password_reset", f"users/{user_id}", affected_count=1)


@router.delete("/users/{user_id}", response_model=AdminActionResponse)
async def delete_user(
    user_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("delete", f"users/{user_id}", affected_count=1)


@router.post("/users/bulk/suspend", response_model=AdminActionResponse)
async def bulk_suspend_users(
    user_ids: list[str],
    preview: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted(
        "bulk_suspend",
        "users",
        preview=preview,
        affected_count=len(user_ids),
        message="Bulk suspend accepted" if not preview else "Bulk suspend preview",
    )


@router.patch("/users/me/checklist-state", response_model=dict[str, Any])
async def update_my_checklist_state(
    payload: ChecklistStateUpdate,
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    user_id = str(current_user.get("sub") or current_user.get("principal_id") or "")
    await session.execute(
        text(
            """
            UPDATE users
            SET first_install_checklist_state = CAST(:state AS jsonb)
            WHERE id = :user_id
            """
        ),
        {"user_id": user_id, "state": json.dumps(payload.state)},
    )
    return {"state": payload.state}


@router.patch("/sessions/me/read-only-mode", response_model=dict[str, bool])
async def update_my_read_only_mode(
    payload: ReadOnlyModeUpdate,
    current_user: dict[str, Any] = Depends(require_admin),
    session: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    session_id = current_user.get("session_id")
    if session_id is not None:
        await session.execute(
            text(
                """
                UPDATE sessions
                SET admin_read_only_mode = :enabled
                WHERE id = :session_id
                """
            ),
            {"enabled": payload.enabled, "session_id": session_id},
        )
    return {"admin_read_only_mode": payload.enabled}


@router.get("/roles", response_model=AdminListResponse)
async def list_roles(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("roles", current_user)


@router.get("/roles/{role_id}", response_model=AdminDetailResponse)
async def get_role(
    role_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("roles", role_id)


@router.put("/roles/{role_id}/permissions", response_model=AdminActionResponse)
async def update_role_permissions(
    role_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("update_permissions", f"roles/{role_id}", affected_count=1)


@router.post("/roles/{role_id}/clone", response_model=AdminActionResponse)
async def clone_role(
    role_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("clone", f"roles/{role_id}", affected_count=1)


@router.post("/roles/{role_id}/assign", response_model=AdminActionResponse)
async def assign_role(
    role_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("assign", f"roles/{role_id}", affected_count=1)


@router.get("/groups", response_model=AdminListResponse)
async def list_groups(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("groups", current_user)


@router.get("/groups/{group_id}", response_model=AdminDetailResponse)
async def get_group(
    group_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("groups", group_id)


@router.post("/groups/{group_id}/role-mappings", response_model=AdminActionResponse)
async def map_group_to_role(
    group_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("map_role", f"groups/{group_id}", affected_count=1)


@router.get("/sessions", response_model=AdminListResponse)
async def list_sessions(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("sessions", current_user)


@router.delete("/sessions/{session_id}", response_model=AdminActionResponse)
async def revoke_session(
    session_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("revoke", f"sessions/{session_id}", affected_count=1)


@router.post("/sessions/bulk-revoke", response_model=AdminActionResponse)
async def bulk_revoke_sessions(
    session_ids: list[str],
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("bulk_revoke", "sessions", affected_count=len(session_ids))


@router.get("/oauth-providers", response_model=AdminListResponse)
async def list_oauth_providers(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("oauth-providers", current_user)


@router.post("/oauth-providers", response_model=AdminActionResponse)
async def create_oauth_provider(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("create", "oauth-providers", affected_count=1)


@router.put("/oauth-providers/{provider_id}", response_model=AdminActionResponse)
async def update_oauth_provider(
    provider_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("update", f"oauth-providers/{provider_id}", affected_count=1)


@router.delete("/oauth-providers/{provider_id}", response_model=AdminActionResponse)
async def delete_oauth_provider(
    provider_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("delete", f"oauth-providers/{provider_id}", affected_count=1)


@router.get("/ibor/connectors", response_model=AdminListResponse)
async def list_ibor_connectors(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("ibor-connectors", current_user)


@router.get("/ibor/connectors/{connector_id}", response_model=AdminDetailResponse)
async def get_ibor_connector(
    connector_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("ibor-connectors", connector_id)


@router.post("/ibor/connectors/{connector_id}/sync", response_model=AdminActionResponse)
async def sync_ibor_connector(
    connector_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("sync", f"ibor-connectors/{connector_id}", affected_count=1)


@router.get("/api-keys", response_model=AdminListResponse)
async def list_api_keys(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("api-keys", current_user)


@router.post("/api-keys/{api_key_id}/rotate", response_model=AdminActionResponse)
async def rotate_api_key(
    api_key_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("rotate", f"api-keys/{api_key_id}", affected_count=1)


@router.delete("/api-keys/{api_key_id}", response_model=AdminActionResponse)
async def revoke_api_key(
    api_key_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("revoke", f"api-keys/{api_key_id}", affected_count=1)
