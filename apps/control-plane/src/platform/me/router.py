from __future__ import annotations

from datetime import datetime
from platform.accounts.memberships_router import router as memberships_router
from platform.audit.dependencies import get_audit_chain_service
from platform.audit.service import AuditChainService
from platform.auth.dependencies import get_auth_service
from platform.auth.service import AuthService
from platform.common.dependencies import get_current_user
from platform.notifications.dependencies import get_notifications_service
from platform.notifications.service import AlertService
from platform.privacy_compliance.dependencies import get_consent_service, get_dsr_service
from platform.privacy_compliance.services.consent_service import ConsentService
from platform.privacy_compliance.services.dsr_service import DSRService
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from .schemas import (
    RevokeOtherSessionsResponse,
    UserActivityListResponse,
    UserConsentHistoryResponse,
    UserConsentListResponse,
    UserConsentRevokeRequest,
    UserDSRDetailResponse,
    UserDSRListResponse,
    UserDSRSubmitRequest,
    UserNotificationPreferencesResponse,
    UserNotificationPreferencesUpdateRequest,
    UserNotificationTestResponse,
    UserServiceAccountCreateRequest,
    UserServiceAccountCreateResponse,
    UserServiceAccountListResponse,
    UserSessionListResponse,
)
from .service import MeService

router = APIRouter(prefix="/me", tags=["me"])
router.include_router(memberships_router)


async def get_me_service(
    auth_service: AuthService = Depends(get_auth_service),
    consent_service: ConsentService = Depends(get_consent_service),
    dsr_service: DSRService = Depends(get_dsr_service),
    notifications_service: AlertService = Depends(get_notifications_service),
    audit_service: AuditChainService = Depends(get_audit_chain_service),
) -> MeService:
    return MeService(
        auth_service=auth_service,
        consent_service=consent_service,
        dsr_service=dsr_service,
        notifications_service=notifications_service,
        audit_service=audit_service,
    )


def _user_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _session_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["session_id"]))


@router.get("/sessions", response_model=UserSessionListResponse)
async def list_user_sessions(
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserSessionListResponse:
    return await me_service.list_sessions(_user_id(current_user), _session_id(current_user))


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_user_session(
    session_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> None:
    try:
        await me_service.revoke_session(
            _user_id(current_user),
            session_id,
            _session_id(current_user),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="cannot revoke current session") from exc


@router.post("/sessions/revoke-others", response_model=RevokeOtherSessionsResponse)
async def revoke_other_sessions(
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> RevokeOtherSessionsResponse:
    return await me_service.revoke_other_sessions(_user_id(current_user), _session_id(current_user))


@router.get("/service-accounts", response_model=UserServiceAccountListResponse)
async def list_service_accounts(
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserServiceAccountListResponse:
    return await me_service.list_service_accounts(_user_id(current_user))


@router.post(
    "/service-accounts",
    response_model=UserServiceAccountCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_service_account(
    payload: UserServiceAccountCreateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserServiceAccountCreateResponse:
    return await me_service.create_service_account(_user_id(current_user), payload)


@router.delete("/service-accounts/{sa_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_service_account(
    sa_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> None:
    await me_service.revoke_service_account(_user_id(current_user), sa_id)


@router.get("/consent", response_model=UserConsentListResponse)
async def list_consents(
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserConsentListResponse:
    return await me_service.list_consents(_user_id(current_user))


@router.post("/consent/revoke")
async def revoke_consent(
    payload: UserConsentRevokeRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> object:
    return await me_service.revoke_consent(_user_id(current_user), payload.consent_type.value)


@router.get("/consent/history", response_model=UserConsentHistoryResponse)
async def list_consent_history(
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserConsentHistoryResponse:
    return await me_service.list_consent_history(_user_id(current_user))


@router.post("/dsr", response_model=UserDSRDetailResponse, status_code=status.HTTP_201_CREATED)
async def submit_dsr(
    payload: UserDSRSubmitRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserDSRDetailResponse:
    return await me_service.submit_dsr(_user_id(current_user), payload)


@router.get("/dsr", response_model=UserDSRListResponse)
async def list_dsrs(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserDSRListResponse:
    return await me_service.list_dsrs(_user_id(current_user), limit, cursor)


@router.get("/dsr/{dsr_id}", response_model=UserDSRDetailResponse)
async def get_dsr(
    dsr_id: UUID,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserDSRDetailResponse:
    return await me_service.get_dsr(_user_id(current_user), dsr_id)


@router.get("/activity", response_model=UserActivityListResponse)
async def list_activity(
    start_ts: datetime | None = Query(default=None),
    end_ts: datetime | None = Query(default=None),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserActivityListResponse:
    return await me_service.list_activity(
        _user_id(current_user),
        start_ts=start_ts,
        end_ts=end_ts,
        event_type=event_type,
        limit=limit,
        cursor=cursor,
    )


@router.get("/notification-preferences", response_model=UserNotificationPreferencesResponse)
async def get_notification_preferences(
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserNotificationPreferencesResponse:
    return await me_service.get_notification_preferences(_user_id(current_user))


@router.put("/notification-preferences", response_model=UserNotificationPreferencesResponse)
async def update_notification_preferences(
    payload: UserNotificationPreferencesUpdateRequest,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserNotificationPreferencesResponse:
    return await me_service.update_notification_preferences(_user_id(current_user), payload)


@router.post(
    "/notification-preferences/test/{event_type}",
    response_model=UserNotificationTestResponse,
)
async def send_test_notification(
    event_type: str,
    current_user: dict[str, Any] = Depends(get_current_user),
    me_service: MeService = Depends(get_me_service),
) -> UserNotificationTestResponse:
    return await me_service.test_notification(_user_id(current_user), event_type)
