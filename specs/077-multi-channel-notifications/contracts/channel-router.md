# Channel Router Contract

**Feature**: 077-multi-channel-notifications
**Module**: `apps/control-plane/src/platform/notifications/channel_router.py`

The channel router is the single fan-out point invoked by `AlertService` whenever an alert needs delivery. It replaces the current direct deliverer dispatch in `service.py:_dispatch_for_settings`.

## Service API

```python
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
    ) -> None: ...

    async def route(
        self,
        alert: UserAlert,
        recipient: User,
        *,
        workspace_id: UUID | None = None,
        severity: str = "medium",
    ) -> RoutingResult:
        """Fan out a single alert to every eligible per-user channel.

        Resolves channels, evaluates quiet hours and filters, applies DLP
        and residency, dispatches to deliverers, persists outcomes, and
        emits monitor.alerts events.

        Returns a RoutingResult with per-channel attempt records.
        """

    async def route_workspace_event(
        self,
        envelope: EventEnvelope,
        workspace_id: UUID,
    ) -> list[WebhookDispatchResult]:
        """Fan out a workspace event to every active outbound_webhook
        subscribed to envelope.event_type.
        """
```

## Routing algorithm — per-user fan-out

```
1. Read enabled, verified channel_configs for recipient where
   alert_type_filter matches alert.alert_type or is NULL.
2. If empty AND multi_channel_enabled is False:
       Fall back to legacy user_alert_settings.delivery_method path.
       Return.
3. If empty AND multi_channel_enabled is True:
       Read user_alert_settings.delivery_method as a single-channel
       fallback. Treat it as a synthetic ChannelConfig of that method.
4. For each channel_config c:
    a. If c.severity_floor is set and severity < c.severity_floor: skip.
    b. If alert.severity != "critical" AND c.quiet_hours is set
       AND now_in_zone(c.quiet_hours.timezone) ∈ [start, end]:
       skip.
    c. Run DLP scan_outbound(payload, workspace_id, c.channel_type).
       If verdict.action == "block": persist outcome=blocked, audit,
       skip.
       If verdict.action == "redact": replace payload with
       verdict.redacted_payload.
    d. If c.channel_type == "webhook":
       residency check; on fail persist outcome=residency_violation,
       skip.
    e. Dispatch via deliverers[c.channel_type].send(...).
    f. Persist alert_delivery_outcomes row with outcome.
    g. Emit monitor.alerts event "notifications.delivery.attempted".
```

## Quiet-hours evaluation

```python
def in_quiet_hours(now_utc: datetime, qh: QuietHoursConfig) -> bool:
    zone = ZoneInfo(qh.timezone)
    local = now_utc.astimezone(zone).time()
    if qh.start <= qh.end:
        return qh.start <= local < qh.end
    # crosses midnight
    return local >= qh.start or local < qh.end
```

The user's zone is taken from `users.timezone`; channel-specific override is on `channel_config.quiet_hours.timezone`.

## Critical-severity bypass

If `alert.severity == "critical"` (or whatever value is set in `notifications.quiet_hours_default_severity_bypass`), quiet-hours suppression is skipped on every channel. Severity filter (`severity_floor`) is still enforced.

## Backward-compat fallback

When `FEATURE_MULTI_CHANNEL_NOTIFICATIONS` is OFF, `route` short-circuits to the legacy `_dispatch_for_settings` path. The new code remains in the codebase but inert. When the flag flips ON, behaviour switches per request — no service restart required.

## Unit-test contract

- **CR1** — alert dispatched to all enabled, verified channels passing filter and quiet-hours.
- **CR2** — channel disabled mid-call: skipped (read-then-act consistency, not atomicity).
- **CR3** — quiet-hours window crossing midnight evaluated correctly across DST transitions (parameterized over Europe/Madrid 2026 spring-forward and 2026 fall-back).
- **CR4** — critical alerts bypass quiet hours; non-critical alerts do not.
- **CR5** — alert_type_filter excludes non-matching types.
- **CR6** — severity_floor on a channel suppresses below-floor alerts.
- **CR7** — DLP block result causes outcome `blocked` and emits audit chain entry.
- **CR8** — DLP redact result replaces payload before delivery.
- **CR9** — residency violation on a webhook channel produces outcome `residency_violation` and emits audit chain entry.
- **CR10** — flag OFF → legacy `_dispatch_for_settings` is invoked (asserted by call spy).
- **CR11** — flag ON, no per-channel rows → legacy `delivery_method` is used as a single-channel fallback.
- **CR12** — flag ON, ≥1 per-channel rows → legacy `delivery_method` is ignored.
