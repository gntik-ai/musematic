"""DPA upload + download endpoints.

Admin surface (require_superadmin):
* ``POST /api/v1/admin/tenants/{id}/dpa`` — multipart upload.
* ``GET  /api/v1/admin/tenants/{id}/dpa`` — list active + history meta.
* ``GET  /api/v1/admin/tenants/{id}/dpa/{version}/download`` — download.

Tenant-admin self-service surface (rule 46):
* ``GET  /api/v1/me/tenant/dpa`` — active DPA metadata for the caller's
  tenant (no Vault path; no historical versions).
"""

from __future__ import annotations

from datetime import date
from platform.common.dependencies import get_current_user
from platform.data_lifecycle.dependencies import get_session
from platform.data_lifecycle.exceptions import (
    DataLifecycleError,
    DPAPdfInvalidError,
    DPAScanUnavailableError,
    DPATooLargeError,
    DPAVersionAlreadyExistsError,
    DPAVersionNotFoundError,
    DPAVirusDetectedError,
    VaultUnreachableError,
)
from platform.data_lifecycle.schemas import DPAUploadResponse
from platform.data_lifecycle.services.dpa_service import (
    MAX_DPA_SIZE_BYTES,
    ClamdScanAdapter,
    DPAService,
)
from typing import Any
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy.ext.asyncio import AsyncSession

admin_router = APIRouter(prefix="/api/v1/admin", tags=["data_lifecycle:admin:dpa"])
me_router = APIRouter(prefix="/api/v1/me", tags=["data_lifecycle:me:dpa"])


def _requester_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _require_superadmin(current_user: dict[str, Any]) -> None:
    roles = current_user.get("roles") or []
    if "superadmin" not in roles and "platform_admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail={"code": "not_superadmin", "message": "super-admin role required"},
        )


def _build_service(request: Request, session: AsyncSession) -> DPAService:
    settings = request.app.state.settings
    environment = getattr(settings, "PLATFORM_ENVIRONMENT", "prod")

    # ClamAV optional in dev — when env vars not set, the service skips
    # scanning (with a structured log warning).
    scanner: ClamdScanAdapter | None = None
    if settings.data_lifecycle.clamav_host:
        scanner = ClamdScanAdapter(
            host=settings.data_lifecycle.clamav_host,
            port=settings.data_lifecycle.clamav_port,
        )

    secret_provider = getattr(request.app.state, "secret_provider", None)
    if secret_provider is None:
        raise HTTPException(
            status_code=503,
            detail={"code": "secret_provider_unavailable", "message": "Vault not initialised"},
        )
    return DPAService(
        session=session,
        settings=settings.data_lifecycle,
        environment=str(environment),
        secret_store=secret_provider,
        clamav_scanner=scanner,
        audit_chain=getattr(request.app.state, "audit_chain_service", None),
        event_producer=request.app.state.clients.get("kafka"),
    )


# =============================================================================
# Admin
# =============================================================================


@admin_router.post(
    "/tenants/{tenant_id}/dpa",
    response_model=DPAUploadResponse,
    status_code=201,
)
async def upload_dpa(
    tenant_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    version: str = Form(...),
    effective_date: date = Form(...),
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> DPAUploadResponse:
    _require_superadmin(current_user)
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_DPA_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "dpa_too_large",
                "message": f"file exceeds {MAX_DPA_SIZE_BYTES // (1024 * 1024)} MB",
            },
        )

    service = _build_service(request, session)
    try:
        result = await service.upload(
            tenant_id=tenant_id,
            version=version,
            effective_date=effective_date,
            pdf_bytes=pdf_bytes,
            actor_user_id=_requester_id(current_user),
        )
    except DPAPdfInvalidError as exc:
        raise HTTPException(
            status_code=400, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DPATooLargeError as exc:
        raise HTTPException(
            status_code=413, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DPAVersionAlreadyExistsError as exc:
        raise HTTPException(
            status_code=409, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DPAVirusDetectedError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DPAScanUnavailableError as exc:
        raise HTTPException(
            status_code=503, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except VaultUnreachableError as exc:
        raise HTTPException(
            status_code=502, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except DataLifecycleError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    return DPAUploadResponse(
        tenant_id=result.tenant_id,
        version=result.version,
        effective_date=result.effective_date,
        sha256=result.sha256,
        vault_path=result.vault_path,
    )


@admin_router.get("/tenants/{tenant_id}/dpa")
async def get_dpa_metadata(
    tenant_id: UUID,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    _require_superadmin(current_user)
    service = _build_service(request, session)
    active = await service.get_active(tenant_id)
    return {
        "active": active,
        # Historical versions live in the audit chain. The Vault path
        # is intentionally not enumerated here.
        "history": [],
    }


@admin_router.get("/tenants/{tenant_id}/dpa/{version}/download")
async def download_dpa(
    tenant_id: UUID,
    version: str,
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    _require_superadmin(current_user)
    service = _build_service(request, session)
    try:
        pdf_bytes = await service.download(
            tenant_id=tenant_id,
            version=version,
            actor_user_id=_requester_id(current_user),
        )
    except DPAVersionNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail={"code": exc.code, "message": exc.message}
        ) from exc
    except VaultUnreachableError as exc:
        raise HTTPException(
            status_code=502, detail={"code": exc.code, "message": exc.message}
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="dpa-{tenant_id}-{version}.pdf"'
            )
        },
    )


# =============================================================================
# Tenant-admin self-service (rule 46)
# =============================================================================


@me_router.get("/tenant/dpa")
async def get_my_tenant_dpa(
    request: Request,
    current_user: dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Return the active DPA metadata for the caller's tenant.

    Operates on ``current_user.tenant_id`` only — the route accepts no
    tenant_id parameter (rule 46). The Vault path is NOT included.
    """

    tenant_id_str = current_user.get("tenant_id") or current_user.get("tid")
    if not tenant_id_str:
        raise HTTPException(
            status_code=403,
            detail={"code": "no_tenant_in_token", "message": "tenant id missing in JWT"},
        )
    tenant_id = UUID(str(tenant_id_str))
    service = _build_service(request, session)
    active = await service.get_active(tenant_id)
    if active is not None:
        active = {k: v for k, v in active.items() if k != "vault_path"}
    return {"active": active}
