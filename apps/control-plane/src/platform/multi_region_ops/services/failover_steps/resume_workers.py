from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.generic import NamedNoopStepAdapter


class ResumeWorkersStepAdapter(NamedNoopStepAdapter):
    def __init__(self) -> None:
        super().__init__("resume_workers", "Resume workers")
