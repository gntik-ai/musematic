from __future__ import annotations

from platform.common.exceptions import PlatformError


class DiscoveryError(PlatformError):
    """Base error for discovery operations."""


class InsufficientHypothesesError(DiscoveryError):
    """Raised when a tournament cannot be run."""

    status_code = 412

    def __init__(self, minimum: int = 2) -> None:
        super().__init__(
            "INSUFFICIENT_HYPOTHESES",
            f"At least {minimum} active hypotheses are required.",
            {"minimum": minimum},
        )


class SessionAlreadyRunningError(DiscoveryError):
    """Raised when a session cannot accept a new running cycle."""

    status_code = 409

    def __init__(self, message: str = "Discovery session already has a running cycle") -> None:
        super().__init__("SESSION_ALREADY_RUNNING", message)


class ExperimentNotApprovedError(DiscoveryError):
    """Raised when an experiment is executed before governance approval."""

    status_code = 409

    def __init__(self, experiment_id: object) -> None:
        super().__init__(
            "EXPERIMENT_NOT_APPROVED",
            f"Experiment is not approved for execution: {experiment_id}",
        )


class ProvenanceQueryError(DiscoveryError):
    """Raised when provenance graph traversal fails."""

    status_code = 500

    def __init__(self, message: str = "Unable to query provenance graph") -> None:
        super().__init__("PROVENANCE_QUERY_ERROR", message)


class DiscoveryNotFoundError(DiscoveryError):
    """Raised when a discovery resource cannot be found."""

    status_code = 404

    def __init__(self, resource: str, resource_id: object) -> None:
        super().__init__("NOT_FOUND", f"{resource} not found: {resource_id}")


class ProximityComputationRunningError(DiscoveryError):
    """Raised when a duplicate proximity computation is requested."""

    status_code = 409

    def __init__(self, session_id: object) -> None:
        super().__init__(
            "PROXIMITY_COMPUTATION_RUNNING",
            f"Proximity computation already running for session: {session_id}",
        )
