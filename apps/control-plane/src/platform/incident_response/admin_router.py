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

router = APIRouter(tags=["admin", "incident-response"])


@router.get("/incidents", response_model=AdminListResponse)
async def list_incidents(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("incidents", current_user)


@router.post("/incidents", response_model=AdminActionResponse)
async def create_manual_incident(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "incidents", affected_count=1)


@router.get("/incidents/{incident_id}", response_model=AdminDetailResponse)
async def get_incident(
    incident_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("incidents", incident_id)


@router.post("/incidents/{incident_id}/runbooks/{runbook_id}", response_model=AdminActionResponse)
async def link_runbook_to_incident(
    incident_id: str,
    runbook_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("link_runbook", f"incidents/{incident_id}/runbooks/{runbook_id}")


@router.post("/incidents/{incident_id}/post-mortem", response_model=AdminActionResponse)
async def generate_post_mortem(
    incident_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("generate_post_mortem", f"incidents/{incident_id}", affected_count=1)


@router.get("/runbooks", response_model=AdminListResponse)
async def list_runbooks(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("runbooks", current_user)


@router.post("/runbooks", response_model=AdminActionResponse)
async def create_runbook(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("create", "runbooks", affected_count=1)


@router.get("/runbooks/{runbook_id}", response_model=AdminDetailResponse)
async def get_runbook(
    runbook_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminDetailResponse:
    return empty_detail("runbooks", runbook_id)


@router.put("/runbooks/{runbook_id}", response_model=AdminActionResponse)
async def update_runbook(
    runbook_id: str,
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("update", f"runbooks/{runbook_id}", affected_count=1)


@router.get("/integrations/incidents", response_model=AdminListResponse)
async def list_incident_integrations(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("incident-integrations", current_user)
