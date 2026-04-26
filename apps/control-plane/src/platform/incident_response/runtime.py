from __future__ import annotations

from platform.audit.dependencies import build_audit_chain_service
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.producer import EventProducer
from platform.incident_response.dependencies import build_incident_service, build_runbook_service
from platform.incident_response.schemas import IncidentRef, IncidentSignal
from platform.incident_response.services.providers.opsgenie import OpsGenieClient
from platform.incident_response.services.providers.pagerduty import PagerDutyClient
from platform.incident_response.services.providers.victorops import VictorOpsClient
from platform.security_compliance.providers.rotatable_secret_provider import RotatableSecretProvider
from typing import Any, cast


class AppIncidentTrigger:
    def __init__(self, app: Any) -> None:
        self.app = app

    async def fire(self, signal: IncidentSignal) -> IncidentRef:
        settings = cast(PlatformSettings, self.app.state.settings)
        redis_client = cast(AsyncRedisClient | None, self.app.state.clients.get("redis"))
        producer = cast(EventProducer | None, self.app.state.clients.get("kafka"))
        async with database.AsyncSessionLocal() as session:
            audit_chain = build_audit_chain_service(
                session=session,
                settings=settings,
                producer=producer,
            )
            runbook_service = build_runbook_service(
                session=session,
                settings=settings,
                audit_chain_service=audit_chain,
            )
            secret_provider = RotatableSecretProvider(
                settings=settings,
                redis_client=redis_client,
            )
            timeout = settings.incident_response.external_alert_request_timeout_seconds
            incident_service = build_incident_service(
                session=session,
                settings=settings,
                redis_client=redis_client,
                producer=producer,
                provider_clients={
                    "pagerduty": PagerDutyClient(
                        secret_provider=secret_provider,
                        timeout_seconds=timeout,
                    ),
                    "opsgenie": OpsGenieClient(
                        secret_provider=secret_provider,
                        timeout_seconds=timeout,
                    ),
                    "victorops": VictorOpsClient(
                        secret_provider=secret_provider,
                        timeout_seconds=timeout,
                    ),
                },
                runbook_service=runbook_service,
                audit_chain_service=audit_chain,
            )
            result = await incident_service.create_from_signal(signal)
            await session.commit()
            return result
