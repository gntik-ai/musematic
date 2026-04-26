from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.generic import NamedNoopStepAdapter


class UpdateDnsStepAdapter(NamedNoopStepAdapter):
    def __init__(self) -> None:
        super().__init__("update_dns", "Update DNS")
