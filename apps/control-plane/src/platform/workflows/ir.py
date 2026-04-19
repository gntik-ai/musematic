from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class RetryConfigIR:
    """Represent the retry config i r."""
    max_retries: int = 3
    backoff_strategy: str = "fixed"
    base_delay_seconds: float = 5.0
    max_delay_seconds: float = 300.0
    retry_on_event_types: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object to a dictionary."""
        payload = asdict(self)
        payload["retry_on_event_types"] = self.retry_on_event_types or []
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RetryConfigIR:
        """Build an instance from a dictionary payload."""
        return cls(
            max_retries=int(payload.get("max_retries", 3)),
            backoff_strategy=str(payload.get("backoff_strategy", "fixed")),
            base_delay_seconds=float(payload.get("base_delay_seconds", 5.0)),
            max_delay_seconds=float(payload.get("max_delay_seconds", 300.0)),
            retry_on_event_types=[str(item) for item in payload.get("retry_on_event_types", [])],
        )


@dataclass(slots=True)
class ApprovalConfigIR:
    """Represent the approval config i r."""
    required_approvers: list[str]
    timeout_seconds: int = 86400
    timeout_action: str = "fail"

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object to a dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ApprovalConfigIR:
        """Build an instance from a dictionary payload."""
        return cls(
            required_approvers=[str(item) for item in payload.get("required_approvers", [])],
            timeout_seconds=int(payload.get("timeout_seconds", 86400)),
            timeout_action=str(payload.get("timeout_action", "fail")),
        )


@dataclass(slots=True)
class StepIR:
    """Represent the step i r."""
    step_id: str
    step_type: str
    agent_fqn: str | None = None
    tool_fqn: str | None = None
    input_bindings: dict[str, str] | None = None
    output_schema: dict[str, Any] | None = None
    retry_config: RetryConfigIR | None = None
    timeout_seconds: int | None = None
    compensation_handler: str | None = None
    approval_config: ApprovalConfigIR | None = None
    reasoning_mode: str | None = None
    compute_budget: float | None = None
    context_budget_tokens: int | None = None
    parallel_group: str | None = None
    condition_expression: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object to a dictionary."""
        return {
            "step_id": self.step_id,
            "step_type": self.step_type,
            "agent_fqn": self.agent_fqn,
            "tool_fqn": self.tool_fqn,
            "input_bindings": dict(self.input_bindings or {}),
            "output_schema": self.output_schema,
            "retry_config": self.retry_config.to_dict() if self.retry_config is not None else None,
            "timeout_seconds": self.timeout_seconds,
            "compensation_handler": self.compensation_handler,
            "approval_config": (
                self.approval_config.to_dict() if self.approval_config is not None else None
            ),
            "reasoning_mode": self.reasoning_mode,
            "compute_budget": self.compute_budget,
            "context_budget_tokens": self.context_budget_tokens,
            "parallel_group": self.parallel_group,
            "condition_expression": self.condition_expression,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> StepIR:
        """Build an instance from a dictionary payload."""
        retry_payload = payload.get("retry_config")
        approval_payload = payload.get("approval_config")
        return cls(
            step_id=str(payload["step_id"]),
            step_type=str(payload["step_type"]),
            agent_fqn=payload.get("agent_fqn"),
            tool_fqn=payload.get("tool_fqn"),
            input_bindings={
                str(key): str(value) for key, value in (payload.get("input_bindings") or {}).items()
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
            compensation_handler=payload.get("compensation_handler"),
            approval_config=(
                ApprovalConfigIR.from_dict(approval_payload)
                if isinstance(approval_payload, dict)
                else None
            ),
            reasoning_mode=payload.get("reasoning_mode"),
            compute_budget=(
                float(payload["compute_budget"])
                if payload.get("compute_budget") is not None
                else None
            ),
            context_budget_tokens=(
                int(payload["context_budget_tokens"])
                if payload.get("context_budget_tokens") is not None
                else None
            ),
            parallel_group=payload.get("parallel_group"),
            condition_expression=payload.get("condition_expression"),
        )


@dataclass(slots=True)
class WorkflowIR:
    """Represent the workflow i r."""
    schema_version: int
    workflow_id: str
    steps: list[StepIR]
    dag_edges: list[tuple[str, str]]
    data_bindings: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize this object to a dictionary."""
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "steps": [item.to_dict() for item in self.steps],
            "dag_edges": [list(edge) for edge in self.dag_edges],
            "data_bindings": list(self.data_bindings or []),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> WorkflowIR:
        """Build an instance from a dictionary payload."""
        return cls(
            schema_version=int(payload["schema_version"]),
            workflow_id=str(payload["workflow_id"]),
            steps=[StepIR.from_dict(item) for item in payload.get("steps", [])],
            dag_edges=[
                (str(edge[0]), str(edge[1]))
                for edge in payload.get("dag_edges", [])
                if isinstance(edge, (list, tuple)) and len(edge) == 2
            ],
            data_bindings=list(payload.get("data_bindings", [])),
            metadata=dict(payload.get("metadata", {})),
        )
