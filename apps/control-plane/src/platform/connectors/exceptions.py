from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError
from uuid import UUID


class ConnectorError(PlatformError):
    pass


class ConnectorNotFoundError(NotFoundError):
    def __init__(self, connector_id: UUID) -> None:
        super().__init__("CONNECTOR_NOT_FOUND", f"Connector '{connector_id}' was not found.")


class ConnectorTypeNotFoundError(NotFoundError):
    def __init__(self, type_slug: str) -> None:
        super().__init__("CONNECTOR_TYPE_NOT_FOUND", f"Connector type '{type_slug}' was not found.")


class ConnectorTypeDeprecatedError(ConnectorError):
    status_code = 409

    def __init__(self, type_slug: str) -> None:
        super().__init__(
            "CONNECTOR_TYPE_DEPRECATED",
            f"Connector type '{type_slug}' is deprecated and cannot be used.",
        )


class ConnectorConfigError(ConnectorError):
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__("CONNECTOR_CONFIG_INVALID", message)


class ConnectorDisabledError(ConnectorError):
    status_code = 400

    def __init__(self, connector_id: UUID) -> None:
        super().__init__("CONNECTOR_DISABLED", f"Connector '{connector_id}' is disabled.")


class ConnectorNameConflictError(ConnectorError):
    status_code = 409

    def __init__(self, name: str) -> None:
        super().__init__(
            "CONNECTOR_NAME_CONFLICT",
            f"Connector name '{name}' is already in use for this workspace.",
        )


class CredentialUnavailableError(ConnectorError):
    status_code = 503

    def __init__(self, credential_key: str) -> None:
        super().__init__(
            "CREDENTIAL_UNAVAILABLE",
            f"Credential '{credential_key}' is not available in the configured vault.",
        )


class WebhookSignatureError(ConnectorError):
    status_code = 401

    def __init__(self, message: str = "Webhook signature is invalid.") -> None:
        super().__init__("WEBHOOK_SIGNATURE_INVALID", message)


class DeliveryError(ConnectorError):
    status_code = 502

    def __init__(self, message: str) -> None:
        super().__init__("DELIVERY_FAILED", message)


class DeliveryPermanentError(DeliveryError):
    status_code = 422

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.code = "DELIVERY_FAILED_PERMANENTLY"


class DeadLetterNotFoundError(NotFoundError):
    def __init__(self, entry_id: UUID) -> None:
        super().__init__("DEAD_LETTER_NOT_FOUND", f"Dead-letter entry '{entry_id}' was not found.")


class DeadLetterAlreadyResolvedError(ConnectorError):
    status_code = 409

    def __init__(self, entry_id: UUID) -> None:
        super().__init__(
            "DEAD_LETTER_ALREADY_RESOLVED",
            f"Dead-letter entry '{entry_id}' has already been resolved.",
        )
