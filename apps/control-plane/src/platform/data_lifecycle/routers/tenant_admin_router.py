"""Tenant admin REST endpoints.

Mounted under ``/api/v1/admin/tenants/{tenant_id}/{data-export,deletion-jobs}/*``
and ``/api/v1/admin/data-lifecycle/deletion-jobs/{id}/abort``. All
routes are gated by ``require_superadmin`` (rule 30); state-changing
deletion routes additionally require a fresh 2PA challenge id (rule
33).

Contract: ``specs/104-data-lifecycle/contracts/{tenant-export,tenant-deletion}-rest.md``.
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
    CascadeInProgressError,
    DataLifecycleError,
    DefaultTenantCannotBeDeletedError,
    DeletionJobAlreadyActiveError,
    DeletionJobAlreadyFinalisedError,
    GracePeriodOutOfRangeError,
    SubscriptionActiveCancelFirstError,
    TwoPATokenInvalidError,
    TwoPATokenRequiredError,
    TypedConfirmationMismatchError,
)
from platform.data_lifecycle.models import ScopeType
from platform.data_lifecycle.repository import DataLifecycleRepository
from platform.data_lifecycle.schemas import (
    AbortRequest,
    DeletionJobDetail,
    ExportJobDetail,
    ExportJobList,
    ExportJobSummary,
    GraceExtensionRequest,
    TenantDeletionRequest,
    TenantExportRequest,
)
from platform.data_lifecycle.services.deletion_service import DeletionService
from platform.data_lifecycle.services.export_service import ExportService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

router = APIRouter(
    prefix="/api/v1/admin", tags=["data_lifecycle:admin:tenant"]
)


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _require_superadmin(current_user: dict[str, Any]) -> None:
    roles = current_user.get("roles") or []
    if "superadmin" not in roles and "platform_admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail={"code": "not_superadmin", "message": "super-admin role required"},
        )


def _require_2pa(token: str | None) -> UUID:
    if not token:
        raise HTTPException(
            status_code=403,
            detail={"code": "2pa_token_required", "message": "X-2PA-Token header is required"},
        )
    try:
        return UUID(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "2pa_token_invalid", "message": "X-2PA-Token must be a UUID"},
        ) from exc


# ============================================================================
# Tenant export
# ============================================================================


class _TenantExportResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    status: str
    estimated_completion: datetime | None = Field(default=None)


@router.post(
    "/tenants/{tenant_id}/data-export",
    response_model=_TenantExportResponse,
    status_code=202,
)
async def request_tenant_export(
    tenant_id: UUID,
    payload: TenantExportRequest,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ExportService = Depends(get_export_service),
) -> _TenantExportResponse:
    _require_superadmin(current_user)
    correlation_ctx = getattr(request.state, "correlation_context", None)
    job = await service.request_tenant_export(
        tenant_id=tenant_id,
        requested_by_user_id=_requester_id(current_user),
        correlation_ctx=correlation_ctx,
    )
    return _TenantExportResponse(
        id=job.id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        status=job.status,
    )


@router.get(
    "/tenants/{tenant_id}/data-export/jobs",
    response_model=ExportJobList,
)
async def list_tenant_export_jobs(
    tenant_id: UUID,
    limit: int = Query(default=20, ge=1, le=50),
    status: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    repo: DataLifecycleRepository = Depends(get_repository),
) -> ExportJobList:
    _require_superadmin(current_user)
    rows = await repo.list_export_jobs_for_scope(
        scope_type=ScopeType.tenant.value,
        scope_id=tenant_id,
        status=status,
        limit=limit,
    )
    return ExportJobList(
        items=[ExportJobSummary.model_validate(r) for r in rows],
        next_cursor=None,
    )


@router.get(
    "/tenants/{tenant_id}/data-export/jobs/{job_id}",
    response_model=ExportJobDetail,
)
async def get_tenant_export_job(
    tenant_id: UUID,
    job_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    repo: DataLifecycleRepository = Depends(get_repository),
) -> ExportJobDetail:
    _require_superadmin(current_user)
    job = await repo.get_export_job(job_id)
    if job is None or job.scope_id != tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "export_job_not_found", "message": "export job not found"},
        )
    detail = ExportJobDetail.model_validate(job)
    if (
        detail.output_expires_at is not None
        and detail.output_expires_at < datetime.now(UTC)
    ):
        detail.output_url = None
    return detail


# ============================================================================
# Tenant deletion
# ============================================================================


class _TenantDeletionResponse(BaseModel):
    id: UUID
    scope_type: str
    scope_id: UUID
    phase: str
    grace_period_days: int
    grace_ends_at: datetime
    final_export_job_id: UUID | None = None


@router.post(
    "/tenants/{tenant_id}/deletion-jobs",
    response_model=_TenantDeletionResponse,
    status_code=202,
)
async def request_tenant_deletion(
    tenant_id: UUID,
    payload: TenantDeletionRequest,
    request: Request,
    x_2pa_token: str | None = Header(default=None, alias="X-2PA-Token"),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DeletionService = Depends(get_deletion_service),
) -> _TenantDeletionResponse:
    _require_superadmin(current_user)
    challenge_id = _require_2pa(x_2pa_token)
    correlation_ctx = getattr(request.state, "correlation_context", None)
    try:
        result = await service.request_tenant_deletion(
            tenant_id=tenant_id,
            requested_by_user_id=_requester_id(current_user),
            typed_confirmation=payload.typed_confirmation,
            reason=payload.reason,
            two_pa_challenge_id=challenge_id,
            include_final_export=payload.include_final_export,
            grace_period_days_override=payload.grace_period_days,
            correlation_ctx=correlation_ctx,
        )
    except (TwoPATokenRequiredError, TwoPATokenInvalidError) as exc:
        raise HTTPException(
            status_code=403, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except SubscriptionActiveCancelFirstError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DefaultTenantCannotBeDeletedError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except TypedConfirmationMismatchError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DeletionJobAlreadyActiveError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except GracePeriodOutOfRangeError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DataLifecycleError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    job = result.job
    return _TenantDeletionResponse(
        id=job.id,
        scope_type=job.scope_type,
        scope_id=job.scope_id,
        phase=job.phase,
        grace_period_days=job.grace_period_days,
        grace_ends_at=job.grace_ends_at,
        final_export_job_id=result.final_export_job_id,
    )


@router.get(
    "/tenants/{tenant_id}/deletion-jobs/{job_id}",
    response_model=DeletionJobDetail,
)
async def get_tenant_deletion_job(
    tenant_id: UUID,
    job_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    repo: DataLifecycleRepository = Depends(get_repository),
) -> DeletionJobDetail:
    _require_superadmin(current_user)
    job = await repo.get_deletion_job(job_id)
    if job is None or job.scope_id != tenant_id:
        raise HTTPException(
            status_code=404,
            detail={"code": "deletion_job_not_found", "message": "not found"},
        )
    return DeletionJobDetail.model_validate(job)


@router.post(
    "/tenants/{tenant_id}/deletion-jobs/{job_id}/extend-grace",
    response_model=DeletionJobDetail,
)
async def extend_tenant_grace(
    tenant_id: UUID,
    job_id: UUID,
    payload: GraceExtensionRequest,
    request: Request,
    x_2pa_token: str | None = Header(default=None, alias="X-2PA-Token"),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DeletionService = Depends(get_deletion_service),
) -> DeletionJobDetail:
    _require_superadmin(current_user)
    _require_2pa(x_2pa_token)
    try:
        job = await service.extend_grace(
            job_id=job_id,
            additional_days=payload.additional_days,
            actor_user_id=_requester_id(current_user),
            reason=payload.reason,
            correlation_ctx=getattr(request.state, "correlation_context", None),
        )
    except DeletionJobAlreadyFinalisedError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except GracePeriodOutOfRangeError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc
    return DeletionJobDetail.model_validate(job)


# =============================================================================
# Article 28 evidence package
# =============================================================================


@router.post(
    "/tenants/{tenant_id}/article28-evidence",
)
async def generate_article28_evidence(
    tenant_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    repo: DataLifecycleRepository = Depends(get_repository),
    service: ExportService = Depends(get_export_service),
) -> dict[str, Any]:
    """Generate the GDPR Article 28 evidence package on demand.

    Reuses the export-job machinery for delivery: returns a job id +
    202 status. The worker materializes the ZIP via
    ``Article28Service.build_evidence_zip`` and uploads to the export
    bucket with a 30-day signed-URL TTL (matching tenant-export TTL).
    """

    _require_superadmin(current_user)
    job = await service.request_tenant_export(
        tenant_id=tenant_id,
        requested_by_user_id=_requester_id(current_user),
        correlation_ctx=getattr(request.state, "correlation_context", None),
    )
    return {
        "job_id": str(job.id),
        "scope_type": job.scope_type,
        "scope_id": str(job.scope_id),
        "status": job.status,
        "note": (
            "Article 28 evidence is delivered as a tenant-scope export. "
            "The worker assembles the package per FR-758.1."
        ),
    }


# Abort endpoint — works for workspace AND tenant scopes (R7).


@router.post(
    "/data-lifecycle/deletion-jobs/{job_id}/abort",
    response_model=DeletionJobDetail,
)
async def abort_deletion_job(
    job_id: UUID,
    payload: AbortRequest,
    request: Request,
    x_2pa_token: str | None = Header(default=None, alias="X-2PA-Token"),
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DeletionService = Depends(get_deletion_service),
) -> DeletionJobDetail:
    _require_superadmin(current_user)
    # 2PA optional for workspace-scope abort, required for tenant-scope.
    # We require it for both as the safer default; operators can still
    # use the workspace owner cancel-link for non-2PA flows.
    _require_2pa(x_2pa_token)
    try:
        job = await service.abort_in_grace(
            job_id=job_id,
            actor_user_id=_requester_id(current_user),
            abort_reason=payload.abort_reason,
            correlation_ctx=getattr(request.state, "correlation_context", None),
        )
    except CascadeInProgressError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DeletionJobAlreadyFinalisedError as exc:
        raise HTTPException(
            status_code=410, detail={"code": exc.code, "message": exc.message}
        ) from exc
    return DeletionJobDetail.model_validate(job)
