from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.privacy_compliance.dependencies import (
    get_dlp_service,
    get_dsr_service,
    get_pia_service,
    get_residency_service,
    require_privacy_admin,
    require_privacy_reader,
)
from platform.privacy_compliance.schemas import (
    ConsentRecordResponse,
    DLPEventResponse,
    DLPRuleCreateRequest,
    DLPRuleResponse,
    DLPRuleUpdateRequest,
    DSRCancelRequest,
    DSRCreateRequest,
    DSRResponse,
    DSRRetryRequest,
    PIACreateRequest,
    PIARejectRequest,
    PIAResponse,
    ResidencyCheckRequest,
    ResidencyCheckResponse,
    ResidencyConfigRequest,
    ResidencyConfigResponse,
    SignedTombstoneResponse,
    TombstoneResponse,
)
from platform.privacy_compliance.services.dlp_service import DLPService
from platform.privacy_compliance.services.dsr_service import DSRService
from platform.privacy_compliance.services.pia_service import PIAService
from platform.privacy_compliance.services.residency_service import ResidencyService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/api/v1/privacy", tags=["admin", "privacy"])


@router.post(
    "/dsr",
    response_model=DSRResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["admin", "privacy", "dsr"],
)
async def create_dsr(
    payload: DSRCreateRequest,
    current_user: dict[str, Any] = Depends(require_privacy_admin),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    return await service.create_request(payload, requested_by=_actor_id(current_user))


@router.get("/dsr", response_model=list[DSRResponse], tags=["admin", "privacy", "dsr"])
async def list_dsrs(
    subject_user_id: UUID | None = None,
    request_type: str | None = None,
    status: str | None = None,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DSRService = Depends(get_dsr_service),
) -> list[DSRResponse]:
    return await service.list_requests(
        subject_user_id=subject_user_id,
        request_type=request_type,
        status=status,
    )


@router.get("/dsr/{dsr_id}", response_model=DSRResponse, tags=["admin", "privacy", "dsr"])
async def get_dsr(
    dsr_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    return await service.get_request(dsr_id)


@router.post("/dsr/{dsr_id}/cancel", response_model=DSRResponse, tags=["admin", "privacy", "dsr"])
async def cancel_dsr(
    dsr_id: UUID,
    payload: DSRCancelRequest,
    _: dict[str, Any] = Depends(require_privacy_admin),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    return await service.cancel(dsr_id, reason=payload.reason)


@router.post("/dsr/{dsr_id}/retry", response_model=DSRResponse, tags=["admin", "privacy", "dsr"])
async def retry_dsr(
    dsr_id: UUID,
    _: DSRRetryRequest,
    __: dict[str, Any] = Depends(require_privacy_admin),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    return await service.retry(dsr_id)


@router.post("/dsr/{dsr_id}/process", response_model=DSRResponse, tags=["admin", "privacy", "dsr"])
async def process_dsr(
    dsr_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_admin),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    return await service.process(dsr_id)


@router.get(
    "/dsr/{dsr_id}/tombstone",
    response_model=TombstoneResponse,
    tags=["admin", "privacy", "dsr"],
)
async def get_tombstone(
    dsr_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DSRService = Depends(get_dsr_service),
) -> TombstoneResponse:
    dsr = await service.repository.get_dsr(dsr_id)
    if dsr is None or dsr.tombstone_id is None:
        from platform.privacy_compliance.exceptions import TombstoneNotFoundError

        raise TombstoneNotFoundError(dsr_id)
    tombstone = await service.repository.get_tombstone(dsr.tombstone_id)
    if tombstone is None:
        from platform.privacy_compliance.exceptions import TombstoneNotFoundError

        raise TombstoneNotFoundError(dsr.tombstone_id)
    return TombstoneResponse(
        id=tombstone.id,
        subject_user_id_hash=tombstone.subject_user_id_hash,
        salt_version=tombstone.salt_version,
        entities_deleted=tombstone.entities_deleted,
        cascade_log=tombstone.cascade_log,
        proof_hash=tombstone.proof_hash,
        created_at=tombstone.created_at,
    )


@router.post(
    "/dsr/{dsr_id}/tombstone/signed",
    response_model=SignedTombstoneResponse,
    tags=["admin", "privacy", "dsr"],
)
async def export_signed_tombstone(
    dsr_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DSRService = Depends(get_dsr_service),
) -> SignedTombstoneResponse:
    dsr = await service.repository.get_dsr(dsr_id)
    if dsr is None or dsr.tombstone_id is None:
        from platform.privacy_compliance.exceptions import TombstoneNotFoundError

        raise TombstoneNotFoundError(dsr_id)
    signed = await service.orchestrator.export_signed(dsr.tombstone_id)
    return SignedTombstoneResponse(
        tombstone=signed.tombstone,
        key_version=signed.key_version,
        signature=signed.signature,
        proof_hash=signed.proof_hash,
    )


@router.get("/dsr/{dsr_id}/export", tags=["admin", "privacy", "dsr"])
async def export_dsr(
    dsr_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DSRService = Depends(get_dsr_service),
) -> dict[str, Any]:
    return {"dsr": (await service.get_request(dsr_id)).model_dump(mode="json")}


@router.get(
    "/consents",
    response_model=list[ConsentRecordResponse],
    tags=["admin", "privacy", "consent"],
)
async def get_consent_history(
    user_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DSRService = Depends(get_dsr_service),
) -> list[ConsentRecordResponse]:
    records = await service.repository.get_consent_records(user_id)
    return [ConsentRecordResponse.model_validate(record) for record in records]


@router.post("/pia", response_model=PIAResponse, status_code=201, tags=["admin", "privacy", "pia"])
async def create_pia(
    payload: PIACreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PIAService = Depends(get_pia_service),
) -> PIAResponse:
    pia = await service.submit_draft(
        subject_type=payload.subject_type.value,
        subject_id=payload.subject_id,
        data_categories=payload.data_categories,
        legal_basis=payload.legal_basis,
        retention_policy=payload.retention_policy,
        risks=payload.risks,
        mitigations=payload.mitigations,
        submitted_by=_actor_id(current_user),
    )
    return PIAResponse.model_validate(pia)


@router.get("/pia", response_model=list[PIAResponse], tags=["admin", "privacy", "pia"])
async def list_pias(
    subject_type: str | None = None,
    subject_id: UUID | None = None,
    status: str | None = None,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: PIAService = Depends(get_pia_service),
) -> list[PIAResponse]:
    items = await service.repository.list_pias(
        subject_type=subject_type,
        subject_id=subject_id,
        status=status,
    )
    return [PIAResponse.model_validate(item) for item in items]


@router.post("/pia/{pia_id}/submit", response_model=PIAResponse, tags=["admin", "privacy", "pia"])
async def submit_pia(
    pia_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: PIAService = Depends(get_pia_service),
) -> PIAResponse:
    return PIAResponse.model_validate(
        await service.submit_for_review(pia_id, _actor_id(current_user))
    )


@router.post("/pia/{pia_id}/approve", response_model=PIAResponse, tags=["admin", "privacy", "pia"])
async def approve_pia(
    pia_id: UUID,
    current_user: dict[str, Any] = Depends(require_privacy_admin),
    service: PIAService = Depends(get_pia_service),
) -> PIAResponse:
    return PIAResponse.model_validate(await service.approve(pia_id, _actor_id(current_user)))


@router.post("/pia/{pia_id}/reject", response_model=PIAResponse, tags=["admin", "privacy", "pia"])
async def reject_pia(
    pia_id: UUID,
    payload: PIARejectRequest,
    current_user: dict[str, Any] = Depends(require_privacy_admin),
    service: PIAService = Depends(get_pia_service),
) -> PIAResponse:
    return PIAResponse.model_validate(
        await service.reject(pia_id, _actor_id(current_user), payload.feedback)
    )


@router.get(
    "/pia/subject/{subject_type}/{subject_id}/active",
    response_model=PIAResponse | None,
    tags=["admin", "privacy", "pia"],
)
async def active_pia(
    subject_type: str,
    subject_id: UUID,
    _: dict[str, Any] = Depends(get_current_user),
    service: PIAService = Depends(get_pia_service),
) -> PIAResponse | None:
    item = await service.get_approved_pia(subject_type, subject_id)
    return None if item is None else PIAResponse.model_validate(item)


@router.get(
    "/residency/{workspace_id}",
    response_model=ResidencyConfigResponse | None,
    tags=["admin", "privacy", "residency"],
)
async def get_residency(
    workspace_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: ResidencyService = Depends(get_residency_service),
) -> ResidencyConfigResponse | None:
    item = await service.get_config(workspace_id)
    return None if item is None else ResidencyConfigResponse.model_validate(item)


@router.put(
    "/residency/{workspace_id}",
    response_model=ResidencyConfigResponse,
    tags=["admin", "privacy", "residency"],
)
async def put_residency(
    workspace_id: UUID,
    payload: ResidencyConfigRequest,
    current_user: dict[str, Any] = Depends(require_privacy_admin),
    service: ResidencyService = Depends(get_residency_service),
) -> ResidencyConfigResponse:
    item = await service.set_config(
        workspace_id,
        payload.region_code,
        payload.allowed_transfer_regions,
        actor=_actor_id(current_user),
    )
    return ResidencyConfigResponse.model_validate(item)


@router.post(
    "/residency/{workspace_id}/check",
    response_model=ResidencyCheckResponse,
    tags=["admin", "privacy", "residency"],
)
async def check_residency(
    workspace_id: UUID,
    payload: ResidencyCheckRequest,
    request: Request,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: ResidencyService = Depends(get_residency_service),
) -> ResidencyCheckResponse:
    origin_region = payload.origin_region or request.headers.get("X-Origin-Region") or "unknown"
    await service.enforce(workspace_id, origin_region)
    return ResidencyCheckResponse(
        allowed=True,
        workspace_id=workspace_id,
        origin_region=origin_region,
    )


@router.delete("/residency/{workspace_id}", status_code=204, tags=["admin", "privacy", "residency"])
async def delete_residency(
    workspace_id: UUID,
    current_user: dict[str, Any] = Depends(require_privacy_admin),
    service: ResidencyService = Depends(get_residency_service),
) -> None:
    await service.delete_config(workspace_id, actor=_actor_id(current_user))


@router.get("/dlp/rules", response_model=list[DLPRuleResponse], tags=["admin", "privacy", "dlp"])
async def list_dlp_rules(
    workspace_id: UUID | None = None,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DLPService = Depends(get_dlp_service),
) -> list[DLPRuleResponse]:
    items = await service.repository.list_dlp_rules(workspace_id)
    return [DLPRuleResponse.model_validate(item) for item in items]


@router.post(
    "/dlp/rules",
    response_model=DLPRuleResponse,
    status_code=201,
    tags=["admin", "privacy", "dlp"],
)
async def create_dlp_rule(
    payload: DLPRuleCreateRequest,
    _: dict[str, Any] = Depends(require_privacy_admin),
    service: DLPService = Depends(get_dlp_service),
) -> DLPRuleResponse:
    return DLPRuleResponse.model_validate(
        await service.create_rule(
            name=payload.name,
            classification=payload.classification.value,
            pattern=payload.pattern,
            action=payload.action.value,
            workspace_id=payload.workspace_id,
        )
    )


@router.patch(
    "/dlp/rules/{rule_id}",
    response_model=DLPRuleResponse,
    tags=["admin", "privacy", "dlp"],
)
async def patch_dlp_rule(
    rule_id: UUID,
    payload: DLPRuleUpdateRequest,
    _: dict[str, Any] = Depends(require_privacy_admin),
    service: DLPService = Depends(get_dlp_service),
) -> DLPRuleResponse:
    return DLPRuleResponse.model_validate(
        await service.update_rule(
            rule_id,
            enabled=payload.enabled,
            action=payload.action.value if payload.action is not None else None,
        )
    )


@router.delete("/dlp/rules/{rule_id}", status_code=204, tags=["admin", "privacy", "dlp"])
async def delete_dlp_rule(
    rule_id: UUID,
    _: dict[str, Any] = Depends(require_privacy_admin),
    service: DLPService = Depends(get_dlp_service),
) -> None:
    await service.delete_rule(rule_id)


@router.get("/dlp/events", response_model=list[DLPEventResponse], tags=["admin", "privacy", "dlp"])
async def list_dlp_events(
    workspace_id: UUID | None = None,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DLPService = Depends(get_dlp_service),
) -> list[DLPEventResponse]:
    items = await service.repository.list_dlp_events(workspace_id)
    return [DLPEventResponse.model_validate(item) for item in items]


@router.get("/dlp/events/aggregate", tags=["admin", "privacy", "dlp"])
async def aggregate_dlp_events(
    workspace_id: UUID | None = None,
    _: dict[str, Any] = Depends(require_privacy_reader),
    service: DLPService = Depends(get_dlp_service),
) -> dict[str, Any]:
    items = await service.repository.list_dlp_events(workspace_id)
    counts: dict[str, int] = {}
    for item in items:
        counts[item.match_summary] = counts.get(item.match_summary, 0) + 1
    return {"counts": counts}


def _actor_id(current_user: dict[str, Any]) -> UUID:
    raw = current_user.get("sub") or current_user.get("principal_id")
    return UUID(str(raw))
