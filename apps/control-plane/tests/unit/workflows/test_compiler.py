from __future__ import annotations

from platform.workflows.compiler import WorkflowCompiler
from platform.workflows.exceptions import WorkflowCompilationError

import pytest


def test_compile_valid_workflow_to_ir() -> None:
    compiler = WorkflowCompiler()

    ir = compiler.compile(
        """
schema_version: 1
workflow_id: test_pipeline
steps:
  - id: fetch_invoice
    step_type: agent_task
    agent_fqn: finance.fetcher
  - id: approve_invoice
    step_type: approval_gate
    depends_on: [fetch_invoice]
    approval_config:
      required_approvers: [finance_admin]
        """.strip(),
        1,
    )

    assert ir.workflow_id == "test_pipeline"
    assert [step.step_id for step in ir.steps] == ["fetch_invoice", "approve_invoice"]
    assert ir.dag_edges == [("fetch_invoice", "approve_invoice")]


def test_compile_reports_field_level_validation_error() -> None:
    compiler = WorkflowCompiler()

    with pytest.raises(WorkflowCompilationError) as exc_info:
        compiler.compile(
            """
schema_version: 1
steps:
  - id: invalid
    step_type: agent_task
    agent_fqn: finance.fetcher
    timeout_seconds: -1
            """.strip(),
            1,
        )

    assert exc_info.value.details["path"] == "steps[0].timeout_seconds"


def test_compile_rejects_cycles_and_missing_dependencies() -> None:
    compiler = WorkflowCompiler()

    with pytest.raises(WorkflowCompilationError, match="Circular dependency detected"):
        compiler.compile(
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    depends_on: [step_b]
  - id: step_b
    step_type: agent_task
    agent_fqn: ns:b
    depends_on: [step_a]
            """.strip(),
            1,
        )

    with pytest.raises(WorkflowCompilationError, match="Undefined dependency step"):
        compiler.compile(
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    depends_on: [missing]
            """.strip(),
            1,
        )


def test_validate_compatibility_reports_active_step_breakage() -> None:
    compiler = WorkflowCompiler()
    old_ir = compiler.compile(
        """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
  - id: step_b
    step_type: tool_call
    tool_fqn: ns:tool
    depends_on: [step_a]
        """.strip(),
        1,
    )
    new_ir = compiler.compile(
        """
schema_version: 1
steps:
  - id: step_a
    step_type: tool_call
    tool_fqn: ns:tool
        """.strip(),
        1,
    )

    result = compiler.validate_compatibility(old_ir, new_ir, ["step_a", "step_b"])

    assert result.compatible is False
    assert any("step_a" in issue for issue in result.issues)
    assert any("step_b" in issue for issue in result.issues)
