from __future__ import annotations

from platform.audit.dependencies import get_audit_chain_service
from platform.audit.schemas import (
    AttestationRequest,
    PublicKeyResponse,
    SignedAttestation,
    VerifyResult,
)
from platform.audit.service import AuditChainService
from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError
from typing import Any

from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/api/v1/security/audit-chain", tags=["admin", "audit-chain"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    return {str(item.get("role")) for item in roles if isinstance(item, dict)}


async def require_audit_reader(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    if _role_names(current_user) & {"superadmin", "auditor"}:
        return current_user
    raise AuthorizationError("PERMISSION_DENIED", "Auditor role required")


@router.get("/verify", response_model=VerifyResult)
async def verify_audit_chain(
    start_seq: int | None = Query(default=None, ge=1),
    end_seq: int | None = Query(default=None, ge=1),
    _current_user: dict[str, Any] = Depends(require_audit_reader),
    service: AuditChainService = Depends(get_audit_chain_service),
) -> VerifyResult:
    return await service.verify(start_seq, end_seq)


@router.post("/attestations", response_model=SignedAttestation)
async def create_attestation(
    payload: AttestationRequest,
    _current_user: dict[str, Any] = Depends(require_audit_reader),
    service: AuditChainService = Depends(get_audit_chain_service),
) -> SignedAttestation:
    return await service.export_attestation(payload.start_seq, payload.end_seq)


@router.get("/public-key", response_model=PublicKeyResponse)
async def get_public_key(
    service: AuditChainService = Depends(get_audit_chain_service),
) -> PublicKeyResponse:
    return PublicKeyResponse(public_key=await service.get_public_verifying_key())
