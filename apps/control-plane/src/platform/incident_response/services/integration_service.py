from __future__ import annotations

import json
from platform.common.clients.model_router import SecretProvider
from platform.incident_response.exceptions import (
    IntegrationNotFoundError,
    IntegrationSecretValidationError,
)
from platform.incident_response.models import IncidentIntegration
from platform.incident_response.repository import IncidentResponseRepository
from platform.incident_response.schemas import IntegrationResponse, PagingProvider
from typing import Any
from uuid import UUID, uuid4


class IntegrationService:
    def __init__(
        self,
        *,
        repository: IncidentResponseRepository,
        secret_provider: SecretProvider,
        audit_chain_service: Any | None = None,
    ) -> None:
        self.repository = repository
        self.secret_provider = secret_provider
        self.audit_chain_service = audit_chain_service

    async def create(
        self,
        *,
        provider: PagingProvider | str,
        integration_key_ref: str,
        alert_severity_mapping: dict[str, str],
        enabled: bool = True,
    ) -> IntegrationResponse:
        await self._validate_secret(integration_key_ref)
        integration = await self.repository.insert_integration(
            provider=str(provider),
            integration_key_ref=integration_key_ref,
            alert_severity_mapping=alert_severity_mapping,
            enabled=enabled,
        )
        await self._audit(
            "integration.created",
            integration=integration,
            extra={"provider": integration.provider},
        )
        return IntegrationResponse.model_validate(integration)

    async def list(self, *, enabled_only: bool = False) -> list[IntegrationResponse]:
        rows = await self.repository.list_integrations(enabled_only=enabled_only)
        return [IntegrationResponse.model_validate(row) for row in rows]

    async def get(self, integration_id: UUID) -> IntegrationResponse:
        integration = await self._get_or_raise(integration_id)
        return IntegrationResponse.model_validate(integration)

    async def enable(self, integration_id: UUID) -> IntegrationResponse:
        integration = await self.repository.update_integration(integration_id, enabled=True)
        if integration is None:
            raise IntegrationNotFoundError(integration_id)
        await self._audit("integration.enabled", integration=integration)
        return IntegrationResponse.model_validate(integration)

    async def disable(self, integration_id: UUID) -> IntegrationResponse:
        integration = await self.repository.update_integration(integration_id, enabled=False)
        if integration is None:
            raise IntegrationNotFoundError(integration_id)
        await self._audit("integration.disabled", integration=integration)
        return IntegrationResponse.model_validate(integration)

    async def update_severity_mapping(
        self,
        integration_id: UUID,
        mapping: dict[str, str],
    ) -> IntegrationResponse:
        integration = await self.repository.update_integration(
            integration_id,
            alert_severity_mapping=mapping,
        )
        if integration is None:
            raise IntegrationNotFoundError(integration_id)
        await self._audit("integration.severity_mapping_updated", integration=integration)
        return IntegrationResponse.model_validate(integration)

    async def update(
        self,
        integration_id: UUID,
        *,
        enabled: bool | None = None,
        alert_severity_mapping: dict[str, str] | None = None,
    ) -> IntegrationResponse:
        integration = await self.repository.update_integration(
            integration_id,
            enabled=enabled,
            alert_severity_mapping=alert_severity_mapping,
        )
        if integration is None:
            raise IntegrationNotFoundError(integration_id)
        await self._audit("integration.updated", integration=integration)
        return IntegrationResponse.model_validate(integration)

    async def delete(self, integration_id: UUID) -> None:
        integration = await self._get_or_raise(integration_id)
        deleted = await self.repository.delete_integration(integration_id)
        if not deleted:
            raise IntegrationNotFoundError(integration_id)
        await self._audit("integration.deleted", integration=integration)

    async def resolve_credential(self, integration: IncidentIntegration) -> str:
        return await self.secret_provider.get_current(integration.integration_key_ref)

    async def _get_or_raise(self, integration_id: UUID) -> IncidentIntegration:
        integration = await self.repository.get_integration(integration_id)
        if integration is None:
            raise IntegrationNotFoundError(integration_id)
        return integration

    async def _validate_secret(self, integration_key_ref: str) -> None:
        try:
            await self.secret_provider.get_current(integration_key_ref)
        except Exception as exc:
            raise IntegrationSecretValidationError(integration_key_ref) from exc

    async def _audit(
        self,
        action: str,
        *,
        integration: IncidentIntegration,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if self.audit_chain_service is None:
            return
        payload = {
            "action": action,
            "provider": integration.provider,
            "integration_id": str(integration.id),
            **(extra or {}),
        }
        append = getattr(self.audit_chain_service, "append", None)
        if append is None:
            return
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        await append(uuid4(), "incident_response.integrations", canonical)
