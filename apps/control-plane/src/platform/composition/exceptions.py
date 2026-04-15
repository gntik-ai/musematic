from __future__ import annotations

from platform.common.exceptions import PlatformError


class CompositionError(PlatformError):
    """Base error for composition operations."""


class LLMServiceUnavailableError(CompositionError):
    """Raised when the configured LLM service cannot produce a blueprint."""

    status_code = 503

    def __init__(self, message: str = "LLM service unavailable") -> None:
        super().__init__("LLM_SERVICE_UNAVAILABLE", message)


class BlueprintVersionConflictError(CompositionError):
    """Raised when a blueprint version conflict is detected."""

    status_code = 409

    def __init__(self, message: str = "Blueprint version conflict") -> None:
        super().__init__("BLUEPRINT_VERSION_CONFLICT", message)


class DescriptionTooLongError(CompositionError):
    """Raised when a natural-language description exceeds the configured limit."""

    status_code = 400

    def __init__(self, limit: int) -> None:
        super().__init__(
            "DESCRIPTION_TOO_LONG",
            f"Description must be {limit} characters or fewer",
            {"limit": limit},
        )


class BlueprintNotFoundError(CompositionError):
    """Raised when a requested blueprint cannot be found in the workspace."""

    status_code = 404

    def __init__(self, blueprint_id: object) -> None:
        super().__init__("BLUEPRINT_NOT_FOUND", f"Blueprint not found: {blueprint_id}")


class CompositionRequestNotFoundError(CompositionError):
    """Raised when a composition request cannot be found in the workspace."""

    status_code = 404

    def __init__(self, request_id: object) -> None:
        super().__init__("COMPOSITION_REQUEST_NOT_FOUND", f"Request not found: {request_id}")


class InvalidOverridePathError(CompositionError):
    """Raised when an override references an unknown field path."""

    status_code = 400

    def __init__(self, field_path: str) -> None:
        super().__init__(
            "INVALID_OVERRIDE_PATH",
            f"Invalid override field path: {field_path}",
            {"field_path": field_path},
        )

