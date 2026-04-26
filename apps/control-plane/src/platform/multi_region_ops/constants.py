from __future__ import annotations

REGION_ROLES = ("primary", "secondary")
REPLICATION_COMPONENTS = (
    "postgres",
    "kafka",
    "s3",
    "clickhouse",
    "qdrant",
    "neo4j",
    "opensearch",
)
REPLICATION_HEALTH = ("healthy", "degraded", "unhealthy", "paused")
MAINTENANCE_STATUSES = ("scheduled", "active", "completed", "cancelled")
FAILOVER_PLAN_STEP_KINDS = (
    "promote_postgres",
    "flip_kafka_mirrormaker",
    "update_dns",
    "verify_health",
    "drain_workers",
    "resume_workers",
    "cutover_s3",
    "cutover_clickhouse",
    "cutover_qdrant",
    "cutover_neo4j",
    "cutover_opensearch",
    "custom",
)
FAILOVER_PLAN_RUN_KINDS = ("rehearsal", "production")
FAILOVER_PLAN_RUN_OUTCOMES = ("succeeded", "failed", "aborted", "in_progress")

KAFKA_TOPIC = "multi_region_ops.events"

REGION_REPLICATION_LAG_EVENT = "region.replication.lag"
REGION_FAILOVER_INITIATED_EVENT = "region.failover.initiated"
REGION_FAILOVER_COMPLETED_EVENT = "region.failover.completed"
MAINTENANCE_MODE_ENABLED_EVENT = "maintenance.mode.enabled"
MAINTENANCE_MODE_DISABLED_EVENT = "maintenance.mode.disabled"

REDIS_KEY_ACTIVE_WINDOW = "multi_region:active_window"
REDIS_KEY_FAILOVER_LOCK_TEMPLATE = "multi_region:failover_lock:{from_region}:{to_region}"
REDIS_KEY_REPLICATION_FINGERPRINT_TEMPLATE = (
    "multi_region:rpo_fingerprint:{component}:{source}:{target}"
)

ACTIVE_ACTIVE_RUNBOOK_PATH = "deploy/runbooks/active-active-considerations.md"
