from __future__ import annotations

import base64
from datetime import UTC, datetime
from platform.audit.repository import AuditChainRepository
from platform.audit.repository import _decode_cursor as _decode_audit_cursor
from platform.audit.repository import _encode_cursor as _encode_audit_cursor
from platform.auth.repository import AuthRepository
from platform.auth.schemas import ServiceAccountCreateResponse
from platform.auth.service import AuthService
from platform.common.config import AuthSettings
from platform.common.exceptions import AuthorizationError, NotFoundError
from platform.common.exceptions import ValidationError as PlatformValidationError
from platform.me.router import (
    create_service_account as route_create_service_account,
)
from platform.me.router import (
    get_dsr as route_get_dsr,
)
from platform.me.router import (
    get_me_service,
)
from platform.me.router import (
    get_notification_preferences as route_get_notification_preferences,
)
from platform.me.router import (
    list_activity as route_list_activity,
)
from platform.me.router import (
    list_consent_history as route_list_consent_history,
)
from platform.me.router import (
    list_consents as route_list_consents,
)
from platform.me.router import (
    list_dsrs as route_list_dsrs,
)
from platform.me.router import (
    list_service_accounts as route_list_service_accounts,
)
from platform.me.router import (
    list_user_sessions as route_list_user_sessions,
)
from platform.me.router import (
    revoke_consent as route_revoke_consent,
)
from platform.me.router import (
    revoke_other_sessions as route_revoke_other_sessions,
)
from platform.me.router import (
    revoke_service_account as route_revoke_service_account,
)
from platform.me.router import (
    revoke_user_session as route_revoke_user_session,
)
from platform.me.router import (
    send_test_notification as route_send_test_notification,
)
from platform.me.router import (
    submit_dsr as route_submit_dsr,
)
from platform.me.router import (
    update_notification_preferences as route_update_notification_preferences,
)
from platform.me.schemas import (
    RevokeOtherSessionsResponse,
    UserActivityItem,
    UserActivityListResponse,
    UserConsentHistoryResponse,
    UserConsentItem,
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
from platform.me.service import (
    MeService,
    _decode_offset_cursor,
    _encode_offset_cursor,
    _hash_prefix,
    _json_safe,
)
from platform.notifications.models import AlertDeliveryOutcome, DeliveryMethod
from platform.notifications.repository import NotificationsRepository
from platform.notifications.schemas import UserAlertSettingsRead
from platform.notifications.service import AlertService
from platform.privacy_compliance.models import ConsentType, DSRRequestType, DSRStatus
from platform.privacy_compliance.schemas import DSRResponse
from platform.privacy_compliance.services.consent_service import ConsentService
from platform.privacy_compliance.services.dsr_service import DSRService
from platform.privacy_compliance.services.dsr_service import (
    _decode_offset_cursor as _decode_dsr_cursor,
)
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _settings(
    user_id: UUID,
    *,
    method: DeliveryMethod = DeliveryMethod.in_app,
) -> UserAlertSettingsRead:
    return UserAlertSettingsRead(
        id=uuid4(),
        user_id=user_id,
        state_transitions=["working_to_pending"],
        delivery_method=method,
        webhook_url=None,
        per_channel_preferences={},
        digest_mode={},
        quiet_hours=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _dsr(subject_user_id: UUID) -> DSRResponse:
    return DSRResponse(
        id=uuid4(),
        subject_user_id=subject_user_id,
        request_type=DSRRequestType.access,
        requested_by=subject_user_id,
        status=DSRStatus.received,
        requested_at=NOW,
    )


def _consent_record(
    user_id: UUID,
    *,
    granted: bool = True,
    revoked_at: datetime | None = None,
) -> SimpleNamespace:
    del user_id
    return SimpleNamespace(
        id=uuid4(),
        consent_type=ConsentType.data_collection,
        granted=granted,
        granted_at=NOW,
        revoked_at=revoked_at,
        workspace_id=uuid4(),
    )


class AuditStub:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.append_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.entry = SimpleNamespace(
            id=uuid4(),
            event_type="notifications.preferences.updated",
            audit_event_source="platform.me",
            severity="info",
            created_at=NOW,
            canonical_payload={"actor_id": str(user_id)},
        )

    async def append(self, *args: Any, **kwargs: Any) -> None:
        self.append_calls.append((args, kwargs))

    async def list_entries_by_actor_or_subject(
        self,
        *,
        actor_id: UUID,
        subject_id: UUID,
        start_ts: Any | None,
        end_ts: Any | None,
        event_type: str | None,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[SimpleNamespace], str]:
        assert actor_id == self.user_id
        assert subject_id == self.user_id
        assert start_ts == NOW
        assert end_ts == NOW
        assert event_type == "notifications.preferences.updated"
        assert limit == 5
        assert cursor == "cursor"
        return [self.entry], "next"


class AuthStub:
    def __init__(self, user_id: UUID, current_session_id: UUID, other_session_id: UUID) -> None:
        self.user_id = user_id
        self.current_session_id = current_session_id
        self.other_session_id = other_session_id
        self.revoked_sessions: list[UUID] = []
        self.revoked_service_accounts: list[UUID] = []

    async def list_user_sessions(
        self,
        user_id: UUID,
        current_session_id: UUID,
    ) -> list[dict[str, Any]]:
        assert user_id == self.user_id
        assert current_session_id == self.current_session_id
        return [
            {
                "session_id": self.current_session_id,
                "device_info": "desktop",
                "ip_address": "127.0.0.1",
                "location": "Localhost",
                "created_at": NOW,
                "last_activity": NOW,
                "is_current": True,
            },
            {
                "session_id": self.other_session_id,
                "device_info": "phone",
                "ip_address": "10.0.0.5",
                "location": "Private network",
                "created_at": NOW,
                "last_activity": NOW,
                "is_current": False,
            },
        ]

    async def revoke_session_by_id(
        self,
        user_id: UUID,
        session_id: UUID,
        current_session_id: UUID,
    ) -> None:
        assert user_id == self.user_id
        assert current_session_id == self.current_session_id
        self.revoked_sessions.append(session_id)

    async def revoke_other_sessions(self, user_id: UUID, current_session_id: UUID) -> int:
        assert user_id == self.user_id
        assert current_session_id == self.current_session_id
        return 2

    async def list_for_current_user(self, user_id: UUID) -> list[SimpleNamespace]:
        assert user_id == self.user_id
        return [
            SimpleNamespace(
                service_account_id=uuid4(),
                name="personal automation",
                role="service_account",
                status="active",
                workspace_id=None,
                created_at=NOW,
                last_used_at=NOW,
                api_key_hash="dummy",
            )
        ]

    async def create_for_current_user(
        self,
        user_id: UUID,
        name: str,
        scopes: list[str],
        expiry: datetime | None,
        mfa_token: str | None,
    ) -> ServiceAccountCreateResponse:
        assert user_id == self.user_id
        assert name == "cli"
        assert scopes == ["agents:read"]
        assert expiry is None
        assert mfa_token == "123456"
        return ServiceAccountCreateResponse(
            service_account_id=uuid4(),
            name=name,
            role="service_account",
            api_key="msk_test",
        )

    async def revoke_for_current_user(self, user_id: UUID, sa_id: UUID) -> None:
        assert user_id == self.user_id
        self.revoked_service_accounts.append(sa_id)


class ConsentStub:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.granted = _consent_record(user_id)
        self.revoked = _consent_record(user_id, granted=False, revoked_at=NOW)

    async def list_for_user(self, user_id: UUID) -> list[SimpleNamespace]:
        assert user_id == self.user_id
        return [self.granted]

    async def revoke(self, user_id: UUID, consent_type: str) -> SimpleNamespace:
        assert user_id == self.user_id
        assert consent_type == ConsentType.data_collection.value
        return self.revoked

    async def list_history_for_user(self, user_id: UUID) -> list[SimpleNamespace]:
        assert user_id == self.user_id
        return [self.granted, self.revoked]


class DSREventsStub:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def publish(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append((args, kwargs))


class DSRStub:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.response = _dsr(user_id)
        self.get_response = self.response
        self.events = DSREventsStub()
        self.created_payloads: list[Any] = []

    async def create_request(self, payload: Any, *, requested_by: UUID) -> DSRResponse:
        assert requested_by == self.user_id
        self.created_payloads.append(payload)
        return self.response

    async def list_for_subject(
        self,
        user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> list[DSRResponse]:
        assert user_id == self.user_id
        assert cursor == _encode_offset_cursor(4)
        return [self.response for _ in range(limit)]

    async def get_request(self, dsr_id: UUID) -> DSRResponse:
        assert dsr_id == self.get_response.id
        return self.get_response


class NotificationRepoStub:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.existing: UserAlertSettingsRead | None = None
        self.upserts: list[dict[str, Any]] = []

    async def get_settings(self, user_id: UUID) -> UserAlertSettingsRead | None:
        assert user_id == self.user_id
        return self.existing

    async def upsert_settings(self, user_id: UUID, payload: dict[str, Any]) -> SimpleNamespace:
        assert user_id == self.user_id
        self.upserts.append(payload)
        return SimpleNamespace(**payload)


class NotificationsStub:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.repo = NotificationRepoStub(user_id)
        self.producer = None
        self.tested: list[str] = []

    async def get_or_default_settings(self, user_id: UUID) -> UserAlertSettingsRead:
        assert user_id == self.user_id
        return _settings(user_id)

    async def test_notification(self, user_id: UUID, event_type: str) -> SimpleNamespace:
        assert user_id == self.user_id
        self.tested.append(event_type)
        return SimpleNamespace(id=uuid4())


@pytest.mark.asyncio
async def test_me_service_self_service_flows() -> None:
    user_id = uuid4()
    current_session_id = uuid4()
    other_session_id = uuid4()
    auth = AuthStub(user_id, current_session_id, other_session_id)
    consent = ConsentStub(user_id)
    dsr = DSRStub(user_id)
    notifications = NotificationsStub(user_id)
    audit = AuditStub(user_id)
    service = MeService(
        auth_service=auth,
        consent_service=consent,
        dsr_service=dsr,
        notifications_service=notifications,
        audit_service=audit,
    )

    sessions = await service.list_sessions(user_id, current_session_id)
    assert [item.is_current for item in sessions.items] == [True, False]

    await service.revoke_session(user_id, other_session_id, current_session_id)
    assert auth.revoked_sessions == [other_session_id]

    revoked = await service.revoke_other_sessions(user_id, current_session_id)
    assert revoked.sessions_revoked == 2

    accounts = await service.list_service_accounts(user_id)
    assert accounts.items[0].api_key_prefix == "hash:dummy"

    created = await service.create_service_account(
        user_id,
        UserServiceAccountCreateRequest(
            name="cli",
            scopes=["agents:read"],
            mfa_token="123456",
        ),
    )
    assert created.api_key == "msk_test"

    service_account_id = uuid4()
    await service.revoke_service_account(user_id, service_account_id)
    assert auth.revoked_service_accounts == [service_account_id]

    consents = await service.list_consents(user_id)
    assert consents.items[0].granted is True
    revoked_consent = await service.revoke_consent(user_id, ConsentType.data_collection.value)
    assert revoked_consent.granted is False
    history = await service.list_consent_history(user_id)
    assert len(history.items) == 2

    submitted = await service.submit_dsr(
        user_id,
        UserDSRSubmitRequest(request_type=DSRRequestType.access, legal_basis="user request"),
    )
    assert submitted.id == dsr.response.id
    assert dsr.created_payloads[0].subject_user_id == user_id
    assert dsr.events.calls

    listed = await service.list_dsrs(user_id, 2, _encode_offset_cursor(4))
    assert listed.next_cursor == _encode_offset_cursor(6)
    assert len(listed.items) == 2

    detail = await service.get_dsr(user_id, dsr.response.id)
    assert detail.subject_user_id == user_id

    other_user_id = uuid4()
    dsr.get_response = _dsr(other_user_id)
    with pytest.raises(NotFoundError):
        await service.get_dsr(user_id, dsr.get_response.id)

    activity = await service.list_activity(
        user_id,
        start_ts=NOW,
        end_ts=NOW,
        event_type="notifications.preferences.updated",
        limit=5,
        cursor="cursor",
    )
    assert activity.next_cursor == "next"
    assert activity.items[0].canonical_payload == {"actor_id": str(user_id)}

    preferences = await service.get_notification_preferences(user_id)
    assert preferences.delivery_method == DeliveryMethod.in_app

    updated = await service.update_notification_preferences(
        user_id,
        UserNotificationPreferencesUpdateRequest(
            delivery_method=DeliveryMethod.email,
            state_transitions=["any_to_failed"],
            per_channel_preferences={"workspace.updated": [DeliveryMethod.email.value]},
            digest_mode={"daily": "09:00"},
        ),
    )
    assert updated.delivery_method == DeliveryMethod.email
    assert notifications.repo.upserts[0]["state_transitions"] == ["any_to_failed"]

    notifications.repo.existing = _settings(user_id, method=DeliveryMethod.sms)
    updated_existing = await service.update_notification_preferences(
        user_id,
        UserNotificationPreferencesUpdateRequest(quiet_hours={"tz": "UTC"}),
    )
    assert updated_existing.delivery_method == DeliveryMethod.sms
    assert notifications.repo.upserts[-1]["quiet_hours"] == {"tz": "UTC"}

    test_result = await service.test_notification(user_id, "workspace.updated")
    assert test_result.event_type == "workspace.updated"

    assert _hash_prefix("abcdef123456") == "hash:abcdef1234"
    assert _decode_offset_cursor(None) == 0
    assert _decode_offset_cursor("not valid base64") == 0
    assert _json_safe({user_id: [DeliveryMethod.email, NOW]}) == {
        str(user_id): [DeliveryMethod.email.value, NOW.isoformat()]
    }
    assert {call["event_type"] for _, call in audit.append_calls} >= {
        "auth.session.revoked",
        "auth.api_key.created",
        "notifications.preferences.updated",
    }


def test_me_schema_cross_model_validation_and_guards() -> None:
    user_id = uuid4()
    auth_response = ServiceAccountCreateResponse(
        service_account_id=uuid4(),
        name="cli",
        role="service_account",
        api_key="msk_test",
    )
    assert (
        UserServiceAccountCreateResponse.model_validate(auth_response).service_account_id
        == auth_response.service_account_id
    )
    assert (
        UserNotificationPreferencesResponse.model_validate(_settings(user_id)).delivery_method
        == DeliveryMethod.in_app
    )
    assert UserDSRDetailResponse.model_validate(_dsr(user_id)).subject_user_id == user_id

    with pytest.raises(ValidationError):
        UserDSRSubmitRequest(request_type=DSRRequestType.erasure)
    with pytest.raises(ValidationError):
        UserNotificationPreferencesUpdateRequest(
            per_channel_preferences={"security.login": []}
        )
    with pytest.raises(ValidationError):
        UserNotificationPreferencesUpdateRequest(
            per_channel_preferences={"workspace.updated": ["pagerduty"]}
        )


class RouterServiceStub:
    def __init__(self, user_id: UUID, session_id: UUID) -> None:
        self.user_id = user_id
        self.session_id = session_id
        self.fail_revoke = False
        self.calls: list[str] = []

    async def list_sessions(self, user_id: UUID, session_id: UUID) -> UserSessionListResponse:
        assert user_id == self.user_id
        assert session_id == self.session_id
        self.calls.append("list_sessions")
        return UserSessionListResponse(items=[])

    async def revoke_session(
        self,
        user_id: UUID,
        target_session_id: UUID,
        session_id: UUID,
    ) -> None:
        assert user_id == self.user_id
        assert session_id == self.session_id
        self.calls.append(f"revoke_session:{target_session_id}")
        if self.fail_revoke:
            raise ValueError("current")

    async def revoke_other_sessions(
        self,
        user_id: UUID,
        session_id: UUID,
    ) -> RevokeOtherSessionsResponse:
        assert user_id == self.user_id
        assert session_id == self.session_id
        self.calls.append("revoke_other_sessions")
        return RevokeOtherSessionsResponse(sessions_revoked=1)

    async def list_service_accounts(self, user_id: UUID) -> UserServiceAccountListResponse:
        assert user_id == self.user_id
        self.calls.append("list_service_accounts")
        return UserServiceAccountListResponse(items=[])

    async def create_service_account(
        self,
        user_id: UUID,
        payload: UserServiceAccountCreateRequest,
    ) -> UserServiceAccountCreateResponse:
        assert user_id == self.user_id
        assert payload.name == "cli"
        self.calls.append("create_service_account")
        return UserServiceAccountCreateResponse(
            service_account_id=uuid4(),
            name=payload.name,
            role="service_account",
            api_key="msk_test",
        )

    async def revoke_service_account(self, user_id: UUID, sa_id: UUID) -> None:
        assert user_id == self.user_id
        self.calls.append(f"revoke_service_account:{sa_id}")

    async def list_consents(self, user_id: UUID) -> UserConsentListResponse:
        assert user_id == self.user_id
        self.calls.append("list_consents")
        return UserConsentListResponse(items=[])

    async def revoke_consent(self, user_id: UUID, consent_type: str) -> UserConsentItem:
        assert user_id == self.user_id
        assert consent_type == ConsentType.data_collection.value
        self.calls.append("revoke_consent")
        return UserConsentItem.model_validate(_consent_record(user_id, granted=False))

    async def list_consent_history(self, user_id: UUID) -> UserConsentHistoryResponse:
        assert user_id == self.user_id
        self.calls.append("list_consent_history")
        return UserConsentHistoryResponse(items=[])

    async def submit_dsr(
        self,
        user_id: UUID,
        payload: UserDSRSubmitRequest,
    ) -> UserDSRDetailResponse:
        assert user_id == self.user_id
        assert payload.request_type == DSRRequestType.access
        self.calls.append("submit_dsr")
        return UserDSRDetailResponse.model_validate(_dsr(user_id))

    async def list_dsrs(
        self,
        user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> UserDSRListResponse:
        assert user_id == self.user_id
        assert limit == 5
        assert cursor == "cursor"
        self.calls.append("list_dsrs")
        return UserDSRListResponse(items=[], next_cursor=None)

    async def get_dsr(self, user_id: UUID, dsr_id: UUID) -> UserDSRDetailResponse:
        assert user_id == self.user_id
        self.calls.append(f"get_dsr:{dsr_id}")
        return UserDSRDetailResponse.model_validate(_dsr(user_id))

    async def list_activity(
        self,
        user_id: UUID,
        *,
        start_ts: Any | None,
        end_ts: Any | None,
        event_type: str | None,
        limit: int,
        cursor: str | None,
    ) -> UserActivityListResponse:
        assert user_id == self.user_id
        assert start_ts == NOW
        assert end_ts == NOW
        assert event_type == "auth.session.revoked"
        assert limit == 5
        assert cursor == "cursor"
        self.calls.append("list_activity")
        return UserActivityListResponse(
            items=[
                UserActivityItem(
                    id=uuid4(),
                    event_type=event_type,
                    audit_event_source="platform.me",
                    severity="info",
                    created_at=NOW,
                    canonical_payload=None,
                )
            ],
            next_cursor="next",
        )

    async def get_notification_preferences(
        self,
        user_id: UUID,
    ) -> UserNotificationPreferencesResponse:
        assert user_id == self.user_id
        self.calls.append("get_notification_preferences")
        return UserNotificationPreferencesResponse.model_validate(_settings(user_id))

    async def update_notification_preferences(
        self,
        user_id: UUID,
        payload: UserNotificationPreferencesUpdateRequest,
    ) -> UserNotificationPreferencesResponse:
        assert user_id == self.user_id
        assert payload.delivery_method == DeliveryMethod.email
        self.calls.append("update_notification_preferences")
        return UserNotificationPreferencesResponse(
            state_transitions=["any_to_failed"],
            delivery_method=DeliveryMethod.email,
        )

    async def test_notification(
        self,
        user_id: UUID,
        event_type: str,
    ) -> UserNotificationTestResponse:
        assert user_id == self.user_id
        assert event_type == "workspace.updated"
        self.calls.append("test_notification")
        return UserNotificationTestResponse(alert_id=uuid4(), event_type=event_type)


@pytest.mark.asyncio
async def test_me_router_functions_forward_authenticated_user() -> None:
    user_id = uuid4()
    session_id = uuid4()
    target_session_id = uuid4()
    current_user = {"sub": str(user_id), "session_id": str(session_id)}
    service = RouterServiceStub(user_id, session_id)

    built = await get_me_service(
        auth_service=object(),
        consent_service=object(),
        dsr_service=object(),
        notifications_service=object(),
        audit_service=object(),
    )
    assert isinstance(built, MeService)

    await route_list_user_sessions(current_user=current_user, me_service=service)
    await route_revoke_user_session(
        target_session_id,
        current_user=current_user,
        me_service=service,
    )
    service.fail_revoke = True
    with pytest.raises(HTTPException) as exc_info:
        await route_revoke_user_session(
            target_session_id,
            current_user=current_user,
            me_service=service,
        )
    assert exc_info.value.status_code == 400
    service.fail_revoke = False

    await route_revoke_other_sessions(current_user=current_user, me_service=service)
    await route_list_service_accounts(current_user=current_user, me_service=service)
    await route_create_service_account(
        UserServiceAccountCreateRequest(name="cli"),
        current_user=current_user,
        me_service=service,
    )
    await route_revoke_service_account(uuid4(), current_user=current_user, me_service=service)
    await route_list_consents(current_user=current_user, me_service=service)
    await route_revoke_consent(
        UserConsentRevokeRequest(consent_type=ConsentType.data_collection),
        current_user=current_user,
        me_service=service,
    )
    await route_list_consent_history(current_user=current_user, me_service=service)
    await route_submit_dsr(
        UserDSRSubmitRequest(request_type=DSRRequestType.access),
        current_user=current_user,
        me_service=service,
    )
    await route_list_dsrs(
        limit=5,
        cursor="cursor",
        current_user=current_user,
        me_service=service,
    )
    await route_get_dsr(uuid4(), current_user=current_user, me_service=service)
    await route_list_activity(
        start_ts=NOW,
        end_ts=NOW,
        event_type="auth.session.revoked",
        limit=5,
        cursor="cursor",
        current_user=current_user,
        me_service=service,
    )
    await route_get_notification_preferences(current_user=current_user, me_service=service)
    await route_update_notification_preferences(
        UserNotificationPreferencesUpdateRequest(delivery_method=DeliveryMethod.email),
        current_user=current_user,
        me_service=service,
    )
    await route_send_test_notification(
        "workspace.updated",
        current_user=current_user,
        me_service=service,
    )

    assert "test_notification" in service.calls


class SessionStoreForAuth:
    def __init__(self, current_session_id: UUID, other_session_id: UUID) -> None:
        self.current_session_id = current_session_id
        self.other_session_id = other_session_id
        self.deleted: list[UUID] = []

    async def list_sessions_by_user(self, user_id: UUID) -> list[dict[str, Any]]:
        return [
            {
                "session_id": str(self.current_session_id),
                "device_info": "laptop",
                "ip_address": "127.0.0.1",
                "created_at": NOW,
                "last_activity": NOW,
                "user_id": str(user_id),
            },
            {
                "session_id": str(self.other_session_id),
                "device_info": "phone",
                "ip_address": "10.1.2.3",
                "created_at": NOW,
                "last_activity": NOW,
                "user_id": str(user_id),
            },
        ]

    async def delete_session(self, user_id: UUID, session_id: UUID) -> None:
        del user_id
        self.deleted.append(session_id)


class AuthRepositoryForSelfService:
    db = None

    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.active_count = 0
        self.revoke_result = True
        self.created_credentials: list[dict[str, Any]] = []
        self.service_account = SimpleNamespace(
            service_account_id=uuid4(),
            name="existing",
            role="service_account",
        )

    async def get_mfa_enrollment(self, user_id: UUID) -> None:
        assert user_id == self.user_id
        return None

    async def count_active_service_accounts_for_user(self, user_id: UUID) -> int:
        assert user_id == self.user_id
        return self.active_count

    async def create_service_account_credential(self, **kwargs: Any) -> SimpleNamespace:
        self.created_credentials.append(kwargs)
        return SimpleNamespace(
            service_account_id=kwargs["sa_id"],
            name=kwargs["name"],
            role=kwargs["role"],
        )

    async def list_service_accounts_for_user(self, user_id: UUID) -> list[SimpleNamespace]:
        assert user_id == self.user_id
        return [self.service_account]

    async def revoke_service_account_for_user(self, user_id: UUID, sa_id: UUID) -> bool:
        assert user_id == self.user_id
        assert sa_id == self.service_account.service_account_id
        return self.revoke_result


@pytest.mark.asyncio
async def test_auth_service_self_service_sessions_and_api_keys() -> None:
    user_id = uuid4()
    current_session_id = uuid4()
    other_session_id = uuid4()
    repository = AuthRepositoryForSelfService(user_id)
    service = AuthService(
        repository=repository,
        redis_client=object(),
        settings=AuthSettings(jwt_secret_key="test-secret", jwt_algorithm="HS256"),
        producer=None,
    )
    session_store = SessionStoreForAuth(current_session_id, other_session_id)
    service.session_store = session_store

    sessions = await service.list_user_sessions(user_id, current_session_id)
    assert [item["location"] for item in sessions] == ["Localhost", "Private network"]
    assert [item["is_current"] for item in sessions] == [True, False]
    assert service._city_level_location("8.8.8.8") is None
    assert service._city_level_location("not-an-ip") is None

    with pytest.raises(ValueError, match="cannot revoke current session"):
        await service.revoke_session_by_id(user_id, current_session_id, current_session_id)

    await service.revoke_session_by_id(user_id, other_session_id, current_session_id)
    assert session_store.deleted == [other_session_id]

    revoked = await service.revoke_other_sessions(user_id, current_session_id)
    assert revoked == 1
    assert session_store.deleted[-1] == other_session_id

    created = await service.create_for_current_user(user_id, "automation")
    assert created.name == "automation"
    assert created.api_key.startswith("msk_")
    assert repository.created_credentials[-1]["created_by_user_id"] == user_id
    assert repository.created_credentials[-1]["workspace_id"] is None

    scope_checks: list[tuple[str, str, UUID | None]] = []

    async def allow_scope_check(
        *,
        user_id: UUID,
        resource_type: str,
        action: str,
        workspace_id: UUID | None,
        **_: Any,
    ) -> SimpleNamespace:
        del user_id
        scope_checks.append((resource_type, action, workspace_id))
        return SimpleNamespace(allowed=True)

    service.check_permission = allow_scope_check  # type: ignore[method-assign]
    await service.create_for_current_user(user_id, "scoped", scopes=["agents:read"])
    await service.create_for_current_user(user_id, "dotted", scopes=["workspaces.read"])
    assert scope_checks == [("agents", "read", None), ("workspaces", "read", None)]

    async def deny_scope_check(
        *,
        user_id: UUID,
        resource_type: str,
        action: str,
        workspace_id: UUID | None,
        **_: Any,
    ) -> SimpleNamespace:
        del user_id, resource_type, action, workspace_id
        return SimpleNamespace(allowed=False)

    service.check_permission = deny_scope_check  # type: ignore[method-assign]
    with pytest.raises(AuthorizationError):
        await service.create_for_current_user(user_id, "forbidden", scopes=["admin:write"])
    with pytest.raises(PlatformValidationError):
        await service.create_for_current_user(user_id, "bad-scope", scopes=["malformed"])

    assert await service.list_for_current_user(user_id) == [repository.service_account]

    await service.revoke_for_current_user(user_id, repository.service_account.service_account_id)
    repository.revoke_result = False
    with pytest.raises(NotFoundError):
        await service.revoke_for_current_user(
            user_id,
            repository.service_account.service_account_id,
        )

    repository.active_count = 10
    with pytest.raises(PlatformValidationError, match="maximum personal API key count reached"):
        await service.create_for_current_user(user_id, "too-many")


class PrivacyRepositoryForListing:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.items = [
            SimpleNamespace(
                id=uuid4(),
                subject_user_id=user_id,
                request_type=DSRRequestType.access.value,
                requested_by=user_id,
                status=DSRStatus.received.value,
                legal_basis=None,
                scheduled_release_at=None,
                requested_at=NOW,
                completed_at=None,
                completion_proof_hash=None,
                failure_reason=None,
                tombstone_id=None,
            )
            for _ in range(4)
        ]
        self.consent_records = [
            _consent_record(user_id, granted=True),
            _consent_record(user_id, granted=False, revoked_at=NOW),
        ]

    async def list_dsrs(self, *, subject_user_id: UUID, **_: Any) -> list[SimpleNamespace]:
        assert subject_user_id == self.user_id
        return self.items

    async def get_consent_records(self, user_id: UUID) -> list[SimpleNamespace]:
        assert user_id == self.user_id
        return list(reversed(self.consent_records))


@pytest.mark.asyncio
async def test_privacy_self_service_listing_helpers() -> None:
    user_id = uuid4()
    repository = PrivacyRepositoryForListing(user_id)
    publisher = DSREventsStub()
    dsr_service = DSRService(repository=repository, event_publisher=publisher)

    cursor = base64.urlsafe_b64encode(b"1").decode("ascii")
    listed = await dsr_service.list_for_subject(user_id, 2, cursor)
    assert [item.id for item in listed] == [repository.items[1].id, repository.items[2].id]
    assert _decode_dsr_cursor(None) == 0
    assert _decode_dsr_cursor("bad cursor") == 0

    consent_service = ConsentService(repository=repository, event_publisher=publisher)
    assert await consent_service.list_for_user(user_id) == list(
        reversed(repository.consent_records)
    )
    history = await consent_service.list_history_for_user(user_id)
    assert history[0].revoked_at == NOW


class AlertRepositoryForSelfService:
    def __init__(self, user_id: UUID, delivery_method: DeliveryMethod) -> None:
        self.user_id = user_id
        self.delivery_method = delivery_method
        self.marked_all_read = False
        self.created_alerts: list[dict[str, Any]] = []

    async def mark_all_read(self, user_id: UUID) -> int:
        assert user_id == self.user_id
        self.marked_all_read = True
        return 3

    async def get_settings(self, user_id: UUID) -> UserAlertSettingsRead:
        assert user_id == self.user_id
        return _settings(user_id, method=self.delivery_method)

    async def create_alert(self, **kwargs: Any) -> SimpleNamespace:
        self.created_alerts.append(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            alert_type=kwargs["alert_type"],
            title=kwargs["title"],
            body=kwargs["body"],
            urgency=kwargs["urgency"],
            read=False,
            interaction_id=kwargs["interaction_id"],
            source_reference=kwargs["source_reference"],
            created_at=NOW,
            updated_at=NOW,
        )


class AlertServiceProbe(AlertService):
    def __init__(self, repo: AlertRepositoryForSelfService, resolved_user: object | None) -> None:
        self.repo = repo
        self.producer = None
        self.localization_service = None
        self.resolved_user = resolved_user
        self.in_app: list[Any] = []
        self.dispatched: list[tuple[Any, Any, Any]] = []

    async def _resolve_user(self, user_id: str) -> object | None:
        assert user_id == str(self.repo.user_id)
        return self.resolved_user

    async def _publish_in_app(self, alert: Any) -> None:
        self.in_app.append(alert)

    async def _dispatch_for_settings(self, alert: Any, settings: Any, user: Any) -> None:
        self.dispatched.append((alert, settings, user))


@pytest.mark.asyncio
async def test_alert_service_mark_all_read_and_test_notification() -> None:
    user_id = uuid4()
    email_repo = AlertRepositoryForSelfService(user_id, DeliveryMethod.email)
    email_service = AlertServiceProbe(email_repo, resolved_user=None)

    marked = await email_service.mark_all_read(user_id)
    assert marked.updated == 3
    assert marked.unread_count == 0
    assert email_repo.marked_all_read is True

    alert = await email_service.test_notification(user_id, "workspace.updated")
    assert alert.alert_type == "workspace.updated"
    assert email_repo.created_alerts[0]["delivery_method"] == DeliveryMethod.email
    assert email_service.in_app

    in_app_repo = AlertRepositoryForSelfService(user_id, DeliveryMethod.in_app)
    in_app_service = AlertServiceProbe(in_app_repo, resolved_user=object())
    await in_app_service.test_notification(user_id, "security.login")
    assert in_app_repo.created_alerts[0]["delivery_method"] is None
    assert in_app_service.dispatched


def test_audit_cursor_helpers_round_trip_and_reject_bad_values() -> None:
    entry = SimpleNamespace(id=uuid4(), created_at=NOW)
    cursor = _encode_audit_cursor(entry)
    created_at, entry_id = _decode_audit_cursor(cursor)
    assert created_at == NOW
    assert entry_id == entry.id
    assert _decode_audit_cursor(None) == (None, None)
    assert _decode_audit_cursor(
        base64.urlsafe_b64encode(b"[]").decode("ascii")
    ) == (None, None)
    assert _decode_audit_cursor("not-json") == (None, None)


class ScalarList:
    def __init__(self, items: list[Any]) -> None:
        self.items = items

    def all(self) -> list[Any]:
        return self.items


class ExecuteResult:
    def __init__(
        self,
        items: list[Any] | None = None,
        *,
        scalar: Any | None = None,
        rowcount: int = 0,
    ) -> None:
        self.items = items or []
        self.scalar = scalar
        self.rowcount = rowcount

    def scalars(self) -> ScalarList:
        return ScalarList(self.items)

    def scalar_one(self) -> Any:
        return self.scalar

    def scalar_one_or_none(self) -> Any | None:
        return self.scalar


class QuerySession:
    def __init__(self, results: list[ExecuteResult]) -> None:
        self.results = results
        self.statements: list[Any] = []
        self.added: list[Any] = []
        self.flushed = 0
        self.scalar_results: list[Any] = []
        self.deleted: list[Any] = []

    async def execute(self, statement: Any) -> ExecuteResult:
        self.statements.append(statement)
        return self.results.pop(0)

    async def scalar(self, statement: Any) -> Any:
        self.statements.append(statement)
        return self.scalar_results.pop(0)

    async def get(self, _: Any, item_id: UUID) -> Any:
        self.statements.append(item_id)
        return self.results.pop(0).scalar

    def add(self, item: Any) -> None:
        self.added.append(item)

    async def delete(self, item: Any) -> None:
        self.deleted.append(item)

    async def flush(self) -> None:
        self.flushed += 1


@pytest.mark.asyncio
async def test_audit_repository_self_service_query_builders() -> None:
    entries = [
        SimpleNamespace(id=uuid4(), created_at=NOW),
        SimpleNamespace(id=uuid4(), created_at=NOW),
    ]
    session = QuerySession([ExecuteResult(entries), ExecuteResult(entries[:1])])
    repository = AuditChainRepository(session)

    page, next_cursor = await repository.list_entries_by_actor_or_subject(
        actor_id=uuid4(),
        subject_id=uuid4(),
        start_ts=NOW,
        end_ts=NOW,
        event_type="auth.session.revoked",
        limit=1,
        cursor=_encode_audit_cursor(entries[0]),
    )
    assert page == entries[:1]
    assert next_cursor is not None

    page_without_filters, cursor = await repository.list_entries_by_actor_or_subject(
        actor_id=None,
        subject_id=None,
        start_ts=None,
        end_ts=None,
        event_type=None,
        limit=5,
        cursor=None,
    )
    assert page_without_filters == entries[:1]
    assert cursor is None

    source_session = QuerySession([ExecuteResult(entries), ExecuteResult(entries)])
    source_repository = AuditChainRepository(source_session)
    assert (
        await source_repository.list_audit_sources_in_window(NOW, NOW, ["platform.me"])
        == entries
    )
    assert await source_repository.list_audit_sources_in_window(NOW, NOW) == entries


@pytest.mark.asyncio
async def test_auth_repository_self_service_queries() -> None:
    user_id = uuid4()
    service_account_id = uuid4()
    credential = SimpleNamespace(service_account_id=service_account_id)
    session = QuerySession(
        [
            ExecuteResult(scalar=2),
            ExecuteResult([credential]),
            ExecuteResult(scalar=credential),
            ExecuteResult(rowcount=1),
        ]
    )
    repository = AuthRepository(session)

    assert await repository.count_active_service_accounts_for_user(user_id) == 2
    assert await repository.list_service_accounts_for_user(user_id) == [credential]
    assert await repository.get_service_account_for_user(user_id, service_account_id) == credential
    assert await repository.revoke_service_account_for_user(user_id, service_account_id) is True

    create_session = QuerySession([])
    create_repository = AuthRepository(create_session)
    created = await create_repository.create_service_account_credential(
        sa_id=service_account_id,
        name="automation",
        key_hash="hash",
        role="service_account",
        workspace_id=None,
        created_by_user_id=user_id,
    )
    assert created.service_account_id == service_account_id
    assert create_session.added == [created]
    assert create_session.flushed == 1


@pytest.mark.asyncio
async def test_auth_repository_user_and_credential_ensure_paths() -> None:
    user_id = uuid4()
    other_user_id = uuid4()
    account = SimpleNamespace(id=user_id)
    other_account = SimpleNamespace(id=other_user_id)
    credential = SimpleNamespace(user_id=user_id)
    other_credential = SimpleNamespace(user_id=other_user_id)
    platform_user = SimpleNamespace(id=user_id)
    session = QuerySession(
        [
            ExecuteResult(scalar=account),
            ExecuteResult(scalar=account),
            ExecuteResult(scalar=credential),
            ExecuteResult(scalar=platform_user),
            ExecuteResult(scalar=platform_user),
            ExecuteResult(),
            ExecuteResult(scalar=account),
            ExecuteResult(),
            ExecuteResult(),
            ExecuteResult(scalar=account),
            ExecuteResult(),
            ExecuteResult(),
            ExecuteResult(scalar=other_account),
            ExecuteResult(),
            ExecuteResult(),
            ExecuteResult(),
        ]
    )
    repository = AuthRepository(session)

    assert await repository.get_account_user(user_id) == account
    assert await repository.get_account_user_by_email("USER@EXAMPLE.COM") == account
    assert await repository.get_credential_by_email("USER@EXAMPLE.COM") == credential
    assert await repository.get_platform_user(user_id) == platform_user
    assert await repository.get_platform_user_by_email("USER@EXAMPLE.COM") == platform_user

    created_platform_user = await repository.create_platform_user(
        user_id,
        "USER@EXAMPLE.COM",
        "User",
    )
    assert created_platform_user.email == "user@example.com"
    created_credential = await repository.create_credential(
        user_id,
        "USER@EXAMPLE.COM",
        "hash",
    )
    assert created_credential.email == "user@example.com"
    assert len(session.added) == 2

    assert await repository.ensure_account_user(user_id, "USER@EXAMPLE.COM", "User") == account
    assert await repository.ensure_account_user(user_id, "USER@EXAMPLE.COM", "User") == account
    with pytest.raises(ValueError, match="Account email already belongs"):
        await repository.ensure_account_user(user_id, "USER@EXAMPLE.COM", "User")
    with pytest.raises(LookupError):
        await repository.ensure_account_user(user_id, "USER@EXAMPLE.COM", "User")

    credential_session = QuerySession(
        [
            ExecuteResult(scalar=credential),
            ExecuteResult(),
            ExecuteResult(scalar=credential),
            ExecuteResult(),
            ExecuteResult(),
            ExecuteResult(scalar=credential),
            ExecuteResult(),
            ExecuteResult(),
            ExecuteResult(scalar=other_credential),
            ExecuteResult(),
            ExecuteResult(),
            ExecuteResult(),
        ]
    )
    credential_repository = AuthRepository(credential_session)

    assert await credential_repository.get_credential_by_user_id(user_id) == credential
    assert (
        await credential_repository.ensure_credential(user_id, "USER@EXAMPLE.COM", "hash")
        == credential
    )
    assert (
        await credential_repository.ensure_credential(user_id, "USER@EXAMPLE.COM", "hash")
        == credential
    )
    with pytest.raises(ValueError, match="Credential email already belongs"):
        await credential_repository.ensure_credential(user_id, "USER@EXAMPLE.COM", "hash")
    with pytest.raises(LookupError):
        await credential_repository.ensure_credential(user_id, "USER@EXAMPLE.COM", "hash")


@pytest.mark.asyncio
async def test_notifications_repository_self_service_delivery_helpers() -> None:
    user_id = uuid4()
    alert_id = uuid4()
    existing_outcome = AlertDeliveryOutcome(
        alert_id=alert_id,
        delivery_method=DeliveryMethod.email,
        attempt_count=1,
    )
    session = QuerySession(
        [
            ExecuteResult(rowcount=4),
            ExecuteResult(scalar=None),
            ExecuteResult(scalar=existing_outcome),
            ExecuteResult(scalar=existing_outcome),
            ExecuteResult(scalar=None),
        ]
    )
    session.scalar_results = [7, None]
    repository = NotificationsRepository(session)

    assert await repository.mark_all_read(user_id) == 4
    assert session.flushed == 1
    assert await repository.get_unread_count(user_id) == 7
    assert await repository.get_unread_count(user_id) == 0

    created = await repository.ensure_alert_delivery_outcome(alert_id, DeliveryMethod.webhook)
    assert created.delivery_method == DeliveryMethod.webhook
    assert created in session.added
    assert session.flushed == 2

    updated = await repository.ensure_alert_delivery_outcome(alert_id, DeliveryMethod.sms)
    assert updated is existing_outcome
    assert existing_outcome.delivery_method == DeliveryMethod.sms

    assert (
        await repository.update_delivery_outcome(
            existing_outcome.id,
            outcome="success",
            error_detail=None,
        )
        is existing_outcome
    )
    assert existing_outcome.outcome == "success"
    assert await repository.update_delivery_outcome(uuid4(), outcome="failed") is None
