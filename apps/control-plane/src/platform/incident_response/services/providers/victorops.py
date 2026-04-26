from __future__ import annotations

from datetime import datetime
from platform.incident_response.models import Incident, IncidentIntegration
from platform.incident_response.services.providers.base import BaseHttpPagingProvider, ProviderRef
from urllib.parse import quote


class VictorOpsClient(BaseHttpPagingProvider):
    provider = "victorops"
    base_url = "https://alert.victorops.com/integrations/generic/20131114/alert"

    async def create_alert(
        self,
        *,
        integration: IncidentIntegration,
        incident: Incident,
        mapped_severity: str,
    ) -> ProviderRef:
        routing_key, routing_name = _split_secret(await self._secret(integration))
        url = self._url(routing_key, routing_name)
        response = await self._post(
            url,
            json={
                "monitoring_tool": "musematic",
                "entity_id": str(incident.id),
                "state_message": incident.description,
                "state_start_time": _to_unix(incident.triggered_at),
                "message_type": _normalize_message_type(mapped_severity),
            },
        )
        return ProviderRef(
            provider_reference=str(response.get("entity_id") or incident.id),
            native_metadata=response,
        )

    async def resolve_alert(
        self,
        *,
        integration: IncidentIntegration,
        provider_reference: str,
    ) -> None:
        routing_key, routing_name = _split_secret(await self._secret(integration))
        await self._post(
            self._url(routing_key, routing_name),
            json={
                "monitoring_tool": "musematic",
                "entity_id": provider_reference,
                "message_type": "RECOVERY",
                "state_message": "Resolved in musematic",
            },
        )

    def _url(self, routing_key: str, routing_name: str) -> str:
        return f"{self.base_url}/{quote(routing_key, safe='')}/{quote(routing_name, safe='')}"


def _split_secret(secret: str) -> tuple[str, str]:
    routing_key, separator, routing_name = secret.partition(":")
    if not separator:
        return routing_key, "musematic"
    return routing_key, routing_name


def _normalize_message_type(mapped_severity: str) -> str:
    normalized = mapped_severity.upper()
    if normalized in {"CRITICAL", "WARNING", "INFO"}:
        return normalized
    if normalized in {"P1", "P2", "HIGH"}:
        return "CRITICAL"
    if normalized in {"P3", "P4", "WARNING"}:
        return "WARNING"
    return "INFO"


def _to_unix(value: datetime) -> int:
    return int(value.timestamp())
