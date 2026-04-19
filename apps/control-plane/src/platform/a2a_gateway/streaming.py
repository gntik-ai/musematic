from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.repository import A2AGatewayRepository
from platform.a2a_gateway.schemas import A2ASSEEvent
from typing import Any


class A2ASSEStream:
    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        poll_interval_seconds: float = 0.5,
    ) -> None:
        self.session_factory = session_factory
        self.poll_interval_seconds = poll_interval_seconds

    async def event_generator(
        self,
        task_id: str,
        last_event_id: str | None = None,
    ) -> AsyncIterator[str]:
        delivered: set[str] = set()
        resume_ready = last_event_id is None
        while True:
            async with self.session_factory() as session:
                repo = A2AGatewayRepository(session)
                task = await repo.get_task_by_task_id(task_id)
                if task is None:
                    return
                events = await repo.list_task_events(task.id)
                for record in events:
                    event_id = str(record.id)
                    if not resume_ready:
                        if event_id == last_event_id:
                            resume_ready = True
                        continue
                    if event_id in delivered:
                        continue
                    payload = A2ASSEEvent(
                        task_id=task.task_id,
                        state=_state_from_action(record.action, task.a2a_state.value),
                        timestamp=record.occurred_at,
                        prompt=_extract_prompt(task.result_payload),
                        result=(
                            task.result_payload
                            if task.a2a_state is A2ATaskState.completed
                            else None
                        ),
                        error_code=task.error_code,
                    )
                    delivered.add(event_id)
                    yield (
                        f"id: {event_id}\n"
                        "event: a2a_task_event\n"
                        f"data: {payload.model_dump_json()}\n\n"
                    )
                if task.a2a_state in {
                    A2ATaskState.completed,
                    A2ATaskState.failed,
                    A2ATaskState.cancelled,
                }:
                    return
            await asyncio.sleep(self.poll_interval_seconds)


def _state_from_action(action: str, fallback: str) -> str:
    mapping = {
        "task_submitted": "submitted",
        "task_state_changed": fallback,
        "task_completed": "completed",
        "task_failed": "failed",
        "task_cancelled": "cancelled",
    }
    return mapping.get(action, fallback)


def _extract_prompt(payload: dict[str, Any] | None) -> str | None:
    if not isinstance(payload, dict):
        return None
    prompt = payload.get("prompt")
    if isinstance(prompt, str):
        return prompt
    parts = payload.get("parts")
    if isinstance(parts, list):
        for part in parts:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    return text
    return None
