# Contract: Neo4j Cluster Infrastructure

**Feature**: 006-neo4j-knowledge-graph  
**Date**: 2026-04-09  
**Type**: Kubernetes infrastructure contract

---

## Overview

The Neo4j cluster is a Kubernetes-managed graph database deployed in the `platform-data` namespace. It provides Bolt protocol access on port 7687 for all platform services in authorized namespaces.

---

## Deployment Contract

### Helm Chart

| Property | Value |
|---------|-------|
| Chart location | `deploy/helm/neo4j/` |
| Base chart | `neo4j/neo4j` (official, pinned version) |
| Release name | `musematic-neo4j` |
| Namespace | `platform-data` |

### Production Mode

```bash
helm install musematic-neo4j deploy/helm/neo4j \
  -n platform-data \
  -f deploy/helm/neo4j/values.yaml \
  -f deploy/helm/neo4j/values-prod.yaml \
  --create-namespace
```

**Post-deploy state**:
- 3 pods running in `platform-data`: 1 leader + 2 followers
- `kubectl get pods -n platform-data -l app.kubernetes.io/name=neo4j` → 3 pods `Running`
- Schema init Job completes successfully within 5 minutes
- Bolt port 7687 accepts connections from `platform-control`

### Development Mode

```bash
helm install musematic-neo4j deploy/helm/neo4j \
  -n platform-data \
  -f deploy/helm/neo4j/values.yaml \
  -f deploy/helm/neo4j/values-dev.yaml \
  --create-namespace
```

**Post-deploy state**:
- 1 pod running in `platform-data` (Community Edition)
- Schema init Job completes successfully within 2 minutes
- Bolt port 7687 accepts connections

---

## Network Policy Contract

### Allowed Ingress

| Source Namespace | Port | Protocol | Purpose |
|-----------------|------|----------|---------|
| `platform-control` | 7687 | TCP | Application Bolt queries |
| `platform-execution` | 7687 | TCP | Execution Bolt queries |
| `platform-control` | 7474 | TCP | Admin browser access |
| `platform-observability` | 7474 | TCP | Prometheus metrics scrape |
| `platform-data` (self) | 5000, 7000, 7687 | TCP | Causal cluster inter-pod |

### Denied Ingress

All other namespaces (including `default`) are blocked.

---

## Secret Contract

| Secret Name | Namespace | Key | Description |
|------------|-----------|-----|-------------|
| `neo4j-credentials` | `platform-data` | `NEO4J_PASSWORD` | Neo4j `neo4j` user password |

Platform services read the password from this Secret and inject it into the driver connection string: `bolt://neo4j:<password>@musematic-neo4j.platform-data:7687`.

---

## Schema Init Contract

The schema init Job (`neo4j-schema-init`) runs as a Helm post-install/post-upgrade hook.

**Completion criteria**:
1. Job exits 0
2. All 5 uniqueness constraints exist: `agent_id`, `workflow_id`, `fleet_id`, `hypothesis_id`, `memory_id`
3. All 3 performance indexes exist: `memory_workspace`, `evidence_hypothesis`, `relationship_type`

**Idempotency**: Re-running on upgrade produces no errors and no duplicate schema objects.

---

## Backup Contract

| Property | Value |
|---------|-------|
| CronJob name | `neo4j-backup` |
| Namespace | `platform-data` |
| Schedule | `0 3 * * *` (daily at 03:00 UTC, configurable) |
| Output path | `s3://backups/neo4j/{YYYY-MM-DD}/neo4j.dump` |
| Max duration | 15 minutes for up to 10M nodes |
| Restore method | `neo4j-admin database load` (manual, documented in quickstart) |

---

## Health and Metrics Contract

| Endpoint | Port | Path | Description |
|---------|------|------|-------------|
| Prometheus metrics | 7474 | `/metrics` | Neo4j JVM, query, transaction metrics |
| Admin browser | 7474 | `/browser` | Neo4j Browser UI |
| Bolt readiness | 7687 | (TCP connect) | Application connectivity check |

**Monitored metrics**:
- `neo4j_database_transaction_active_total` — active transactions
- `neo4j_database_query_execution_latency_millis` — query latency
- `neo4j_causal_clustering_role` — cluster role (leader/follower)
- `neo4j_database_store_size_total_bytes` — storage usage
- `neo4j_vm_memory_used_bytes` — JVM heap usage

---

## Service Discovery

| Internal DNS | Port | Purpose |
|-------------|------|---------|
| `musematic-neo4j.platform-data.svc.cluster.local` | 7687 | Bolt (application) |
| `musematic-neo4j.platform-data.svc.cluster.local` | 7474 | HTTP admin |
