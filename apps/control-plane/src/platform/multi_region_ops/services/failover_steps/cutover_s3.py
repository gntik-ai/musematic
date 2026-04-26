from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.generic import NamedNoopStepAdapter


class CutoverS3StepAdapter(NamedNoopStepAdapter):
    def __init__(self) -> None:
        super().__init__("cutover_s3", "Cut over S3-compatible storage")
