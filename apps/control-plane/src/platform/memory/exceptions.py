from __future__ import annotations

from platform.common.exceptions import PlatformError
from uuid import UUID


class MemoryError(PlatformError):  # noqa: A001
    status_code = 400


class WriteGateAuthError(MemoryError):
    status_code = 403

    def __init__(self, namespace: str, agent_fqn: str) -> None:
        super().__init__(
            "MEMORY_WRITE_AUTH_FAILED",
            "Agent is not authorized to write memory in this namespace or scope",
            {"namespace": namespace, "agent_fqn": agent_fqn},
        )


class WriteGateRateLimitError(MemoryError):
    status_code = 429

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "MEMORY_RATE_LIMIT_EXCEEDED",
            "Memory write rate limit exceeded",
            {"retry_after_seconds": retry_after_seconds},
        )
        self.retry_after_seconds = retry_after_seconds


class WriteGateRetentionError(MemoryError):
    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__("MEMORY_RETENTION_INVALID", message)


class ConflictDetectedError(MemoryError):
    status_code = 409

    def __init__(self, conflict_id: UUID) -> None:
        super().__init__(
            "MEMORY_CONFLICT_DETECTED",
            "Potential contradiction detected for memory entry",
            {"conflict_id": str(conflict_id)},
        )
        self.conflict_id = conflict_id


class ScopeIsolationError(MemoryError):
    status_code = 403

    def __init__(self) -> None:
        super().__init__(
            "MEMORY_SCOPE_ISOLATION",
            "Memory entry is outside the caller visibility scope",
        )


class MemoryEntryNotFoundError(MemoryError):
    status_code = 404

    def __init__(self, entry_id: UUID) -> None:
        super().__init__(
            "MEMORY_ENTRY_NOT_FOUND",
            "Memory entry not found",
            {"entry_id": str(entry_id)},
        )


class EvidenceConflictNotFoundError(MemoryError):
    status_code = 404

    def __init__(self, conflict_id: UUID) -> None:
        super().__init__(
            "EVIDENCE_CONFLICT_NOT_FOUND",
            "Evidence conflict not found",
            {"conflict_id": str(conflict_id)},
        )


class TrajectoryNotFoundError(MemoryError):
    status_code = 404

    def __init__(self, trajectory_id: UUID) -> None:
        super().__init__(
            "TRAJECTORY_NOT_FOUND",
            "Trajectory record not found",
            {"trajectory_id": str(trajectory_id)},
        )


class PatternNotFoundError(MemoryError):
    status_code = 404

    def __init__(self, pattern_id: UUID) -> None:
        super().__init__(
            "PATTERN_NOT_FOUND",
            "Pattern asset not found",
            {"pattern_id": str(pattern_id)},
        )


class KnowledgeNodeNotFoundError(MemoryError):
    status_code = 404

    def __init__(self, node_id: UUID) -> None:
        super().__init__(
            "KNOWLEDGE_NODE_NOT_FOUND",
            "Knowledge node not found",
            {"node_id": str(node_id)},
        )


class KnowledgeEdgeNotFoundError(MemoryError):
    status_code = 404

    def __init__(self, edge_id: UUID) -> None:
        super().__init__(
            "KNOWLEDGE_EDGE_NOT_FOUND",
            "Knowledge edge not found",
            {"edge_id": str(edge_id)},
        )


class GraphUnavailableError(MemoryError):
    status_code = 503

    def __init__(self, message: str = "Knowledge graph is unavailable") -> None:
        super().__init__(
            "GRAPH_UNAVAILABLE",
            message,
            {"partial_sources": ["graph"]},
        )
