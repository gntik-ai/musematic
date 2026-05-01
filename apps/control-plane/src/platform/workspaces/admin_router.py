from __future__ import annotations

from platform.admin.rbac import require_admin
from platform.admin.responses import (
    AdminActionResponse,
    AdminDetailResponse,
    AdminListResponse,
    accepted,
    empty_detail,
    empty_list,
)
from typing import Any

from fastapi import APIRouter, Depends, Query

router = APIRouter(tags=["admin", "workspaces"])


@router.get("/workspaces", response_model=AdminListResponse)
async def list_workspaces(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("workspaces", current_user)


@router.post("/workspaces", response_model=AdminActionResponse)
async def create_workspace(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "workspaces", affected_count=1)


@router.get("/workspaces/{workspace_id}", response_model=AdminDetailResponse)
async def get_workspace(
    workspace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("workspaces", workspace_id)


@router.put("/workspaces/{workspace_id}", response_model=AdminActionResponse)
async def configure_workspace(
    workspace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("configure", f"workspaces/{workspace_id}", affected_count=1)


@router.post("/workspaces/{workspace_id}/archive", response_model=AdminActionResponse)
async def archive_workspace(
    workspace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("archive", f"workspaces/{workspace_id}", affected_count=1)


@router.delete("/workspaces/{workspace_id}", response_model=AdminActionResponse)
async def delete_workspace(
    workspace_id: str,
    preview: bool = Query(default=False),
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("delete", f"workspaces/{workspace_id}", preview=preview, affected_count=1)


@router.get("/workspaces/{workspace_id}/quotas", response_model=AdminDetailResponse)
async def get_workspace_quotas(
    workspace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("workspace-quotas", workspace_id)


@router.put("/workspaces/{workspace_id}/quotas", response_model=AdminActionResponse)
async def configure_workspace_quotas(
    workspace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("configure_quotas", f"workspaces/{workspace_id}/quotas", affected_count=1)


@router.get("/namespaces", response_model=AdminListResponse)
async def list_namespaces(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("namespaces", current_user)


@router.post("/namespaces", response_model=AdminActionResponse)
async def create_namespace(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "namespaces", affected_count=1)


@router.put("/namespaces/{namespace_id}", response_model=AdminActionResponse)
async def update_namespace(
    namespace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("update", f"namespaces/{namespace_id}", affected_count=1)


@router.delete("/namespaces/{namespace_id}", response_model=AdminActionResponse)
async def delete_namespace(
    namespace_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("delete", f"namespaces/{namespace_id}", affected_count=1)
