from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.base import NoopStepAdapter


class CustomStepAdapter(NoopStepAdapter):
    kind = "custom"
    default_name = "Custom operator step"
