# Planning Input — Multi-Region High-Availability Deployment

> Verbatim brownfield input that motivated this spec. Preserved here as a
> planning artifact. The implementation strategy (specific tables,
> services, schemas, code-level integration points, Helm chart shape) is
> intentionally deferred to the planning phase. This file is a planning
> input, not a contract.

## Brownfield Context
**New bounded context:** `multi_region_ops/`
**Modifies:** Helm charts, runbooks, `deploy/`
**FRs:** FR-478, FR-479, FR-480, FR-481, FR-482

## Summary
Add multi-region active-passive deployment support with documented replication for all data stores, active-active considerations documentation, zero-downtime upgrade procedures, maintenance mode, and capacity planning.

## Database Changes (planning input — not a contract)
```sql
CREATE TABLE region_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    region_code VARCHAR(32) NOT NULL UNIQUE,
    region_role VARCHAR(16) NOT NULL, -- primary, secondary
    endpoint_urls JSONB NOT NULL,
    rpo_target_minutes INTEGER DEFAULT 15,
    rto_target_minutes INTEGER DEFAULT 60,
    enabled BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE replication_statuses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_region VARCHAR(32) NOT NULL,
    target_region VARCHAR(32) NOT NULL,
    component VARCHAR(64) NOT NULL, -- postgres, kafka, s3, clickhouse, qdrant, neo4j, opensearch
    lag_seconds INTEGER,
    status VARCHAR(32) NOT NULL,
    measured_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE failover_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(256) NOT NULL,
    from_region VARCHAR(32) NOT NULL,
    to_region VARCHAR(32) NOT NULL,
    steps JSONB NOT NULL,
    tested_at TIMESTAMPTZ,
    last_executed_at TIMESTAMPTZ
);

CREATE TABLE maintenance_windows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    reason TEXT,
    blocks_writes BOOLEAN NOT NULL DEFAULT true,
    announcement_text TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'scheduled'
);
```

## New Files
- `multi_region_ops/` bounded context
- `multi_region_ops/services/region_service.py` — region config CRUD
- `multi_region_ops/services/replication_monitor.py` — polls replication lag per component, emits alerts on drift
- `multi_region_ops/services/failover_service.py` — failover orchestration
- `multi_region_ops/services/maintenance_mode_service.py` — schedule, enable, disable, drain
- `multi_region_ops/middleware/maintenance_gate.py` — FastAPI middleware that rejects writes during maintenance

## New Helm Charts
- `deploy/helm/platform/values-multi-region.yaml` — overlay for secondary region
- `deploy/helm/platform/templates/replication-jobs/` — PostgreSQL streaming, Kafka MirrorMaker, S3 cross-region, ClickHouse replication
- `deploy/runbooks/failover.md` — documented procedure
- `deploy/runbooks/zero-downtime-upgrade.md` — expand-migrate-contract pattern

## Acceptance Criteria
- [ ] Secondary region deployable via Helm overlay
- [ ] Replication lag visible on operator dashboard
- [ ] RPO/RTO alerts fire when thresholds exceeded
- [ ] Failover tested quarterly via runbook
- [ ] Maintenance mode blocks writes with graceful in-flight completion
- [ ] Zero-downtime upgrade procedure documented
- [ ] Capacity planning signals on operator dashboard
