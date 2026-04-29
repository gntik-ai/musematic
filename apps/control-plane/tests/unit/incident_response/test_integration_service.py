from __future__ import annotations

from platform.common.exceptions import AuthorizationError
from platform.incident_response.router import create_integration
from platform.incident_response.schemas import IntegrationCreateRequest, PagingProvider
from platform.incident_response.services.integration_service import IntegrationService
from typing import Any
from uuid import UUID

import pytest

from tests.unit.incident_response.support import RecordingSecretProvider, make_integration


class FakeIntegrationRepository:
    def __init__(self) -> None:
        self.integrations: dict[UUID, Any] = {}

    async def insert_integration(self, **fields: Any) -> Any:
        integration = make_integration(
            provider=fields["provider"],
            enabled=fields["enabled"],
            mapping=fields["alert_severity_mapping"],
            key_ref=fields["integration_key_ref"],
        )
        self.integrations[integration.id] = integration
        return integration

    async def list_integrations(self, *, enabled_only: bool = False) -> list[Any]:
        rows = list(self.integrations.values())
        return [item for item in rows if item.enabled] if enabled_only else rows

    async def get_integration(self, integration_id: UUID) -> Any | None:
        return self.integrations.get(integration_id)

    async def update_integration(self, integration_id: UUID, **fields: Any) -> Any | None:
        integration = self.integrations.get(integration_id)
        if integration is None:
            return None
        if fields.get("enabled") is not None:
            integration.enabled = fields["enabled"]
        if fields.get("alert_severity_mapping") is not None:
            integration.alert_severity_mapping = fields["alert_severity_mapping"]
        return integration

    async def delete_integration(self, integration_id: UUID) -> bool:
        return self.integrations.pop(integration_id, None) is not None


class RecordingAuditChain:
    def __init__(self) -> None:
        self.entries: list[tuple[Any, str, bytes]] = []

    async def append(self, event_id: Any, source: str, canonical_payload: bytes) -> None:
        self.entries.append((event_id, source, canonical_payload))


@pytest.mark.asyncio
async def test_integration_crud_audits_and_never_returns_secret_value() -> None:
    repo = FakeIntegrationRepository()
    secret_provider = RecordingSecretProvider("super-secret-routing-key")
    audit = RecordingAuditChain()
    service = IntegrationService(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=secret_provider,  # type: ignore[arg-type]
        audit_chain_service=audit,
    )

    created = await service.create(
        provider=PagingProvider.pagerduty,
        integration_key_ref="incident-response/integrations/pagerduty-primary",
        alert_severity_mapping={"critical": "critical"},
    )
    resolved = await service.resolve_credential(next(iter(repo.integrations.values())))
    disabled = await service.disable(created.id)
    updated = await service.update_severity_mapping(created.id, {"warning": "warning"})
    await service.enable(created.id)
    await service.delete(created.id)

    assert resolved == "super-secret-routing-key"
    assert secret_provider.calls == [
        "incident-response/integrations/pagerduty-primary",
        "incident-response/integrations/pagerduty-primary",
    ]
    assert "super-secret-routing-key" not in str(created.model_dump())
    assert disabled.enabled is False
    assert updated.alert_severity_mapping == {"warning": "warning"}
    assert [entry[1] for entry in audit.entries] == [
        "incident_response.integrations",
        "incident_response.integrations",
        "incident_response.integrations",
        "incident_response.integrations",
        "incident_response.integrations",
    ]
    assert b"super-secret-routing-key" not in b"".join(entry[2] for entry in audit.entries)


@pytest.mark.asyncio
async def test_integration_admin_router_requires_superadmin_role() -> None:
    payload = IntegrationCreateRequest(
        provider=PagingProvider.pagerduty,
        integration_key_ref="incident-response/integrations/pagerduty-primary",
        alert_severity_mapping={"critical": "critical"},
    )

    with pytest.raises(AuthorizationError):
        await create_integration(
            payload,
            current_user={"sub": "00000000-0000-0000-0000-000000000001", "roles": []},
            integration_service=object(),  # type: ignore[arg-type]
        )
