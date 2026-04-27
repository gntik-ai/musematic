from __future__ import annotations

from collections.abc import Awaitable, Callable
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import clear_context, set_context_from_event_envelope

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


async def run_with_event_logging_context(
    envelope: EventEnvelope,
    handler: EventHandler,
) -> None:
    tokens = set_context_from_event_envelope(envelope)
    try:
        await handler(envelope)
    finally:
        clear_context(tokens)


def with_event_logging_context(handler: EventHandler) -> EventHandler:
    async def wrapped(envelope: EventEnvelope) -> None:
        await run_with_event_logging_context(envelope, handler)

    return wrapped
