from __future__ import annotations

from platform.admin.rbac import require_admin
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

router = APIRouter(prefix="/health", tags=["admin", "health"])


class ComponentHealth(BaseModel):
    name: str
    status: str
    details: dict[str, Any] = Field(default_factory=dict)


class AdminHealthResponse(BaseModel):
    status: str
    components: list[ComponentHealth]


@router.get("", response_model=AdminHealthResponse)
async def get_admin_health(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminHealthResponse:
    components = [
        ComponentHealth(name="control-plane", status="ok"),
        ComponentHealth(name="web", status="unknown"),
        ComponentHealth(name="observability", status="unknown"),
        ComponentHealth(name="reasoning-engine", status="unknown"),
        ComponentHealth(name="runtime-controller", status="unknown"),
        ComponentHealth(name="sandbox-manager", status="unknown"),
        ComponentHealth(name="simulation-controller", status="unknown"),
    ]
    return AdminHealthResponse(status="degraded", components=components)

