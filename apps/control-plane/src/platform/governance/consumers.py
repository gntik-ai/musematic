from __future__ import annotations

import logging
from platform.common import database
from platform.common.clients.redis import AsyncRedisClient
from platform.common.config import PlatformSettings
from platform.common.events.consumer import EventConsumerManager
from platform.common.events.envelope import EventEnvelope
from platform.common.events.producer import EventProducer
from platform.governance.dependencies import (
    build_enforcer_service,
    build_judge_service,
    build_pipeline_config_service,
)
from platform.governance.events import GovernanceEventType, VerdictIssuedPayload
from platform.governance.models import VerdictType
from platform.governance.repository import GovernanceRepository
from platform.registry.service import RegistryService
from uuid import UUID

LOGGER = logging.getLogger(__name__)


class ObserverSignalConsumer:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        redis_client: AsyncRedisClient,
        producer: EventProducer | None,
        registry_service: RegistryService | None,
    ) -> None:
        self.settings = settings
        self.redis_client = redis_client
        self.producer = producer
        self.registry_service = registry_service

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            "monitor.alerts",
            f"{self.settings.kafka.consumer_group}.governance-observer-signals",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        fleet_id = envelope.correlation_context.fleet_id or _uuid_or_none(
            envelope.payload.get("fleet_id")
        )
        workspace_id = envelope.correlation_context.workspace_id or _uuid_or_none(
            envelope.payload.get("workspace_id")
        )
        if fleet_id is None and workspace_id is None:
            return
        async with database.AsyncSessionLocal() as session:
            service = build_judge_service(
                session=session,
                settings=self.settings,
                producer=self.producer,
                redis_client=self.redis_client,
                registry_service=self.registry_service,
            )
            try:
                await service.process_signal(envelope, fleet_id, workspace_id)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Failed to process governance observer signal")


class VerdictConsumer:
    def __init__(
        self,
        *,
        settings: PlatformSettings,
        producer: EventProducer | None,
        registry_service: RegistryService | None,
    ) -> None:
        self.settings = settings
        self.producer = producer
        self.registry_service = registry_service

    def register(self, manager: EventConsumerManager) -> None:
        manager.subscribe(
            "governance.events",
            f"{self.settings.kafka.consumer_group}.governance-verdict-enforcer",
            self.handle_event,
        )

    async def handle_event(self, envelope: EventEnvelope) -> None:
        if envelope.event_type != GovernanceEventType.verdict_issued.value:
            return
        payload = VerdictIssuedPayload.model_validate(envelope.payload)
        async with database.AsyncSessionLocal() as session:
            repo = GovernanceRepository(session)
            verdict = await repo.get_verdict(payload.verdict_id)
            if verdict is None:
                return
            pipeline_config = build_pipeline_config_service(
                session=session,
                registry_service=self.registry_service,
            )
            chain = await pipeline_config.resolve_chain(verdict.fleet_id, verdict.workspace_id)
            if chain is None:
                return
            if (
                verdict.verdict_type is VerdictType.COMPLIANT
                and verdict.verdict_type.value not in chain.verdict_to_action_mapping
            ):
                return
            service = build_enforcer_service(
                session=session,
                settings=self.settings,
                producer=self.producer,
            )
            try:
                await service.process_verdict(verdict, chain)
                await session.commit()
            except Exception:
                await session.rollback()
                LOGGER.exception("Failed to process governance verdict")


def _uuid_or_none(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError:
        return None
