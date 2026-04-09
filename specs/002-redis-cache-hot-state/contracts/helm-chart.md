# Contract: Redis Helm Chart Interface

**Feature**: 002-redis-cache-hot-state  
**Date**: 2026-04-09  
**Type**: Infrastructure — consumed by platform operators

---

## Overview

The `deploy/helm/redis/` chart wraps the Bitnami `redis-cluster` chart as a dependency and adds a custom `NetworkPolicy` and credentials `Secret`.

---

## Chart Values Contract

### Required Values

| Key | Type | Description |
|-----|------|-------------|
| `auth.password` | `string` | Redis password (or use `existingSecret`) |

### Optional Values with Defaults

| Key | Default (prod) | Default (dev) | Description |
|-----|----------------|---------------|-------------|
| `cluster.nodes` | `6` | `1` | Total cluster nodes |
| `cluster.replicas` | `1` | `0` | Replicas per master |
| `persistence.size` | `"100Gi"` | `"10Gi"` | PVC size |
| `redis.maxmemory` | `"4Gi"` | `"1Gi"` | Maximum memory |
| `redis.maxmemoryPolicy` | `"allkeys-lru"` | `"allkeys-lru"` | Eviction policy |
| `resources.requests.cpu` | `"1000m"` | `"250m"` | CPU request |
| `resources.requests.memory` | `"2Gi"` | `"512Mi"` | Memory request |
| `metrics.enabled` | `true` | `false` | redis-exporter sidecar |
| `networkPolicy.enabled` | `true` | `false` | Restrict access by namespace |

---

## Cluster Topology Contract

### Production

- **Nodes**: 6 (3 masters + 3 replicas)
- **Mode**: Redis Cluster with 16384 hash slots
- **Persistence**: AOF enabled (`appendonly yes`, `appendfsync everysec`)
- **Failover**: Automatic, target SLA <10 seconds (`cluster-node-timeout: 15000`)
- **PDB**: `maxUnavailable: 1`
- **Metrics**: redis-exporter sidecar on port 9121
- **Network policy**: Ingress from `platform-control` and `platform-execution` only

### Development

- **Nodes**: 1 (standalone, no cluster mode)
- **Persistence**: AOF enabled
- **Failover**: N/A
- **PDB**: Disabled
- **Metrics**: Disabled
- **Network policy**: Disabled

---

## Kubernetes Resources Created

| Resource | Kind | Production | Development |
|----------|------|-----------|-------------|
| `musematic-redis-cluster` | `StatefulSet` | 6 pods | 1 pod |
| `redis-credentials` | `Secret` | Yes | Yes |
| `redis-cluster-netpol` | `NetworkPolicy` | Yes | No |
| `musematic-redis-cluster-metrics` | `ServiceMonitor` | Yes | No |

---

## Service Endpoints

| Service | Port | Usage |
|---------|------|-------|
| `musematic-redis-cluster:6379` | 6379 | Client connections (cluster-aware) |
| `musematic-redis-cluster-headless:6379` | 6379 | Pod-to-pod cluster gossip |
| `musematic-redis-cluster-metrics:9121` | 9121 | Prometheus metrics |

---

## Deployment Commands

```bash
# Production
helm install musematic-redis deploy/helm/redis \
  -n platform-data --create-namespace \
  -f deploy/helm/redis/values.yaml \
  -f deploy/helm/redis/values-prod.yaml

# Development
helm install musematic-redis deploy/helm/redis \
  -n platform-data --create-namespace \
  -f deploy/helm/redis/values.yaml \
  -f deploy/helm/redis/values-dev.yaml
```

---

## Observability Contract

When `metrics.enabled: true`:

- `redis_up` — gauge, 1 when reachable
- `redis_memory_used_bytes` — current memory usage
- `redis_memory_max_bytes` — configured maxmemory
- `redis_connected_clients` — active connections
- `redis_total_commands_processed_total` — command throughput
- `redis_keyspace_hits_total` / `redis_keyspace_misses_total` — cache hit ratio
- `redis_replication_offset` — replication lag

**Alert thresholds**:
- Memory > 80% of `maxmemory` → warning
- `redis_up == 0` → critical
- Replication lag > 10s → warning
