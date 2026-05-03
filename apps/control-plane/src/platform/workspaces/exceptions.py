from __future__ import annotations

from platform.common.exceptions import PlatformError


class WorkspacesError(PlatformError):
    status_code = 400


class WorkspaceNotFoundError(WorkspacesError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("WORKSPACE_NOT_FOUND", "Workspace not found")


class WorkspaceLimitError(WorkspacesError):
    status_code = 403

    def __init__(self, limit: int) -> None:
        super().__init__(
            "WORKSPACE_LIMIT_REACHED",
            "Workspace limit reached",
            {"limit": limit},
        )


class WorkspaceNameConflictError(WorkspacesError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            "WORKSPACE_NAME_CONFLICT",
            "Workspace name already exists for this owner",
            {"name": name},
        )


class WorkspaceAuthorizationError(WorkspacesError):
    status_code = 403

    def __init__(self, message: str = "Insufficient workspace permissions") -> None:
        super().__init__("WORKSPACE_PERMISSION_DENIED", message)


class WorkspaceStateConflictError(WorkspacesError):
    status_code = 409

    def __init__(self, code: str, message: str) -> None:
        super().__init__(code, message)


class LastOwnerError(WorkspacesError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__(
            "LAST_OWNER_CONFLICT",
            "Cannot remove the last workspace owner",
        )


class MemberAlreadyExistsError(WorkspacesError):
    status_code = 409

    def __init__(self) -> None:
        super().__init__("MEMBER_ALREADY_EXISTS", "User is already a workspace member")


class MemberNotFoundError(WorkspacesError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("MEMBER_NOT_FOUND", "Workspace member not found")


class WorkspaceGovernanceNotFoundError(WorkspacesError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__(
            "WORKSPACE_GOVERNANCE_NOT_FOUND",
            "Workspace governance chain not configured",
        )


class InvalidGoalTransitionError(WorkspacesError):
    status_code = 409

    def __init__(self, from_status: str, to_status: str) -> None:
        super().__init__(
            "INVALID_GOAL_TRANSITION",
            f"Cannot transition goal from {from_status} to {to_status}",
            {"from_status": from_status, "to_status": to_status},
        )


class GoalNotFoundError(WorkspacesError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("GOAL_NOT_FOUND", "Workspace goal not found")


class VisibilityGrantNotFoundError(WorkspacesError):
    status_code = 404

    def __init__(self) -> None:
        super().__init__("VISIBILITY_GRANT_NOT_FOUND", "Workspace visibility grant not found")


class WorkspacePendingDeletionError(WorkspacesError):
    status_code = 423

    def __init__(self) -> None:
        super().__init__(
            "WORKSPACE_PENDING_DELETION",
            (
                "Workspace is pending deletion; writes are blocked until the "
                "grace period ends or deletion is cancelled."
            ),
        )
