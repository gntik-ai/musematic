from __future__ import annotations

from importlib import import_module
from platform.common.config import PlatformSettings, Settings
from platform.common.config import settings as default_settings
from platform.common.events.envelope import CorrelationContext, EventEnvelope
from platform.common.events.registry import event_registry
from platform.common.exceptions import KafkaProducerError, ValidationError
from platform.common.kafka_tracing import inject_trace_context
from platform.common.tenant_context import current_tenant
from typing import Any


class EventProducer:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or default_settings
        self._producer: Any | None = None

    @classmethod
    def from_settings(cls, settings: PlatformSettings) -> EventProducer:
        return cls(settings)

    async def connect(self, brokers: str | None = None) -> None:
        if self._producer is not None:
            return
        aiokafka = import_module("aiokafka")
        producer_cls = aiokafka.AIOKafkaProducer
        self._producer = producer_cls(bootstrap_servers=brokers or self.settings.KAFKA_BROKERS)
        await self._producer.start()

    async def close(self) -> None:
        if self._producer is None:
            return
        await self._producer.stop()
        self._producer = None

    async def health_check(self) -> bool:
        try:
            await self.connect()
            return True
        except Exception:
            return False

    async def publish(
        self,
        topic: str,
        key: str,
        event_type: str,
        payload: dict[str, Any],
        correlation_ctx: CorrelationContext,
        source: str,
    ) -> None:
        payload = _tenant_enriched_payload(payload)
        correlation_ctx = _tenant_enriched_correlation(correlation_ctx)
        if not event_registry.is_registered(event_type):
            raise ValidationError("UNKNOWN_EVENT_TYPE", f"Unregistered event type: {event_type}")
        event_registry.validate(event_type, payload)
        envelope = EventEnvelope(
            event_type=event_type,
            source=source,
            correlation_context=correlation_ctx,
            payload=payload,
        )
        try:
            producer = await self._ensure_producer()
            headers = list(inject_trace_context({}).items())
            await producer.send_and_wait(
                topic,
                envelope.model_dump_json().encode("utf-8"),
                key=key.encode("utf-8"),
                headers=headers,
            )
        except Exception as exc:
            raise KafkaProducerError(str(exc)) from exc

    async def _ensure_producer(self) -> Any:
        await self.connect()
        assert self._producer is not None
        return self._producer


AsyncKafkaProducer = EventProducer


def _tenant_enriched_payload(payload: dict[str, Any]) -> dict[str, Any]:
    tenant = current_tenant.get(None)
    if tenant is None:
        return payload
    enriched = dict(payload)
    enriched.setdefault("tenant_id", str(tenant.id))
    enriched.setdefault("tenant_slug", tenant.slug)
    enriched.setdefault("tenant_kind", tenant.kind)
    return enriched


def _tenant_enriched_correlation(correlation_ctx: CorrelationContext) -> CorrelationContext:
    tenant = current_tenant.get(None)
    if tenant is None or correlation_ctx.tenant_id is not None:
        return correlation_ctx
    return correlation_ctx.model_copy(
        update={
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
            "tenant_kind": tenant.kind,
        }
    )
