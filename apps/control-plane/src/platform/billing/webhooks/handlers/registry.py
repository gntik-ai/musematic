"""UPD-052 — webhook event-type → handler dispatch registry.

Handlers are registered per ``stripe.Event.type``. The dispatch is a thin
lookup: when no handler is registered for an event type the router returns
``ignored`` (HTTP 200) so Stripe doesn't keep retrying. Handler-side
exceptions propagate to the router which converts them to HTTP 500 to force
a retry.

The registry is intentionally module-level (a global dict). The handlers are
imported lazily from the parent package to keep cyclic-import surface
small — see :func:`build_default_registry`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from platform.billing.providers.protocol import WebhookEvent
from platform.common.events.envelope import CorrelationContext
from platform.common.events.producer import EventProducer
from platform.common.logging import get_logger
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

LOGGER = get_logger(__name__)


@dataclass(frozen=True)
class HandlerContext:
    """Per-event context handed to every handler.

    Carries the SQLAlchemy session, the Kafka producer, and the correlation
    context derived from the event for telemetry. Additional services can be
    attached via :meth:`with_extra` so individual handlers don't bloat the
    constructor.
    """

    session: AsyncSession
    producer: EventProducer | None
    correlation_ctx: CorrelationContext
    extras: dict[str, Any]

    def with_extra(self, **values: Any) -> HandlerContext:
        merged = {**self.extras, **values}
        return HandlerContext(
            session=self.session,
            producer=self.producer,
            correlation_ctx=self.correlation_ctx,
            extras=merged,
        )


HandlerFn = Callable[[WebhookEvent, HandlerContext], Awaitable[None]]


class HandlerRegistry:
    """Thin dispatch table mapping event_type → async handler."""

    def __init__(self) -> None:
        self._handlers: dict[str, HandlerFn] = {}

    def register(self, event_type: str, handler: HandlerFn) -> None:
        if event_type in self._handlers:
            LOGGER.warning(
                "billing.webhook_handler_replaced",
                event_type=event_type,
            )
        self._handlers[event_type] = handler

    def get(self, event_type: str) -> HandlerFn | None:
        return self._handlers.get(event_type)

    def event_types(self) -> list[str]:
        return sorted(self._handlers.keys())

    async def dispatch(
        self,
        event: WebhookEvent,
        context: HandlerContext,
    ) -> str:
        """Dispatch an event to its handler.

        Returns ``"processed"`` when a handler ran, ``"ignored"`` when no
        handler is registered for the event type. The router maps both to
        HTTP 200; handler exceptions are NOT caught here — the router
        converts them to 500.
        """
        handler = self._handlers.get(event.type)
        if handler is None:
            LOGGER.info(
                "billing.webhook_event_ignored",
                event_type=event.type,
                event_id=event.id,
            )
            return "ignored"
        await handler(event, context)
        return "processed"


def build_default_registry() -> HandlerRegistry:
    """Construct the registry with the canonical UPD-052 handlers wired in.

    Imports are deferred so a unit test that only needs the registry surface
    doesn't drag in the SDK and ORM modules transitively.
    """
    from platform.billing.webhooks.handlers import (
        dispute,
        invoice,
        payment_method,
        subscription,
    )

    registry = HandlerRegistry()
    registry.register("customer.subscription.created", subscription.on_created)
    registry.register("customer.subscription.updated", subscription.on_updated)
    registry.register("customer.subscription.deleted", subscription.on_deleted)
    registry.register(
        "customer.subscription.trial_will_end", subscription.on_trial_ending
    )
    registry.register("invoice.payment_succeeded", invoice.on_paid)
    registry.register("invoice.payment_failed", invoice.on_failed)
    registry.register("payment_method.attached", payment_method.on_attached)
    registry.register("charge.dispute.created", dispute.on_dispute)
    return registry
