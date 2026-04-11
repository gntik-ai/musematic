from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class AnalyticsError(PlatformError):
    status_code = 400


class WorkspaceAuthorizationError(AnalyticsError):
    status_code = 403

    def __init__(self, workspace_id: UUID) -> None:
        super().__init__(
            "WORKSPACE_ACCESS_DENIED",
            f"Workspace {workspace_id} not found or you do not have access",
        )


class AnalyticsStoreUnavailableError(AnalyticsError):
    status_code = 503

    def __init__(self, message: str = "Analytics store is temporarily unavailable") -> None:
        super().__init__("ANALYTICS_STORE_UNAVAILABLE", message)
