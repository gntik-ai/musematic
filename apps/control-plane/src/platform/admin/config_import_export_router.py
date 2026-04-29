from __future__ import annotations

from dataclasses import asdict
from platform.admin.config_export_service import ConfigExportService, ConfigScope
from platform.admin.config_import_service import ConfigImportService, DiffPreview
from platform.admin.rbac import require_admin, require_superadmin
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from typing import Any, cast
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

router = APIRouter(prefix="/config", tags=["admin", "config"])


@router.post("/export")
async def export_config(
    request: Request,
    scope: ConfigScope = Body(default="platform"),
    tenant_id: UUID | None = Body(default=None),
    _current_user: dict[str, Any] = Depends(require_admin),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> Response:
    settings = _settings(request)
    bundle, bundle_hash = await ConfigExportService(settings, audit_chain).export_config(
        scope=scope,
        tenant_id=tenant_id,
    )
    return Response(
        content=bundle,
        media_type="application/gzip",
        headers={
            "Content-Disposition": 'attachment; filename="musematic-config.tar.gz"',
            "X-Config-Bundle-SHA256": bundle_hash,
        },
    )


@router.post("/import/preview", response_model=dict[str, Any])
async def preview_config_import(
    bundle: UploadFile = File(...),
    _current_user: dict[str, Any] = Depends(require_superadmin),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> dict[str, Any]:
    try:
        preview = await ConfigImportService(audit_chain).preview_import(await bundle.read())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _preview_dict(preview)


@router.post("/import/apply", response_model=dict[str, Any])
async def apply_config_import(
    confirmation_phrase: str = Form(...),
    bundle: UploadFile = File(...),
    current_user: dict[str, Any] = Depends(require_superadmin),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> dict[str, Any]:
    try:
        result = await ConfigImportService(audit_chain).apply_import(
            await bundle.read(),
            confirmation_phrase,
            current_user,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return asdict(result)


def _preview_dict(preview: DiffPreview) -> dict[str, Any]:
    return {
        "valid_signature": preview.valid_signature,
        "bundle_hash": preview.bundle_hash,
        "diffs": [asdict(diff) for diff in preview.diffs],
    }


def _settings(request: Request) -> PlatformSettings:
    return cast(PlatformSettings, request.app.state.settings)
