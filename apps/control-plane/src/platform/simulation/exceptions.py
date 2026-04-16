from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from typing import Any
from uuid import UUID


class SimulationError(PlatformError):
    status_code = 500


class SimulationNotFoundError(NotFoundError):
    def __init__(self, resource: str, resource_id: UUID | str) -> None:
        super().__init__(
            "SIMULATION_RESOURCE_NOT_FOUND",
            f"{resource} not found",
            {"resource_id": str(resource_id)},
        )


class SimulationNotCancellableError(SimulationError):
    status_code = 409

    def __init__(self, run_id: UUID, status: str) -> None:
        super().__init__(
            "SIMULATION_NOT_CANCELLABLE",
            "Simulation run cannot be cancelled from its current status",
            {"run_id": str(run_id), "status": status},
        )


class SimulationInfrastructureUnavailableError(SimulationError):
    status_code = 409

    def __init__(self, component: str, reason: str) -> None:
        super().__init__(
            "SIMULATION_INFRASTRUCTURE_UNAVAILABLE",
            f"Simulation infrastructure unavailable: {component}",
            {"component": component, "reason": reason},
        )


class IncompatibleComparisonError(ValidationError):
    def __init__(self, reasons: list[str]) -> None:
        super().__init__(
            "INCOMPATIBLE_COMPARISON",
            "Simulation comparison inputs are incompatible",
            {"incompatibility_reasons": reasons},
        )


class InsufficientPredictionDataError(SimulationError):
    status_code = 200

    def __init__(self, twin_id: UUID, history_days_used: int, min_days: int) -> None:
        super().__init__(
            "INSUFFICIENT_PREDICTION_DATA",
            "Insufficient behavioral history to generate a reliable prediction",
            {
                "twin_id": str(twin_id),
                "status": "insufficient_data",
                "history_days_used": history_days_used,
                "min_prediction_history_days": min_days,
            },
        )


class SimulationValidationError(ValidationError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("SIMULATION_VALIDATION_ERROR", message, details)

