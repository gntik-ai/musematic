from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class RegistryError(PlatformError):
    status_code = 400


class FQNConflictError(RegistryError):
    status_code = 409

    def __init__(self, fqn: str) -> None:
        super().__init__(
            "REGISTRY_FQN_CONFLICT",
            "Agent FQN already exists",
            {"fqn": fqn},
        )


class NamespaceConflictError(RegistryError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            "REGISTRY_NAMESPACE_CONFLICT",
            "Namespace name already exists in this workspace",
            {"name": name},
        )


class NamespaceNotFoundError(RegistryError):
    status_code = 404

    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(
            "REGISTRY_NAMESPACE_NOT_FOUND",
            "Registry namespace not found",
            {"namespace": str(identifier)},
        )


class PackageValidationError(RegistryError):
    status_code = 422

    def __init__(self, error_type: str, detail: str, field: str | None = None) -> None:
        details = {"error_type": error_type, "field": field}
        super().__init__("REGISTRY_PACKAGE_INVALID", detail, details)
        self.error_type = error_type
        self.field = field


class InvalidTransitionError(RegistryError):
    status_code = 409

    def __init__(self, current: str, target: str, valid: list[str]) -> None:
        super().__init__(
            "REGISTRY_INVALID_TRANSITION",
            (
                f"Invalid transition: {current} -> {target}. "
                f"Valid transitions from {current}: {valid}"
            ),
            {"current_status": current, "target_status": target, "valid_transitions": valid},
        )


class AgentNotFoundError(RegistryError):
    status_code = 404

    def __init__(self, identifier: UUID | str) -> None:
        super().__init__(
            "REGISTRY_AGENT_NOT_FOUND",
            "Registry agent not found",
            {"agent": str(identifier)},
        )


class WorkspaceAuthorizationError(RegistryError):
    status_code = 403

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(
            "REGISTRY_WORKSPACE_ACCESS_DENIED",
            "Requester does not have access to the workspace",
            {"workspace_id": str(workspace_id)},
        )


class RegistryStoreUnavailableError(RegistryError):
    status_code = 503

    def __init__(self, store: str, detail: str | None = None) -> None:
        super().__init__(
            "REGISTRY_STORE_UNAVAILABLE",
            detail or f"Registry dependency unavailable: {store}",
            {"store": store},
        )


class InvalidVisibilityPatternError(RegistryError):
    status_code = 422

    def __init__(self, pattern: str) -> None:
        super().__init__(
            "REGISTRY_INVALID_VISIBILITY_PATTERN",
            "Invalid visibility pattern",
            {"pattern": pattern},
        )


class RevisionConflictError(RegistryError):
    status_code = 409

    def __init__(self, version: str) -> None:
        super().__init__(
            "REGISTRY_REVISION_CONFLICT",
            "Agent revision already exists",
            {"version": version},
        )
