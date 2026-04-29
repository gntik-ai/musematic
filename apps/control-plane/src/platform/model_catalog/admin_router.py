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

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "model-catalog"])


@router.get("/model-catalog", response_model=AdminListResponse)
async def list_model_catalog_entries(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("model-catalog", current_user)


@router.post("/model-catalog", response_model=AdminActionResponse)
async def upsert_model_catalog_entry(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("upsert", "model-catalog", affected_count=1)


@router.get("/model-catalog/{model_id}", response_model=AdminDetailResponse)
async def get_model_catalog_entry(
    model_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("model-catalog", model_id)


@router.post("/model-catalog/{model_id}/deprecate", response_model=AdminActionResponse)
async def deprecate_model_catalog_entry(
    model_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("deprecate", f"model-catalog/{model_id}", affected_count=1)


@router.post("/model-catalog/{model_id}/model-card", response_model=AdminActionResponse)
async def upload_model_card(
    model_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("upload_model_card", f"model-catalog/{model_id}", affected_count=1)


@router.put("/model-catalog/{model_id}/fallback-policy", response_model=AdminActionResponse)
async def configure_fallback_policy(
    model_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("configure_fallback_policy", f"model-catalog/{model_id}", affected_count=1)
