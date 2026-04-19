from __future__ import annotations

from platform.a2a_gateway.models import A2ATaskState
from platform.a2a_gateway.streaming import A2ASSEStream, _extract_prompt, _state_from_action

import pytest
from tests.a2a_gateway_support import FakeA2ARepository, build_audit_record, build_task


class _SessionContext:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


@pytest.mark.asyncio
async def test_event_generator_streams_events_and_resumes_from_last_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task = build_task(
        a2a_state=A2ATaskState.completed,
        result_payload={"role": "agent", "parts": [{"type": "text", "text": "done"}]},
    )
    first = build_audit_record(task_id=task.id, action="task_submitted")
    second = build_audit_record(task_id=task.id, action="task_completed")
    repo = FakeA2ARepository()
    repo.tasks[task.task_id] = task
    repo.audits[:] = [first, second]
    monkeypatch.setattr("platform.a2a_gateway.streaming.A2AGatewayRepository", lambda session: repo)

    stream = A2ASSEStream(session_factory=_SessionContext, poll_interval_seconds=0)
    events = [item async for item in stream.event_generator(task.task_id)]
    resumed = [
        item async for item in stream.event_generator(task.task_id, last_event_id=str(first.id))
    ]

    assert len(events) == 2
    assert f"id: {first.id}" in events[0]
    assert '"state":"completed"' in events[1]
    assert resumed == [events[1]]


def test_streaming_helper_functions_cover_prompt_and_state_mapping() -> None:
    assert _state_from_action("task_cancelled", "working") == "cancelled"
    assert _state_from_action("task_state_changed", "input_required") == "input_required"
    assert _extract_prompt({"prompt": "Need more input"}) == "Need more input"
    assert (
        _extract_prompt({"parts": [{"type": "text", "text": "Fallback prompt"}]})
        == "Fallback prompt"
    )
    assert _extract_prompt(None) is None


@pytest.mark.asyncio
async def test_event_generator_waits_for_terminal_state_and_skips_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_task = build_task(a2a_state=A2ATaskState.working)
    first = build_audit_record(task_id=first_task.id, action="task_submitted")
    second = build_audit_record(task_id=first_task.id, action="task_completed")

    class RepoSequence:
        def __init__(self) -> None:
            self.calls = 0

        async def get_task_by_task_id(self, task_id: str):
            del task_id
            self.calls += 1
            if self.calls == 1:
                return first_task
            completed = build_task(
                id=first_task.id,
                task_id=first_task.task_id,
                a2a_state=A2ATaskState.completed,
                result_payload={"role": "agent", "parts": [{"type": "text", "text": "done"}]},
            )
            return completed

        async def list_task_events(self, task_db_id):
            del task_db_id
            if self.calls == 1:
                return [first]
            return [first, second]

    repo = RepoSequence()
    monkeypatch.setattr(
        "platform.a2a_gateway.streaming.A2AGatewayRepository",
        lambda session: repo,
    )
    sleep_calls: list[float] = []

    async def _sleep(interval: float) -> None:
        sleep_calls.append(interval)

    monkeypatch.setattr("platform.a2a_gateway.streaming.asyncio.sleep", _sleep)

    stream = A2ASSEStream(session_factory=_SessionContext, poll_interval_seconds=0.01)
    events = [item async for item in stream.event_generator(first_task.task_id)]

    assert len(events) == 2
    assert events[0].count("id: ") == 1
    assert f"id: {first.id}" in events[0]
    assert f"id: {second.id}" in events[1]
    assert sleep_calls == [0.01]


def test_streaming_extract_prompt_ignores_non_text_parts() -> None:
    assert _extract_prompt({"parts": [{"type": "image", "text": 1}]}) is None
