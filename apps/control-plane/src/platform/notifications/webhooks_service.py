from __future__ import annotations

import base64
import builtins
import secrets
from datetime import UTC, datetime, timedelta
from platform.common.config import PlatformSettings
from platform.notifications.canonical import derive_idempotency_key
from platform.notifications.channel_router import DlpService, ResidencyService, SecretProvider
from platform.notifications.deliverers.webhook_deliverer import WebhookDeliverer
from platform.notifications.exceptions import (
    DeadLetterNotReplayableError,
    InvalidWebhookUrlError,
    QuotaExceededError,
    ResidencyViolationError,
    WebhookInactiveError,
    WebhookNotFoundError,
)
from platform.notifications.models import DeliveryOutcome, WebhookDelivery, WebhookDeliveryStatus
from platform.notifications.repository import NotificationsRepository
from platform.notifications.schemas import (
    DeadLetterListItem,
    OutboundWebhookCreate,
    OutboundWebhookCreateResponse,
    OutboundWebhookRead,
    OutboundWebhookUpdate,
    WebhookDeliveryRead,
)
from typing import Any
from uuid import UUID, uuid4


class OutboundWebhookService:
    def __init__(
        self,
        *,
        repo: NotificationsRepository,
        settings: PlatformSettings,
        secrets: SecretProvider,
        residency_service: ResidencyService,
        dlp_service: DlpService | None = None,
        deliverer: WebhookDeliverer | None = None,
    ) -> None:
        self.repo = repo
        self.settings = settings
        self.secrets = secrets
        self.residency_service = residency_service
        self.dlp_service = dlp_service
        self.deliverer = deliverer or WebhookDeliverer()

    async def create(
        self,
        payload: OutboundWebhookCreate,
        *,
        actor_id: UUID,
    ) -> OutboundWebhookCreateResponse:
        await self._validate_url(str(payload.url), payload.workspace_id)
        active_count = await self.repo.count_active_webhooks(payload.workspace_id)
        if active_count >= self.settings.notifications.webhooks_per_workspace_max:
            raise QuotaExceededError("Maximum outbound webhooks per workspace exceeded")

        secret = _new_hmac_secret()
        secret_ref = f"secret/data/notifications/webhook-secrets/pending-{secrets.token_hex(8)}"
        webhook = await self.repo.create_outbound_webhook(
            workspace_id=payload.workspace_id,
            name=payload.name,
            url=str(payload.url),
            event_types=payload.event_types,
            signing_secret_ref=secret_ref,
            active=True,
            retry_policy=payload.retry_policy or self._default_retry_policy(),
            region_pinned_to=payload.region_pinned_to,
            created_by=actor_id,
        )
        secret_ref = f"secret/data/notifications/webhook-secrets/{webhook.id}"
        await self.secrets.write_secret(secret_ref, {"hmac_secret": secret})
        updated = await self.repo.update_outbound_webhook(
            webhook.id,
            signing_secret_ref=secret_ref,
        )
        assert updated is not None
        data = OutboundWebhookRead.model_validate(updated).model_dump()
        return OutboundWebhookCreateResponse(**data, signing_secret=secret)

    async def list(self, workspace_id: UUID) -> list[OutboundWebhookRead]:
        return [
            OutboundWebhookRead.model_validate(item)
            for item in await self.repo.list_outbound_webhooks(workspace_id)
        ]

    async def get(self, webhook_id: UUID) -> OutboundWebhookRead:
        webhook = await self.repo.get_outbound_webhook(webhook_id)
        if webhook is None:
            raise WebhookNotFoundError(webhook_id)
        return OutboundWebhookRead.model_validate(webhook)

    async def update(
        self,
        webhook_id: UUID,
        payload: OutboundWebhookUpdate,
    ) -> OutboundWebhookRead:
        webhook = await self.repo.get_outbound_webhook(webhook_id)
        if webhook is None:
            raise WebhookNotFoundError(webhook_id)
        fields = payload.model_dump(exclude_unset=True)
        if "url" in fields and fields["url"] is not None:
            await self._validate_url(str(payload.url), webhook.workspace_id)
            fields["url"] = str(payload.url)
        updated = await self.repo.update_outbound_webhook(webhook_id, **fields)
        assert updated is not None
        return OutboundWebhookRead.model_validate(updated)

    async def rotate_secret(self, webhook_id: UUID) -> OutboundWebhookRead:
        webhook = await self.repo.get_outbound_webhook(webhook_id)
        if webhook is None:
            raise WebhookNotFoundError(webhook_id)
        await self.secrets.write_secret(
            webhook.signing_secret_ref,
            {"hmac_secret": _new_hmac_secret()},
        )
        updated = await self.repo.update_outbound_webhook(
            webhook_id,
            last_rotated_at=datetime.now(UTC),
        )
        assert updated is not None
        return OutboundWebhookRead.model_validate(updated)

    async def deactivate(self, webhook_id: UUID) -> OutboundWebhookRead:
        webhook = await self.repo.update_outbound_webhook(webhook_id, active=False)
        if webhook is None:
            raise WebhookNotFoundError(webhook_id)
        return OutboundWebhookRead.model_validate(webhook)

    async def list_dead_letters(
        self,
        workspace_id: UUID,
        filters: dict[str, Any] | None = None,
    ) -> builtins.list[DeadLetterListItem]:
        rows = await self.repo.list_dead_letters(workspace_id, filters)
        return [_dead_letter_item(row) for row in rows]

    async def get_dead_letter(self, delivery_id: UUID) -> DeadLetterListItem:
        delivery = await self.repo.get_delivery(delivery_id, include_webhook=True)
        if delivery is None:
            raise WebhookNotFoundError(delivery_id)
        return _dead_letter_item(delivery)

    async def replay_dead_letter(
        self,
        delivery_id: UUID,
        *,
        actor_id: UUID,
    ) -> WebhookDeliveryRead:
        original = await self.repo.get_delivery(delivery_id, include_webhook=True)
        if original is None:
            raise WebhookNotFoundError(delivery_id)
        if original.status != WebhookDeliveryStatus.dead_letter.value:
            raise DeadLetterNotReplayableError(delivery_id)
        replay = await self.repo.replay_dead_letter(
            original,
            actor_id=actor_id,
            now=datetime.now(UTC),
        )
        return WebhookDeliveryRead.model_validate(replay)

    async def replay_dead_letters(
        self,
        *,
        workspace_id: UUID,
        actor_id: UUID,
        filters: dict[str, Any] | None = None,
    ) -> builtins.list[WebhookDeliveryRead]:
        rows = await self.repo.list_dead_letters(workspace_id, filters)
        replayed: builtins.list[WebhookDeliveryRead] = []
        for row in rows:
            replay = await self.repo.replay_dead_letter(
                row,
                actor_id=actor_id,
                now=datetime.now(UTC),
            )
            replayed.append(WebhookDeliveryRead.model_validate(replay))
        return replayed

    async def resolve_dead_letter(
        self,
        delivery_id: UUID,
        *,
        actor_id: UUID,
        resolution: str,
    ) -> WebhookDeliveryRead:
        delivery = await self.repo.get_delivery(delivery_id, include_webhook=True)
        if delivery is None:
            raise WebhookNotFoundError(delivery_id)
        if delivery.status != WebhookDeliveryStatus.dead_letter.value:
            raise DeadLetterNotReplayableError(delivery_id)
        updated = await self.repo.update_delivery_status(
            delivery_id,
            resolved_at=datetime.now(UTC),
            resolved_by=actor_id,
            resolution_reason=resolution,
        )
        assert updated is not None
        return WebhookDeliveryRead.model_validate(updated)

    async def send_test_event(self, webhook_id: UUID, *, actor_id: UUID) -> WebhookDeliveryRead:
        webhook = await self.repo.get_outbound_webhook(webhook_id)
        if webhook is None:
            raise WebhookNotFoundError(webhook_id)
        if not webhook.active:
            raise WebhookInactiveError(webhook_id)

        now = datetime.now(UTC)
        event_id = uuid4()
        event_type = "notifications.webhook.test"
        payload = {
            "event_id": str(event_id),
            "event_type": event_type,
            "workspace_id": str(webhook.workspace_id),
            "webhook_id": str(webhook.id),
            "triggered_by": str(actor_id),
            "test": True,
            "sent_at": now.isoformat(),
        }
        failure_reason = await self._policy_failure_reason(
            payload=payload,
            workspace_id=webhook.workspace_id,
            region_pinned_to=webhook.region_pinned_to,
        )
        status = (
            WebhookDeliveryStatus.dead_letter.value
            if failure_reason
            else WebhookDeliveryStatus.delivering.value
        )
        delivery = await self.repo.insert_delivery(
            webhook_id=webhook.id,
            idempotency_key=derive_idempotency_key(webhook.id, event_id),
            event_id=event_id,
            event_type=event_type,
            payload=payload,
            status=status,
            failure_reason=failure_reason,
            attempts=0,
            next_attempt_at=None,
            dead_lettered_at=now if failure_reason else None,
        )
        if failure_reason is not None:
            return WebhookDeliveryRead.model_validate(delivery)

        secret_payload = await self.secrets.read_secret(webhook.signing_secret_ref)
        secret = str(secret_payload.get("hmac_secret", ""))
        outcome, error_detail, _idempotency_key = await self.deliverer.send_signed(
            webhook_id=webhook.id,
            event_id=event_id,
            webhook_url=webhook.url,
            payload=payload,
            secret=secret,
            platform_version=self.settings.profile,
        )
        updated = await self._record_test_attempt(
            delivery=delivery,
            outcome=outcome,
            error_detail=error_detail,
            retry_policy=webhook.retry_policy,
        )
        return WebhookDeliveryRead.model_validate(updated or delivery)

    async def _validate_url(self, url: str, workspace_id: UUID) -> None:
        if url.startswith("http://") and not self.settings.notifications.allow_http_webhooks:
            raise InvalidWebhookUrlError("Outbound webhook URLs must use HTTPS")
        region = await self.residency_service.resolve_region_for_url(url)
        if not await self.residency_service.check_egress(workspace_id, region):
            raise ResidencyViolationError("Outbound webhook URL violates workspace residency")

    async def _policy_failure_reason(
        self,
        *,
        payload: dict[str, Any],
        workspace_id: UUID,
        region_pinned_to: str | None,
    ) -> str | None:
        if self.dlp_service is not None:
            verdict = await self.dlp_service.scan_outbound(
                payload=payload,
                workspace_id=workspace_id,
                channel_type="webhook",
            )
            if _verdict_action(verdict) == "block":
                return "dlp_blocked"
        if region_pinned_to and not await self.residency_service.check_egress(
            workspace_id,
            region_pinned_to,
        ):
            return "residency_violation"
        return None

    async def _record_test_attempt(
        self,
        *,
        delivery: WebhookDelivery,
        outcome: DeliveryOutcome,
        error_detail: str | None,
        retry_policy: dict[str, Any],
    ) -> WebhookDelivery | None:
        now = datetime.now(UTC)
        if outcome == DeliveryOutcome.success:
            return await self.repo.update_delivery_status(
                delivery.id,
                status=WebhookDeliveryStatus.delivered.value,
                attempts=1,
                last_attempt_at=now,
                next_attempt_at=None,
                failure_reason=None,
            )
        if outcome == DeliveryOutcome.failed:
            return await self.repo.update_delivery_status(
                delivery.id,
                status=WebhookDeliveryStatus.dead_letter.value,
                attempts=1,
                last_attempt_at=now,
                next_attempt_at=None,
                failure_reason=error_detail or "4xx_permanent",
                dead_lettered_at=now,
            )
        delay_seconds = _retry_delay_seconds(
            error_detail,
            retry_policy,
            self.settings,
        )
        return await self.repo.update_delivery_status(
            delivery.id,
            status=WebhookDeliveryStatus.failed.value,
            attempts=1,
            last_attempt_at=now,
            next_attempt_at=now + timedelta(seconds=delay_seconds),
            failure_reason=error_detail,
        )

    def _default_retry_policy(self) -> dict[str, object]:
        return {
            "max_retries": 3,
            "backoff_seconds": list(self.settings.notifications.webhook_default_backoff_seconds),
            "total_window_seconds": self.settings.notifications.webhook_max_retry_window_seconds,
        }


def _new_hmac_secret() -> str:
    return base64.b64encode(secrets.token_bytes(32)).decode("ascii")


def _dead_letter_item(delivery: WebhookDelivery) -> DeadLetterListItem:
    item = DeadLetterListItem.model_validate(delivery)
    webhook = getattr(delivery, "webhook", None)
    return item.model_copy(
        update={
            "workspace_id": getattr(webhook, "workspace_id", None),
            "webhook_name": getattr(webhook, "name", None),
        }
    )


def _verdict_action(verdict: object) -> str:
    if isinstance(verdict, dict):
        return str(verdict.get("action", "allow"))
    return str(getattr(verdict, "action", "allow"))


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
    backoff = retry_policy.get(
        "backoff_seconds",
        settings.notifications.webhook_default_backoff_seconds,
    )
    if isinstance(backoff, list) and backoff:
        return int(backoff[0])
    return 60
