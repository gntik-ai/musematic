from __future__ import annotations

from datetime import UTC, datetime
from platform.admin.audit_utils import append_admin_audit
from platform.admin.rbac import require_superadmin
from platform.admin.schemas.vault import (
    CacheFlushRequest,
    CacheFlushResponse,
    ConnectivityTestResponse,
    TokenRotationRequest,
    TokenRotationResponse,
    VaultStatusResponse,
)
from platform.admin.services.vault_admin_service import VaultAdminService
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.common.config import PlatformSettings
from platform.common.secret_provider import SecretProvider
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

router = APIRouter(prefix="/vault", tags=["admin", "vault"])


def get_vault_admin_service(request: Request) -> VaultAdminService:
    provider = getattr(request.app.state, "secret_provider", None)
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "vault_provider_unavailable",
                "message": "Secret provider is not configured for this process.",
            },
        )
    return VaultAdminService(
        cast(SecretProvider, provider),
        cast(PlatformSettings, request.app.state.settings),
    )


@router.get("/status", response_model=VaultStatusResponse)
async def get_status(
    _current_user: dict[str, Any] = Depends(require_superadmin),
    service: VaultAdminService = Depends(get_vault_admin_service),
) -> VaultStatusResponse:
    return await service.status()


@router.post("/cache-flush", response_model=CacheFlushResponse)
async def flush_cache(
    payload: CacheFlushRequest,
    current_user: dict[str, Any] = Depends(require_superadmin),
    service: VaultAdminService = Depends(get_vault_admin_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> CacheFlushResponse:
    try:
        response = await service.flush_cache(payload)
    except Exception as exc:
        await _append_vault_admin_audit(
            audit_chain,
            event_type="vault.cache_flushed",
            actor=current_user,
            result="failure",
            details={"path": payload.path, "error": f"{type(exc).__name__}: {exc}"},
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error_code": "vault_cache_flush_failed",
                "message": "Vault cache flush failed.",
            },
        ) from exc
    await _append_vault_admin_audit(
        audit_chain,
        event_type="vault.cache_flushed",
        actor=current_user,
        result="success",
        details={
            "path": response.path,
            "flushed_count": response.flushed_count,
            "scope": response.scope,
        },
    )
    return response


@router.post("/connectivity-test", response_model=ConnectivityTestResponse)
async def connectivity_test(
    current_user: dict[str, Any] = Depends(require_superadmin),
    service: VaultAdminService = Depends(get_vault_admin_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> ConnectivityTestResponse:
    response = await service.connectivity_test()
    await _append_vault_admin_audit(
        audit_chain,
        event_type="vault.connectivity_test",
        actor=current_user,
        result="success" if response.success else "failure",
        details={"latency_ms": response.latency_ms, "error": response.error},
    )
    return response


@router.post("/rotate-token", response_model=TokenRotationResponse)
async def rotate_token(
    payload: TokenRotationRequest,
    current_user: dict[str, Any] = Depends(require_superadmin),
    service: VaultAdminService = Depends(get_vault_admin_service),
    audit_chain: AuditChainService = Depends(get_audit_chain_service),
) -> TokenRotationResponse:
    response = await service.rotate_token(payload)
    await _append_vault_admin_audit(
        audit_chain,
        event_type="vault.token_rotation_requested",
        actor=current_user,
        result="success" if response.success else "failure",
        details={"pod": response.pod, "status": response.status, "error": response.error},
    )
    return response


async def _append_vault_admin_audit(
    audit_chain: AuditChainService,
    *,
    event_type: str,
    actor: dict[str, Any],
    result: str,
    details: dict[str, Any],
) -> None:
    await append_admin_audit(
        audit_chain,
        event_type=event_type,
        actor=actor,
        payload={
            "timestamp": datetime.now(UTC).isoformat(),
            "result": result,
            **details,
        },
    )
