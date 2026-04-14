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


@pytest.mark.parametrize(
    ("yaml_source", "path", "message"),
    [
        ("[1, 2, 3]", None, "deserialize to an object"),
        (
            """
schema_version: 2
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            "schema_version",
            "must equal 1",
        ),
        (
            """
schema_version: 1
workflow_id: "  "
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            "workflow_id",
            "non-empty string",
        ),
        (
            """
schema_version: 1
steps: {}
            """.strip(),
            "steps",
            "must be an array",
        ),
        (
            """
schema_version: 1
steps: []
            """.strip(),
            "steps",
            "at least one step",
        ),
        (
            """
schema_version: 1
unexpected: true
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            "unexpected",
            "Unexpected field",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: tool_call
            """.strip(),
            "steps[0].tool_fqn",
            "non-empty string",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    input_bindings: []
            """.strip(),
            "steps[0].input_bindings",
            "must be an object",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    output_schema: []
            """.strip(),
            "steps[0].output_schema",
            "object or null",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: approval_gate
            """.strip(),
            "steps[0].approval_config",
            "approval_config is required",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    metadata: "bad"
            """.strip(),
            "steps[0].metadata",
            "Unexpected field",
        ),
        (
            """
schema_version: 1
data_bindings: "bad"
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            "data_bindings",
            "must be an array",
        ),
        (
            """
schema_version: 1
metadata: "bad"
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            "metadata",
            "must be an object",
        ),
    ],
)
def test_compile_rejects_invalid_root_and_step_shapes(
    yaml_source: str,
    path: str | None,
    message: str,
) -> None:
    compiler = WorkflowCompiler()

    with pytest.raises(WorkflowCompilationError, match=message) as exc_info:
        compiler.compile(yaml_source, 1)

    if path is not None:
        assert exc_info.value.details["path"] == path


@pytest.mark.parametrize(
    ("yaml_source", "path", "message"),
    [
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: unknown
    agent_fqn: ns:a
            """.strip(),
            "steps[0].step_type",
            "Unsupported step_type",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    depends_on: step_b
            """.strip(),
            "steps[0].depends_on",
            "depends_on must be an array",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    depends_on: [""]
            """.strip(),
            "steps[0].depends_on[0]",
            "non-empty strings",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    depends_on: [step_b, step_b]
  - id: step_b
    step_type: tool_call
    tool_fqn: ns:tool
            """.strip(),
            "steps[0].depends_on[1]",
            "must be unique",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    input_bindings:
      3: $.value
            """.strip(),
            "steps[0].input_bindings",
            "keys must be strings",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    input_bindings:
      field: 3
            """.strip(),
            "steps[0].input_bindings.field",
            "values must be strings",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    retry_config: []
            """.strip(),
            "steps[0].retry_config",
            "object or null",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    retry_config:
      backoff_strategy: jitter
            """.strip(),
            "steps[0].retry_config.backoff_strategy",
            "Unsupported backoff_strategy",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    retry_config:
      retry_on_event_types: failed
            """.strip(),
            "steps[0].retry_config.retry_on_event_types",
            "must be an array",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    retry_config:
      retry_on_event_types: [failed, 2]
            """.strip(),
            "steps[0].retry_config.retry_on_event_types[1]",
            "must be strings",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    retry_config:
      base_delay_seconds: true
            """.strip(),
            "steps[0].retry_config.base_delay_seconds",
            "must be a number",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    retry_config:
      max_delay_seconds: -1
            """.strip(),
            "steps[0].retry_config.max_delay_seconds",
            "greater than or equal to 0.0",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: approval_gate
    approval_config: bad
            """.strip(),
            "steps[0].approval_config",
            "object or null",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: approval_gate
    approval_config:
      required_approvers: []
            """.strip(),
            "steps[0].approval_config.required_approvers",
            "non-empty array",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: approval_gate
    approval_config:
      required_approvers: [ops, ""]
            """.strip(),
            "steps[0].approval_config.required_approvers[1]",
            "non-empty strings",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: approval_gate
    approval_config:
      required_approvers: [ops]
      timeout_action: later
            """.strip(),
            "steps[0].approval_config.timeout_action",
            "Unsupported timeout_action",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: 7
            """.strip(),
            "steps[0].agent_fqn",
            "must be a string or null",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    context_budget_tokens: 0
            """.strip(),
            "steps[0].context_budget_tokens",
            "greater than or equal to 1",
        ),
        (
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    condition_expression: 8
            """.strip(),
            "steps[0].condition_expression",
            "must be a string or null",
        ),
    ],
)
def test_compile_rejects_invalid_nested_step_configuration(
    yaml_source: str,
    path: str,
    message: str,
) -> None:
    compiler = WorkflowCompiler()

    with pytest.raises(WorkflowCompilationError, match=message) as exc_info:
        compiler.compile(yaml_source, 1)

    assert exc_info.value.details["path"] == path


def test_compile_rejects_bad_yaml_and_schema_files(tmp_path) -> None:
    compiler = WorkflowCompiler(schema_root=tmp_path)

    with pytest.raises(WorkflowCompilationError, match="Failed to parse workflow YAML"):
        compiler.compile("schema_version: [", 1)

    with pytest.raises(WorkflowCompilationError, match="not supported"):
        compiler.compile(
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            1,
        )

    (tmp_path / "v1.json").write_text("[]", encoding="utf-8")
    with pytest.raises(WorkflowCompilationError, match="contain an object schema"):
        compiler.compile(
            """
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
            """.strip(),
            1,
        )


def test_compiler_covers_optional_helpers_and_dependency_none_branch() -> None:
    compiler = WorkflowCompiler()

    ir = compiler.compile(
        """
schema_version: 1
workflow_id: helper-workflow
data_bindings:
  - source: $.payload.id
    target: $.invoice_id
metadata:
  team: ops
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ns:a
    depends_on: null
    retry_config:
      max_retries: 2
      backoff_strategy: linear
      base_delay_seconds: 1.5
      max_delay_seconds: 10
      retry_on_event_types: [failed]
    approval_config:
      required_approvers: [ops]
      timeout_seconds: 10
      timeout_action: fail
    compensation_handler: undo_step_a
    reasoning_mode: deep
    context_budget_tokens: 512
    parallel_group: alpha
    condition_expression: $.ready == true
            """.strip(),
        1,
    )

    assert ir.workflow_id == "helper-workflow"
    assert ir.steps[0].retry_config is not None
    assert ir.steps[0].retry_config.backoff_strategy == "linear"
    assert ir.steps[0].approval_config is not None
    assert ir.steps[0].approval_config.timeout_seconds == 10
    assert WorkflowCompiler._format_path(["steps", 0, "id"]) == "steps[0].id"
    assert WorkflowCompiler._optional_str("  value  ") == "value"
    assert WorkflowCompiler._optional_str("  ") is None
