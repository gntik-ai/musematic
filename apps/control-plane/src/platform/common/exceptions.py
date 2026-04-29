from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class PlatformError(Exception):
    status_code: int = 500

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class NotFoundError(PlatformError):
    status_code = 404


class AuthorizationError(PlatformError):
    status_code = 403


class ValidationError(PlatformError):
    status_code = 422


class PolicyViolationError(PlatformError):
    status_code = 403


class PolicySecretLeakError(PlatformError):
    status_code = 403

    def __init__(self, secret_type: str) -> None:
        super().__init__(
            "PROMPT_SECRET_DETECTED",
            f"Prompt preflight blocked secret pattern: {secret_type}",
            {"secret_type": secret_type},
        )
        self.secret_type = secret_type


class BudgetExceededError(PlatformError):
    status_code = 429


class ConvergenceFailedError(PlatformError):
    status_code = 500


async def platform_exception_handler(request: Request, exc: PlatformError) -> JSONResponse:
    del request
    headers: dict[str, str] = {}
    retry_after = exc.details.get("retry_after")
    if isinstance(retry_after, (int, float)) and retry_after > 0:
        headers["Retry-After"] = str(max(1, int(retry_after)))
    return JSONResponse(
        status_code=exc.status_code,
        headers=headers,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )


class KafkaProducerError(Exception):
    """Raised when Kafka producer delivery fails."""


class KafkaConsumerError(Exception):
    """Raised when Kafka consumer operations fail."""


class ObjectStorageError(Exception):
    """Raised when object storage operations fail."""


class ObjectNotFoundError(ObjectStorageError):
    """Raised when an object key or version cannot be found."""


class BucketNotFoundError(ObjectStorageError):
    """Raised when a target bucket does not exist."""


class QdrantError(Exception):
    """Raised when Qdrant operations fail."""


class Neo4jClientError(Exception):
    """Raised when Neo4j client operations fail."""


class Neo4jConstraintViolationError(Neo4jClientError):
    """Raised when a Neo4j uniqueness or schema constraint is violated."""


class Neo4jNodeNotFoundError(Neo4jClientError):
    """Raised when a referenced Neo4j node does not exist."""


class Neo4jConnectionError(Neo4jClientError):
    """Raised when the Neo4j driver cannot connect to the database."""


class HopLimitExceededError(Neo4jClientError):
    """Raised when local graph mode is asked to traverse beyond the supported hop limit."""


class ClickHouseClientError(Exception):
    """Raised when ClickHouse client operations fail."""


class ClickHouseConnectionError(ClickHouseClientError):
    """Raised when ClickHouse is not configured or cannot be reached."""


class ClickHouseQueryError(ClickHouseClientError):
    """Raised when a ClickHouse query or insert fails."""
