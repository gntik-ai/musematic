from __future__ import annotations

from platform.incident_response.schemas import PagingProvider
from platform.incident_response.services.integration_service import IntegrationService

import pytest

from tests.integration.incident_response.support import (
    FailingAudit,
    MemoryIncidentRepository,
    RecordingAudit,
    SecretProvider,
)


@pytest.mark.asyncio
async def test_admin_integration_mutations_emit_audit_without_credential_value() -> None:
    repo = MemoryIncidentRepository()
    audit = RecordingAudit()
    service = IntegrationService(
        repository=repo,  # type: ignore[arg-type]
        secret_provider=SecretProvider("credential-value"),  # type: ignore[arg-type]
        audit_chain_service=audit,
    )

    created = await service.create(
        provider=PagingProvider.pagerduty,
        integration_key_ref="incident-response/integrations/pagerduty-primary",
        alert_severity_mapping={"critical": "P1"},
    )
    await service.disable(created.id)
    await service.update_severity_mapping(created.id, {"warning": "P3"})
    await service.delete(created.id)

    assert len(audit.entries) == 4
    canonical_payloads = b"".join(entry[2] for entry in audit.entries)
    assert str(created.id).encode() in canonical_payloads
    assert b"credential-value" not in canonical_payloads


@pytest.mark.asyncio
async def test_admin_integration_failed_audit_write_propagates() -> None:
    service = IntegrationService(
        repository=MemoryIncidentRepository(),  # type: ignore[arg-type]
        secret_provider=SecretProvider(),  # type: ignore[arg-type]
        audit_chain_service=FailingAudit(),
    )

    with pytest.raises(RuntimeError, match="audit unavailable"):
        await service.create(
            provider=PagingProvider.pagerduty,
            integration_key_ref="incident-response/integrations/pagerduty-primary",
            alert_severity_mapping={"critical": "P1"},
        )
