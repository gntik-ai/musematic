from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.model_catalog.dependencies import (
    get_catalog_service,
    get_credential_service,
    get_fallback_policy_service,
    get_injection_defense_service,
    get_model_card_service,
)
from platform.model_catalog.schemas import (
    BlockRequest,
    CatalogEntryCreate,
    CatalogEntryListResponse,
    CatalogEntryPatch,
    CatalogEntryResponse,
    CredentialCreate,
    CredentialListResponse,
    CredentialResponse,
    CredentialRotateRequest,
    CredentialRotateResponse,
    CredentialVaultRefPatch,
    DeprecateRequest,
    FallbackPolicyCreate,
    FallbackPolicyListResponse,
    FallbackPolicyPatch,
    FallbackPolicyResponse,
    InjectionFindingResponse,
    InjectionPatternCreate,
    InjectionPatternListResponse,
    InjectionPatternPatch,
    InjectionPatternResponse,
    ModelCardFields,
    ModelCardResponse,
    ReapproveRequest,
)
from platform.model_catalog.services.catalog_service import CatalogService
from platform.model_catalog.services.credential_service import CredentialService
from platform.model_catalog.services.fallback_service import FallbackPolicyService
from platform.model_catalog.services.injection_defense_service import InjectionDefenseService
from platform.model_catalog.services.model_card_service import ModelCardService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

router = APIRouter(prefix="/api/v1/model-catalog", tags=["admin", "model-catalog"])


def _role_names(current_user: dict[str, Any]) -> set[str]:
    roles = current_user.get("roles", [])
    if not isinstance(roles, list):
        return set()
    names: set[str] = set()
    for item in roles:
        if isinstance(item, dict) and item.get("role") is not None:
            names.add(str(item["role"]))
        elif isinstance(item, str):
            names.add(item)
    return names


def _require_admin(current_user: dict[str, Any]) -> None:
    if not (_role_names(current_user) & {"admin", "owner", "platform_admin", "superadmin"}):
        raise AuthorizationError("ADMIN_REQUIRED", "Model catalog mutation requires admin role")


def _require_superadmin(current_user: dict[str, Any]) -> None:
    if not (_role_names(current_user) & {"superadmin"}):
        raise AuthorizationError(
            "SUPERADMIN_REQUIRED",
            "Re-approving a model requires superadmin role",
        )


def _actor_id(current_user: dict[str, Any]) -> UUID:
    subject = current_user.get("sub")
    if subject is None:
        raise ValidationError("USER_ID_REQUIRED", "Human user subject is required")
    return UUID(str(subject))


def _workspace_id(request: Request) -> UUID | None:
    raw = request.headers.get("X-Workspace-ID")
    return None if not raw else UUID(raw)


@router.post("/entries", response_model=CatalogEntryResponse, status_code=201)
async def create_entry(
    payload: CatalogEntryCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryResponse:
    _require_admin(current_user)
    return await service.create_entry(payload, approved_by=_actor_id(current_user))


@router.get("/entries", response_model=CatalogEntryListResponse)
async def list_entries(
    provider: str | None = Query(default=None),
    status: str | None = Query(default=None),
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryListResponse:
    return await service.list_entries(provider=provider, status=status)


@router.get("/entries/{entry_id}", response_model=CatalogEntryResponse)
async def get_entry(
    entry_id: UUID,
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryResponse:
    return await service.get_entry(entry_id)


@router.patch("/entries/{entry_id}", response_model=CatalogEntryResponse)
async def update_entry(
    entry_id: UUID,
    payload: CatalogEntryPatch,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryResponse:
    _require_admin(current_user)
    return await service.update_entry(entry_id, payload, changed_by=_actor_id(current_user))


@router.post("/entries/{entry_id}/block", response_model=CatalogEntryResponse)
async def block_entry(
    entry_id: UUID,
    payload: BlockRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryResponse:
    _require_admin(current_user)
    return await service.block_entry(entry_id, payload, changed_by=_actor_id(current_user))


@router.post("/entries/{entry_id}/deprecate", response_model=CatalogEntryResponse)
async def deprecate_entry(
    entry_id: UUID,
    payload: DeprecateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryResponse:
    _require_admin(current_user)
    return await service.deprecate_entry(entry_id, payload, changed_by=_actor_id(current_user))


@router.post("/entries/{entry_id}/reapprove", response_model=CatalogEntryResponse)
async def reapprove_entry(
    entry_id: UUID,
    payload: ReapproveRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CatalogService = Depends(get_catalog_service),
) -> CatalogEntryResponse:
    _require_superadmin(current_user)
    return await service.reapprove_entry(entry_id, payload, changed_by=_actor_id(current_user))


@router.post("/fallback-policies", response_model=FallbackPolicyResponse, status_code=201)
async def create_fallback_policy(
    payload: FallbackPolicyCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FallbackPolicyService = Depends(get_fallback_policy_service),
) -> FallbackPolicyResponse:
    _require_admin(current_user)
    return await service.create_policy(payload)


@router.get("/fallback-policies", response_model=FallbackPolicyListResponse)
async def list_fallback_policies(
    primary_model_id: UUID | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    service: FallbackPolicyService = Depends(get_fallback_policy_service),
) -> FallbackPolicyListResponse:
    return await service.list_policies(primary_model_id=primary_model_id, scope_type=scope_type)


@router.patch("/fallback-policies/{policy_id}", response_model=FallbackPolicyResponse)
async def update_fallback_policy(
    policy_id: UUID,
    payload: FallbackPolicyPatch,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FallbackPolicyService = Depends(get_fallback_policy_service),
) -> FallbackPolicyResponse:
    _require_admin(current_user)
    return await service.update_policy(policy_id, payload)


@router.delete("/fallback-policies/{policy_id}", status_code=204)
async def delete_fallback_policy(
    policy_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: FallbackPolicyService = Depends(get_fallback_policy_service),
) -> Response:
    _require_admin(current_user)
    await service.delete_policy(policy_id)
    return Response(status_code=204)


@router.put("/entries/{entry_id}/card", response_model=ModelCardResponse)
async def upsert_card(
    entry_id: UUID,
    payload: ModelCardFields,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ModelCardService = Depends(get_model_card_service),
) -> ModelCardResponse:
    _require_admin(current_user)
    return await service.upsert_card(entry_id, payload)


@router.get("/entries/{entry_id}/card", response_model=ModelCardResponse)
async def get_card(
    entry_id: UUID,
    service: ModelCardService = Depends(get_model_card_service),
) -> ModelCardResponse:
    return await service.get_card(entry_id)


@router.get("/entries/{entry_id}/card/history", response_model=list[ModelCardResponse])
async def get_card_history(
    entry_id: UUID,
    service: ModelCardService = Depends(get_model_card_service),
) -> list[ModelCardResponse]:
    return await service.get_card_history(entry_id)


@router.post("/credentials", response_model=CredentialResponse, status_code=201)
async def create_credential(
    payload: CredentialCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> CredentialResponse:
    _require_admin(current_user)
    return await service.register_credential(payload)


@router.get("/credentials", response_model=CredentialListResponse)
async def list_credentials(
    request: Request,
    provider: str | None = Query(default=None),
    service: CredentialService = Depends(get_credential_service),
) -> CredentialListResponse:
    return await service.list_credentials(workspace_id=_workspace_id(request), provider=provider)


@router.patch("/credentials/{credential_id}/vault-ref", response_model=CredentialResponse)
async def update_credential_vault_ref(
    credential_id: UUID,
    payload: CredentialVaultRefPatch,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> CredentialResponse:
    _require_admin(current_user)
    return await service.update_vault_ref(credential_id, payload.vault_ref)


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> Response:
    _require_admin(current_user)
    await service.delete_credential(credential_id)
    return Response(status_code=204)


@router.post("/credentials/{credential_id}/rotate", response_model=CredentialRotateResponse)
async def rotate_credential(
    credential_id: UUID,
    payload: CredentialRotateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: CredentialService = Depends(get_credential_service),
) -> CredentialRotateResponse:
    _require_admin(current_user)
    return await service.trigger_rotation(
        credential_id,
        payload,
        requester_id=_actor_id(current_user),
    )


@router.post("/injection-patterns", response_model=InjectionPatternResponse, status_code=201)
async def create_injection_pattern(
    payload: InjectionPatternCreate,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: InjectionDefenseService = Depends(get_injection_defense_service),
) -> InjectionPatternResponse:
    _require_admin(current_user)
    return await service.create_pattern(payload)


@router.get("/injection-patterns", response_model=InjectionPatternListResponse)
async def list_injection_patterns(
    request: Request,
    layer: str | None = Query(default=None),
    service: InjectionDefenseService = Depends(get_injection_defense_service),
) -> InjectionPatternListResponse:
    return await service.list_patterns(layer=layer, workspace_id=_workspace_id(request))


@router.patch("/injection-patterns/{pattern_id}", response_model=InjectionPatternResponse)
async def update_injection_pattern(
    pattern_id: UUID,
    payload: InjectionPatternPatch,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: InjectionDefenseService = Depends(get_injection_defense_service),
) -> InjectionPatternResponse:
    _require_admin(current_user)
    return await service.update_pattern(pattern_id, payload)


@router.delete("/injection-patterns/{pattern_id}", status_code=204)
async def delete_injection_pattern(
    pattern_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: InjectionDefenseService = Depends(get_injection_defense_service),
) -> Response:
    _require_admin(current_user)
    await service.delete_pattern(pattern_id)
    return Response(status_code=204)


@router.get("/injection-findings", response_model=list[InjectionFindingResponse])
async def list_injection_findings(
    request: Request,
    layer: str | None = Query(default=None),
    service: InjectionDefenseService = Depends(get_injection_defense_service),
) -> list[InjectionFindingResponse]:
    return service.list_findings(workspace_id=_workspace_id(request), layer=layer)
