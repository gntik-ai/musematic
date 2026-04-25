from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from platform.accounts.models import User
from platform.accounts.repository import AccountsRepository
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.models.user import User as PlatformUser
from platform.notifications.canonical import derive_idempotency_key
from platform.notifications.deliverers.email_deliverer import EmailDeliverer
from platform.notifications.deliverers.sms_deliverer import SmsDeliverer
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.events import (
    AlertCreatedPayload,
    DeliveryAttemptedPayload,
    publish_alert_created,
    publish_delivery_attempted,
)
from platform.notifications.models import DeliveryMethod, DeliveryOutcome, UserAlert
from platform.notifications.quiet_hours import in_quiet_hours
from platform.notifications.repository import NotificationsRepository
from platform.workspaces.service import WorkspacesService
from typing import Any, Protocol, cast
from uuid import UUID, uuid4


class DlpService(Protocol):
    async def scan_outbound(
        self,
        *,
        payload: dict[str, Any],
        workspace_id: UUID | None,
        channel_type: str,
    ) -> object: ...


class ResidencyService(Protocol):
    async def resolve_region_for_url(self, url: str) -> str | None: ...

    async def check_egress(self, workspace_id: UUID, region: str | None) -> bool: ...


class SecretProvider(Protocol):
    async def read_secret(self, path: str) -> dict[str, Any]: ...

    async def write_secret(self, path: str, payload: dict[str, Any]) -> None: ...


class AuditChainService(Protocol):
    async def append(self, payload: dict[str, Any]) -> object: ...


@dataclass(frozen=True)
class RoutingAttempt:
    channel_type: DeliveryMethod
    target: str
    outcome: str
    error_detail: str | None = None


@dataclass(frozen=True)
class RoutingResult:
    attempts: list[RoutingAttempt]


@dataclass(frozen=True)
class WebhookDispatchResult:
    webhook_id: UUID
    delivery_id: UUID
    status: str


@dataclass(frozen=True)
class ChannelDelivererRegistry:
    email: EmailDeliverer
    webhook: WebhookDeliverer
    extras: dict[DeliveryMethod, object] | None = None

    def get(self, delivery_method: DeliveryMethod) -> object:
        if delivery_method == DeliveryMethod.email:
            return self.email
        if delivery_method == DeliveryMethod.webhook:
            return self.webhook
        if self.extras and delivery_method in self.extras:
            return self.extras[delivery_method]
        raise KeyError(delivery_method)


@dataclass(frozen=True)
class _ChannelView:
    channel_type: DeliveryMethod
    target: str
    quiet_hours: dict[str, Any] | None = None
    alert_type_filter: list[str] | None = None
    severity_floor: str | None = None
    extra: dict[str, Any] | None = None


class ChannelRouter:
    def __init__(
        self,
        *,
        repo: NotificationsRepository,
        accounts_repo: AccountsRepository,
        workspaces_service: WorkspacesService | None,
        dlp_service: DlpService,
        residency_service: ResidencyService,
        secrets: SecretProvider,
        audit_chain: AuditChainService,
        producer: EventProducer | None,
        settings: PlatformSettings,
        deliverers: ChannelDelivererRegistry,
    ) -> None:
        self.repo = repo
        self.accounts_repo = accounts_repo
        self.workspaces_service = workspaces_service
        self.dlp_service = dlp_service
        self.residency_service = residency_service
        self.secrets = secrets
        self.audit_chain = audit_chain
        self.producer = producer
        self.settings = settings
        self.deliverers = deliverers

    async def route(
        self,
        alert: UserAlert,
        recipient: User | PlatformUser,
        *,
        workspace_id: UUID | None = None,
        severity: str = "medium",
    ) -> RoutingResult:
        configs: list[_ChannelView] = []
        if self.settings.notifications.multi_channel_enabled:
            configs = [
                _ChannelView(
                    channel_type=config.channel_type,
                    target=config.target,
                    quiet_hours=config.quiet_hours,
                    alert_type_filter=config.alert_type_filter,
                    severity_floor=config.severity_floor,
                    extra=config.extra,
                )
                for config in await self.repo.list_enabled_channel_configs(recipient.id)
            ]
        if not configs:
            legacy = await self.repo.get_settings(recipient.id)
            method = legacy.delivery_method if legacy is not None else DeliveryMethod.in_app
            target = "in_app"
            if method == DeliveryMethod.email:
                target = recipient.email
            elif method == DeliveryMethod.webhook and legacy is not None and legacy.webhook_url:
                target = legacy.webhook_url
            configs = [_ChannelView(channel_type=method, target=target)]

        attempts: list[RoutingAttempt] = []
        for config in configs:
            if config.alert_type_filter and alert.alert_type not in config.alert_type_filter:
                continue
            if config.severity_floor and _severity_rank(severity) < _severity_rank(
                config.severity_floor
            ):
                continue
            if config.quiet_hours and in_quiet_hours(
                datetime.now(UTC),
                config.quiet_hours,
                severity=severity,
                bypass_severity=self.settings.notifications.quiet_hours_default_severity_bypass,
            ):
                continue

            verdict = await self.dlp_service.scan_outbound(
                payload=_alert_payload(alert),
                workspace_id=workspace_id,
                channel_type=config.channel_type.value,
            )
            verdict_action = _verdict_action(verdict)
            if verdict_action == "block":
                attempts.append(
                    await self._record_attempt(
                        alert,
                        config,
                        DeliveryOutcome.failed,
                        workspace_id=workspace_id,
                        error_detail="dlp_blocked",
                    )
                )
                continue
            delivery_alert = _alert_for_delivery(alert, _redacted_payload(verdict))

            if config.channel_type == DeliveryMethod.in_app:
                await self._publish_in_app(delivery_alert)
                attempts.append(
                    RoutingAttempt(
                        channel_type=config.channel_type,
                        target=config.target,
                        outcome=DeliveryOutcome.success.value,
                    )
                )
                await self._publish_attempt(alert, config, DeliveryOutcome.success, workspace_id)
                continue

            if config.channel_type == DeliveryMethod.email:
                email_deliverer = cast(
                    EmailDeliverer,
                    self.deliverers.get(DeliveryMethod.email),
                )
                outcome = await email_deliverer.send(delivery_alert, config.target, config)
                attempts.append(
                    await self._record_attempt(
                        alert,
                        config,
                        outcome,
                        workspace_id=workspace_id,
                        error_detail=None
                        if outcome == DeliveryOutcome.success
                        else "email delivery failed",
                    )
                )
                continue

            if config.channel_type == DeliveryMethod.webhook:
                if workspace_id is not None:
                    region = await self.residency_service.resolve_region_for_url(config.target)
                    if not await self.residency_service.check_egress(workspace_id, region):
                        attempts.append(
                            await self._record_attempt(
                                alert,
                                config,
                                DeliveryOutcome.failed,
                                workspace_id=workspace_id,
                                error_detail="residency_violation",
                            )
                        )
                        continue
                webhook_deliverer = cast(
                    WebhookDeliverer,
                    self.deliverers.get(DeliveryMethod.webhook),
                )
                outcome, error_detail = await webhook_deliverer.send(delivery_alert, config.target)
                attempts.append(
                    await self._record_attempt(
                        alert,
                        config,
                        outcome,
                        workspace_id=workspace_id,
                        error_detail=error_detail,
                    )
                )
                continue

            if config.channel_type in {DeliveryMethod.slack, DeliveryMethod.teams}:
                deliverer = cast(Any, self.deliverers.get(config.channel_type))
                outcome, error_detail = await deliverer.send(
                    delivery_alert,
                    config.target,
                    config,
                )
                attempts.append(
                    await self._record_attempt(
                        alert,
                        config,
                        outcome,
                        workspace_id=workspace_id,
                        error_detail=error_detail,
                    )
                )
                continue

            if config.channel_type == DeliveryMethod.sms:
                sms_deliverer = cast(SmsDeliverer, self.deliverers.get(DeliveryMethod.sms))
                outcome, error_detail = await sms_deliverer.send(
                    delivery_alert,
                    config.target,
                    config,
                    workspace_id=workspace_id,
                )
                attempts.append(
                    await self._record_attempt(
                        alert,
                        config,
                        outcome,
                        workspace_id=workspace_id,
                        error_detail=error_detail,
                    )
                )
                continue

            attempts.append(
                RoutingAttempt(
                    channel_type=config.channel_type,
                    target=config.target,
                    outcome=DeliveryOutcome.failed.value,
                    error_detail="deliverer_not_registered",
                )
            )
        return RoutingResult(attempts=attempts)

    async def route_workspace_event(
        self,
        envelope: object,
        workspace_id: UUID,
    ) -> list[WebhookDispatchResult]:
        event_type = _event_type(envelope)
        event_id = _event_id(envelope)
        payload = _event_payload(envelope)
        webhooks = await self.repo.list_active_outbound_webhooks(workspace_id, event_type)
        results: list[WebhookDispatchResult] = []
        for webhook in webhooks:
            idempotency_key = derive_idempotency_key(webhook.id, event_id)
            existing_delivery = await self._get_existing_workspace_delivery(
                webhook.id,
                idempotency_key,
            )
            if existing_delivery is not None:
                results.append(
                    WebhookDispatchResult(
                        webhook_id=webhook.id,
                        delivery_id=existing_delivery.id,
                        status=str(existing_delivery.status),
                    )
                )
                continue
            verdict = await self.dlp_service.scan_outbound(
                payload=payload,
                workspace_id=workspace_id,
                channel_type=DeliveryMethod.webhook.value,
            )
            failure_reason: str | None = None
            if _verdict_action(verdict) == "block":
                failure_reason = "dlp_blocked"
            elif webhook.region_pinned_to and not await self.residency_service.check_egress(
                workspace_id,
                webhook.region_pinned_to,
            ):
                failure_reason = "residency_violation"

            status = "dead_letter" if failure_reason else "delivering"
            delivery = await self.repo.insert_delivery(
                webhook_id=webhook.id,
                idempotency_key=idempotency_key,
                event_id=event_id,
                event_type=event_type,
                payload=payload,
                status=status,
                failure_reason=failure_reason,
                attempts=0,
                next_attempt_at=None,
                dead_lettered_at=datetime.now(UTC) if failure_reason else None,
            )
            if not failure_reason:
                status = await self._dispatch_workspace_delivery(webhook, delivery, payload)
            results.append(
                WebhookDispatchResult(
                    webhook_id=webhook.id,
                    delivery_id=delivery.id,
                    status=status,
                )
            )
        return results

    async def _get_existing_workspace_delivery(
        self,
        webhook_id: UUID,
        idempotency_key: UUID,
    ) -> Any | None:
        lookup = getattr(self.repo, "get_webhook_delivery_by_idempotency", None)
        if not callable(lookup):
            return None
        return await lookup(webhook_id, idempotency_key)

    async def _dispatch_workspace_delivery(
        self,
        webhook: object,
        delivery: object,
        payload: dict[str, Any],
    ) -> str:
        webhook_row = cast(Any, webhook)
        delivery_row = cast(Any, delivery)
        secret_payload = await self.secrets.read_secret(webhook_row.signing_secret_ref)
        secret = str(secret_payload.get("hmac_secret", ""))
        webhook_deliverer = cast(
            WebhookDeliverer,
            self.deliverers.get(DeliveryMethod.webhook),
        )
        outcome, error_detail, _idempotency_key = await webhook_deliverer.send_signed(
            webhook_id=webhook_row.id,
            event_id=delivery_row.event_id,
            webhook_url=webhook_row.url,
            payload=payload,
            secret=secret,
            platform_version=self.settings.profile,
        )
        if outcome == DeliveryOutcome.success:
            await self.repo.update_delivery_status(
                delivery_row.id,
                status="delivered",
                attempts=1,
                last_attempt_at=datetime.now(UTC),
                next_attempt_at=None,
                failure_reason=None,
            )
            return "delivered"
        if outcome == DeliveryOutcome.failed:
            await self.repo.update_delivery_status(
                delivery_row.id,
                status="dead_letter",
                attempts=1,
                failure_reason=error_detail or "4xx_permanent",
                next_attempt_at=None,
                dead_lettered_at=datetime.now(UTC),
            )
            return "dead_letter"
        await self.repo.update_delivery_status(
            delivery_row.id,
            status="failed",
            attempts=1,
            failure_reason=error_detail,
            last_attempt_at=datetime.now(UTC),
            next_attempt_at=datetime.now(UTC)
            + timedelta(
                seconds=_retry_delay_seconds(
                    error_detail,
                    webhook_row.retry_policy,
                    self.settings,
                )
            ),
        )
        return "failed"

    async def _record_attempt(
        self,
        alert: UserAlert,
        config: _ChannelView,
        outcome: DeliveryOutcome,
        *,
        workspace_id: UUID | None,
        error_detail: str | None,
    ) -> RoutingAttempt:
        delivery = await self.repo.ensure_alert_delivery_outcome(alert.id, config.channel_type)
        await self.repo.update_delivery_outcome(
            delivery.id,
            outcome=outcome,
            error_detail=error_detail,
            delivered_at=datetime.now(UTC) if outcome == DeliveryOutcome.success else None,
            next_retry_at=None,
        )
        await self._publish_attempt(alert, config, outcome, workspace_id, error_detail)
        return RoutingAttempt(
            channel_type=config.channel_type,
            target=config.target,
            outcome=outcome.value,
            error_detail=error_detail,
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

    async def _publish_attempt(
        self,
        alert: UserAlert,
        config: _ChannelView,
        outcome: DeliveryOutcome,
        workspace_id: UUID | None,
        error_detail: str | None = None,
    ) -> None:
        await publish_delivery_attempted(
            self.producer,
            DeliveryAttemptedPayload(
                alert_id=alert.id,
                channel_type=config.channel_type.value,
                outcome=outcome.value,
                workspace_id=workspace_id,
                error_detail=error_detail,
                occurred_at=datetime.now(UTC),
            ),
            CorrelationContext(
                correlation_id=uuid4(),
                workspace_id=workspace_id,
                interaction_id=alert.interaction_id,
            ),
        )


_SEVERITY_RANK: dict[str, int] = {
    "info": 0,
    "low": 0,
    "medium": 1,
    "warn": 2,
    "warning": 2,
    "high": 3,
    "critical": 4,
}


def _severity_rank(severity: str) -> int:
    return _SEVERITY_RANK.get(severity.lower(), 1)


def _alert_payload(alert: UserAlert) -> dict[str, Any]:
    return {
        "id": str(alert.id),
        "user_id": str(alert.user_id),
        "alert_type": alert.alert_type,
        "title": alert.title,
        "body": alert.body,
        "urgency": alert.urgency,
        "interaction_id": None if alert.interaction_id is None else str(alert.interaction_id),
        "source_reference": alert.source_reference,
        "created_at": alert.created_at.isoformat(),
    }


def _verdict_action(verdict: object) -> str:
    if isinstance(verdict, dict):
        return str(verdict.get("action", "allow"))
    return str(getattr(verdict, "action", "allow"))


def _event_type(envelope: object) -> str:
    if isinstance(envelope, dict):
        return str(envelope["event_type"])
    return str(cast(Any, envelope).event_type)


def _event_id(envelope: object) -> UUID:
    raw = envelope["event_id"] if isinstance(envelope, dict) else cast(Any, envelope).event_id
    return raw if isinstance(raw, UUID) else UUID(str(raw))


def _event_payload(envelope: object) -> dict[str, Any]:
    if isinstance(envelope, dict):
        return cast(dict[str, Any], _jsonable_payload(envelope))
    model_dump = getattr(envelope, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="json")
        return value if isinstance(value, dict) else {"payload": value}
    return cast(
        dict[str, Any],
        _jsonable_payload(getattr(envelope, "__dict__", {"payload": str(envelope)})),
    )


def _jsonable_payload(value: object) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable_payload(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable_payload(item) for item in value]
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    return value


def _first_backoff(retry_policy: dict[str, Any], settings: PlatformSettings) -> int:
    backoff = retry_policy.get(
        "backoff_seconds",
        settings.notifications.webhook_default_backoff_seconds,
    )
    if isinstance(backoff, list) and backoff:
        return int(backoff[0])
    return 60


def _retry_delay_seconds(
    error_detail: str | None,
    retry_policy: dict[str, Any],
    settings: PlatformSettings,
) -> int:
    retry_after_prefix = "retry_after="
    if error_detail:
        for segment in error_detail.split(";"):
            segment = segment.strip()
            if segment.startswith(retry_after_prefix):
                try:
                    return max(0, int(segment.removeprefix(retry_after_prefix)))
                except ValueError:
                    break
    return _first_backoff(retry_policy, settings)


def _redacted_payload(verdict: object) -> dict[str, Any] | None:
    if _verdict_action(verdict) != "redact":
        return None
    if isinstance(verdict, dict):
        payload = verdict.get("redacted_payload")
    else:
        payload = getattr(verdict, "redacted_payload", None)
    return payload if isinstance(payload, dict) else None


def _alert_for_delivery(alert: UserAlert, payload: dict[str, Any] | None) -> UserAlert:
    if not payload:
        return alert
    alert.title = str(payload.get("title", alert.title))
    body = payload.get("body", alert.body)
    alert.body = None if body is None else str(body)
    return alert
