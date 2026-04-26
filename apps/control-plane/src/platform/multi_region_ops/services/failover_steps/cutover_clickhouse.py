from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.generic import NamedNoopStepAdapter


class CutoverClickHouseStepAdapter(NamedNoopStepAdapter):
    def __init__(self) -> None:
        super().__init__("cutover_clickhouse", "Cut over ClickHouse")
