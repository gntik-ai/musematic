# Contract: PostgreSQL Helm Chart Interface

**Feature**: 001-postgresql-schema-foundation  
**Date**: 2026-04-09  
**Type**: Infrastructure — consumed by platform operators

---

## Overview

The `deploy/helm/postgresql` chart is the single point of deployment for the PostgreSQL cluster, PgBouncer pooler, and associated monitoring resources in both production and development environments.

---

## Chart Values Contract

### Required Values

| Key | Type | Description |
|-----|------|-------------|
| `environment` | `string` | `"production"` or `"development"` |
| `storage.storageClass` | `string` | Kubernetes storage class name |

### Optional Values with Defaults

| Key | Default | Description |
|-----|---------|-------------|
| `storage.size` | `"100Gi"` (prod), `"10Gi"` (dev) | PVC size |
| `resources.requests.cpu` | `"1000m"` (prod), `"250m"` (dev) | CPU request |
| `resources.requests.memory` | `"2Gi"` (prod), `"512Mi"` (dev) | Memory request |
| `postgresql.maxConnections` | `"200"` | `max_connections` PostgreSQL parameter |
| `pgbouncer.maxClientConn` | `1000` | PgBouncer `max_client_conn` (production only) |
| `pgbouncer.maxDbConnections` | `200` | PgBouncer `max_db_connections` (production only) |
| `monitoring.enabled` | `true` (prod), `false` (dev) | Deploy pg_exporter + PodMonitor |

---

## Cluster Topology Contract

### Production (`environment: production`)

- **Instances**: 3 (1 primary + 2 synchronous replicas)
- **Failover**: Automatic, target SLA ≤ 30 seconds
- **Pooler**: CNPG Pooler CRD deployed with 2 replicas (transaction mode)
- **PDB**: `maxUnavailable: 1` on cluster pods
- **Monitoring**: pg_exporter sidecar auto-deployed; PodMonitor created

### Development (`environment: development`)

- **Instances**: 1 (single primary, no replicas)
- **Pooler**: Not deployed
- **PDB**: Not deployed
- **Monitoring**: Disabled

---

## Kubernetes Resources Created

| Resource | Kind | Production | Development |
|----------|------|-----------|-------------|
| `musematic-postgres` | `Cluster` (CNPG) | 3 instances | 1 instance |
| `musematic-pooler` | `Pooler` (CNPG) | Yes (2 replicas) | No |
| `musematic-postgres-pdb` | `PodDisruptionBudget` | Yes | No |
| `postgres-credentials` | `Secret` | Yes | Yes |

---

## Service Endpoints Contract

| Service | Port | Target | Usage |
|---------|------|--------|-------|
| `musematic-postgres-rw` | 5432 | Primary pod | Migrations, admin |
| `musematic-postgres-ro` | 5432 | Replica pods | Read-only queries (optional) |
| `musematic-pooler` | 5432 | PgBouncer | All application traffic (prod) |

---

## Observability Contract

When `monitoring.enabled: true`:

- `pg_up` — gauge, 1 when PostgreSQL is reachable
- `pg_stat_activity_count` — gauge, active connections by state
- `pg_replication_*` — lag and slot metrics for each replica

Prometheus must be configured to scrape the auto-created `PodMonitor` in the `platform-data` namespace.

---

## Upgrade Contract

- `helm upgrade` with the same values is idempotent
- Changing `instances` from 1 to 3 triggers a rolling addition of replicas (no downtime)
- Changing `storage.size` requires manual PVC resize (not handled by Helm)
