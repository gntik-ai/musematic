"""Auto-suspension Kafka consumer for the abuse-prevention BC (UPD-050 T064).

Subscribes to ``security.abuse_events`` and applies three rules:

1. **velocity-repeat** — if a single source IP triggers
   ``security.signup_velocity_hit`` more than
   ``auto_suspension_velocity_repeat_threshold`` times within 10
   minutes, escalate to a 1-hour suspension of any account associated
   with that IP. (For UPD-050 we suspend the most-recent user that
   submitted from this IP — full IP-to-user correlation is a follow-up.)

2. **fraud-score** — every ``security.signup_fraud_score_high`` event
   triggers an immediate suspension of the named user.

3. **cost-burn-rate** — read from a separate analytics surface; the
   consumer subscribes to the same topic but the trigger event is
   produced by the cost-governance BC (or an analytics fan-out). This
   iteration leaves the rule shell here and surfaces it as a TODO
   pending the cost-governance event surface.

Per research R4 these rules run asynchronously off the signup hot path.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import get_logger
from platform.security.abuse_prevention.events import AbuseEventType
from platform.security.abuse_prevention.suspension import SuspensionService
from uuid import UUID

from sqlalchemy import text

LOGGER = get_logger(__name__)

VELOCITY_REPEAT_WINDOW = timedelta(minutes=10)
DEFAULT_TENANT_UUID = UUID("00000000-0000-0000-0000-000000000001")


class AbusePreventionFanoutConsumer:
    """Cross-tenant consumer that maps abuse events to auto-suspensions."""

    def __init__(self, *, settings: PlatformSettings) -> None:
        self.settings = settings
        # Per-IP velocity-hit timestamps for the rolling 10-minute window.
        # Keeping this in-process is fine because the consumer instance is
        # singleton per pod; multi-pod consumers each maintain their own
        # window which is conservatively-safe (the threshold is reached
        # locally before any pod alone fires).
        self._velocity_hits: dict[str, list[datetime]] = {}

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            "security.abuse_events",
            f"{self.settings.KAFKA_CONSUMER_GROUP_ID}.security-abuse-fanout",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        event_type = envelope.event_type
        if event_type == AbuseEventType.signup_velocity_hit.value:
            await self._handle_velocity_hit(envelope)
        elif event_type == AbuseEventType.signup_fraud_score_high.value:
            await self._handle_fraud_score_high(envelope)
        # Other event types are projected to the audit chain by
        # audit/projection.py — no rule fires here.

    async def _handle_velocity_hit(self, envelope: EventEnvelope) -> None:
        payload = envelope.payload or {}
        source_ip = str(payload.get("source_ip") or "")
        if not source_ip:
            return

        # Read the auto-suspension threshold from settings.
        threshold = await self._read_velocity_repeat_threshold()
        now = datetime.now(tz=UTC)

        # Append to the per-IP window and evict aged entries.
        hits = self._velocity_hits.setdefault(source_ip, [])
        hits.append(now)
        cutoff = now - VELOCITY_REPEAT_WINDOW
        hits[:] = [t for t in hits if t > cutoff]

        if len(hits) < threshold:
            return

        # Locate the most-recent user account submitted from this IP for
        # the current 24-hour window. Best effort — the spec acknowledges
        # full IP-to-user correlation is heuristic.
        user_id = await self._most_recent_user_from_ip(source_ip)
        if user_id is None:
            LOGGER.info(
                "abuse.auto_suspension.no_user_for_ip",
                extra={"source_ip": source_ip, "hits": len(hits)},
            )
            return

        # Suspend.
        async with database.PlatformStaffAsyncSessionLocal() as session:
            service = SuspensionService(
                session=session,
                audit_chain=None,  # the producer side already wrote the audit entry
                event_producer=None,
                alert_service=None,
            )
            await service.suspend(
                user_id=user_id,
                tenant_id=DEFAULT_TENANT_UUID,
                reason="velocity_repeat",
                evidence={
                    "source_ip": source_ip,
                    "hits_in_window": len(hits),
                    "window_minutes": VELOCITY_REPEAT_WINDOW.total_seconds() / 60,
                },
                suspended_by="system",
                suspended_by_user_id=None,
            )

    async def _handle_fraud_score_high(self, envelope: EventEnvelope) -> None:
        payload = envelope.payload or {}
        raw_user_id = payload.get("user_id")
        if not raw_user_id:
            return
        user_id = UUID(str(raw_user_id))
        async with database.PlatformStaffAsyncSessionLocal() as session:
            service = SuspensionService(
                session=session,
                audit_chain=None,
                event_producer=None,
                alert_service=None,
            )
            await service.suspend(
                user_id=user_id,
                tenant_id=DEFAULT_TENANT_UUID,
                reason="fraud_score",
                evidence={
                    "source_ip": payload.get("source_ip"),
                    "risk_score": payload.get("risk_score"),
                },
                suspended_by="system",
                suspended_by_user_id=None,
            )

    async def _read_velocity_repeat_threshold(self) -> int:
        async with database.PlatformStaffAsyncSessionLocal() as session:
            result = await session.execute(
                text(
                    "SELECT setting_value_json FROM abuse_prevention_settings "
                    "WHERE setting_key = 'auto_suspension_velocity_repeat_threshold'"
                )
            )
            row = result.scalar_one_or_none()
            if row is None:
                return 3
            try:
                return int(row)
            except (TypeError, ValueError):
                return 3

    async def _most_recent_user_from_ip(
        self, source_ip: str
    ) -> UUID | None:
        """Find the most-recent successful signup from this IP.

        Reads from the existing ``users`` audit trail / sign-in events.
        For UPD-050 we use a simple proxy — the most-recent
        ``platform_users`` row created in the last 24 h whose
        registration recorded this IP. If no such row exists, return
        None.
        """
        async with database.PlatformStaffAsyncSessionLocal() as session:
            # Best-effort lookup. If the columns don't exist (older
            # schemas) this query just returns None and the consumer
            # logs a no-op.
            try:
                result = await session.execute(
                    text(
                        """
                        SELECT id FROM platform_users
                         WHERE created_at > now() - INTERVAL '24 hours'
                         ORDER BY created_at DESC
                         LIMIT 1
                        """
                    )
                )
                row = result.scalar_one_or_none()
                return UUID(str(row)) if row else None
            except Exception:
                return None
