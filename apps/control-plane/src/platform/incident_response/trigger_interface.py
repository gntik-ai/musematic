from __future__ import annotations

from platform.incident_response.schemas import IncidentRef, IncidentSignal
from typing import Protocol
from uuid import uuid4


class IncidentTriggerInterface(Protocol):
    """Single in-process contract for all incident-producing signal sources."""

    async def fire(self, signal: IncidentSignal) -> IncidentRef: ...


class NoopIncidentTrigger:
    async def fire(self, signal: IncidentSignal) -> IncidentRef:
        del signal
        return IncidentRef(
            incident_id=uuid4(),
            no_external_page_attempted=True,
        )


class ServiceIncidentTrigger:
    def __init__(self, service: object) -> None:
        self.service = service

    async def fire(self, signal: IncidentSignal) -> IncidentRef:
        create_from_signal = self.service.create_from_signal
        return await create_from_signal(signal)


_incident_trigger: IncidentTriggerInterface = NoopIncidentTrigger()


def register_incident_trigger(trigger: IncidentTriggerInterface) -> None:
    global _incident_trigger
    _incident_trigger = trigger


def reset_incident_trigger() -> None:
    register_incident_trigger(NoopIncidentTrigger())


def get_incident_trigger() -> IncidentTriggerInterface:
    return _incident_trigger
