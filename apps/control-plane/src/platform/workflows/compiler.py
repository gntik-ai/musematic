from __future__ import annotations

import json
from pathlib import Path
from platform.workflows.exceptions import WorkflowCompilationError
from platform.workflows.ir import ApprovalConfigIR, RetryConfigIR, StepIR, WorkflowIR
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:
    from platform.execution.schemas import HotChangeCompatibilityResult


class WorkflowCompiler:
    def __init__(self, schema_root: Path | None = None) -> None:
        self.schema_root = schema_root or Path(__file__).resolve().parent / "schemas"

    def compile(self, yaml_source: str, schema_version: int) -> WorkflowIR:
        try:
            payload = yaml.safe_load(yaml_source) or {}
        except yaml.YAMLError as exc:
            raise WorkflowCompilationError(
                f"Failed to parse workflow YAML: {exc}",
                code="WORKFLOW_YAML_INVALID",
            ) from exc
        if not isinstance(payload, dict):
            raise WorkflowCompilationError("Workflow YAML must deserialize to an object")

        self._load_schema(schema_version)
        self._validate_payload(payload, schema_version)

        steps_payload = payload.get("steps", [])
        if not isinstance(steps_payload, list):
            raise WorkflowCompilationError("Workflow steps must be an array", path="steps")
        step_ids = [str(item["id"]) for item in steps_payload]
        if len(step_ids) != len(set(step_ids)):
            raise WorkflowCompilationError(
                "Workflow step ids must be unique",
                path="steps",
                code="WORKFLOW_DUPLICATE_STEP",
            )

        dag_edges = self._build_dag_edges(steps_payload)
        self._assert_acyclic(step_ids, dag_edges)

        steps = [self._build_step_ir(item) for item in steps_payload]
        return WorkflowIR(
            schema_version=schema_version,
            workflow_id=str(payload.get("workflow_id") or payload.get("name") or "workflow"),
            steps=steps,
            dag_edges=dag_edges,
            data_bindings=list(payload.get("data_bindings", [])),
            metadata=dict(payload.get("metadata", {})),
        )

    def validate_compatibility(
        self,
        old_ir: WorkflowIR,
        new_ir: WorkflowIR,
        active_step_ids: list[str],
    ) -> HotChangeCompatibilityResult:
        from platform.execution.schemas import HotChangeCompatibilityResult

        old_map = {step.step_id: step for step in old_ir.steps}
        new_map = {step.step_id: step for step in new_ir.steps}
        issues: list[str] = []
        for step_id in active_step_ids:
            old_step = old_map.get(step_id)
            new_step = new_map.get(step_id)
            if old_step is None:
                continue
            if new_step is None:
                issues.append(f"Active step '{step_id}' was removed")
                continue
            if old_step.step_type != new_step.step_type:
                issues.append(f"Active step '{step_id}' changed type")
            if old_step.agent_fqn != new_step.agent_fqn:
                issues.append(f"Active step '{step_id}' changed agent assignment")
            if old_step.tool_fqn != new_step.tool_fqn:
                issues.append(f"Active step '{step_id}' changed tool assignment")
            if (old_step.input_bindings or {}) != (new_step.input_bindings or {}):
                issues.append(f"Active step '{step_id}' changed input bindings")
        return HotChangeCompatibilityResult(
            compatible=not issues,
            issues=issues,
            active_step_ids=active_step_ids,
        )

    def _load_schema(self, schema_version: int) -> dict[str, Any]:
        schema_path = self.schema_root / f"v{schema_version}.json"
        if not schema_path.exists():
            raise WorkflowCompilationError(
                f"Workflow schema version {schema_version} is not supported",
                path="schema_version",
            )
        payload = json.loads(schema_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise WorkflowCompilationError("Workflow schema file must contain an object schema")
        return payload

    def _validate_payload(self, payload: dict[str, Any], schema_version: int) -> None:
        allowed_root_keys = {
            "schema_version",
            "workflow_id",
            "steps",
            "data_bindings",
            "metadata",
        }
        self._assert_allowed_keys(payload, allowed_root_keys, path="")
        self._require_int(payload, "schema_version", path="schema_version", minimum=1)
        if int(payload["schema_version"]) != schema_version:
            raise WorkflowCompilationError(
                f"Workflow schema_version must equal {schema_version}",
                path="schema_version",
                value=payload["schema_version"],
                code="WORKFLOW_SCHEMA_INVALID",
            )
        if "workflow_id" in payload:
            self._require_non_empty_string(
                payload,
                "workflow_id",
                path="workflow_id",
            )
        steps = payload.get("steps")
        if not isinstance(steps, list):
            raise WorkflowCompilationError(
                "Workflow steps must be an array",
                path="steps",
                value=steps,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        if not steps:
            raise WorkflowCompilationError(
                "Workflow must declare at least one step",
                path="steps",
                value=steps,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        for index, step in enumerate(steps):
            self._validate_step(step, index)
        data_bindings = payload.get("data_bindings")
        if data_bindings is not None and not isinstance(data_bindings, list):
            raise WorkflowCompilationError(
                "data_bindings must be an array",
                path="data_bindings",
                value=data_bindings,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        metadata = payload.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise WorkflowCompilationError(
                "metadata must be an object",
                path="metadata",
                value=metadata,
                code="WORKFLOW_SCHEMA_INVALID",
            )

    def _validate_step(self, step: Any, index: int) -> None:
        path = f"steps[{index}]"
        if not isinstance(step, dict):
            raise WorkflowCompilationError(
                "Workflow steps must be objects",
                path=path,
                value=step,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        allowed_step_keys = {
            "id",
            "step_type",
            "agent_fqn",
            "tool_fqn",
            "depends_on",
            "input_bindings",
            "output_schema",
            "retry_config",
            "timeout_seconds",
            "compensation_handler",
            "approval_config",
            "reasoning_mode",
            "context_budget_tokens",
            "parallel_group",
            "condition_expression",
        }
        self._assert_allowed_keys(step, allowed_step_keys, path=path)
        self._require_non_empty_string(step, "id", path=f"{path}.id")
        step_type = self._require_non_empty_string(step, "step_type", path=f"{path}.step_type")
        allowed_types = {
            "agent_task",
            "tool_call",
            "approval_gate",
            "parallel_fork",
            "parallel_join",
            "conditional",
        }
        if step_type not in allowed_types:
            raise WorkflowCompilationError(
                f"Unsupported step_type '{step_type}'",
                path=f"{path}.step_type",
                value=step_type,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        self._validate_optional_string(step, "agent_fqn", path=f"{path}.agent_fqn")
        self._validate_optional_string(step, "tool_fqn", path=f"{path}.tool_fqn")
        if step_type == "agent_task":
            self._require_non_empty_string(step, "agent_fqn", path=f"{path}.agent_fqn")
        if step_type == "tool_call":
            self._require_non_empty_string(step, "tool_fqn", path=f"{path}.tool_fqn")
        self._validate_depends_on(step.get("depends_on"), path=f"{path}.depends_on")
        self._validate_input_bindings(step.get("input_bindings"), path=f"{path}.input_bindings")
        output_schema = step.get("output_schema")
        if output_schema is not None and not isinstance(output_schema, dict):
            raise WorkflowCompilationError(
                "output_schema must be an object or null",
                path=f"{path}.output_schema",
                value=output_schema,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        self._validate_retry_config(step.get("retry_config"), path=f"{path}.retry_config")
        if "timeout_seconds" in step:
            self._require_int(step, "timeout_seconds", path=f"{path}.timeout_seconds", minimum=1)
        self._validate_optional_string(
            step,
            "compensation_handler",
            path=f"{path}.compensation_handler",
        )
        self._validate_approval_config(step.get("approval_config"), path=f"{path}.approval_config")
        if step_type == "approval_gate" and not isinstance(step.get("approval_config"), dict):
            raise WorkflowCompilationError(
                "approval_config is required for approval_gate steps",
                path=f"{path}.approval_config",
                value=step.get("approval_config"),
                code="WORKFLOW_SCHEMA_INVALID",
            )
        self._validate_optional_string(step, "reasoning_mode", path=f"{path}.reasoning_mode")
        if "context_budget_tokens" in step and step.get("context_budget_tokens") is not None:
            self._require_int(
                step,
                "context_budget_tokens",
                path=f"{path}.context_budget_tokens",
                minimum=1,
            )
        self._validate_optional_string(step, "parallel_group", path=f"{path}.parallel_group")
        self._validate_optional_string(
            step,
            "condition_expression",
            path=f"{path}.condition_expression",
        )

    def _validate_depends_on(self, value: Any, *, path: str) -> None:
        if value is None:
            return
        if not isinstance(value, list):
            raise WorkflowCompilationError(
                "depends_on must be an array of step ids",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        seen: set[str] = set()
        for index, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                raise WorkflowCompilationError(
                    "depends_on items must be non-empty strings",
                    path=f"{path}[{index}]",
                    value=item,
                    code="WORKFLOW_SCHEMA_INVALID",
                )
            if item in seen:
                raise WorkflowCompilationError(
                    "depends_on items must be unique",
                    path=f"{path}[{index}]",
                    value=item,
                    code="WORKFLOW_SCHEMA_INVALID",
                )
            seen.add(item)

    def _validate_input_bindings(self, value: Any, *, path: str) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            raise WorkflowCompilationError(
                "input_bindings must be an object",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        for key, item in value.items():
            if not isinstance(key, str):
                raise WorkflowCompilationError(
                    "input_bindings keys must be strings",
                    path=path,
                    value=key,
                    code="WORKFLOW_SCHEMA_INVALID",
                )
            if not isinstance(item, str):
                raise WorkflowCompilationError(
                    "input_bindings values must be strings",
                    path=f"{path}.{key}",
                    value=item,
                    code="WORKFLOW_SCHEMA_INVALID",
                )

    def _validate_retry_config(self, value: Any, *, path: str) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            raise WorkflowCompilationError(
                "retry_config must be an object or null",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        allowed_keys = {
            "max_retries",
            "backoff_strategy",
            "base_delay_seconds",
            "max_delay_seconds",
            "retry_on_event_types",
        }
        self._assert_allowed_keys(value, allowed_keys, path=path)
        if "max_retries" in value:
            self._require_int(value, "max_retries", path=f"{path}.max_retries", minimum=0)
        if "backoff_strategy" in value:
            strategy = self._require_non_empty_string(
                value,
                "backoff_strategy",
                path=f"{path}.backoff_strategy",
            )
            if strategy not in {"fixed", "exponential", "linear"}:
                raise WorkflowCompilationError(
                    f"Unsupported backoff_strategy '{strategy}'",
                    path=f"{path}.backoff_strategy",
                    value=strategy,
                    code="WORKFLOW_SCHEMA_INVALID",
                )
        if "base_delay_seconds" in value:
            self._require_number(
                value,
                "base_delay_seconds",
                path=f"{path}.base_delay_seconds",
                minimum=0.0,
            )
        if "max_delay_seconds" in value:
            self._require_number(
                value,
                "max_delay_seconds",
                path=f"{path}.max_delay_seconds",
                minimum=0.0,
            )
        retry_on = value.get("retry_on_event_types")
        if retry_on is not None:
            if not isinstance(retry_on, list):
                raise WorkflowCompilationError(
                    "retry_on_event_types must be an array",
                    path=f"{path}.retry_on_event_types",
                    value=retry_on,
                    code="WORKFLOW_SCHEMA_INVALID",
                )
            for index, item in enumerate(retry_on):
                if not isinstance(item, str):
                    raise WorkflowCompilationError(
                        "retry_on_event_types items must be strings",
                        path=f"{path}.retry_on_event_types[{index}]",
                        value=item,
                        code="WORKFLOW_SCHEMA_INVALID",
                    )

    def _validate_approval_config(self, value: Any, *, path: str) -> None:
        if value is None:
            return
        if not isinstance(value, dict):
            raise WorkflowCompilationError(
                "approval_config must be an object or null",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        allowed_keys = {"required_approvers", "timeout_seconds", "timeout_action"}
        self._assert_allowed_keys(value, allowed_keys, path=path)
        approvers = value.get("required_approvers")
        if not isinstance(approvers, list) or not approvers:
            raise WorkflowCompilationError(
                "required_approvers must be a non-empty array",
                path=f"{path}.required_approvers",
                value=approvers,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        for index, item in enumerate(approvers):
            if not isinstance(item, str) or not item.strip():
                raise WorkflowCompilationError(
                    "required_approvers items must be non-empty strings",
                    path=f"{path}.required_approvers[{index}]",
                    value=item,
                    code="WORKFLOW_SCHEMA_INVALID",
                )
        if "timeout_seconds" in value:
            self._require_int(value, "timeout_seconds", path=f"{path}.timeout_seconds", minimum=1)
        if "timeout_action" in value:
            action = self._require_non_empty_string(
                value,
                "timeout_action",
                path=f"{path}.timeout_action",
            )
            if action not in {"fail", "skip", "escalate"}:
                raise WorkflowCompilationError(
                    f"Unsupported timeout_action '{action}'",
                    path=f"{path}.timeout_action",
                    value=action,
                    code="WORKFLOW_SCHEMA_INVALID",
                )

    def _assert_allowed_keys(
        self,
        payload: dict[str, Any],
        allowed_keys: set[str],
        *,
        path: str,
    ) -> None:
        for key in payload:
            if key not in allowed_keys:
                key_path = f"{path}.{key}" if path else key
                raise WorkflowCompilationError(
                    f"Unexpected field '{key}'",
                    path=key_path,
                    value=payload[key],
                    code="WORKFLOW_SCHEMA_INVALID",
                )

    def _require_non_empty_string(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        path: str,
    ) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise WorkflowCompilationError(
                f"{key} must be a non-empty string",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        return value

    def _validate_optional_string(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        path: str,
    ) -> None:
        if key not in payload or payload[key] is None:
            return
        if not isinstance(payload[key], str):
            raise WorkflowCompilationError(
                f"{key} must be a string or null",
                path=path,
                value=payload[key],
                code="WORKFLOW_SCHEMA_INVALID",
            )

    def _require_int(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        path: str,
        minimum: int,
    ) -> int:
        value = payload.get(key)
        if not isinstance(value, int):
            raise WorkflowCompilationError(
                f"{key} must be an integer",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        if value < minimum:
            raise WorkflowCompilationError(
                f"{key} must be greater than or equal to {minimum}",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        return value

    def _require_number(
        self,
        payload: dict[str, Any],
        key: str,
        *,
        path: str,
        minimum: float,
    ) -> float:
        value = payload.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise WorkflowCompilationError(
                f"{key} must be a number",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        number = float(value)
        if number < minimum:
            raise WorkflowCompilationError(
                f"{key} must be greater than or equal to {minimum}",
                path=path,
                value=value,
                code="WORKFLOW_SCHEMA_INVALID",
            )
        return number

    def _build_dag_edges(self, steps_payload: list[dict[str, Any]]) -> list[tuple[str, str]]:
        known_ids = {str(item["id"]) for item in steps_payload}
        dag_edges: list[tuple[str, str]] = []
        for index, step in enumerate(steps_payload):
            dependencies = step.get("depends_on", [])
            if dependencies is None:
                dependencies = []
            if not isinstance(dependencies, list):
                raise WorkflowCompilationError(
                    "depends_on must be an array of step ids",
                    path=f"steps[{index}].depends_on",
                )
            for dependency in dependencies:
                dep = str(dependency)
                if dep not in known_ids:
                    raise WorkflowCompilationError(
                        f"Undefined dependency step '{dep}'",
                        path=f"steps[{index}].depends_on",
                    )
                dag_edges.append((dep, str(step["id"])))
        return dag_edges

    def _assert_acyclic(self, step_ids: list[str], edges: list[tuple[str, str]]) -> None:
        adjacency: dict[str, list[str]] = {step_id: [] for step_id in step_ids}
        for source, target in edges:
            adjacency.setdefault(source, []).append(target)

        visiting: set[str] = set()
        visited: set[str] = set()
        trail: list[str] = []

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in visiting:
                cycle_start = trail.index(node)
                cycle = [*trail[cycle_start:], node]
                raise WorkflowCompilationError(
                    f"Circular dependency detected: {' -> '.join(cycle)}",
                    path="dag_edges",
                )
            visiting.add(node)
            trail.append(node)
            for child in adjacency.get(node, []):
                visit(child)
            trail.pop()
            visiting.remove(node)
            visited.add(node)

        for step_id in step_ids:
            visit(step_id)

    def _build_step_ir(self, payload: dict[str, Any]) -> StepIR:
        retry_payload = payload.get("retry_config")
        approval_payload = payload.get("approval_config")
        return StepIR(
            step_id=str(payload["id"]),
            step_type=str(payload["step_type"]),
            agent_fqn=self._optional_str(payload.get("agent_fqn")),
            tool_fqn=self._optional_str(payload.get("tool_fqn")),
            input_bindings={
                str(key): str(value)
                for key, value in dict(payload.get("input_bindings", {})).items()
            },
            output_schema=payload.get("output_schema"),
            retry_config=(
                RetryConfigIR.from_dict(retry_payload) if isinstance(retry_payload, dict) else None
            ),
            timeout_seconds=(
                int(payload["timeout_seconds"])
                if payload.get("timeout_seconds") is not None
                else None
            ),
            compensation_handler=self._optional_str(payload.get("compensation_handler")),
            approval_config=(
                ApprovalConfigIR.from_dict(approval_payload)
                if isinstance(approval_payload, dict)
                else None
            ),
            reasoning_mode=self._optional_str(payload.get("reasoning_mode")),
            context_budget_tokens=(
                int(payload["context_budget_tokens"])
                if payload.get("context_budget_tokens") is not None
                else None
            ),
            parallel_group=self._optional_str(payload.get("parallel_group")),
            condition_expression=self._optional_str(payload.get("condition_expression")),
        )

    @staticmethod
    def _format_path(parts: list[Any]) -> str:
        if not parts:
            return ""
        rendered = ""
        for part in parts:
            if isinstance(part, int):
                rendered += f"[{part}]"
            else:
                rendered += f".{part}" if rendered else str(part)
        return rendered

    @staticmethod
    def _optional_str(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
