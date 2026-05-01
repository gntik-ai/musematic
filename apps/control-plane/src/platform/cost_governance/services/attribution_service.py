from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from platform.billing.exceptions import NoActiveSubscriptionError
from platform.billing.subscriptions.resolver import SubscriptionResolver
from platform.common.config import PlatformSettings
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from platform.cost_governance.clickhouse_repository import ClickHouseCostRepository, cost_event_row
from platform.cost_governance.events import (
    CostExecutionAttributedPayload,
    CostGovernanceEventType,
    publish_cost_governance_event,
)
from platform.cost_governance.models import CostAttribution
from platform.cost_governance.repository import CostGovernanceRepository
from typing import Any
from uuid import UUID, uuid4

LOGGER = get_logger(__name__)
DECIMAL_ZERO = Decimal("0")


class AttributionService:
    def __init__(
        self,
        *,
        repository: CostGovernanceRepository,
        settings: PlatformSettings,
        clickhouse_repository: ClickHouseCostRepository | None = None,
        kafka_producer: EventProducer | None = None,
        model_catalog_service: Any | None = None,
        budget_service: Any | None = None,
        fail_open: bool = True,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.cost_settings = settings.cost_governance
        self.clickhouse_repository = clickhouse_repository
        self.kafka_producer = kafka_producer
        self.model_catalog_service = model_catalog_service
        self.budget_service = budget_service
        self.fail_open = fail_open

    async def record_step_cost(
        self,
        *,
        execution_id: UUID,
        step_id: str | None,
        workspace_id: UUID,
        agent_id: UUID | None,
        user_id: UUID | None,
        payload: dict[str, Any],
        correlation_ctx: CorrelationContext | None = None,
    ) -> CostAttribution | None:
        try:
            return await self._record_step_cost(
                execution_id=execution_id,
                step_id=step_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                user_id=user_id,
                payload=payload,
                correlation_ctx=correlation_ctx,
            )
        except Exception:
            if not self.fail_open:
                raise
            LOGGER.warning(
                "Cost attribution failed open",
                exc_info=True,
                extra={"workspace_id": str(workspace_id), "execution_id": str(execution_id)},
            )
            return None

    async def _record_step_cost(
        self,
        *,
        execution_id: UUID,
        step_id: str | None,
        workspace_id: UUID,
        agent_id: UUID | None,
        user_id: UUID | None,
        payload: dict[str, Any],
        correlation_ctx: CorrelationContext | None,
    ) -> CostAttribution:
        model_id = _string_or_none(payload.get("model_id") or payload.get("model"))
        tokens_in = _int_value(payload, "tokens_in", "input_tokens", "prompt_tokens")
        tokens_out = _int_value(payload, "tokens_out", "output_tokens", "completion_tokens")
        duration_ms = _decimal_value(payload.get("duration_ms") or payload.get("latency_ms"))
        bytes_written = _decimal_value(payload.get("bytes_written") or payload.get("storage_bytes"))
        provider = _string_or_none(payload.get("provider") or payload.get("model_provider"))
        pricing = await self._resolve_pricing(model_id, provider)
        input_rate = _decimal_value(
            payload.get("input_cost_per_1k_tokens")
            or payload.get("input_rate_per_1k")
            or pricing.get("input_cost_per_1k_tokens")
        )
        output_rate = _decimal_value(
            payload.get("output_cost_per_1k_tokens")
            or payload.get("output_rate_per_1k")
            or pricing.get("output_cost_per_1k_tokens")
        )
        model_cost = _cost_value(
            payload.get("model_cost_cents"),
            (
                (Decimal(tokens_in) * input_rate + Decimal(tokens_out) * output_rate)
                / Decimal(1000)
            ),
        )
        compute_cost = _cost_value(
            payload.get("compute_cost_cents"),
            duration_ms * Decimal(str(self.cost_settings.compute_cost_per_ms_cents)),
        )
        storage_cost = _cost_value(
            payload.get("storage_cost_cents"),
            bytes_written * Decimal(str(self.cost_settings.storage_cost_per_byte_cents)),
        )
        existing = await self.repository.get_attribution_by_execution(execution_id)
        overhead_default = (
            Decimal(str(self.cost_settings.overhead_cost_per_execution_cents))
            if existing is None
            else DECIMAL_ZERO
        )
        overhead_cost = _cost_value(
            payload.get("overhead_cost_cents"),
            overhead_default,
        )
        currency = str(payload.get("currency") or self.cost_settings.default_currency)
        origin = (
            "system_trigger"
            if user_id is None
            else str(payload.get("origin") or "user_trigger")
        )
        subscription_id: UUID | None = None
        try:
            subscription = await SubscriptionResolver(
                self.repository.session
            ).resolve_active_subscription(workspace_id)
            subscription_id = subscription.id
        except NoActiveSubscriptionError:
            subscription_id = None

        if existing is None:
            attribution = await self.repository.insert_attribution(
                execution_id=execution_id,
                step_id=step_id,
                workspace_id=workspace_id,
                agent_id=agent_id,
                user_id=user_id,
                subscription_id=subscription_id,
                origin=origin,
                model_id=model_id,
                currency=currency,
                model_cost_cents=model_cost,
                compute_cost_cents=compute_cost,
                storage_cost_cents=storage_cost,
                overhead_cost_cents=overhead_cost,
                token_counts={"tokens_in": tokens_in, "tokens_out": tokens_out},
                metadata={"source": "execution.runtime_event"},
            )
        else:
            attribution = await self.repository.insert_attribution_correction(
                existing.id,
                model_cost_cents=model_cost,
                compute_cost_cents=compute_cost,
                storage_cost_cents=storage_cost,
                overhead_cost_cents=overhead_cost,
                metadata={"source": "execution.runtime_event", "step_id": step_id},
            )

        if self.budget_service is not None:
            invalidator = getattr(self.budget_service, "invalidate_hot_counter", None)
            if callable(invalidator):
                await invalidator(workspace_id, "monthly")

        await self._enqueue_clickhouse(attribution)
        await self._emit_event(
            attribution,
            correlation_ctx
            or CorrelationContext(
                workspace_id=workspace_id,
                execution_id=execution_id,
                correlation_id=uuid4(),
            ),
        )
        return attribution

    async def record_correction(
        self,
        original_attribution_id: UUID,
        *,
        deltas: dict[str, Decimal | int | float | str],
        reason: str | None = None,
    ) -> CostAttribution:
        correction = await self.repository.insert_attribution_correction(
            original_attribution_id,
            model_cost_cents=_decimal_value(deltas.get("model_cost_cents")),
            compute_cost_cents=_decimal_value(deltas.get("compute_cost_cents")),
            storage_cost_cents=_decimal_value(deltas.get("storage_cost_cents")),
            overhead_cost_cents=_decimal_value(deltas.get("overhead_cost_cents")),
            metadata={"reason": reason or "late_arriving_cost"},
        )
        await self._enqueue_clickhouse(correction)
        return correction

    async def get_execution_cost(self, execution_id: UUID) -> dict[str, Any] | None:
        rows = await self.repository.list_execution_attributions(execution_id)
        if not rows:
            return None
        original = next((row for row in rows if row.correction_of is None), rows[0])
        totals = {
            "model_cost_cents": sum((row.model_cost_cents for row in rows), DECIMAL_ZERO),
            "compute_cost_cents": sum((row.compute_cost_cents for row in rows), DECIMAL_ZERO),
            "storage_cost_cents": sum((row.storage_cost_cents for row in rows), DECIMAL_ZERO),
            "overhead_cost_cents": sum((row.overhead_cost_cents for row in rows), DECIMAL_ZERO),
            "total_cost_cents": sum((row.total_cost_cents for row in rows), DECIMAL_ZERO),
        }
        return {"attribution": original, "corrections": rows[1:], "totals": totals}

    async def _resolve_pricing(self, model_id: str | None, provider: str | None) -> dict[str, Any]:
        if model_id is None or self.model_catalog_service is None:
            return {}
        getter = getattr(self.model_catalog_service, "get_pricing", None)
        if callable(getter):
            pricing = await getter(model_id)
            return dict(pricing or {})
        repo = getattr(self.model_catalog_service, "repository", None)
        lookup = getattr(repo, "get_entry_by_provider_model", None)
        if callable(lookup) and provider is not None:
            entry = await lookup(provider, model_id)
            if entry is None:
                return {}
            return {
                "input_cost_per_1k_tokens": getattr(entry, "input_cost_per_1k_tokens", 0),
                "output_cost_per_1k_tokens": getattr(entry, "output_cost_per_1k_tokens", 0),
            }
        return {}

    async def _enqueue_clickhouse(self, attribution: CostAttribution) -> None:
        if self.clickhouse_repository is None:
            return
        await self.clickhouse_repository.enqueue_cost_event(
            cost_event_row(
                event_id=uuid4(),
                attribution_id=attribution.id,
                execution_id=attribution.execution_id,
                workspace_id=attribution.workspace_id,
                agent_id=attribution.agent_id,
                user_id=attribution.user_id,
                model_cost_cents=attribution.model_cost_cents,
                compute_cost_cents=attribution.compute_cost_cents,
                storage_cost_cents=attribution.storage_cost_cents,
                overhead_cost_cents=attribution.overhead_cost_cents,
                total_cost_cents=attribution.total_cost_cents,
                currency=attribution.currency,
                occurred_at=attribution.created_at or datetime.now(UTC),
            )
        )

    async def _emit_event(
        self,
        attribution: CostAttribution,
        correlation_ctx: CorrelationContext,
    ) -> None:
        await publish_cost_governance_event(
            self.kafka_producer,
            CostGovernanceEventType.execution_attributed,
            CostExecutionAttributedPayload(
                attribution_id=attribution.id,
                execution_id=attribution.execution_id,
                workspace_id=attribution.workspace_id,
                agent_id=attribution.agent_id,
                user_id=attribution.user_id,
                total_cost_cents=attribution.total_cost_cents,
                currency=attribution.currency,
                attributed_at=attribution.created_at or datetime.now(UTC),
            ),
            correlation_ctx,
        )


def _string_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_value(payload: dict[str, Any], *keys: str) -> int:
    for key in keys:
        if key in payload and payload[key] is not None:
            return int(payload[key])
    return 0


def _decimal_value(value: Any) -> Decimal:
    if value is None:
        return DECIMAL_ZERO
    return Decimal(str(value))


def _cost_value(explicit: Any, fallback: Decimal) -> Decimal:
    value = _decimal_value(explicit) if explicit is not None else fallback
    return value.quantize(Decimal("0.0001"))
