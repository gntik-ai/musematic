from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.generic import NamedNoopStepAdapter


class FlipKafkaMirrorMakerStepAdapter(NamedNoopStepAdapter):
    def __init__(self) -> None:
        super().__init__("flip_kafka_mirrormaker", "Flip Kafka MirrorMaker")
