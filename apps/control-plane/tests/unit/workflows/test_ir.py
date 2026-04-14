from __future__ import annotations

from platform.workflows.ir import ApprovalConfigIR, RetryConfigIR, StepIR, WorkflowIR


def test_ir_models_round_trip_nested_payloads() -> None:
    step = StepIR(
        step_id="step_a",
        step_type="approval_gate",
        input_bindings={"invoice_id": "$.invoice_id"},
        retry_config=RetryConfigIR(
            max_retries=4,
            retry_on_event_types=["failed"],
        ),
        approval_config=ApprovalConfigIR(
            required_approvers=["ops", "finance"],
            timeout_seconds=30,
            timeout_action="escalate",
        ),
        compensation_handler="undo_step_a",
        reasoning_mode="deep",
        context_budget_tokens=1024,
        parallel_group="review",
        condition_expression="$.approved == true",
    )
    workflow = WorkflowIR(
        schema_version=1,
        workflow_id="invoice-workflow",
        steps=[step],
        dag_edges=[("step_a", "step_b")],
        data_bindings=[{"target": "$.invoice_id", "source": "$.payload.id"}],
        metadata={"team": "finance"},
    )

    payload = workflow.to_dict()
    restored = WorkflowIR.from_dict(payload)

    assert payload["steps"][0]["retry_config"]["retry_on_event_types"] == ["failed"]
    assert restored.steps[0].retry_config is not None
    assert restored.steps[0].retry_config.max_retries == 4
    assert restored.steps[0].approval_config is not None
    assert restored.steps[0].approval_config.timeout_action == "escalate"
    assert restored.dag_edges == [("step_a", "step_b")]
