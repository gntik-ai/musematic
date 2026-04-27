from __future__ import annotations

import hashlib
import logging
import secrets
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from platform.accounts.models import User
from platform.accounts.repository import AccountsRepository
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.exceptions import ValidationError
from platform.common.models.user import User as PlatformUser
from platform.connectors.retry import compute_next_retry_at
from platform.interactions.events import AttentionRequestedPayload, InteractionStateChangedPayload
from platform.notifications.channel_router import ChannelRouter
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.slack_deliverer import SlackDeliverer
from platform.notifications.deliverers.sms_deliverer import SmsDeliverer
from platform.notifications.deliverers.teams_deliverer import TeamsDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.events import (
    AlertCreatedPayload,
    AlertReadPayload,
    publish_alert_created,
    publish_alert_read,
)
from platform.notifications.exceptions import (
    AlertAuthorizationError,
    AlertNotFoundError,
    ChannelNotFoundError,
    ChannelVerificationError,
    QuotaExceededError,
)
from platform.notifications.models import (
    AlertDeliveryOutcome,
    DeliveryMethod,
    DeliveryOutcome,
    NotificationChannelConfig,
    UserAlert,
)
from platform.notifications.repository import NotificationsRepository
from platform.notifications.schemas import (
    AlertListResponse,
    ChannelConfigCreate,
    ChannelConfigRead,
    ChannelConfigUpdate,
    MarkAllReadResponse,
    UnreadCountResponse,
    UserAlertDetail,
    UserAlertRead,
    UserAlertSettingsRead,
    UserAlertSettingsUpdate,
)
from platform.workspaces.service import WorkspacesService
from types import MappingProxyType
from typing import ClassVar
from uuid import UUID, uuid4

LOGGER = logging.getLogger(__name__)


class AlertService:
    DEFAULT_TRANSITIONS: ClassVar[tuple[str, ...]] = (
        "working_to_pending",
        "any_to_complete",
        "any_to_failed",
    )
    _STATE_ALIASES: ClassVar[Mapping[str, str]] = MappingProxyType(
        {
            "working": "running",
            "pending": "waiting",
            "complete": "completed",
            "completed": "completed",
            "failed": "failed",
            "ready": "ready",
            "paused": "paused",
            "canceled": "canceled",
            "cancelled": "canceled",
            "running": "running",
            "waiting": "waiting",
            "initializing": "initializing",
        }
    )
    _ALLOWED_URGENCIES: ClassVar[frozenset[str]] = frozenset({"low", "medium", "high", "critical"})

    def __init__(
        self,
        *,
        repo: NotificationsRepository,
        accounts_repo: AccountsRepository,
        workspaces_service: WorkspacesService | None,
        redis: AsyncRedisClient,
        producer: EventProducer | None,
        settings: PlatformSettings,
        email_deliverer: EmailDeliverer,
        webhook_deliverer: WebhookDeliverer,
        channel_router: ChannelRouter | None = None,
        sms_deliverer: SmsDeliverer | None = None,
    ) -> None:
        self.repo = repo
        self.accounts_repo = accounts_repo
        self.workspaces_service = workspaces_service
        self.redis = redis
        self.producer = producer
        self.settings = settings
        self.email_deliverer = email_deliverer
        self.webhook_deliverer = webhook_deliverer
        self.channel_router = channel_router
        self.sms_deliverer = sms_deliverer

    @classmethod
    def matches_transition_pattern(cls, pattern: str, from_state: str, to_state: str) -> bool:
        raw_from, separator, raw_to = pattern.partition("_to_")
        if not separator:
            return False
        resolved_to = cls._normalize_state(raw_to)
        if resolved_to is None:
            return False
        resolved_from = "any" if raw_from == "any" else cls._normalize_state(raw_from)
        if raw_from != "any" and resolved_from is None:
            return False
        current_from = cls._normalize_state(from_state)
        current_to = cls._normalize_state(to_state)
        if current_from is None or current_to is None:
            return False
        if current_to != resolved_to:
            return False
        return resolved_from == "any" or current_from == resolved_from

    async def get_or_default_settings(self, user_id: UUID) -> UserAlertSettingsRead:
        settings = await self.repo.get_settings(user_id)
        if settings is not None:
            return UserAlertSettingsRead.model_validate(settings)
        now = datetime.now(UTC)
        return UserAlertSettingsRead(
            id=uuid4(),
            user_id=user_id,
            state_transitions=list(self.DEFAULT_TRANSITIONS),
            delivery_method=DeliveryMethod.in_app,
            webhook_url=None,
            created_at=now,
            updated_at=now,
        )

    async def upsert_settings(
        self,
        user_id: UUID,
        data: UserAlertSettingsUpdate,
    ) -> UserAlertSettingsRead:
        if data.delivery_method == DeliveryMethod.webhook and data.webhook_url is None:
            raise ValidationError(
                "WEBHOOK_URL_REQUIRED",
                "webhook_url is required when delivery_method is webhook",
            )
        settings = await self.repo.upsert_settings(
            user_id,
            {
                "state_transitions": list(data.state_transitions),
                "delivery_method": data.delivery_method,
                "webhook_url": None if data.webhook_url is None else str(data.webhook_url),
            },
        )
        return UserAlertSettingsRead.model_validate(settings)

    async def process_attention_request(
        self,
        payload: AttentionRequestedPayload,
    ) -> UserAlert | None:
        user = await self._resolve_user(payload.target_identity)
        if user is None:
            LOGGER.warning(
                "Skipping alert creation for unknown target identity %s",
                payload.target_identity,
            )
            return None
        if not await self._allow_source(payload.source_agent_fqn, user.id):
            LOGGER.warning(
                "Dropping attention alert due to rate limit",
                extra={"source_agent_fqn": payload.source_agent_fqn, "user_id": str(user.id)},
            )
            return None
        alert_settings = await self.get_or_default_settings(user.id)
        urgency = self._normalize_urgency(payload.urgency)
        alert = await self.repo.create_alert(
            user_id=user.id,
            interaction_id=payload.related_interaction_id,
            source_reference={"type": "attention_request", "id": str(payload.request_id)},
            alert_type="attention_request",
            title=f"Attention requested by {payload.source_agent_fqn}",
            body=payload.context_summary,
            urgency=urgency,
            delivery_method=(
                alert_settings.delivery_method
                if alert_settings.delivery_method != DeliveryMethod.in_app
                else None
            ),
        )
        await self._dispatch_for_settings(alert, alert_settings, user)
        return alert

    async def process_state_change(
        self,
        payload: InteractionStateChangedPayload,
        workspace_id: UUID,
    ) -> list[UserAlert]:
        if (
            self._normalize_state(payload.from_state) is None
            or self._normalize_state(payload.to_state) is None
        ):
            LOGGER.warning(
                "Skipping state change alert for unrecognized states",
                extra={"from_state": payload.from_state, "to_state": payload.to_state},
            )
            return []
        member_ids = await self._list_workspace_member_ids(workspace_id)
        created: list[UserAlert] = []
        for user_id in member_ids:
            alert_settings = await self.get_or_default_settings(user_id)
            if not any(
                self.matches_transition_pattern(pattern, payload.from_state, payload.to_state)
                for pattern in alert_settings.state_transitions
            ):
                continue
            if not await self._allow_source(str(payload.interaction_id), user_id):
                LOGGER.warning(
                    "Dropping state-change alert due to rate limit",
                    extra={"interaction_id": str(payload.interaction_id), "user_id": str(user_id)},
                )
                continue
            user = await self._resolve_user(str(user_id))
            if user is None:
                continue
            alert = await self.repo.create_alert(
                user_id=user_id,
                interaction_id=payload.interaction_id,
                source_reference={"type": "state_change", "id": str(payload.interaction_id)},
                alert_type="state_change",
                title=f"Interaction transitioned to {payload.to_state}",
                body=f"Interaction transitioned from {payload.from_state} to {payload.to_state}.",
                urgency="medium",
                delivery_method=(
                    alert_settings.delivery_method
                    if alert_settings.delivery_method != DeliveryMethod.in_app
                    else None
                ),
            )
            await self._dispatch_for_settings(
                alert,
                alert_settings,
                user,
                workspace_id=workspace_id,
            )
            created.append(alert)
        return created

    async def list_alerts(
        self,
        user_id: UUID,
        *,
        read_filter: str,
        cursor: str | None,
        limit: int,
    ) -> AlertListResponse:
        items, next_cursor, total_unread = await self.repo.list_alerts(
            user_id,
            read_filter,
            cursor,
            limit,
        )
        return AlertListResponse(
            items=[UserAlertRead.model_validate(item) for item in items],
            next_cursor=next_cursor,
            total_unread=total_unread,
        )

    async def get_alert(self, alert_id: UUID, user_id: UUID) -> UserAlertDetail:
        alert = await self.repo.get_alert_by_id(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        if alert.user_id != user_id:
            raise AlertAuthorizationError()
        return UserAlertDetail.model_validate(alert)

    async def mark_alert_read(self, alert_id: UUID, user_id: UUID) -> UserAlertRead:
        alert = await self.repo.get_alert_by_id(alert_id)
        if alert is None:
            raise AlertNotFoundError(alert_id)
        if alert.user_id != user_id:
            raise AlertAuthorizationError()
        alert = await self.repo.mark_read(alert_id, user_id)
        assert alert is not None
        unread_count = await self.repo.get_unread_count(user_id)
        await publish_alert_read(
            self.producer,
            AlertReadPayload(
                alert_id=alert.id,
                user_id=user_id,
                unread_count=unread_count,
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
        return UserAlertRead.model_validate(alert)

    async def mark_all_read(self, user_id: UUID) -> MarkAllReadResponse:
        updated = await self.repo.mark_all_read(user_id)
        await publish_alert_read(
            self.producer,
            AlertReadPayload(
                alert_id=uuid4(),
                user_id=user_id,
                unread_count=0,
            ),
            CorrelationContext(correlation_id=uuid4()),
        )
        return MarkAllReadResponse(updated=updated, unread_count=0)

    async def get_unread_count(self, user_id: UUID) -> UnreadCountResponse:
        return UnreadCountResponse(count=await self.repo.get_unread_count(user_id))

    async def test_notification(self, user_id: UUID, event_type: str) -> UserAlertRead:
        alert_settings = await self.get_or_default_settings(user_id)
        alert = await self.repo.create_alert(
            user_id=user_id,
            interaction_id=None,
            source_reference={"type": "notification_test", "event_type": event_type},
            alert_type=event_type,
            title=f"Test notification: {event_type}",
            body="This is a test notification generated from your preferences page.",
            urgency="medium",
            delivery_method=(
                alert_settings.delivery_method
                if alert_settings.delivery_method != DeliveryMethod.in_app
                else None
            ),
        )
        user = await self._resolve_user(str(user_id))
        if user is None:
            await self._publish_in_app(alert)
        else:
            await self._dispatch_for_settings(alert, alert_settings, user)
        return UserAlertRead.model_validate(alert)

    async def list_channel_configs(self, user_id: UUID) -> list[ChannelConfigRead]:
        return [
            ChannelConfigRead.model_validate(item)
            for item in await self.repo.list_user_channel_configs(user_id)
        ]

    async def get_channel_config_for_user(
        self,
        user_id: UUID,
        channel_config_id: UUID,
    ) -> ChannelConfigRead:
        return ChannelConfigRead.model_validate(
            await self._authorize_channel_access(user_id, channel_config_id)
        )

    async def create_channel_config(
        self,
        user_id: UUID,
        data: ChannelConfigCreate,
    ) -> ChannelConfigRead:
        total = await self.repo.count_user_channels(user_id)
        if total >= self.settings.notifications.channels_per_user_max:
            raise QuotaExceededError("Maximum notification channels per user exceeded")
        token, token_hash, expires_at = self._verification_challenge(data.channel_type)
        severity_floor = data.severity_floor
        if data.channel_type == DeliveryMethod.sms and severity_floor is None:
            severity_floor = self.settings.notifications.sms_default_severity_floor
        config = await self.repo.create_channel_config(
            user_id=user_id,
            channel_type=data.channel_type,
            target=data.target,
            display_name=data.display_name,
            enabled=True,
            verified_at=None,
            verification_token_hash=token_hash,
            verification_expires_at=expires_at,
            quiet_hours=None if data.quiet_hours is None else data.quiet_hours.model_dump(),
            alert_type_filter=data.alert_type_filter,
            severity_floor=severity_floor,
            extra=data.extra,
        )
        await self._send_channel_verification(config, token)
        return ChannelConfigRead.model_validate(config)

    async def update_channel_config(
        self,
        user_id: UUID,
        channel_config_id: UUID,
        data: ChannelConfigUpdate,
    ) -> ChannelConfigRead:
        await self._authorize_channel_access(user_id, channel_config_id)
        fields = data.model_dump(exclude_unset=True)
        if "quiet_hours" in fields and fields["quiet_hours"] is not None:
            fields["quiet_hours"] = data.quiet_hours.model_dump() if data.quiet_hours else None
        config = await self.repo.update_channel_config(channel_config_id, **fields)
        assert config is not None
        return ChannelConfigRead.model_validate(config)

    async def delete_channel_config(self, user_id: UUID, channel_config_id: UUID) -> None:
        await self._authorize_channel_access(user_id, channel_config_id)
        await self.repo.delete_channel_config(channel_config_id)

    async def verify_channel_config(
        self,
        user_id: UUID,
        channel_config_id: UUID,
        token: str,
    ) -> ChannelConfigRead:
        token_hash = self._hash_token(token)
        config = await self.repo.get_channel_config_by_token_hash(token_hash)
        if config is None or config.id != channel_config_id or config.user_id != user_id:
            raise ChannelVerificationError("Verification token is invalid")
        if config.verification_expires_at and config.verification_expires_at < datetime.now(UTC):
            raise ChannelVerificationError("Verification token has expired")
        updated = await self.repo.update_channel_config(
            channel_config_id,
            verified_at=datetime.now(UTC),
            verification_token_hash=None,
            verification_expires_at=None,
        )
        assert updated is not None
        return ChannelConfigRead.model_validate(updated)

    async def resend_channel_verification(
        self,
        user_id: UUID,
        channel_config_id: UUID,
    ) -> ChannelConfigRead:
        await self._authorize_channel_access(user_id, channel_config_id)
        config = await self._authorize_channel_access(user_id, channel_config_id)
        token, token_hash, expires_at = self._verification_challenge(config.channel_type)
        updated = await self.repo.update_channel_config(
            channel_config_id,
            verification_token_hash=token_hash,
            verification_expires_at=expires_at,
        )
        assert updated is not None
        await self._send_channel_verification(updated, token)
        return ChannelConfigRead.model_validate(updated)

    async def run_webhook_retry_scan(self) -> int:
        retried = 0
        outcomes = await self.repo.get_pending_webhook_deliveries()
        for outcome in outcomes:
            if outcome.attempt_count >= self.settings.notifications.webhook_max_retries:
                if outcome.next_retry_at is not None:
                    await self.repo.update_delivery_outcome(outcome.id, next_retry_at=None)
                continue
            settings = await self.get_or_default_settings(outcome.alert.user_id)
            await self.repo.update_delivery_outcome(
                outcome.id,
                attempt_count=outcome.attempt_count + 1,
            )
            await self._dispatch_webhook(outcome.alert, settings, outcome)
            retried += 1
        return retried

    async def run_retention_gc(self) -> int:
        return await self.repo.delete_expired_alerts(
            self.settings.notifications.alert_retention_days
        )

    async def run_dead_letter_retention_gc(self) -> int:
        cutoff = datetime.now(UTC) - timedelta(
            days=self.settings.notifications.dead_letter_retention_days
        )
        return await self.repo.delete_dead_letter_older_than(cutoff)

    async def _dispatch_for_settings(
        self,
        alert: UserAlert,
        alert_settings: UserAlertSettingsRead,
        user: User | PlatformUser,
        *,
        workspace_id: UUID | None = None,
    ) -> None:
        if self.settings.notifications.multi_channel_enabled and self.channel_router is not None:
            await self.channel_router.route(
                alert,
                user,
                workspace_id=workspace_id,
                severity=alert.urgency,
            )
            return
        if alert_settings.delivery_method == DeliveryMethod.in_app:
            await self._publish_in_app(alert)
            return
        if alert_settings.delivery_method == DeliveryMethod.email:
            await self._dispatch_email(alert, user)
            return
        await self._dispatch_webhook(alert, alert_settings, alert.delivery_outcome)

    async def _dispatch_email(self, alert: UserAlert, user: User | PlatformUser) -> None:
        if alert.delivery_outcome is None:
            return
        smtp_settings = self._smtp_settings()
        outcome = await self.email_deliverer.send(alert, user.email, smtp_settings)
        await self.repo.update_delivery_outcome(
            alert.delivery_outcome.id,
            outcome=outcome,
            error_detail=None if outcome == DeliveryOutcome.success else "email delivery failed",
            delivered_at=datetime.now(UTC) if outcome == DeliveryOutcome.success else None,
            next_retry_at=None,
        )

    async def _dispatch_webhook(
        self,
        alert: UserAlert,
        alert_settings: UserAlertSettingsRead,
        delivery_outcome: AlertDeliveryOutcome | None,
    ) -> None:
        if delivery_outcome is None:
            return
        if not alert_settings.webhook_url:
            await self.repo.update_delivery_outcome(
                delivery_outcome.id,
                outcome=DeliveryOutcome.fallback,
                error_detail="webhook_url missing; fell back to in-app delivery",
                next_retry_at=None,
            )
            await self._publish_in_app(alert)
            return
        outcome, error_detail = await self.webhook_deliverer.send(
            alert,
            alert_settings.webhook_url,
        )
        next_retry_at = None
        delivered_at = None
        if outcome == DeliveryOutcome.success:
            delivered_at = datetime.now(UTC)
        elif delivery_outcome.attempt_count < self.settings.notifications.webhook_max_retries:
            next_retry_at = compute_next_retry_at(delivery_outcome.attempt_count)
        await self.repo.update_delivery_outcome(
            delivery_outcome.id,
            outcome=outcome,
            error_detail=error_detail,
            next_retry_at=next_retry_at,
            delivered_at=delivered_at,
        )

    async def _publish_in_app(self, alert: UserAlert) -> None:
        await publish_alert_created(
            self.producer,
            AlertCreatedPayload(
                id=alert.id,
                user_id=alert.user_id,
                alert_type=alert.alert_type,
                title=alert.title,
                body=alert.body,
                urgency=alert.urgency,
                read=alert.read,
                interaction_id=alert.interaction_id,
                source_reference=alert.source_reference,
                created_at=alert.created_at,
                updated_at=alert.updated_at,
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=None,
                interaction_id=alert.interaction_id,
            ),
        )

    async def _allow_source(self, source_key: str, user_id: UUID) -> bool:
        result = await self.redis.check_rate_limit(
            "notifications",
            f"{source_key}:{user_id}",
            self.settings.notifications.rate_limit_per_source_per_minute,
            60_000,
        )
        return bool(result.allowed)

    async def _resolve_user(self, target_identity: str) -> User | PlatformUser | None:
        try:
            user_id = UUID(str(target_identity))
        except ValueError:
            user_id = None
        if user_id is not None:
            user = await self.accounts_repo.get_user_by_id(user_id)
            if user is not None:
                return user
        return await self.accounts_repo.get_user_by_email(str(target_identity))

    async def _list_workspace_member_ids(self, workspace_id: UUID) -> list[UUID]:
        if self.workspaces_service is None:
            return []
        list_member_ids = getattr(self.workspaces_service, "list_member_ids", None)
        if callable(list_member_ids):
            return list(await list_member_ids(workspace_id))
        return []

    @classmethod
    def _normalize_state(cls, state: str) -> str | None:
        return cls._STATE_ALIASES.get(state.lower())

    def _normalize_urgency(self, urgency: object) -> str:
        raw = getattr(urgency, "value", urgency)
        value = str(raw).lower()
        if value in self._ALLOWED_URGENCIES:
            return value
        LOGGER.warning("Unknown alert urgency %s; defaulting to medium", raw)
        return "medium"

    def _smtp_settings(self) -> dict[str, object]:
        return {
            "hostname": getattr(self.settings, "SMTP_HOST", None),
            "port": getattr(self.settings, "SMTP_PORT", None),
            "username": getattr(self.settings, "SMTP_USERNAME", None),
            "password": getattr(self.settings, "SMTP_PASSWORD", None),
            "from_address": getattr(self.settings, "SMTP_FROM", None),
        }

    def _verification_challenge(
        self,
        channel_type: DeliveryMethod = DeliveryMethod.email,
    ) -> tuple[str, str, datetime]:
        if channel_type == DeliveryMethod.sms:
            raw_token = f"{secrets.randbelow(1_000_000):06d}"
            return raw_token, self._hash_token(raw_token), datetime.now(UTC) + timedelta(
                minutes=10
            )
        raw_token = secrets.token_urlsafe(32)
        return raw_token, self._hash_token(raw_token), datetime.now(UTC) + timedelta(hours=24)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def _send_channel_verification(
        self,
        config: NotificationChannelConfig,
        token: str,
    ) -> None:
        if config.channel_type not in {
            DeliveryMethod.email,
            DeliveryMethod.slack,
            DeliveryMethod.teams,
            DeliveryMethod.sms,
        }:
            return
        alert = UserAlert(
            id=uuid4(),
            user_id=config.user_id,
            interaction_id=None,
            source_reference={"type": "notification_channel_verification"},
            alert_type="notification_channel_verification",
            title="Verify your notification channel",
            body=(
                "Use this verification token to activate your notification channel: "
                f"{token}"
            ),
            urgency="medium",
            read=False,
        )
        alert.created_at = datetime.now(UTC)
        alert.updated_at = alert.created_at
        if config.channel_type == DeliveryMethod.email:
            await self.email_deliverer.send(alert, config.target, self._smtp_settings())
            return
        if config.channel_type == DeliveryMethod.slack:
            await SlackDeliverer().send(alert, config.target, config)
            return
        if config.channel_type == DeliveryMethod.teams:
            await TeamsDeliverer().send(alert, config.target, config)
            return
        if config.channel_type == DeliveryMethod.sms and self.sms_deliverer is not None:
            sms_alert = UserAlert(
                id=alert.id,
                user_id=alert.user_id,
                interaction_id=None,
                source_reference=alert.source_reference,
                alert_type=alert.alert_type,
                title="Musematic verification",
                body=f"Your Musematic verification code is {token}.",
                urgency="critical",
                read=False,
            )
            sms_alert.created_at = alert.created_at
            sms_alert.updated_at = alert.updated_at
            await self.sms_deliverer.send(sms_alert, config.target, config)

    async def _authorize_channel_access(
        self,
        user_id: UUID,
        channel_config_id: UUID,
    ) -> NotificationChannelConfig:
        config = await self.repo.get_channel_config(channel_config_id)
        if config is None:
            raise ChannelNotFoundError(channel_config_id)
        if config.user_id != user_id:
            raise AlertAuthorizationError()
        return config
