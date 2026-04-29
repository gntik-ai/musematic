from __future__ import annotations

from platform.common.exceptions import (
    AuthorizationError,
    NotFoundError,
    PlatformError,
    ValidationError,
)
from uuid import UUID


class TagAttachLimitExceededError(ValidationError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            "TAG_ATTACH_LIMIT_EXCEEDED",
            f"An entity can have at most {limit} tags.",
            {"limit": limit},
        )


class LabelAttachLimitExceededError(ValidationError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            "LABEL_ATTACH_LIMIT_EXCEEDED",
            f"An entity can have at most {limit} labels.",
            {"limit": limit},
        )


class InvalidTagError(ValidationError):
    def __init__(self, tag: str) -> None:
        super().__init__(
            "INVALID_TAG",
            "Tags must be 1-128 characters and match ^[a-zA-Z0-9._-]+$.",
            {"tag": tag},
        )


class InvalidLabelKeyError(ValidationError):
    def __init__(self, key: str) -> None:
        super().__init__(
            "INVALID_LABEL_KEY",
            "Label keys must start with a letter and match ^[a-zA-Z][a-zA-Z0-9._-]*$.",
            {"key": key},
        )


class LabelValueTooLongError(ValidationError):
    def __init__(self, max_length: int) -> None:
        super().__init__(
            "LABEL_VALUE_TOO_LONG",
            f"Label values can be at most {max_length} characters.",
            {"max_length": max_length},
        )


class ReservedLabelNamespaceError(AuthorizationError):
    def __init__(self, key: str) -> None:
        super().__init__(
            "RESERVED_LABEL_NAMESPACE",
            "Only superadmin or service-account callers may write reserved label namespaces.",
            {"key": key},
        )


class SavedViewNotFoundError(NotFoundError):
    def __init__(self, view_id: UUID | None = None) -> None:
        details = {"view_id": str(view_id)} if view_id is not None else {}
        super().__init__("SAVED_VIEW_NOT_FOUND", "Saved view not found.", details)


class SavedViewNameTakenError(PlatformError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            "SAVED_VIEW_NAME_TAKEN",
            "A saved view with this name already exists in the workspace.",
            {"name": name},
        )


class LabelExpressionSyntaxError(ValidationError):
    def __init__(self, line: int, col: int, token: str, message: str) -> None:
        super().__init__(
            "LABEL_EXPRESSION_SYNTAX_ERROR",
            message,
            {"line": line, "col": col, "token": token, "message": message},
        )
        self.line = line
        self.col = col
        self.token = token


class EntityTypeNotRegisteredError(ValidationError):
    def __init__(self, entity_type: str) -> None:
        super().__init__(
            "ENTITY_TYPE_NOT_REGISTERED",
            "Entity type is not registered for tagging.",
            {"entity_type": entity_type},
        )


class EntityNotFoundForTagError(NotFoundError):
    def __init__(self, entity_type: str, entity_id: UUID) -> None:
        super().__init__(
            "ENTITY_NOT_FOUND_FOR_TAG",
            "Cannot tag an entity that does not exist or is not visible.",
            {"entity_type": entity_type, "entity_id": str(entity_id)},
        )
