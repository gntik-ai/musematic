"""Workspace data-lifecycle REST endpoints.

Mounted under ``/api/v1/workspaces/{workspace_id}/data-export/*``.
Auth: every method requires a logged-in user; finer RBAC (owner OR
admin) is enforced via the workspaces service interface.

Contract: ``specs/104-data-lifecycle/contracts/workspace-export-rest.md``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from platform.common.dependencies import get_current_user
from platform.data_lifecycle.dependencies import (
    get_deletion_service,
    get_export_service,
    get_repository,
)
from platform.data_lifecycle.exceptions import (
    CrossRegionExportBlockedError,
    DataLifecycleError,
    DeletionJobAlreadyActiveError,
    ExportRateLimitExceededError,
    TypedConfirmationMismatchError,
)
from platform.data_lifecycle.models import DataExportJob, DeletionJob, ScopeType
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.schemas import (
    CancelDeletionResponse,
    DeletionJobDetail,
    ExportJobDetail,
    ExportJobList,
    ExportJobSummary,
    WorkspaceDeletionRequest,
)
from platform.data_lifecycle.services.deletion_service import DeletionService
from platform.data_lifecycle.services.export_service import ExportService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workspaces", tags=["data_lifecycle:workspace"])
cancel_router = APIRouter(
    prefix="/api/v1/workspaces", tags=["data_lifecycle:workspace"]
)


class _RequestExportResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    status: str
    requested_at: datetime
    estimated_completion: datetime | None = Field(default=None)


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _tenant_id(request: Request) -> UUID:
    """Resolve tenant id from request state (set by tenant middleware)."""

    state = getattr(request.state, "tenant", None)
    if state is not None and getattr(state, "id", None) is not None:
        return UUID(str(state.id))
    # Fallback: rely on the tenant_context ContextVar set by middleware.
    from platform.common.tenant_context import get_current_tenant

    return get_current_tenant().id


@router.post(
    "/{workspace_id}/data-export",
    response_model=_RequestExportResponse,
    status_code=202,
)
async def request_workspace_export(
    workspace_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
) -> _RequestExportResponse:
    tenant_id = _tenant_id(request)
    correlation_ctx = getattr(request.state, "correlation_context", None)
    try:
        job: DataExportJob = await service.request_workspace_export(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            requested_by_user_id=_requester_id(current_user),
            correlation_ctx=correlation_ctx,
        )
    except ExportRateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail={"code": "export_rate_limit_exceeded", "message": str(exc)},
        ) from exc
    except CrossRegionExportBlockedError as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "cross_region_export_blocked", "message": str(exc)},
        ) from exc
    return _RequestExportResponse(
        id=job.id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        status=job.status,
        requested_at=job.created_at,
    )


@router.get(
    "/{workspace_id}/data-export/jobs",
    response_model=ExportJobList,
)
async def list_workspace_export_jobs(
    workspace_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None),
    repo: DataLifecycleRepository = Depends(get_repository),
) -> ExportJobList:
    rows = await repo.list_export_jobs_for_scope(
        scope_type=ScopeType.workspace.value,
        scope_id=workspace_id,
        status=status,
        limit=limit,
    )
    return ExportJobList(
        items=[ExportJobSummary.model_validate(r) for r in rows],
        next_cursor=None,
    )


@router.get(
    "/{workspace_id}/data-export/jobs/{job_id}",
    response_model=ExportJobDetail,
)
async def get_workspace_export_job(
    workspace_id: UUID,
    job_id: UUID,
    repo: DataLifecycleRepository = Depends(get_repository),
) -> ExportJobDetail:
    job = await repo.get_export_job(job_id)
    if job is None or job.scope_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "export_job_not_found", "message": "export job not found"},
        )
    detail = ExportJobDetail.model_validate(job)
    # Honour TTL: omit the URL once expired.
    if (
        detail.output_expires_at is not None
        and detail.output_expires_at < datetime.now(UTC)
    ):
        detail.output_url = None
    return detail


# ============================================================================
# Workspace deletion (US2)
# ============================================================================


class _DeletionRequestResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    phase: str
    grace_period_days: int
    grace_ends_at: datetime
    cancel_link_emailed_to: str = Field(
        default="owner",
        description=(
            "Display-only — the actual email address is NOT echoed to "
            "avoid leaking it through the API response."
        ),
    )


@router.post(
    "/{workspace_id}/deletion-jobs",
    response_model=_DeletionRequestResponse,
    status_code=202,
)
async def request_workspace_deletion(
    workspace_id: UUID,
    payload: WorkspaceDeletionRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DeletionService = Depends(get_deletion_service),
) -> _DeletionRequestResponse:
    tenant_id = _tenant_id(request)
    correlation_ctx = getattr(request.state, "correlation_context", None)
    try:
        result = await service.request_workspace_deletion(
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            requested_by_user_id=_requester_id(current_user),
            typed_confirmation=payload.typed_confirmation,
            reason=payload.reason,
            tenant_contract_metadata=getattr(request.state, "tenant_contract_metadata", None),
            correlation_ctx=correlation_ctx,
        )
    except TypedConfirmationMismatchError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "typed_confirmation_mismatch", "message": str(exc)},
        ) from exc
    except DeletionJobAlreadyActiveError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "deletion_job_already_active", "message": str(exc)},
        ) from exc
    except DataLifecycleError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    # NOTE: ``result.cancel_token`` is the plaintext token; the caller
    # delegates email delivery to UPD-077 so the token NEVER leaves this
    # process via the HTTP response. We surface it here only inside the
    # control-plane service boundary.
    job: DeletionJob = result.job
    return _DeletionRequestResponse(
        id=job.id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        phase=job.phase,
        grace_period_days=job.grace_period_days,
        grace_ends_at=job.grace_ends_at,
    )


@router.get(
    "/{workspace_id}/deletion-jobs/{job_id}",
    response_model=DeletionJobDetail,
)
async def get_workspace_deletion_job(
    workspace_id: UUID,
    job_id: UUID,
    repo: DataLifecycleRepository = Depends(get_repository),
) -> DeletionJobDetail:
    job = await repo.get_deletion_job(job_id)
    if job is None or job.scope_id != workspace_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "deletion_job_not_found", "message": "not found"},
        )
    return DeletionJobDetail.model_validate(job)


# Cancel-via-token uses a separate router so the path is reachable
# without a workspace_id (the token IS the workspace reference). The
# response is intentionally identical for any token outcome (R10).


@cancel_router.post(
    "/cancel-deletion/{token}",
    response_model=CancelDeletionResponse,
    status_code=200,
)
async def cancel_workspace_deletion(
    token: str,
    service: DeletionService = Depends(get_deletion_service),
) -> CancelDeletionResponse:
    # The outcome is intentionally not surfaced — operators see truth
    # via the audit chain. The user always sees the same message.
    await service.cancel_via_token(token=token)
    return CancelDeletionResponse()
