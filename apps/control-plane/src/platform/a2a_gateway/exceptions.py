from __future__ import annotations

from platform.common.exceptions import PlatformError
from typing import Any


class A2AError(PlatformError):
    def __init__(
        self,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
        *,
        status_code: int,
    ) -> None:
        super().__init__(code, message, details)
        self.status_code = status_code


class A2AAuthenticationError(A2AError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__("authentication_error", message, status_code=401)


class A2AAuthorizationError(A2AError):
    def __init__(self, message: str = "Authorization failed") -> None:
        super().__init__("authorization_error", message, status_code=403)


class A2APolicyDeniedError(A2AError):
    def __init__(self, reason: str = "policy_denied") -> None:
        super().__init__(
            "policy_denied",
            "A2A request blocked by policy",
            {"reason": reason},
            status_code=403,
        )


class A2AAgentNotFoundError(A2AError):
    def __init__(self, agent_fqn: str) -> None:
        super().__init__(
            "agent_not_found",
            f"Agent '{agent_fqn}' was not found",
            status_code=404,
        )


class A2ATaskNotFoundError(A2AError):
    def __init__(self, task_id: str) -> None:
        super().__init__(
            "task_not_found",
            f"Task '{task_id}' was not found",
            status_code=404,
        )


class A2ARateLimitError(A2AError):
    def __init__(self, retry_after_ms: int) -> None:
        super().__init__(
            "rate_limit_exceeded",
            "A2A rate limit exceeded",
            {"retry_after_ms": retry_after_ms},
            status_code=429,
        )


class A2AProtocolVersionError(A2AError):
    def __init__(self, supported: list[str]) -> None:
        super().__init__(
            "protocol_version_unsupported",
            "Unsupported A2A protocol version",
            {"supported": supported},
            status_code=400,
        )


class A2APayloadTooLargeError(A2AError):
    def __init__(self, max_bytes: int) -> None:
        super().__init__(
            "payload_too_large",
            "A2A payload exceeds maximum size",
            {"max_bytes": max_bytes},
            status_code=400,
        )


class A2AUnsupportedCapabilityError(A2AError):
    def __init__(self, capability: str) -> None:
        super().__init__(
            "unsupported_capability",
            f"Unsupported A2A capability: {capability}",
            {"capability": capability},
            status_code=400,
        )


class A2AInvalidTaskStateError(A2AError):
    def __init__(self, current_state: str) -> None:
        super().__init__(
            "invalid_task_state",
            "Task is not in a valid state for this operation",
            {"current_state": current_state},
            status_code=400,
        )


class A2AHttpsRequiredError(A2AError):
    def __init__(self, message: str = "HTTPS endpoint is required") -> None:
        super().__init__("https_required", message, status_code=400)


class A2AEndpointConflictError(A2AError):
    def __init__(self) -> None:
        super().__init__(
            "endpoint_already_registered",
            "The external endpoint is already registered",
            status_code=400,
        )
