"""Failover step adapter registry."""

from __future__ import annotations

from platform.multi_region_ops.services.failover_steps.base import FailoverStepAdapter
from platform.multi_region_ops.services.failover_steps.custom import CustomStepAdapter
from platform.multi_region_ops.services.failover_steps.cutover_clickhouse import (
    CutoverClickHouseStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.cutover_neo4j import (
    CutoverNeo4jStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.cutover_opensearch import (
    CutoverOpenSearchStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.cutover_qdrant import (
    CutoverQdrantStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.cutover_s3 import CutoverS3StepAdapter
from platform.multi_region_ops.services.failover_steps.drain_workers import DrainWorkersStepAdapter
from platform.multi_region_ops.services.failover_steps.flip_kafka_mirrormaker import (
    FlipKafkaMirrorMakerStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.promote_postgres import (
    PromotePostgresStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.resume_workers import (
    ResumeWorkersStepAdapter,
)
from platform.multi_region_ops.services.failover_steps.update_dns import UpdateDnsStepAdapter
from platform.multi_region_ops.services.failover_steps.verify_health import VerifyHealthStepAdapter


def default_step_adapters() -> dict[str, FailoverStepAdapter]:
    adapters: list[FailoverStepAdapter] = [
        PromotePostgresStepAdapter(),
        FlipKafkaMirrorMakerStepAdapter(),
        UpdateDnsStepAdapter(),
        VerifyHealthStepAdapter(),
        DrainWorkersStepAdapter(),
        ResumeWorkersStepAdapter(),
        CutoverS3StepAdapter(),
        CutoverClickHouseStepAdapter(),
        CutoverQdrantStepAdapter(),
        CutoverNeo4jStepAdapter(),
        CutoverOpenSearchStepAdapter(),
        CustomStepAdapter(),
    ]
    return {adapter.kind: adapter for adapter in adapters}
