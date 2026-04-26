from __future__ import annotations

from platform.incident_response.models import Incident, IncidentIntegration
from platform.incident_response.services.providers.base import BaseHttpPagingProvider, ProviderRef
from urllib.parse import quote


class OpsGenieClient(BaseHttpPagingProvider):
    provider = "opsgenie"
    base_url = "https://api.opsgenie.com/v2/alerts"

    async def create_alert(
        self,
        *,
        integration: IncidentIntegration,
        incident: Incident,
        mapped_severity: str,
    ) -> ProviderRef:
        api_key = await self._secret(integration)
        priority = _normalize_priority(mapped_severity)
        response = await self._post(
            self.base_url,
            headers={"Authorization": f"GenieKey {api_key}"},
            json={
                "message": incident.title,
                "alias": str(incident.id),
                "priority": priority,
                "description": incident.description,
                "details": {
                    "severity": incident.severity,
                    "runbook_scenario": incident.runbook_scenario or "",
                    "related_executions": ",".join(
                        str(item) for item in incident.related_executions
                    ),
                },
            },
        )
        request_id = response.get("requestId") or response.get("id") or incident.id
        return ProviderRef(provider_reference=str(request_id), native_metadata=response)

    async def resolve_alert(
        self,
        *,
        integration: IncidentIntegration,
        provider_reference: str,
    ) -> None:
        api_key = await self._secret(integration)
        alias = quote(provider_reference, safe="")
        await self._post(
            f"{self.base_url}/{alias}/close?identifierType=alias",
            headers={"Authorization": f"GenieKey {api_key}"},
            json={"note": "Resolved in musematic"},
        )


def _normalize_priority(mapped_severity: str) -> str:
    normalized = mapped_severity.upper()
    if normalized in {"P1", "P2", "P3", "P4", "P5"}:
        return normalized
    mapping = {
        "CRITICAL": "P1",
        "HIGH": "P2",
        "WARNING": "P3",
        "INFO": "P5",
    }
    return mapping.get(normalized, "P3")
