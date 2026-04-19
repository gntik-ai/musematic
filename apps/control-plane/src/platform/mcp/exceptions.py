from __future__ import annotations

from platform.common.exceptions import PlatformError
from typing import Any
from uuid import UUID


class MCPError(PlatformError):
    status_code: int = 400

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(code, message, details)


class MCPServerNotFoundError(MCPError):
    status_code = 404

    def __init__(self, server_id: UUID | str) -> None:
        super().__init__("mcp_server_not_found", f"MCP server '{server_id}' was not found")


class MCPServerSuspendedError(MCPError):
    status_code = 409

    def __init__(self, server_id: UUID | str) -> None:
        super().__init__(
            "mcp_server_suspended",
            f"MCP server '{server_id}' is not active",
            {"server_id": str(server_id)},
        )


class MCPServerUnavailableError(MCPError):
    status_code = 502

    def __init__(
        self,
        message: str,
        *,
        classification: str,
        retry_safe: bool | None = None,
    ) -> None:
        super().__init__(
            "mcp_server_unavailable",
            message,
            {
                "classification": classification,
                "retry_safe": classification == "transient"
                if retry_safe is None
                else retry_safe,
            },
        )
        self.classification = classification
        self.retry_safe = (
            classification == "transient" if retry_safe is None else retry_safe
        )


class MCPToolNotFoundError(MCPError):
    status_code = 404

    def __init__(self, tool_identifier: str) -> None:
        super().__init__(
            "tool_not_found",
            f"MCP tool '{tool_identifier}' was not found",
            {"tool_identifier": tool_identifier},
        )


class MCPProtocolVersionError(MCPError):
    status_code = 400

    def __init__(self, supported: list[str]) -> None:
        super().__init__(
            "protocol_version_unsupported",
            "Unsupported MCP protocol version",
            {"supported": supported},
        )


class MCPPayloadTooLargeError(MCPError):
    status_code = 400

    def __init__(self, max_bytes: int, payload_size_bytes: int | None = None) -> None:
        details = {"max_bytes": max_bytes}
        if payload_size_bytes is not None:
            details["payload_size_bytes"] = payload_size_bytes
        super().__init__("payload_too_large", "MCP payload exceeds maximum size", details)


class MCPDuplicateRegistrationError(MCPError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__(
            "endpoint_already_registered",
            "The external MCP endpoint is already registered",
        )


class MCPInsecureTransportError(MCPError):
    status_code = 400

    def __init__(self) -> None:
        super().__init__("https_required", "HTTPS endpoint is required")


class MCPPolicyDeniedError(MCPError):
    status_code = 403

    def __init__(self, reason: str) -> None:
        super().__init__(
            "policy_denied",
            "MCP invocation blocked by policy",
            {"reason": reason},
        )


class MCPToolError(MCPError):
    status_code = 502

    def __init__(self, code: str, message: str, *, classification: str) -> None:
        super().__init__(code, message, {"classification": classification})
        self.classification = classification
