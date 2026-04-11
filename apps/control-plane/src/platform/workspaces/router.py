from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.workspaces.dependencies import get_workspaces_service
from platform.workspaces.models import GoalStatus, WorkspaceStatus
from platform.workspaces.schemas import (
    AddMemberRequest,
    ChangeMemberRoleRequest,
    CreateGoalRequest,
    CreateWorkspaceRequest,
    GoalListResponse,
    GoalResponse,
    MemberListResponse,
    MembershipResponse,
    SettingsResponse,
    SetVisibilityGrantRequest,
    UpdateGoalStatusRequest,
    UpdateSettingsRequest,
    UpdateWorkspaceRequest,
    VisibilityGrantResponse,
    WorkspaceDeletedResponse,
    WorkspaceListResponse,
    WorkspaceResponse,
)
from platform.workspaces.service import WorkspacesService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


@router.post("", response_model=WorkspaceResponse, status_code=201)
async def create_workspace(
    payload: CreateWorkspaceRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceResponse:
    return await workspaces_service.create_workspace(_requester_id(current_user), payload)


@router.get("", response_model=WorkspaceListResponse)
async def list_workspaces(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: WorkspaceStatus | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceListResponse:
    return await workspaces_service.list_workspaces(
        _requester_id(current_user),
        page,
        page_size,
        status,
    )


@router.get("/{workspace_id}/members", response_model=MemberListResponse)
async def list_members(
    workspace_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> MemberListResponse:
    return await workspaces_service.list_members(
        workspace_id,
        _requester_id(current_user),
        page,
        page_size,
    )


@router.post("/{workspace_id}/members", response_model=MembershipResponse, status_code=201)
async def add_member(
    workspace_id: UUID,
    payload: AddMemberRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> MembershipResponse:
    return await workspaces_service.add_member(
        workspace_id,
        _requester_id(current_user),
        payload,
    )


@router.patch("/{workspace_id}/members/{user_id}", response_model=MembershipResponse)
async def change_member_role(
    workspace_id: UUID,
    user_id: UUID,
    payload: ChangeMemberRoleRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> MembershipResponse:
    return await workspaces_service.change_member_role(
        workspace_id,
        _requester_id(current_user),
        user_id,
        payload,
    )


@router.delete("/{workspace_id}/members/{user_id}", status_code=204)
async def remove_member(
    workspace_id: UUID,
    user_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> Response:
    await workspaces_service.remove_member(
        workspace_id,
        _requester_id(current_user),
        user_id,
    )
    return Response(status_code=204)


@router.post("/{workspace_id}/goals", response_model=GoalResponse, status_code=201)
async def create_goal(
    workspace_id: UUID,
    payload: CreateGoalRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> GoalResponse:
    return await workspaces_service.create_goal(
        workspace_id,
        _requester_id(current_user),
        payload,
    )


@router.get("/{workspace_id}/goals", response_model=GoalListResponse)
async def list_goals(
    workspace_id: UUID,
    status: GoalStatus | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> GoalListResponse:
    return await workspaces_service.list_goals(
        workspace_id,
        _requester_id(current_user),
        page,
        page_size,
        status,
    )


@router.get("/{workspace_id}/goals/{goal_id}", response_model=GoalResponse)
async def get_goal(
    workspace_id: UUID,
    goal_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> GoalResponse:
    return await workspaces_service.get_goal(
        workspace_id,
        _requester_id(current_user),
        goal_id,
    )


@router.patch("/{workspace_id}/goals/{goal_id}", response_model=GoalResponse)
async def update_goal_status(
    workspace_id: UUID,
    goal_id: UUID,
    payload: UpdateGoalStatusRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> GoalResponse:
    return await workspaces_service.update_goal_status(
        workspace_id,
        _requester_id(current_user),
        goal_id,
        payload,
    )


@router.put("/{workspace_id}/visibility", response_model=VisibilityGrantResponse)
async def set_visibility_grant(
    workspace_id: UUID,
    payload: SetVisibilityGrantRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> VisibilityGrantResponse:
    return await workspaces_service.set_visibility_grant(
        workspace_id,
        _requester_id(current_user),
        payload,
    )


@router.get("/{workspace_id}/visibility", response_model=VisibilityGrantResponse)
async def get_visibility_grant(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> VisibilityGrantResponse:
    return await workspaces_service.get_visibility_grant(
        workspace_id,
        _requester_id(current_user),
    )


@router.delete("/{workspace_id}/visibility", status_code=204)
async def delete_visibility_grant(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> Response:
    await workspaces_service.delete_visibility_grant(workspace_id, _requester_id(current_user))
    return Response(status_code=204)


@router.get("/{workspace_id}/settings", response_model=SettingsResponse)
async def get_settings(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> SettingsResponse:
    return await workspaces_service.get_settings(workspace_id, _requester_id(current_user))


@router.patch("/{workspace_id}/settings", response_model=SettingsResponse)
async def update_settings(
    workspace_id: UUID,
    payload: UpdateSettingsRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> SettingsResponse:
    return await workspaces_service.update_settings(
        workspace_id,
        _requester_id(current_user),
        payload,
    )


@router.get("/{workspace_id}", response_model=WorkspaceResponse)
async def get_workspace(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceResponse:
    return await workspaces_service.get_workspace(workspace_id, _requester_id(current_user))


@router.patch("/{workspace_id}", response_model=WorkspaceResponse)
async def update_workspace(
    workspace_id: UUID,
    payload: UpdateWorkspaceRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceResponse:
    return await workspaces_service.update_workspace(
        workspace_id,
        _requester_id(current_user),
        payload,
    )


@router.post("/{workspace_id}/archive", response_model=WorkspaceResponse)
async def archive_workspace(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceResponse:
    return await workspaces_service.archive_workspace(workspace_id, _requester_id(current_user))


@router.post("/{workspace_id}/restore", response_model=WorkspaceResponse)
async def restore_workspace(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceResponse:
    return await workspaces_service.restore_workspace(workspace_id, _requester_id(current_user))


@router.delete("/{workspace_id}", response_model=WorkspaceDeletedResponse, status_code=202)
async def delete_workspace(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    workspaces_service: WorkspacesService = Depends(get_workspaces_service),
) -> WorkspaceDeletedResponse:
    return await workspaces_service.delete_workspace(
        workspace_id,
        _requester_id(current_user),
        allow_platform_admin=bool({"platform_admin", "superadmin"} & _role_names(current_user)),
    )
