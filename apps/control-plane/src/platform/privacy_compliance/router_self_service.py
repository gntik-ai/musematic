from __future__ import annotations

from platform.common.dependencies import get_current_user
from platform.privacy_compliance.dependencies import get_consent_service, get_dsr_service
from platform.privacy_compliance.models import ConsentType
from platform.privacy_compliance.schemas import (
    ConsentRecordRequest,
    ConsentRecordResponse,
    ConsentStateResponse,
    DisclosureResponse,
    DSRResponse,
    DSRSelfServiceCreateRequest,
)
from platform.privacy_compliance.services.consent_service import DISCLOSURE_TEXT, ConsentService
from platform.privacy_compliance.services.dsr_service import DSRService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

router = APIRouter(prefix="/api/v1/me", tags=["privacy", "self-service"])


@router.post("/dsr", response_model=DSRResponse, status_code=status.HTTP_201_CREATED)
async def create_own_dsr(
    payload: DSRSelfServiceCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    user_id = _user_id(current_user)
    from platform.privacy_compliance.schemas import DSRCreateRequest

    return await service.create_request(
        DSRCreateRequest(
            subject_user_id=user_id,
            request_type=payload.request_type,
            legal_basis=payload.legal_basis,
        ),
        requested_by=user_id,
    )


@router.get("/dsr", response_model=list[DSRResponse])
async def list_own_dsrs(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DSRService = Depends(get_dsr_service),
) -> list[DSRResponse]:
    return await service.list_requests(subject_user_id=_user_id(current_user))


@router.get("/dsr/{dsr_id}", response_model=DSRResponse)
async def get_own_dsr(
    dsr_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: DSRService = Depends(get_dsr_service),
) -> DSRResponse:
    response = await service.get_request(dsr_id)
    if response.subject_user_id != _user_id(current_user):
        from platform.common.exceptions import AuthorizationError

        raise AuthorizationError("PRIVACY_DSR_SCOPE_VIOLATION", "Cannot access another user's DSR")
    return response


@router.get("/consents", response_model=ConsentStateResponse)
async def get_own_consents(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ConsentService = Depends(get_consent_service),
) -> ConsentStateResponse:
    return ConsentStateResponse(state=await service.get_state(_user_id(current_user)))


@router.put("/consents", response_model=list[ConsentRecordResponse])
async def put_own_consents(
    payload: ConsentRecordRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ConsentService = Depends(get_consent_service),
) -> list[ConsentRecordResponse]:
    records = await service.record_consents(
        _user_id(current_user),
        payload.choices,
        payload.workspace_id,
    )
    return [ConsentRecordResponse.model_validate(record) for record in records]


@router.post("/consents/{consent_type}/revoke", response_model=ConsentRecordResponse)
async def revoke_own_consent(
    consent_type: ConsentType,
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ConsentService = Depends(get_consent_service),
) -> ConsentRecordResponse:
    return ConsentRecordResponse.model_validate(
        await service.revoke(_user_id(current_user), consent_type.value)
    )


@router.get("/consents/history", response_model=list[ConsentRecordResponse])
async def get_own_consent_history(
    current_user: dict[str, Any] = Depends(get_current_user),
    service: ConsentService = Depends(get_consent_service),
) -> list[ConsentRecordResponse]:
    return [
        ConsentRecordResponse.model_validate(record)
        for record in await service.history(_user_id(current_user))
    ]


@router.get("/consents/disclosure", response_model=DisclosureResponse)
async def get_disclosure() -> DisclosureResponse:
    return DisclosureResponse(text=DISCLOSURE_TEXT, required_consents=list(ConsentType))


def _user_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user.get("sub") or current_user.get("principal_id")))
