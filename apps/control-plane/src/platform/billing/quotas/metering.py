from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from platform.billing.metrics import metrics
from platform.billing.plans.models import Plan, PlanVersion
from platform.billing.providers.protocol import PaymentProvider
from platform.billing.quotas.models import ProcessedEventID
from platform.billing.quotas.usage_repository import UsageRepository
from platform.billing.subscriptions.models import Subscription
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import get_logger
from typing import Any
from uuid import UUID, uuid5

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)
CONSUMER_NAME = "billing.metering"
NAMESPACE = UUID("368e86e0-a271-4e93-a956-9fd11cb55cbd")


@dataclass(frozen=True, slots=True)
class MeteringResult:
    event_id: UUID
    processed: bool
    minutes: Decimal = Decimal("0")
    overage_minutes: Decimal = Decimal("0")


class MeteringJob:
    def __init__(
        self,
        *,
        session: AsyncSession | None = None,
        settings: PlatformSettings,
        payment_provider: PaymentProvider | None = None,
        redis_client: AsyncRedisClient | None = None,
    ) -> None:
        self.session = session
        self.settings = settings
        self.payment_provider = payment_provider
        self.usage = UsageRepository(session, redis_client) if session is not None else None

    async def process_event(self, envelope: EventEnvelope) -> MeteringResult:
        if envelope.event_type != "execution.compute.end":
            return MeteringResult(event_id=_event_id(envelope), processed=False)
        if self.session is None:
            raise RuntimeError("metering session is required to process events")
        if self.usage is None:
            raise RuntimeError("metering usage repository is required to process events")

        event_id = _event_id(envelope)
        inserted = await self._mark_processed(event_id)
        if not inserted:
            return MeteringResult(event_id=event_id, processed=False)

        workspace_id = _workspace_id(envelope)
        tenant_id = envelope.correlation_context.tenant_id or _uuid(
            envelope.payload.get("tenant_id")
        )
        if tenant_id is not None:
            await self.session.execute(
                text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
                {"tenant_id": str(tenant_id)},
            )
        subscription = await SubscriptionResolver(self.session).resolve_active_subscription(
            workspace_id
        )
        plan, version = await self._plan_context(subscription)
        start_ts = _timestamp(
            envelope.payload.get("active_started_at")
            or envelope.payload.get("start_ts")
            or envelope.payload.get("started_at")
        )
        end_ts = _timestamp(
            envelope.payload.get("active_ended_at")
            or envelope.payload.get("end_ts")
            or envelope.payload.get("ended_at")
        )
        minutes = _minutes_between(start_ts, end_ts)
        post_executions = await self.usage.increment(
            subscription.id,
            subscription.current_period_start,
            "executions",
            Decimal("1"),
            False,
            workspace_id=workspace_id,
            period_end=subscription.current_period_end,
            tenant_id=subscription.tenant_id,
        )
        post_minutes = await self.usage.increment(
            subscription.id,
            subscription.current_period_start,
            "minutes",
            minutes,
            False,
            workspace_id=workspace_id,
            period_end=subscription.current_period_end,
            tenant_id=subscription.tenant_id,
        )
        overage_minutes = _new_overage_minutes(
            previous=post_minutes - minutes,
            current=post_minutes,
            included_limit=Decimal(version.minutes_per_month),
            overage_price=Decimal(version.overage_price_per_minute),
        )
        if overage_minutes > 0:
            await self.usage.increment(
                subscription.id,
                subscription.current_period_start,
                "minutes",
                overage_minutes,
                True,
                workspace_id=workspace_id,
                period_end=subscription.current_period_end,
                tenant_id=subscription.tenant_id,
            )
            if self.payment_provider is not None:
                await self.payment_provider.report_usage(
                    subscription.stripe_subscription_id or f"stub_sub_{subscription.id.hex[:24]}",
                    overage_minutes,
                    str(event_id),
                )
        LOGGER.info(
            "billing.metering.processed",
            event_id=str(event_id),
            workspace_id=str(workspace_id),
            plan_tier=plan.tier,
            executions=str(post_executions),
            minutes=str(post_minutes),
            overage_minutes=str(overage_minutes),
        )
        metrics.record_metering_lag(
            max((datetime.now(UTC) - envelope.occurred_at).total_seconds(), 0.0)
        )
        return MeteringResult(
            event_id=event_id,
            processed=True,
            minutes=minutes,
            overage_minutes=overage_minutes,
        )

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            "execution.compute.end",
            f"{self.settings.kafka.consumer_group}.billing-metering",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        async with database.AsyncSessionLocal() as session:
            job = MeteringJob(
                session=session,
                settings=self.settings,
                payment_provider=self.payment_provider,
            )
            try:
                await job.process_event(envelope)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Billing metering event failed")
                raise

    async def _mark_processed(self, event_id: UUID) -> bool:
        statement = (
            insert(ProcessedEventID)
            .values(event_id=event_id, consumer_name=CONSUMER_NAME)
            .on_conflict_do_nothing(index_elements=[ProcessedEventID.event_id])
            .returning(ProcessedEventID.event_id)
        )
        result = await self.session.execute(statement)
        await self.session.flush()
        return result.scalar_one_or_none() is not None

    async def _plan_context(self, subscription: Subscription) -> tuple[Plan, PlanVersion]:
        result = await self.session.execute(
            select(Plan, PlanVersion)
            .join(PlanVersion, PlanVersion.plan_id == Plan.id)
            .where(
                Plan.id == subscription.plan_id,
                PlanVersion.plan_id == subscription.plan_id,
                PlanVersion.version == subscription.plan_version,
            )
        )
        return result.one()


def _event_id(envelope: EventEnvelope) -> UUID:
    raw = (
        envelope.payload.get("event_id")
        or envelope.payload.get("execution_event_id")
        or envelope.correlation_context.execution_id
        or envelope.payload.get("execution_id")
        or envelope.correlation_context.correlation_id
    )
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except ValueError:
        return uuid5(NAMESPACE, str(raw))


def _workspace_id(envelope: EventEnvelope) -> UUID:
    workspace_id = envelope.correlation_context.workspace_id or _uuid(
        envelope.payload.get("workspace_id")
    )
    if workspace_id is None:
        raise ValueError("execution.compute.end missing workspace_id")
    return workspace_id


def _uuid(value: Any) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if value is None:
        return None
    return UUID(str(value))


def _timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    if value is None:
        raise ValueError("execution.compute.end missing active compute timestamp")
    raw = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _minutes_between(start_ts: datetime, end_ts: datetime) -> Decimal:
    seconds = max((end_ts - start_ts).total_seconds(), 0.0)
    minutes = Decimal(str(seconds)) / Decimal("60")
    return minutes.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _new_overage_minutes(
    *,
    previous: Decimal,
    current: Decimal,
    included_limit: Decimal,
    overage_price: Decimal,
) -> Decimal:
    if included_limit <= 0 or overage_price <= 0:
        return Decimal("0")
    previous_overage = max(previous - included_limit, Decimal("0"))
    current_overage = max(current - included_limit, Decimal("0"))
    return max(current_overage - previous_overage, Decimal("0")).quantize(
        Decimal("0.0001"),
        rounding=ROUND_HALF_UP,
    )
