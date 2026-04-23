from __future__ import annotations

from platform.common.exceptions import AuthorizationError, NotFoundError, PlatformError


class MarketplaceError(PlatformError):
    pass


class AgentNotFoundError(NotFoundError):
    def __init__(self, agent_id: object) -> None:
        super().__init__(
            "MARKETPLACE_AGENT_NOT_FOUND",
            "Marketplace agent not found.",
            {"agent_id": str(agent_id)},
        )


class VisibilityDeniedError(AuthorizationError):
    def __init__(self, agent_id: object) -> None:
        super().__init__(
            "MARKETPLACE_VISIBILITY_DENIED",
            "The requested agent is outside your visibility scope.",
            {"agent_id": str(agent_id)},
        )


class InvocationRequiredError(AuthorizationError):
    def __init__(self, agent_id: object) -> None:
        super().__init__(
            "INVOCATION_REQUIRED",
            "You must invoke this agent before submitting a rating.",
            {"agent_id": str(agent_id)},
        )


class ComparisonRangeError(MarketplaceError):
    status_code = 400

    def __init__(self, provided: int) -> None:
        super().__init__(
            "COMPARISON_RANGE_INVALID",
            "Please select between 2 and 4 agents to compare.",
            {"provided": provided},
        )
