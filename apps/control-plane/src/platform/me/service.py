from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from platform.audit.service import AuditChainService
from platform.auth.service import AuthService
from platform.common.events.envelope import CorrelationContext
from platform.common.exceptions import NotFoundError
from platform.notifications.events import (
    NotificationPreferencesUpdatedPayload,
    publish_notification_preferences_updated,
)
from platform.notifications.models import DeliveryMethod
from platform.notifications.service import AlertService
from platform.privacy_compliance.events import (
    DSRLifecyclePayload,
    PrivacyEventType,
    make_correlation,
)
from platform.privacy_compliance.schemas import DSRCreateRequest
from platform.privacy_compliance.services.consent_service import ConsentService
from platform.privacy_compliance.services.dsr_service import DSRService
from typing import Any
from uuid import UUID, uuid4

from .schemas import (
    RevokeOtherSessionsResponse,
    UserActivityItem,
    UserActivityListResponse,
    UserConsentHistoryResponse,
    UserConsentItem,
    UserConsentListResponse,
    UserDSRDetailResponse,
    UserDSRListResponse,
    UserDSRSubmitRequest,
    UserNotificationPreferencesResponse,
    UserNotificationPreferencesUpdateRequest,
    UserNotificationTestResponse,
    UserServiceAccountCreateRequest,
    UserServiceAccountCreateResponse,
    UserServiceAccountListResponse,
    UserServiceAccountSummary,
    UserSessionDetail,
    UserSessionListResponse,
)


class MeService:
    def __init__(
        self,
        *,
        auth_service: AuthService,
        consent_service: ConsentService,
        dsr_service: DSRService,
        notifications_service: AlertService,
        audit_service: AuditChainService,
    ) -> None:
        self.auth = auth_service
        self.consent = consent_service
        self.dsr = dsr_service
        self.notifications = notifications_service
        self.audit = audit_service

    async def list_sessions(
        self,
        current_user_id: UUID,
        current_session_id: UUID,
    ) -> UserSessionListResponse:
        sessions = await self.auth.list_user_sessions(current_user_id, current_session_id)
        return UserSessionListResponse(
            items=[UserSessionDetail.model_validate(item) for item in sessions]
        )

    async def revoke_session(
        self,
        current_user_id: UUID,
        session_id: UUID,
        current_session_id: UUID,
    ) -> None:
        await self.auth.revoke_session_by_id(current_user_id, session_id, current_session_id)
        await self._append_activity(
            "auth.session.revoked",
            current_user_id,
            session_id=session_id,
            reason="self_service",
        )

    async def revoke_other_sessions(
        self,
        current_user_id: UUID,
        current_session_id: UUID,
    ) -> RevokeOtherSessionsResponse:
        count = await self.auth.revoke_other_sessions(current_user_id, current_session_id)
        await self._append_activity(
            "auth.session.revoked_all_others",
            current_user_id,
            current_session_id=current_session_id,
            sessions_revoked=count,
        )
        return RevokeOtherSessionsResponse(sessions_revoked=count)

    async def list_service_accounts(self, current_user_id: UUID) -> UserServiceAccountListResponse:
        items = []
        for credential in await self.auth.list_for_current_user(current_user_id):
            items.append(
                UserServiceAccountSummary(
                    service_account_id=credential.service_account_id,
                    name=credential.name,
                    role=credential.role,
                    status=credential.status,
                    workspace_id=credential.workspace_id,
                    created_at=credential.created_at,
                    last_used_at=credential.last_used_at,
                    api_key_prefix=_hash_prefix(credential.api_key_hash),
                )
            )
        return UserServiceAccountListResponse(items=items)

    async def create_service_account(
        self,
        current_user_id: UUID,
        payload: UserServiceAccountCreateRequest,
    ) -> UserServiceAccountCreateResponse:
        created = await self.auth.create_for_current_user(
            current_user_id,
            payload.name,
            payload.scopes,
            payload.expires_at,
            payload.mfa_token,
        )
        await self._append_activity(
            "auth.api_key.created",
            current_user_id,
            service_account_id=created.service_account_id,
            source="user_self",
        )
        return UserServiceAccountCreateResponse.model_validate(created)

    async def revoke_service_account(self, current_user_id: UUID, sa_id: UUID) -> None:
        await self.auth.revoke_for_current_user(current_user_id, sa_id)
        await self._append_activity(
            "auth.api_key.revoked",
            current_user_id,
            service_account_id=sa_id,
            source="user_self",
        )

    async def list_consents(self, current_user_id: UUID) -> UserConsentListResponse:
        records = await self.consent.list_for_user(current_user_id)
        return UserConsentListResponse(
            items=[UserConsentItem.model_validate(record) for record in records]
        )

    async def revoke_consent(self, current_user_id: UUID, consent_type: str) -> UserConsentItem:
        record = await self.consent.revoke(current_user_id, consent_type)
        await self._append_activity(
            "privacy.consent.revoked",
            current_user_id,
            consent_type=consent_type,
            workspace_id=record.workspace_id,
        )
        return UserConsentItem.model_validate(record)

    async def list_consent_history(self, current_user_id: UUID) -> UserConsentHistoryResponse:
        records = await self.consent.list_history_for_user(current_user_id)
        return UserConsentHistoryResponse(
            items=[UserConsentItem.model_validate(record) for record in records]
        )

    async def submit_dsr(
        self,
        current_user_id: UUID,
        payload: UserDSRSubmitRequest,
    ) -> UserDSRDetailResponse:
        created = await self.dsr.create_request(
            DSRCreateRequest(
                subject_user_id=current_user_id,
                request_type=payload.request_type,
                legal_basis=payload.legal_basis,
                hold_hours=payload.hold_hours,
            ),
            requested_by=current_user_id,
        )
        await self.dsr.events.publish(
            PrivacyEventType.dsr_submitted,
            DSRLifecyclePayload(
                dsr_id=created.id,
                subject_user_id=current_user_id,
                request_type=created.request_type.value,
                status=created.status.value,
                occurred_at=datetime.now(UTC),
                source="self_service",
            ),
            key=str(current_user_id),
            correlation_ctx=make_correlation(),
        )
        await self._append_activity(
            "privacy.dsr.submitted",
            current_user_id,
            dsr_id=created.id,
            request_type=created.request_type.value,
            source="self_service",
        )
        return UserDSRDetailResponse.model_validate(created)

    async def list_dsrs(
        self,
        current_user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> UserDSRListResponse:
        offset = _decode_offset_cursor(cursor)
        items = await self.dsr.list_for_subject(current_user_id, limit, cursor)
        next_cursor = None
        if len(items) == limit:
            next_cursor = _encode_offset_cursor(offset + limit)
        return UserDSRListResponse(
            items=[UserDSRDetailResponse.model_validate(item) for item in items],
            next_cursor=next_cursor,
        )

    async def get_dsr(self, current_user_id: UUID, dsr_id: UUID) -> UserDSRDetailResponse:
        item = await self.dsr.get_request(dsr_id)
        if item.subject_user_id != current_user_id:
            raise NotFoundError("DSR_NOT_FOUND", "DSR request not found")
        return UserDSRDetailResponse.model_validate(item)

    async def list_activity(
        self,
        current_user_id: UUID,
        *,
        start_ts: Any | None,
        end_ts: Any | None,
        event_type: str | None,
        limit: int,
        cursor: str | None,
    ) -> UserActivityListResponse:
        entries, next_cursor = await self.audit.list_entries_by_actor_or_subject(
            actor_id=current_user_id,
            subject_id=current_user_id,
            start_ts=start_ts,
            end_ts=end_ts,
            event_type=event_type,
            limit=limit,
            cursor=cursor,
        )
        return UserActivityListResponse(
            items=[
                UserActivityItem(
                    id=entry.id,
                    event_type=entry.event_type,
                    audit_event_source=entry.audit_event_source,
                    severity=entry.severity,
                    created_at=entry.created_at,
                    canonical_payload=entry.canonical_payload,
                )
                for entry in entries
            ],
            next_cursor=next_cursor,
        )

    async def get_notification_preferences(
        self,
        current_user_id: UUID,
    ) -> UserNotificationPreferencesResponse:
        settings = await self.notifications.get_or_default_settings(current_user_id)
        return UserNotificationPreferencesResponse.model_validate(settings)

    async def update_notification_preferences(
        self,
        current_user_id: UUID,
        payload: UserNotificationPreferencesUpdateRequest,
    ) -> UserNotificationPreferencesResponse:
        existing = await self.notifications.repo.get_settings(current_user_id)
        if existing is None:
            current = await self.notifications.get_or_default_settings(current_user_id)
            data = current.model_dump()
        else:
            data = {
                "state_transitions": existing.state_transitions,
                "delivery_method": existing.delivery_method,
                "webhook_url": existing.webhook_url,
                "per_channel_preferences": existing.per_channel_preferences,
                "digest_mode": existing.digest_mode,
                "quiet_hours": existing.quiet_hours,
            }
        updates = payload.model_dump(exclude_unset=True)
        data.update(updates)
        saved = await self.notifications.repo.upsert_settings(
            current_user_id,
            {
                "state_transitions": data["state_transitions"],
                "delivery_method": data["delivery_method"] or DeliveryMethod.in_app,
                "webhook_url": data.get("webhook_url"),
                "per_channel_preferences": data.get("per_channel_preferences") or {},
                "digest_mode": data.get("digest_mode") or {},
                "quiet_hours": data.get("quiet_hours"),
            },
        )
        await publish_notification_preferences_updated(
            self.notifications.producer,
            NotificationPreferencesUpdatedPayload(
                user_id=current_user_id,
                actor_id=current_user_id,
                occurred_at=datetime.now(UTC),
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
        await self._append_activity(
            "notifications.preferences.updated",
            current_user_id,
            changed_fields=sorted(updates),
        )
        return UserNotificationPreferencesResponse(
            state_transitions=list(saved.state_transitions),
            delivery_method=saved.delivery_method,
            webhook_url=saved.webhook_url,
            per_channel_preferences=saved.per_channel_preferences,
            digest_mode=saved.digest_mode,
            quiet_hours=saved.quiet_hours,
        )

    async def test_notification(
        self,
        current_user_id: UUID,
        event_type: str,
    ) -> UserNotificationTestResponse:
        alert = await self.notifications.test_notification(current_user_id, event_type)
        return UserNotificationTestResponse(alert_id=alert.id, event_type=event_type)

    async def _append_activity(
        self,
        event_type: str,
        current_user_id: UUID,
        **fields: Any,
    ) -> None:
        payload = {
            "event_type": event_type,
            "actor_id": str(current_user_id),
            "subject_id": str(current_user_id),
            "source": fields.pop("source", "self_service"),
            "occurred_at": datetime.now(UTC).isoformat(),
            **{key: _json_safe(value) for key, value in fields.items()},
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        await self.audit.append(
            None,
            "platform.me",
            canonical,
            event_type=event_type,
            severity="info",
            canonical_payload_json=payload,
        )


def _hash_prefix(api_key_hash: str) -> str:
    return f"hash:{api_key_hash[:10]}"


def _encode_offset_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(str(offset).encode("ascii")).decode("ascii")


def _decode_offset_cursor(cursor: str | None) -> int:
    if cursor is None:
        return 0
    try:
        return max(0, int(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("ascii")))
    except (ValueError, UnicodeDecodeError, binascii.Error):
        return 0


def _json_safe(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_json_safe(item) for item in value]
    if hasattr(value, "value"):
        return _json_safe(value.value)
    return value
