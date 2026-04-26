from __future__ import annotations

from datetime import UTC, datetime
from platform.multi_region_ops.constants import REPLICATION_COMPONENTS, REPLICATION_HEALTH
from platform.multi_region_ops.models import RegionConfig
from typing import Protocol

from pydantic import BaseModel, Field, field_validator


class ReplicationMeasurement(BaseModel):
    component: str
    lag_seconds: int | None = None
    health: str
    pause_reason: str | None = None
    error_detail: str | None = None
    measured_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("component")
    @classmethod
    def _known_component(cls, value: str) -> str:
        if value not in REPLICATION_COMPONENTS:
            raise ValueError(f"Unknown replication component: {value}")
        return value

    @field_validator("health")
    @classmethod
    def _known_health(cls, value: str) -> str:
        if value not in REPLICATION_HEALTH:
            raise ValueError(f"Unknown replication health: {value}")
        return value


class ReplicationProbe(Protocol):
    component: str

    async def measure(
        self,
        *,
        source: RegionConfig,
        target: RegionConfig,
    ) -> ReplicationMeasurement: ...


class ReplicationProbeRegistry:
    def __init__(self) -> None:
        self._probes: dict[str, ReplicationProbe] = {}

    def register(self, probe: ReplicationProbe) -> None:
        self._probes[probe.component] = probe

    def get(self, component: str) -> ReplicationProbe | None:
        return self._probes.get(component)

    def components(self) -> tuple[str, ...]:
        return tuple(self._probes)

    def items(self) -> tuple[tuple[str, ReplicationProbe], ...]:
        return tuple(self._probes.items())

    def missing_components(self) -> tuple[str, ...]:
        return tuple(
            component for component in REPLICATION_COMPONENTS if component not in self._probes
        )
