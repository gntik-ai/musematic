from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class AgentOpsError(PlatformError):
    status_code = 400


class CanaryConflictError(AgentOpsError):
    status_code = 409

    def __init__(self, agent_fqn: str, workspace_id: UUID) -> None:
        super().__init__(
            "AGENTOPS_CANARY_CONFLICT",
            f"Agent '{agent_fqn}' already has an active canary deployment",
            {
                "agent_fqn": agent_fqn,
                "workspace_id": str(workspace_id),
            },
        )


class CanaryStateError(AgentOpsError):
    status_code = 409

    def __init__(self, canary_id: UUID | str, status: str) -> None:
        super().__init__(
            "AGENTOPS_CANARY_INVALID_STATE",
            f"Canary deployment '{canary_id}' is not active",
            {
                "canary_id": str(canary_id),
                "status": status,
            },
        )


class BaselineNotReadyError(AgentOpsError):
    status_code = 412

    def __init__(self, revision_id: UUID | str) -> None:
        super().__init__(
            "AGENTOPS_BASELINE_NOT_READY",
            f"Behavioral baseline for revision '{revision_id}' is not ready",
            {"revision_id": str(revision_id)},
        )


class RetirementConflictError(AgentOpsError):
    status_code = 409

    def __init__(self, agent_fqn: str, workspace_id: UUID) -> None:
        super().__init__(
            "AGENTOPS_RETIREMENT_CONFLICT",
            f"Agent '{agent_fqn}' already has an active retirement workflow",
            {
                "agent_fqn": agent_fqn,
                "workspace_id": str(workspace_id),
            },
        )


class InsufficientSampleError(AgentOpsError):
    status_code = 412

    def __init__(self, dimension: str, minimum: int, actual: int) -> None:
        super().__init__(
            "AGENTOPS_INSUFFICIENT_SAMPLE",
            f"Insufficient sample size for '{dimension}'",
            {
                "dimension": dimension,
                "minimum": minimum,
                "actual": actual,
            },
        )


class WeightSumError(AgentOpsError):
    status_code = 400

    def __init__(self, total: float) -> None:
        super().__init__(
            "AGENTOPS_WEIGHT_SUM_INVALID",
            "Health score weights must sum to 100.0",
            {"total": round(total, 4)},
        )
