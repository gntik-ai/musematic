from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from platform.execution.models import ApprovalDecision, ExecutionEventType, ExecutionStatus
from platform.execution.schemas import ApprovalDecisionRequest

from tests.integration.execution.support import create_execution, create_workflow


@pytest.mark.asyncio
async def test_execution_journal_is_append_only_and_tracks_approval_resume(
    workflow_execution_stack,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    workspace_id = uuid4()
    workflow_id = await create_workflow(
        workflow_execution_stack,
        workspace_id=workspace_id,
        name="Journal Workflow",
        yaml_source="""
schema_version: 1
steps:
  - id: approval_step
    step_type: approval_gate
    approval_config:
      required_approvers: [ops]
      timeout_seconds: 300
      timeout_action: fail
        """,
    )
    execution_id = await create_execution(
        workflow_execution_stack,
        workflow_id=workflow_id,
        workspace_id=workspace_id,
    )

    initial_journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    assert initial_journal.total == 1
    assert initial_journal.items[0].event_type == ExecutionEventType.created
    assert initial_journal.items[0].sequence == 1

    initial_state = await workflow_execution_stack.execution_service.get_execution_state(execution_id)
    assert initial_state.status == ExecutionStatus.queued

    await workflow_execution_stack.session.commit()

    async with session_factory() as mutation_session:
        with pytest.raises(DBAPIError, match="execution_events is append-only"):
            await mutation_session.execute(
                text(
                    """
                    UPDATE execution_events
                    SET event_type = 'completed'
                    WHERE execution_id = :execution_id
                    """
                ),
                {"execution_id": execution_id},
            )
            await mutation_session.flush()
        await mutation_session.rollback()

    await workflow_execution_stack.scheduler_service.tick()
    approval = await workflow_execution_stack.execution_service.record_approval_decision(
        execution_id,
        "approval_step",
        ApprovalDecisionRequest(
            decision=ApprovalDecision.approved,
            comment="ship it",
        ),
        decided_by=UUID(workflow_execution_stack.current_user["sub"]),
    )

    journal = await workflow_execution_stack.execution_service.get_journal(execution_id)
    event_types = [item.event_type for item in journal.items]
    sequences = [item.sequence for item in journal.items]

    assert approval.decision == ApprovalDecision.approved
    assert sequences == sorted(sequences)
    assert event_types == [
        ExecutionEventType.created,
        ExecutionEventType.queued,
        ExecutionEventType.waiting_for_approval,
        ExecutionEventType.approved,
        ExecutionEventType.resumed,
    ]

    resumed_event = journal.items[-1]
    assert resumed_event.step_id == "approval_step"
    assert resumed_event.payload == {"reason": "approval_granted"}

    state_after_approval = await workflow_execution_stack.execution_service.get_execution_state(
        execution_id
    )
    assert state_after_approval.status == ExecutionStatus.queued
    assert state_after_approval.completed_step_ids == ["approval_step"]
