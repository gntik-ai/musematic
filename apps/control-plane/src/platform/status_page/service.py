"""Status page service for FR-675-FR-682.

See specs/095-public-status-banner-workbench-uis/plan.md for the implementation plan.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from platform.common.exceptions import AuthorizationError, ValidationError
from platform.incident_response.models import Incident
from platform.multi_region_ops.models import MaintenanceWindow
from platform.notifications.models import DeliveryOutcome
from platform.status_page.exceptions import ConfirmationTokenInvalidError, SubscriptionNotFoundError
from platform.status_page.models import PlatformStatusSnapshot, StatusSubscription
from platform.status_page.repository import StatusPageRepository
from platform.status_page.schemas import (
    AntiEnumerationResponse,
    ComponentDetail,
    ComponentHistoryPoint,
    ComponentStatus,
    MaintenanceWindowSummary,
    MyIncidentSummary,
    MyMaintenanceWindowSummary,
    MyPlatformStatus,
    MyStatusSubscription,
    OverallState,
    PlatformStatusSnapshotPayload,
    PlatformStatusSnapshotRead,
    PublicIncident,
    PublicIncidentsResponse,
    SourceKind,
    TokenActionResponse,
    UptimeSummary,
    WebhookSubscribeResponse,
    snapshot_read_from_payload,
)
from typing import Any, NoReturn
from uuid import UUID, uuid4

CURRENT_SNAPSHOT_KEY = "status:snapshot:current"
LAST_GOOD_SNAPSHOT_KEY = "status:fallback:lastgood"

DEFAULT_COMPONENTS: tuple[tuple[str, str], ...] = (
    ("control-plane-api", "Control Plane API"),
    ("web-app", "Authenticated Web App"),
    ("reasoning-engine", "Reasoning Engine"),
    ("workflow-engine", "Workflow Engine"),
)


@dataclass(frozen=True)
class SnapshotWithSource:
    snapshot: PlatformStatusSnapshotRead
    source: str

    @property
    def age_seconds(self) -> int:
        generated_at = self.snapshot.generated_at
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=UTC)
        return max(0, int((datetime.now(UTC) - generated_at).total_seconds()))


class StatusPageService:
    def __init__(
        self,
        *,
        repository: StatusPageRepository,
        redis_client: Any | None = None,
        email_deliverer: Any | None = None,
        webhook_deliverer: Any | None = None,
        slack_deliverer: Any | None = None,
        smtp_settings: dict[str, Any] | object | None = None,
        platform_version: str = "dev",
    ) -> None:
        self.repository = repository
        self.redis_client = redis_client
        self.email_deliverer = email_deliverer
        self.webhook_deliverer = webhook_deliverer
        self.slack_deliverer = slack_deliverer
        self.smtp_settings = smtp_settings or {}
        self.platform_version = platform_version

    async def compose_current_snapshot(
        self,
        *,
        component_health: list[dict[str, Any]] | None = None,
        source_kind: SourceKind = SourceKind.poll,
    ) -> PlatformStatusSnapshotRead:
        generated_at = datetime.now(UTC)
        active_incidents = [
            self._incident_to_public(incident)
            for incident in await self.repository.list_active_incidents()
        ]
        recently_resolved = [
            self._incident_to_public(incident)
            for incident in await self.repository.list_recent_resolved_incidents(days=7)
        ]
        scheduled = [
            self._maintenance_to_summary(window)
            for window in await self.repository.list_scheduled_maintenance(days=30)
        ]
        active_maintenance_windows = await self.repository.list_active_maintenance()
        active_maintenance = (
            self._maintenance_to_summary(active_maintenance_windows[0])
            if active_maintenance_windows
            else None
        )
        uptime = self._normalise_uptime(await self.repository.get_uptime_30d())
        components = self._normalise_components(
            component_health,
            generated_at=generated_at,
            uptime=uptime,
        )
        overall_state = self._aggregate_overall_state(
            components=components,
            active_incidents=active_incidents,
            active_maintenance=active_maintenance,
        )
        payload = PlatformStatusSnapshotPayload(
            overall_state=overall_state,
            components=components,
            active_incidents=active_incidents,
            scheduled_maintenance=scheduled,
            active_maintenance=active_maintenance,
            recently_resolved_incidents=recently_resolved,
            uptime_30d=uptime,
        )
        row = await self.repository.insert_snapshot(
            generated_at=generated_at,
            overall_state=overall_state.value,
            payload=payload.model_dump(mode="json"),
            source_kind=source_kind.value,
        )
        snapshot = self._snapshot_from_row(row)
        await self._cache_snapshot(snapshot)
        return snapshot

    async def get_public_snapshot(self) -> SnapshotWithSource:
        cached = await self._get_cached_snapshot(CURRENT_SNAPSHOT_KEY)
        if cached is not None:
            return SnapshotWithSource(cached, "redis")

        row = await self.repository.get_current_snapshot()
        if row is not None:
            snapshot = self._snapshot_from_row(row)
            await self._cache_snapshot(snapshot, current_only=True)
            return SnapshotWithSource(snapshot, "postgres")

        snapshot = await self.compose_current_snapshot(source_kind=SourceKind.fallback)
        return SnapshotWithSource(snapshot, "fallback")

    async def get_component_detail(self, component_id: str, *, days: int = 30) -> ComponentDetail:
        current = await self.get_public_snapshot()
        component = next(
            (item for item in current.snapshot.components if item.id == component_id),
            None,
        )
        if component is None:
            raise KeyError(component_id)
        history = [
            ComponentHistoryPoint.model_validate(point)
            for point in await self.repository.get_component_history(component_id, days=days)
        ]
        return ComponentDetail(**component.model_dump(), history_30d=history)

    async def list_public_incidents(
        self,
        *,
        status: str | None = None,
    ) -> PublicIncidentsResponse:
        if status == "active":
            incidents = [
                self._incident_to_public(incident)
                for incident in await self.repository.list_active_incidents()
            ]
        elif status == "resolved":
            incidents = [
                self._incident_to_public(incident)
                for incident in await self.repository.list_recent_resolved_incidents(days=7)
            ]
        else:
            snapshot = (await self.get_public_snapshot()).snapshot
            incidents = snapshot.active_incidents + snapshot.recently_resolved_incidents
        return PublicIncidentsResponse(incidents=incidents)

    async def get_my_platform_status(self, current_user: dict[str, Any]) -> MyPlatformStatus:
        del current_user
        snapshot = (await self.get_public_snapshot()).snapshot
        active_maintenance = None
        if snapshot.active_maintenance is not None:
            active_maintenance = MyMaintenanceWindowSummary(
                **snapshot.active_maintenance.model_dump(),
                affects_my_features=[],
            )

        return MyPlatformStatus(
            overall_state=snapshot.overall_state,
            active_maintenance=active_maintenance,
            active_incidents=[
                MyIncidentSummary(**incident.model_dump(), affects_my_features=[])
                for incident in snapshot.active_incidents
            ],
        )

    async def submit_email_subscription(
        self,
        *,
        email: str,
        scope_components: list[str],
    ) -> AntiEnumerationResponse:
        confirmation_token = _new_token()
        unsubscribe_token = _new_token()
        subscription = await self.repository.create_subscription(
            channel="email",
            target=email.strip().lower(),
            scope_components=_normalise_scope(scope_components),
            confirmation_token_hash=_hash_token(confirmation_token),
            unsubscribe_token_hash=_hash_token(unsubscribe_token),
            health="pending",
        )
        await self._send_email(
            email=email.strip().lower(),
            subject="Confirm Musematic status updates",
            body=_render_template(
                "confirm_subscription.txt",
                confirmation_token=confirmation_token,
                unsubscribe_token=unsubscribe_token,
                subscription_id=str(subscription.id),
            ),
        )
        await self._capture_e2e_subscription_tokens(
            email=email.strip().lower(),
            confirmation_token=confirmation_token,
            unsubscribe_token=unsubscribe_token,
        )
        return AntiEnumerationResponse()

    async def confirm_email_subscription(self, token: str) -> TokenActionResponse:
        subscription = await self.repository.get_subscription_by_confirmation_hash(
            _hash_token(token),
        )
        if subscription is None:
            raise ConfirmationTokenInvalidError()
        await self.repository.confirm_subscription(subscription)
        return TokenActionResponse(
            status="confirmed",
            message="Subscription confirmed.",
        )

    async def unsubscribe(self, token: str) -> TokenActionResponse:
        subscription = await self.repository.get_subscription_by_unsubscribe_hash(
            _hash_token(token),
        )
        if subscription is None:
            raise SubscriptionNotFoundError()
        await self.repository.mark_unsubscribed(subscription)
        await self._send_email(
            email=subscription.target,
            subject="Musematic status updates unsubscribed",
            body=_render_template("unsubscribed.txt", subscription_id=str(subscription.id)),
        )
        return TokenActionResponse(
            status="unsubscribed",
            message="Subscription removed.",
        )

    async def submit_webhook_subscription(
        self,
        *,
        url: str,
        scope_components: list[str],
        contact_email: str | None = None,
    ) -> WebhookSubscribeResponse:
        del contact_email
        secret = _new_token()
        event_id = uuid4()
        webhook_id = uuid4()
        outcome = DeliveryOutcome.success
        if self.webhook_deliverer is not None:
            outcome, _error, _idempotency = await self.webhook_deliverer.send_signed(
                webhook_id=webhook_id,
                event_id=event_id,
                webhook_url=url,
                payload={
                    "event_id": str(event_id),
                    "event_type": "status.subscription.test",
                    "test": True,
                },
                secret=secret,
                platform_version=self.platform_version,
            )
        subscription = await self.repository.create_subscription(
            channel="webhook",
            target=url,
            scope_components=_normalise_scope(scope_components),
            unsubscribe_token_hash=_hash_token(_new_token()),
            confirmed_at=datetime.now(UTC) if outcome == DeliveryOutcome.success else None,
            health="healthy" if outcome == DeliveryOutcome.success else "unhealthy",
        )
        return WebhookSubscribeResponse(
            subscription_id=str(subscription.id),
            signing_secret_hint=f"...{secret[-6:]}",
            verification_state="healthy" if outcome == DeliveryOutcome.success else "failed",
        )

    async def submit_slack_subscription(
        self,
        *,
        webhook_url: str,
        scope_components: list[str],
    ) -> WebhookSubscribeResponse:
        subscription = await self.repository.create_subscription(
            channel="slack",
            target=webhook_url,
            scope_components=_normalise_scope(scope_components),
            unsubscribe_token_hash=_hash_token(_new_token()),
            confirmed_at=datetime.now(UTC),
            health="healthy",
        )
        return WebhookSubscribeResponse(
            subscription_id=str(subscription.id),
            verification_state="healthy",
        )

    async def dispatch_event(self, event_kind: str, payload: dict[str, Any]) -> int:
        event_id = _event_id(payload)
        affected_components = _affected_components(payload)
        subscriptions = await self.repository.list_confirmed_subscriptions_for_event(
            affected_components=affected_components,
        )
        sent = 0
        for subscription in subscriptions:
            outcome, error = await self._deliver_subscription_event(
                subscription,
                event_kind,
                event_id,
                payload,
            )
            await self.repository.insert_dispatch(
                subscription_id=subscription.id,
                event_kind=event_kind,
                event_id=event_id,
                outcome=outcome,
                error_summary=error,
            )
            if outcome == "sent":
                sent += 1
        return sent

    async def list_my_subscriptions(
        self,
        current_user: dict[str, Any],
    ) -> list[MyStatusSubscription]:
        rows = await self.repository.list_user_subscriptions(
            user_id=_user_id(current_user),
            workspace_id=_optional_workspace_id(current_user),
        )
        return [_my_subscription(row) for row in rows]

    async def create_my_subscription(
        self,
        current_user: dict[str, Any],
        *,
        channel: str,
        target: str,
        scope_components: list[str],
    ) -> MyStatusSubscription:
        if channel not in {"email", "webhook", "slack"}:
            raise ValidationError(
                "status.subscription.invalid_channel",
                "Status subscriptions support email, webhook, or Slack channels",
            )
        now = datetime.now(UTC)
        confirmed_at = now if channel in {"webhook", "slack"} else None
        health = "healthy" if channel in {"webhook", "slack"} else "pending"
        webhook_id: UUID | None = None
        if channel == "webhook":
            webhook_id = uuid4()
            if self.webhook_deliverer is not None:
                outcome, _error, _idempotency = await self.webhook_deliverer.send_signed(
                    webhook_id=webhook_id,
                    event_id=uuid4(),
                    webhook_url=target,
                    payload={
                        "event_type": "status.subscription.test",
                        "test": True,
                    },
                    secret="status-page-dev-secret",
                    platform_version=self.platform_version,
                )
                if outcome != DeliveryOutcome.success:
                    confirmed_at = None
                    health = "unhealthy"
        subscription = await self.repository.create_subscription(
            channel=channel,
            target=target,
            scope_components=_normalise_scope(scope_components),
            unsubscribe_token_hash=_hash_token(_new_token()),
            confirmed_at=confirmed_at,
            health=health,
            workspace_id=_optional_workspace_id(current_user),
            user_id=_user_id(current_user),
            webhook_id=webhook_id,
        )
        return _my_subscription(subscription)

    async def update_my_subscription(
        self,
        current_user: dict[str, Any],
        subscription_id: UUID,
        *,
        target: str | None = None,
        scope_components: list[str] | None = None,
    ) -> MyStatusSubscription:
        values: dict[str, Any] = {}
        if target is not None:
            values["target"] = target
        if scope_components is not None:
            values["scope_components"] = _normalise_scope(scope_components)
        subscription = await self.repository.update_user_subscription(
            subscription_id=subscription_id,
            user_id=_user_id(current_user),
            values=values,
        )
        if subscription is None:
            await self._raise_not_found_or_forbidden(current_user, subscription_id)
        return _my_subscription(subscription)

    async def delete_my_subscription(
        self,
        current_user: dict[str, Any],
        subscription_id: UUID,
    ) -> TokenActionResponse:
        subscription = await self.repository.get_user_subscription(
            subscription_id=subscription_id,
            user_id=_user_id(current_user),
        )
        if subscription is None:
            await self._raise_not_found_or_forbidden(current_user, subscription_id)
        await self.repository.mark_unsubscribed(subscription)
        return TokenActionResponse(status="unsubscribed", message="Subscription removed.")

    async def _raise_not_found_or_forbidden(
        self,
        current_user: dict[str, Any],
        subscription_id: UUID,
    ) -> NoReturn:
        getter = getattr(self.repository, "get_subscription", None)
        existing = await getter(subscription_id) if callable(getter) else None
        if existing is not None and existing.user_id != _user_id(current_user):
            raise AuthorizationError(
                "status.subscription.forbidden",
                "Cannot access another user's status subscription",
            )
        raise SubscriptionNotFoundError()

    def _snapshot_from_row(self, row: PlatformStatusSnapshot) -> PlatformStatusSnapshotRead:
        return snapshot_read_from_payload(
            generated_at=row.generated_at,
            payload=row.payload,
            source_kind=row.source_kind,
            snapshot_id=str(row.id),
        )

    def _normalise_components(
        self,
        component_health: list[dict[str, Any]] | None,
        *,
        generated_at: datetime,
        uptime: dict[str, UptimeSummary],
    ) -> list[ComponentStatus]:
        raw_components = component_health
        if raw_components is None:
            raw_components = [
                {
                    "id": component_id,
                    "name": name,
                    "state": OverallState.operational.value,
                    "last_check_at": generated_at,
                    "uptime_30d_pct": uptime.get(
                        component_id,
                        UptimeSummary(pct=100, incidents=0),
                    ).pct,
                }
                for component_id, name in DEFAULT_COMPONENTS
            ]

        components: list[ComponentStatus] = []
        for item in raw_components:
            component_id = str(item.get("id", "")).strip()
            if not component_id:
                continue
            state = self._normalise_state(str(item.get("state", OverallState.operational.value)))
            components.append(
                ComponentStatus(
                    id=component_id,
                    name=str(item.get("name") or component_id.replace("-", " ").title()),
                    state=state,
                    last_check_at=item.get("last_check_at") or generated_at,
                    uptime_30d_pct=item.get("uptime_30d_pct")
                    or uptime.get(component_id, UptimeSummary(pct=100, incidents=0)).pct,
                )
            )
        return components

    def _normalise_uptime(self, raw: dict[str, Any]) -> dict[str, UptimeSummary]:
        uptime: dict[str, UptimeSummary] = {}
        for component_id, value in raw.items():
            if isinstance(value, UptimeSummary):
                uptime[str(component_id)] = value
            elif isinstance(value, dict):
                uptime[str(component_id)] = UptimeSummary.model_validate(value)
        for component_id, _name in DEFAULT_COMPONENTS:
            uptime.setdefault(component_id, UptimeSummary(pct=100, incidents=0))
        return uptime

    def _aggregate_overall_state(
        self,
        *,
        components: list[ComponentStatus],
        active_incidents: list[PublicIncident],
        active_maintenance: MaintenanceWindowSummary | None,
    ) -> OverallState:
        if active_maintenance is not None:
            return OverallState.maintenance
        if not components:
            return OverallState.degraded if active_incidents else OverallState.operational
        outage_states = {OverallState.partial_outage, OverallState.full_outage}
        if all(component.state in outage_states for component in components):
            return OverallState.full_outage
        if any(component.state in outage_states for component in components):
            return OverallState.partial_outage
        if any(component.state == OverallState.degraded for component in components):
            return OverallState.degraded
        if any(
            incident.severity.value in {"high", "critical", "warning"}
            for incident in active_incidents
        ):
            return OverallState.degraded
        return OverallState.operational

    def _normalise_state(self, state: str) -> OverallState:
        if state in {"outage", "down", "unavailable"}:
            return OverallState.partial_outage
        try:
            return OverallState(state)
        except ValueError:
            return OverallState.degraded

    def _incident_to_public(self, incident: Incident) -> PublicIncident:
        last_update_at = incident.resolved_at or incident.triggered_at
        last_update_summary = (
            "Incident resolved." if incident.resolved_at is not None else incident.description
        )
        return PublicIncident(
            id=str(incident.id),
            title=incident.title,
            severity=incident.severity,
            started_at=incident.triggered_at,
            resolved_at=incident.resolved_at,
            components_affected=self._incident_components(incident),
            last_update_at=last_update_at,
            last_update_summary=last_update_summary,
            updates=[{"at": last_update_at, "text": last_update_summary}],
        )

    def _incident_components(self, incident: Incident) -> list[str]:
        candidates = [
            incident.alert_rule_class,
            incident.runbook_scenario or "",
            incident.condition_fingerprint,
            incident.title,
        ]
        lowered = " ".join(candidates).lower()
        components: list[str] = []
        if "control" in lowered or "api" in lowered:
            components.append("control-plane-api")
        if "reasoning" in lowered:
            components.append("reasoning-engine")
        if "workflow" in lowered or "execution" in lowered:
            components.append("workflow-engine")
        return components

    def _maintenance_to_summary(self, window: MaintenanceWindow) -> MaintenanceWindowSummary:
        return MaintenanceWindowSummary(
            window_id=str(window.id),
            title=window.announcement_text or window.reason or "Scheduled maintenance",
            starts_at=window.starts_at,
            ends_at=window.ends_at,
            blocks_writes=window.blocks_writes,
            components_affected=[],
        )

    async def _get_cached_snapshot(self, key: str) -> PlatformStatusSnapshotRead | None:
        if self.redis_client is None:
            return None
        getter = getattr(self.redis_client, "get", None)
        if not callable(getter):
            return None
        value = await getter(key)
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return PlatformStatusSnapshotRead.model_validate_json(str(value))

    async def _cache_snapshot(
        self,
        snapshot: PlatformStatusSnapshotRead,
        *,
        current_only: bool = False,
    ) -> None:
        if self.redis_client is None:
            return
        body = snapshot.model_dump_json().encode("utf-8")
        await self._redis_set(CURRENT_SNAPSHOT_KEY, body, ttl=90)
        if not current_only:
            await self._redis_set(LAST_GOOD_SNAPSHOT_KEY, body, ttl=24 * 60 * 60)

    async def _redis_set(self, key: str, value: bytes, *, ttl: int) -> None:
        setter = getattr(self.redis_client, "set", None)
        if not callable(setter):
            return
        try:
            await setter(key, value, ttl=ttl)
        except TypeError:
            await setter(key, value, ex=ttl)

    async def _capture_e2e_subscription_tokens(
        self,
        *,
        email: str,
        confirmation_token: str,
        unsubscribe_token: str,
    ) -> None:
        if not (
            os.getenv("FEATURE_E2E_MODE") == "true"
            or os.getenv("PLATFORM_FEATURE_E2E_MODE") == "true"
        ):
            return
        await self._redis_set(
            f"e2e:status-subscriptions:tokens:{email}",
            json.dumps(
                {
                    "email": email,
                    "confirmation_token": confirmation_token,
                    "unsubscribe_token": unsubscribe_token,
                },
            ).encode("utf-8"),
            ttl=3600,
        )

    async def _send_email(self, *, email: str, subject: str, body: str) -> None:
        if self.email_deliverer is None:
            return
        alert = _Alert(title=subject, body=body, urgency="medium")
        await self.email_deliverer.send(alert, email, self.smtp_settings)

    async def _deliver_subscription_event(
        self,
        subscription: StatusSubscription,
        event_kind: str,
        event_id: UUID,
        payload: dict[str, Any],
    ) -> tuple[str, str | None]:
        if subscription.channel == "email":
            unsubscribe_token = _new_token()
            rotate = getattr(self.repository, "rotate_unsubscribe_token", None)
            if callable(rotate):
                await rotate(subscription, _hash_token(unsubscribe_token))
            else:
                subscription.unsubscribe_token_hash = _hash_token(unsubscribe_token)
            await self._send_email(
                email=subscription.target,
                subject=f"Musematic status update: {event_kind}",
                body=_render_template(
                    f"{event_kind.replace('.', '_')}.txt",
                    event_kind=event_kind,
                    payload=payload,
                    unsubscribe_url=_unsubscribe_url(unsubscribe_token, payload),
                ),
            )
            return "sent", None
        if subscription.channel == "slack" and self.slack_deliverer is not None:
            alert = _Alert(
                title=f"Musematic status update: {event_kind}",
                body=str(payload.get("summary") or payload.get("title") or event_kind),
                urgency=str(payload.get("severity") or "medium"),
            )
            outcome, error = await self.slack_deliverer.send(alert, subscription.target)
            return _delivery_outcome(outcome), error
        if subscription.channel == "webhook" and self.webhook_deliverer is not None:
            webhook_id = subscription.webhook_id or uuid4()
            outcome, error, _idempotency = await self.webhook_deliverer.send_signed(
                webhook_id=webhook_id,
                event_id=event_id,
                webhook_url=subscription.target,
                payload={"event_type": event_kind, **payload},
                secret="status-page-dev-secret",
                platform_version=self.platform_version,
            )
            return _delivery_outcome(outcome), error
        return "sent", None


@dataclass(slots=True)
class _Alert:
    title: str
    body: str
    urgency: str
    id: UUID = field(default_factory=uuid4)
    alert_type: str = "status_page"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _hash_token(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def _normalise_scope(scope_components: list[str]) -> list[str]:
    return sorted({component.strip() for component in scope_components if component.strip()})


def _event_id(payload: dict[str, Any]) -> UUID:
    for key in ("event_id", "incident_id", "id", "window_id"):
        value = payload.get(key)
        if value:
            try:
                return UUID(str(value))
            except ValueError:
                continue
    return uuid4()


def _affected_components(payload: dict[str, Any]) -> list[str]:
    for key in ("components_affected", "affected_components", "scope_components", "components"):
        value = payload.get(key)
        if isinstance(value, list):
            return [str(item) for item in value]
    return []


def _unsubscribe_url(token: str, payload: dict[str, Any]) -> str:
    base_url = payload.get("public_status_base_url") or payload.get("base_url") or ""
    base = str(base_url).rstrip("/")
    return f"{base}/api/v1/public/subscribe/email/unsubscribe?token={token}"


def _user_id(current_user: dict[str, Any]) -> UUID:
    return UUID(str(current_user["sub"]))


def _optional_workspace_id(current_user: dict[str, Any]) -> UUID | None:
    value = current_user.get("workspace_id") or current_user.get("workspace")
    return UUID(str(value)) if value else None


def _my_subscription(subscription: StatusSubscription) -> MyStatusSubscription:
    return MyStatusSubscription(
        id=str(subscription.id),
        channel=subscription.channel,
        target=subscription.target,
        scope_components=subscription.scope_components,
        health=subscription.health,
        confirmed_at=subscription.confirmed_at,
        created_at=subscription.created_at,
    )


def _delivery_outcome(outcome: DeliveryOutcome) -> str:
    if outcome == DeliveryOutcome.success:
        return "sent"
    if outcome == DeliveryOutcome.timed_out:
        return "retrying"
    return "dead_lettered"


def _render_template(template_name: str, **values: Any) -> str:
    template_path = Path(__file__).with_name("email_templates") / template_name
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = "Musematic status update: {event_kind}\n\n{payload}"
    return template.format(**values)
