from __future__ import annotations

from platform.incident_response.models import Incident, IncidentIntegration
from platform.incident_response.services.providers.base import BaseHttpPagingProvider, ProviderRef


class PagerDutyClient(BaseHttpPagingProvider):
    provider = "pagerduty"
    base_url = "https://events.pagerduty.com/v2/enqueue"

    async def create_alert(
        self,
        *,
        integration: IncidentIntegration,
        incident: Incident,
        mapped_severity: str,
    ) -> ProviderRef:
        routing_key = await self._secret(integration)
        payload = {
            "event_action": "trigger",
            "routing_key": routing_key,
            "dedup_key": str(incident.id),
            "payload": {
                "summary": incident.title,
                "source": "musematic",
                "severity": mapped_severity,
                "custom_details": {
                    "description": incident.description,
                    "related_executions": [str(item) for item in incident.related_executions],
                    "runbook_scenario": incident.runbook_scenario,
                },
            },
        }
        response = await self._post(self.base_url, json=payload)
        return ProviderRef(
            provider_reference=str(response.get("dedup_key") or incident.id),
            native_metadata=response,
        )

    async def resolve_alert(
        self,
        *,
        integration: IncidentIntegration,
        provider_reference: str,
    ) -> None:
        routing_key = await self._secret(integration)
        await self._post(
            self.base_url,
            json={
                "event_action": "resolve",
                "routing_key": routing_key,
                "dedup_key": provider_reference,
            },
        )
