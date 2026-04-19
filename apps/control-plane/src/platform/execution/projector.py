from __future__ import annotations

import logging
from platform.execution.models import ExecutionCheckpoint, ExecutionEvent, ExecutionStatus
from platform.execution.schemas import ExecutionStateResponse
from typing import Any

LOGGER = logging.getLogger(__name__)


class ExecutionProjector:
    """Project execution state."""

    def project_state(
        self,
        events: list[ExecutionEvent],
        checkpoint: ExecutionCheckpoint | None = None,
    ) -> ExecutionStateResponse:
        """Project execution state from recorded events."""
        state = ExecutionStateResponse(
            execution_id=events[-1].execution_id if events else checkpoint.execution_id,  # type: ignore[union-attr]
            status=ExecutionStatus.queued,
            completed_step_ids=list(checkpoint.completed_step_ids) if checkpoint else [],
            active_step_ids=list(checkpoint.active_step_ids) if checkpoint else [],
            pending_step_ids=list(checkpoint.pending_step_ids) if checkpoint else [],
            step_results=dict(checkpoint.step_results) if checkpoint else {},
            last_event_sequence=checkpoint.last_event_sequence if checkpoint else 0,
        )
        if checkpoint is not None and checkpoint.execution_data:
            state.step_results.setdefault("_execution_data", dict(checkpoint.execution_data))

        for event in events:
            state.execution_id = event.execution_id
            state.last_event_sequence = event.sequence
            handler = getattr(self, f"_apply_{event.event_type.value}", None)
            if callable(handler):
                handler(state, event)
            else:
                LOGGER.warning("Ignoring unknown execution event type: %s", event.event_type.value)
        return state

    def _apply_created(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        payload = event.payload
        all_step_ids = [str(item) for item in payload.get("all_step_ids", [])]
        precompleted = [str(item) for item in payload.get("precompleted_step_ids", [])]
        state.completed_step_ids = self._dedupe(precompleted)
        state.active_step_ids = []
        state.pending_step_ids = [
            step_id for step_id in all_step_ids if step_id not in precompleted
        ]
        state.step_results.update(dict(payload.get("step_results", {})))
        workflow_version_id = payload.get("workflow_version_id")
        if workflow_version_id is not None:
            state.workflow_version_id = workflow_version_id
        state.status = ExecutionStatus.queued

    def _apply_queued(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        del event
        state.status = ExecutionStatus.queued

    def _apply_dispatched(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._move_to_active(state, event.step_id)
        state.status = ExecutionStatus.running

    def _apply_runtime_started(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._move_to_active(state, event.step_id)
        state.status = ExecutionStatus.running

    def _apply_sandbox_requested(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        self._move_to_active(state, event.step_id)
        state.status = ExecutionStatus.running

    def _apply_waiting_for_approval(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        self._move_to_active(state, event.step_id)
        state.status = ExecutionStatus.waiting_for_approval

    def _apply_approved(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._remove_active(state, event.step_id)
        state.status = ExecutionStatus.running
        if event.step_id is not None:
            self._mark_completed(state, event.step_id, event.payload)

    def _apply_rejected(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._remove_active(state, event.step_id)
        state.status = ExecutionStatus.failed
        if event.step_id is not None:
            state.step_results[event.step_id] = {"status": "rejected", **dict(event.payload)}

    def _apply_approval_timed_out(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        self._remove_active(state, event.step_id)
        timeout_action = event.payload.get("timeout_action", "fail")
        state.status = (
            ExecutionStatus.failed if timeout_action == "fail" else ExecutionStatus.running
        )
        if event.step_id is not None:
            state.step_results[event.step_id] = {
                "status": "approval_timed_out",
                **dict(event.payload),
            }

    def _apply_resumed(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        del event
        state.status = ExecutionStatus.queued

    def _apply_retried(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._move_to_active(state, event.step_id)
        state.status = ExecutionStatus.running

    def _apply_completed(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        if event.step_id is not None:
            self._mark_completed(state, event.step_id, event.payload)
        if event.payload.get("execution_completed") is True:
            state.status = ExecutionStatus.completed
        elif state.status != ExecutionStatus.completed:
            state.status = ExecutionStatus.running

    def _apply_failed(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._remove_active(state, event.step_id)
        if event.step_id is not None:
            state.step_results[event.step_id] = {"status": "failed", **dict(event.payload)}
        state.status = ExecutionStatus.failed

    def _apply_canceled(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        self._remove_active(state, event.step_id)
        state.status = ExecutionStatus.canceled

    def _apply_compensated(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        if event.step_id is not None:
            state.step_results[event.step_id] = {"status": "compensated", **dict(event.payload)}
        state.status = ExecutionStatus.running

    def _apply_compensation_failed(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        if event.step_id is not None:
            state.step_results[event.step_id] = {
                "status": "compensation_failed",
                **dict(event.payload),
            }
        state.status = ExecutionStatus.failed

    def _apply_hot_changed(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        workflow_version_id = event.payload.get("new_version_id")
        if workflow_version_id is not None:
            state.workflow_version_id = workflow_version_id

    def _apply_reasoning_trace_emitted(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        del state, event

    def _apply_self_correction_started(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        del state, event

    def _apply_self_correction_converged(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        del state, event

    def _apply_context_assembled(
        self, state: ExecutionStateResponse, event: ExecutionEvent
    ) -> None:
        if event.step_id is not None:
            state.step_results.setdefault(event.step_id, {}).update({"context": event.payload})

    def _apply_reprioritized(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        state.step_results.setdefault("_reprioritization", []).append(dict(event.payload))

    def _apply_rolled_back(self, state: ExecutionStateResponse, event: ExecutionEvent) -> None:
        payload = dict(event.payload)
        state.completed_step_ids = self._dedupe(
            [str(item) for item in payload.get("completed_step_ids", [])]
        )
        state.pending_step_ids = self._dedupe(
            [str(item) for item in payload.get("pending_step_ids", [])]
        )
        state.active_step_ids = self._dedupe(
            [str(item) for item in payload.get("active_step_ids", [])]
        )
        state.step_results = dict(payload.get("step_results", {}))
        workflow_version_id = payload.get("workflow_version_id")
        if workflow_version_id is not None:
            state.workflow_version_id = workflow_version_id
        state.status = ExecutionStatus.rolled_back

    @staticmethod
    def _dedupe(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            if value not in seen:
                seen.add(value)
                ordered.append(value)
        return ordered

    def _move_to_active(self, state: ExecutionStateResponse, step_id: str | None) -> None:
        if step_id is None:
            return
        if step_id not in state.active_step_ids:
            state.active_step_ids.append(step_id)
        if step_id in state.pending_step_ids:
            state.pending_step_ids.remove(step_id)

    def _remove_active(self, state: ExecutionStateResponse, step_id: str | None) -> None:
        if step_id is None:
            return
        if step_id in state.active_step_ids:
            state.active_step_ids.remove(step_id)

    def _mark_completed(
        self,
        state: ExecutionStateResponse,
        step_id: str,
        payload: dict[str, Any],
    ) -> None:
        self._remove_active(state, step_id)
        if step_id in state.pending_step_ids:
            state.pending_step_ids.remove(step_id)
        if step_id not in state.completed_step_ids:
            state.completed_step_ids.append(step_id)
        result_payload = dict(payload)
        result_payload.setdefault("status", "completed")
        state.step_results[step_id] = result_payload
