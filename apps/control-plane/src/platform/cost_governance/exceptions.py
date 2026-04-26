from __future__ import annotations

from platform.common.exceptions import (
    BudgetExceededError,
    NotFoundError,
    PlatformError,
    ValidationError,
)


class BudgetNotConfiguredError(NotFoundError):
    def __init__(self) -> None:
        super().__init__("BUDGET_NOT_CONFIGURED", "Workspace budget is not configured")


class WorkspaceCostBudgetExceededError(BudgetExceededError):
    def __init__(self, *, workspace_id: str, override_endpoint: str) -> None:
        super().__init__(
            "WORKSPACE_COST_BUDGET_EXCEEDED",
            "Workspace cost budget has been exceeded",
            {
                "workspace_id": workspace_id,
                "block_reason": "workspace_cost_budget_exceeded",
                "override_endpoint": override_endpoint,
            },
        )


class OverrideExpiredError(PlatformError):
    status_code = 410

    def __init__(self) -> None:
        super().__init__("OVERRIDE_EXPIRED", "Budget override token has expired")


class OverrideAlreadyRedeemedError(PlatformError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("OVERRIDE_ALREADY_REDEEMED", "Budget override token was already redeemed")


class InvalidBudgetConfigError(ValidationError):
    def __init__(self, message: str) -> None:
        super().__init__("INVALID_BUDGET_CONFIG", message)


class InsufficientHistoryError(Exception):
    """Raised internally when a forecast or anomaly baseline has too little history."""

