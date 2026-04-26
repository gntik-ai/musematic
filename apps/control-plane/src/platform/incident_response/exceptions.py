from __future__ import annotations

from platform.common.exceptions import NotFoundError, PlatformError, ValidationError
from uuid import UUID


class IntegrationNotFoundError(NotFoundError):
    def __init__(self, integration_id: UUID) -> None:
        super().__init__(
            "INCIDENT_INTEGRATION_NOT_FOUND",
            "Incident integration not found",
            {"integration_id": str(integration_id)},
        )


class IntegrationProviderUnreachableError(PlatformError):
    status_code = 503

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            "INCIDENT_PROVIDER_UNREACHABLE",
            "Incident paging provider is unreachable",
            {"provider": provider, "reason": reason},
        )


class IntegrationSecretValidationError(ValidationError):
    def __init__(self, integration_key_ref: str) -> None:
        super().__init__(
            "INCIDENT_INTEGRATION_SECRET_INVALID",
            "Incident integration credential reference could not be resolved",
            {"integration_key_ref": integration_key_ref},
        )


class IncidentNotFoundError(NotFoundError):
    def __init__(self, incident_id: UUID) -> None:
        super().__init__(
            "INCIDENT_NOT_FOUND",
            "Incident not found",
            {"incident_id": str(incident_id)},
        )


class ExternalAlertNotFoundError(NotFoundError):
    def __init__(self, external_alert_id: UUID) -> None:
        super().__init__(
            "INCIDENT_EXTERNAL_ALERT_NOT_FOUND",
            "Incident external alert not found",
            {"external_alert_id": str(external_alert_id)},
        )


class RunbookNotFoundError(NotFoundError):
    def __init__(self, runbook_id: UUID | str) -> None:
        super().__init__(
            "RUNBOOK_NOT_FOUND",
            "Runbook not found",
            {"runbook_id": str(runbook_id)},
        )


class RunbookConcurrentEditError(PlatformError):
    status_code = 409

    def __init__(self, runbook_id: UUID, current_version: int | None) -> None:
        super().__init__(
            "RUNBOOK_CONCURRENT_EDIT",
            "Runbook has been modified by another author",
            {"runbook_id": str(runbook_id), "current_version": current_version},
        )
        self.current_version = current_version


class PostMortemNotFoundError(NotFoundError):
    def __init__(self, post_mortem_id: UUID | str) -> None:
        super().__init__(
            "POST_MORTEM_NOT_FOUND",
            "Post-mortem not found",
            {"post_mortem_id": str(post_mortem_id)},
        )


class PostMortemOnOpenIncidentError(PlatformError):
    status_code = 409

    def __init__(self, incident_id: UUID, status: str) -> None:
        super().__init__(
            "POST_MORTEM_ON_OPEN_INCIDENT",
            "Post-mortem can only be started for resolved incidents",
            {"incident_id": str(incident_id), "status": status},
        )


class PostMortemAlreadyExistsError(PlatformError):
    status_code = 409

    def __init__(self, incident_id: UUID, post_mortem_id: UUID) -> None:
        super().__init__(
            "POST_MORTEM_ALREADY_EXISTS",
            "A post-mortem already exists for this incident",
            {"incident_id": str(incident_id), "post_mortem_id": str(post_mortem_id)},
        )


class PostMortemDistributionFailedError(PlatformError):
    status_code = 207

    def __init__(self, outcomes: list[dict[str, str]]) -> None:
        super().__init__(
            "POST_MORTEM_DISTRIBUTION_PARTIAL_FAILURE",
            "One or more post-mortem recipients could not be reached",
            {"outcomes": outcomes},
        )
        self.outcomes = outcomes
