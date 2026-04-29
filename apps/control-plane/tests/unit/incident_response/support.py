from __future__ import annotations

from datetime import UTC, datetime
from platform.incident_response.services.providers.base import ProviderRef
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4


def make_integration(
    *,
    provider: str = "pagerduty",
    enabled: bool = True,
    mapping: dict[str, str] | None = None,
    integration_id: UUID | None = None,
    key_ref: str | None = None,
) -> SimpleNamespace:
    now = datetime.now(UTC)
    resolved_id = integration_id or uuid4()
    return SimpleNamespace(
        id=resolved_id,
        provider=provider,
        integration_key_ref=key_ref or f"incident-response/integrations/{resolved_id}",
        enabled=enabled,
        alert_severity_mapping=mapping or {
            "critical": "critical",
            "high": "high",
            "warning": "warning",
            "info": "info",
        },
        created_at=now,
        updated_at=now,
    )


def make_incident(
    *,
    incident_id: UUID | None = None,
    condition_fingerprint: str = "rule:workspace",
    severity: str = "critical",
    status: str = "open",
    related_event_ids: list[UUID] | None = None,
    related_executions: list[UUID] | None = None,
    runbook_scenario: str | None = "kafka_lag",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=incident_id or uuid4(),
        condition_fingerprint=condition_fingerprint,
        severity=severity,
        status=status,
        title="Kafka lag above threshold",
        description="Consumer group lag has exceeded the on-call threshold.",
        triggered_at=datetime.now(UTC),
        resolved_at=None,
        related_executions=related_executions or [],
        related_event_ids=related_event_ids or [],
        runbook_scenario=runbook_scenario,
        alert_rule_class="kafka_lag",
        post_mortem_id=None,
    )


class RecordingProducer:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []

    async def publish(self, **payload: Any) -> None:
        self.messages.append(payload)


class RecordingSecretProvider:
    def __init__(self, value: str = "provider-secret") -> None:
        self.value = value
        self.calls: list[str] = []

    async def get_current(self, path: str) -> str:
        self.calls.append(path)
        return self.value


class RecordingProviderClient:
    def __init__(self) -> None:
        self.created: list[dict[str, Any]] = []
        self.resolved: list[dict[str, Any]] = []

    async def create_alert(self, **kwargs: Any) -> ProviderRef:
        self.created.append(kwargs)
        return ProviderRef(
            provider_reference=f"provider-{kwargs['incident'].id}",
            native_metadata={"ok": True},
        )

    async def resolve_alert(self, **kwargs: Any) -> None:
        self.resolved.append(kwargs)
