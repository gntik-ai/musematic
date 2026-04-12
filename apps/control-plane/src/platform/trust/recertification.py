from __future__ import annotations

from datetime import UTC, datetime
from platform.trust.events import (
    RecertificationTriggeredPayload,
    TrustEventPublisher,
    make_correlation,
    utcnow,
)
from platform.trust.models import (
    CertificationStatus,
    RecertificationTriggerStatus,
    RecertificationTriggerType,
    TrustCertification,
    TrustRecertificationTrigger,
)
from platform.trust.repository import TrustRepository
from platform.trust.schemas import (
    RecertificationTriggerListResponse,
    RecertificationTriggerResponse,
)
from typing import Any
from uuid import UUID


class RecertificationService:
    def __init__(
        self,
        *,
        repository: TrustRepository,
        settings: Any,
        producer: Any | None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.events = TrustEventPublisher(producer)

    async def create_trigger(
        self,
        agent_id: str,
        revision_id: str,
        trigger_type: RecertificationTriggerType,
        originating_event: dict[str, Any],
    ) -> RecertificationTriggerResponse | None:
        existing = await self.repository.get_pending_trigger(
            agent_id=agent_id,
            agent_revision_id=revision_id,
            trigger_type=trigger_type,
        )
        if existing is not None:
            return None
        trigger = await self.repository.create_trigger(
            TrustRecertificationTrigger(
                agent_id=agent_id,
                agent_revision_id=revision_id,
                trigger_type=trigger_type,
                originating_event_type=self._optional_text(originating_event.get("event_type")),
                originating_event_id=self._optional_text(originating_event.get("event_id")),
                original_certification_id=self._uuid_or_none(
                    originating_event.get("certification_id")
                ),
                status=RecertificationTriggerStatus.pending,
            )
        )
        return RecertificationTriggerResponse.model_validate(trigger)

    async def list_triggers(
        self, agent_id: str | None = None
    ) -> RecertificationTriggerListResponse:
        items = await self.repository.list_triggers(agent_id=agent_id)
        return RecertificationTriggerListResponse(
            items=[RecertificationTriggerResponse.model_validate(item) for item in items],
            total=len(items),
        )

    async def get_trigger(self, trigger_id: UUID) -> RecertificationTriggerResponse:
        item = await self.repository.get_trigger(trigger_id)
        if item is None:
            raise LookupError(str(trigger_id))
        return RecertificationTriggerResponse.model_validate(item)

    async def process_pending_triggers(self) -> int:
        processed = 0
        for trigger in await self.repository.list_pending_triggers():
            latest = await self.repository.get_latest_certification_for_agent(trigger.agent_id)
            agent_fqn = latest.agent_fqn if latest is not None else trigger.agent_id
            certification = await self.repository.create_certification(
                TrustCertification(
                    agent_id=trigger.agent_id,
                    agent_fqn=agent_fqn,
                    agent_revision_id=trigger.agent_revision_id,
                    status=CertificationStatus.pending,
                    issued_by="system:recertification",
                    created_by=None,
                    updated_by=None,
                )
            )
            trigger.status = RecertificationTriggerStatus.processed
            trigger.processed_at = datetime.now(UTC)
            trigger.new_certification_id = certification.id
            processed += 1
            await self.events.publish_recertification_triggered(
                RecertificationTriggeredPayload(
                    trigger_id=trigger.id,
                    agent_id=trigger.agent_id,
                    trigger_type=trigger.trigger_type.value,
                    new_certification_id=certification.id,
                    occurred_at=utcnow(),
                ),
                make_correlation(),
            )
        await self.repository.session.flush()
        return processed

    async def scan_expiry_approaching(self) -> int:
        days = int(
            getattr(
                getattr(self.settings, "trust", self.settings),
                "recertification_expiry_threshold_days",
                30,
            )
        )
        created = 0
        for certification in await self.repository.list_expiry_approaching_certifications(
            now=datetime.now(UTC),
            within_days=days,
        ):
            response = await self.create_trigger(
                certification.agent_id,
                certification.agent_revision_id,
                RecertificationTriggerType.expiry_approaching,
                {"certification_id": str(certification.id), "event_type": "expiry_approaching"},
            )
            if response is not None:
                created += 1
        return created

    async def handle_registry_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", event)
        agent_id = payload.get("agent_id")
        revision_id = payload.get("agent_revision_id") or payload.get("revision_id")
        if isinstance(agent_id, str) and isinstance(revision_id, str):
            await self.create_trigger(
                agent_id,
                revision_id,
                RecertificationTriggerType.revision_changed,
                {
                    "event_type": payload.get("event_type", "agent_revision.published"),
                    "event_id": payload.get("event_id"),
                },
            )

    async def handle_policy_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", event)
        agent_id = payload.get("agent_id")
        revision_id = payload.get("agent_revision_id") or payload.get("revision_id")
        if isinstance(agent_id, str) and isinstance(revision_id, str):
            await self.create_trigger(
                agent_id,
                revision_id,
                RecertificationTriggerType.policy_changed,
                {
                    "event_type": payload.get("event_type", "policy.updated"),
                    "event_id": payload.get("event_id"),
                },
            )

    async def handle_runtime_event(self, event: dict[str, Any]) -> None:
        payload = event.get("payload", event)
        agent_id = payload.get("agent_id")
        revision_id = payload.get("agent_revision_id") or payload.get("revision_id")
        if isinstance(agent_id, str) and isinstance(revision_id, str):
            await self.create_trigger(
                agent_id,
                revision_id,
                RecertificationTriggerType.conformance_failed,
                {
                    "event_type": payload.get("event_type", "execution.guardrail_failed"),
                    "event_id": payload.get("event_id"),
                },
            )

    @staticmethod
    def _uuid_or_none(value: Any) -> UUID | None:
        if value in {None, ""}:
            return None
        try:
            return UUID(str(value))
        except ValueError:
            return None

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value in {None, ""}:
            return None
        return str(value)
