from __future__ import annotations

from platform.admin.rbac import require_admin, require_superadmin
from platform.admin.responses import AdminActionResponse, AdminListResponse, accepted, empty_list
from typing import Any

from fastapi import APIRouter, Depends

router = APIRouter(tags=["admin", "security-compliance"])


@router.get("/audit-chain", response_model=AdminListResponse)
async def list_audit_chain_status(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("audit-chain", current_user)


@router.post("/audit-chain/verify", response_model=AdminActionResponse)
async def verify_audit_chain(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("verify", "audit-chain", affected_count=1)


@router.post("/audit-chain/export", response_model=AdminActionResponse)
async def export_audit_chain(
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("export", "audit-chain", affected_count=1)


@router.get("/security/sbom", response_model=AdminListResponse)
async def list_sboms(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("sboms", current_user)


@router.get("/security/pentests", response_model=AdminListResponse)
async def list_pentests(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("pentests", current_user)


@router.post("/security/pentests", response_model=AdminActionResponse)
async def schedule_pentest(
    _current_user: dict[str, Any] = Depends(require_admin),
) -> AdminActionResponse:
    return accepted("schedule", "pentests", affected_count=1)


@router.get("/security/rotations", response_model=AdminListResponse)
async def list_rotations(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("secret-rotations", current_user)


@router.post("/security/rotations/{rotation_id}/trigger", response_model=AdminActionResponse)
async def trigger_rotation(
    rotation_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("trigger", f"secret-rotations/{rotation_id}", affected_count=1)


@router.get("/security/jit", response_model=AdminListResponse)
async def list_jit_credentials(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("jit-credentials", current_user)


@router.post("/security/jit/{grant_id}/approve", response_model=AdminActionResponse)
async def approve_jit_credential(
    grant_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("approve", f"jit-credentials/{grant_id}", affected_count=1)


@router.post("/security/jit/{grant_id}/revoke", response_model=AdminActionResponse)
async def revoke_jit_credential(
    grant_id: str,
    _current_user: dict[str, Any] = Depends(require_superadmin),
) -> AdminActionResponse:
    return accepted("revoke", f"jit-credentials/{grant_id}", affected_count=1)


@router.get("/compliance", response_model=AdminListResponse)
async def list_compliance_controls(
    current_user: dict[str, Any] = Depends(require_admin),
) -> AdminListResponse:
    return empty_list("compliance-controls", current_user)
