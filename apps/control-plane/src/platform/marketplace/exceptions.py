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


class MarketplaceParityProbeSetupError(MarketplaceError):
    """Raised by the dev-only parity-probe path when the synthetic publish
    fixture fails to set up or roll back. Distinct from a parity violation:
    this error means the probe could not run at all and the caller should
    investigate the savepoint / synthetic-publish path.
    """

    status_code = 500

    def __init__(self, reason: str) -> None:
        super().__init__(
            "MARKETPLACE_PARITY_PROBE_SETUP_FAILED",
            "Parity probe could not complete its synthetic-publish + rollback.",
            {"reason": reason},
        )
