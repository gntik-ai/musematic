from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class ContextEngineeringError(PlatformError):
    status_code = 400


class ContextSourceUnavailableError(ContextEngineeringError):
    status_code = 503

    def __init__(self, source_type: str, detail: str | None = None) -> None:
        super().__init__(
            "CE_CONTEXT_SOURCE_UNAVAILABLE",
            detail or "Context source unavailable",
            {"source_type": source_type},
        )


class ProfileNotFoundError(ContextEngineeringError):
    status_code = 404

    def __init__(self, profile_id: UUID | str) -> None:
        super().__init__(
            "CE_PROFILE_NOT_FOUND",
            "Context engineering profile not found",
            {"profile_id": str(profile_id)},
        )


class ProfileConflictError(ContextEngineeringError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            "CE_PROFILE_CONFLICT",
            "Context engineering profile name already exists in this workspace",
            {"name": name},
        )


class ProfileInUseError(ContextEngineeringError):
    status_code = 409

    def __init__(self, profile_id: UUID) -> None:
        super().__init__(
            "CE_PROFILE_IN_USE",
            "Context engineering profile is still assigned or referenced by an active A/B test",
            {"profile_id": str(profile_id)},
        )


class InvalidProfileAssignmentError(ContextEngineeringError):
    status_code = 422

    def __init__(self, detail: str) -> None:
        super().__init__(
            "CE_INVALID_PROFILE_ASSIGNMENT",
            detail,
        )


class AbTestNotFoundError(ContextEngineeringError):
    status_code = 404

    def __init__(self, test_id: UUID | str) -> None:
        super().__init__(
            "CE_AB_TEST_NOT_FOUND",
            "Context engineering A/B test not found",
            {"ab_test_id": str(test_id)},
        )


class WorkspaceAuthorizationError(ContextEngineeringError):
    status_code = 403

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(
            "CE_WORKSPACE_ACCESS_DENIED",
            "Requester does not have access to the workspace",
            {"workspace_id": str(workspace_id)},
        )


class BudgetExceededMinimumError(ContextEngineeringError):
    status_code = 409

    def __init__(self, max_tokens: int, minimum_tokens: int) -> None:
        super().__init__(
            "CE_BUDGET_EXCEEDED_MINIMUM",
            "Minimum viable context exceeds the configured budget",
            {
                "max_tokens": max_tokens,
                "minimum_tokens": minimum_tokens,
            },
        )
        self.max_tokens = max_tokens
        self.minimum_tokens = minimum_tokens
