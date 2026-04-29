from __future__ import annotations

from platform.common import database
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.logging import get_logger
from platform.security_compliance.repository import SecurityComplianceRepository
from platform.security_compliance.services.compliance_service import ComplianceService
from typing import Any

LOGGER = get_logger(__name__)

SECURITY_TOPICS: tuple[str, ...] = (
    "security.sbom.published",
    "security.scan.completed",
    "security.pentest.finding.raised",
    "security.secret.rotated",
    "security.jit.issued",
    "security.jit.revoked",
    "security.audit.chain.verified",
)


class ComplianceEvidenceConsumer:
    def __init__(self, settings: PlatformSettings, object_storage: Any | None = None) -> None:
        self.settings = settings
        self.object_storage = object_storage

    def register(self, manager: EventConsumerManager) -> None:
        for topic in SECURITY_TOPICS:
            manager.subscribe(
                topic,
                f"{self.settings.kafka.consumer_group}-compliance-evidence-{topic}",
                self.handle_event,
            )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        async with database.AsyncSessionLocal() as session:
            service = ComplianceService(
                SecurityComplianceRepository(session),
                self.settings,
                object_storage=self.object_storage,
            )
            try:
                entity_id = str(
                    envelope.payload.get("sbom_id")
                    or envelope.payload.get("scan_id")
                    or envelope.payload.get("finding_id")
                    or envelope.payload.get("schedule_id")
                    or envelope.payload.get("grant_id")
                    or envelope.correlation_context.correlation_id
                )
                await service.on_security_event(
                    evidence_type=envelope.event_type,
                    source=envelope.source,
                    entity_id=entity_id,
                    payload=envelope.payload,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Failed to collect compliance evidence")
