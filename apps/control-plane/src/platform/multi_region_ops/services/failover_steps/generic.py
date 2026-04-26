from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.base import NoopStepAdapter


class NamedNoopStepAdapter(NoopStepAdapter):
    def __init__(self, kind: str, default_name: str) -> None:
        self.kind = kind
        self.default_name = default_name
