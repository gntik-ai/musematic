# Contract: ClickHouse Analytics Cluster Infrastructure

**Feature**: 007-clickhouse-analytics  
**Date**: 2026-04-10  
**Type**: Kubernetes infrastructure contract

---

## Overview

The ClickHouse analytics cluster is a Kubernetes-managed OLAP database deployed in the `platform-data` namespace. It provides HTTP access on port 8123 for application queries and native TCP on port 9000 for bulk inserts. ClickHouse Keeper provides replica coordination in production.

---

## Deployment Contract

### Helm Chart

| Property | Value |
|---------|-------|
| Chart location | `deploy/helm/clickhouse/` |
| Release name | `musematic-clickhouse` |
| Namespace | `platform-data` |

### Production Mode

```bash
helm install musematic-clickhouse deploy/helm/clickhouse \
  -n platform-data \
  -f deploy/helm/clickhouse/values.yaml \
  -f deploy/helm/clickhouse/values-prod.yaml \
  --create-namespace
```

**Post-deploy state**:
- 2 ClickHouse server pods running in `platform-data`
- 3 ClickHouse Keeper pods running in `platform-data`
- Schema init Job completes successfully within 5 minutes
- HTTP port 8123 accepts connections from `platform-control`

### Development Mode

```bash
helm install musematic-clickhouse deploy/helm/clickhouse \
  -n platform-data \
  -f deploy/helm/clickhouse/values.yaml \
  -f deploy/helm/clickhouse/values-dev.yaml \
  --create-namespace
```

**Post-deploy state**:
- 1 ClickHouse server pod running (no Keeper)
- Schema init Job completes successfully within 2 minutes

---

## Network Policy Contract

### Allowed Ingress

| Source Namespace | Port | Protocol | Purpose |
|-----------------|------|----------|---------|
| `platform-control` | 8123 | TCP | HTTP queries |
| `platform-control` | 9000 | TCP | Native bulk inserts |
| `platform-execution` | 8123 | TCP | HTTP queries |
| `platform-execution` | 9000 | TCP | Native bulk inserts |
| `platform-observability` | 8123 | TCP | Prometheus metrics scrape (`/metrics`) |
| `platform-data` (self) | 9000, 9009 | TCP | ClickHouse inter-replica |
| `platform-data` (self) | 9181, 9234, 9444 | TCP | Keeper client + Raft |

### Denied Ingress

All other namespaces (including `default`) are blocked.

---

## Secret Contract

| Secret Name | Namespace | Key | Description |
|------------|-----------|-----|-------------|
| `clickhouse-credentials` | `platform-data` | `CLICKHOUSE_PASSWORD` | ClickHouse `default` user password |

Platform services read the password and connect via: `http://default:<password>@musematic-clickhouse.platform-data:8123`.

---

## Schema Init Contract

The schema init Job (`clickhouse-schema-init`) runs as a Helm post-install/post-upgrade hook.

**Completion criteria**:
1. Job exits 0
2. All 4 base tables exist: `usage_events`, `behavioral_drift`, `fleet_performance`, `self_correction_analytics`
3. Rollup target table `usage_hourly` exists
4. Materialized view `usage_hourly_mv` exists and is active

**Idempotency**: All statements use `IF NOT EXISTS`. Safe to re-run on upgrade.

---

## Backup Contract

| Property | Value |
|---------|-------|
| CronJob name | `clickhouse-backup` |
| Namespace | `platform-data` |
| Schedule | `0 4 * * *` (daily at 04:00 UTC, configurable) |
| Image | `altinity/clickhouse-backup:2.5` |
| Output path | `s3://backups/clickhouse/{YYYY-MM-DD}/` |
| Max duration | 30 minutes for up to 100M rows |
| Restore method | `clickhouse-backup restore` (manual, documented in quickstart) |

---

## Health and Metrics Contract

| Endpoint | Port | Path | Description |
|---------|------|------|-------------|
| Prometheus metrics | 8123 | `/metrics` | ClickHouse server metrics |
| Play UI (query console) | 8123 | `/play` | Interactive query console |
| Health ping | 8123 | `/ping` | Returns `Ok.\n` if healthy |
| Readiness | 8123 | `/replicas_status` | Replica lag status |

**Monitored metrics**:
- `ClickHouseMetrics_Query` — active queries
- `ClickHouseMetrics_Merge` — active merges
- `ClickHouseProfileEvents_InsertedRows` — inserted rows
- `ClickHouseAsyncMetrics_ReplicasMaxQueueSize` — replication lag
- `ClickHouseMetrics_TCPConnection` — active TCP connections

---

## Service Discovery

| Internal DNS | Port | Purpose |
|-------------|------|---------|
| `musematic-clickhouse.platform-data.svc.cluster.local` | 8123 | HTTP (queries + metrics + Play UI) |
| `musematic-clickhouse.platform-data.svc.cluster.local` | 9000 | Native TCP (bulk inserts) |
| `musematic-clickhouse-keeper.platform-data.svc.cluster.local` | 9181 | Keeper client (internal only) |
