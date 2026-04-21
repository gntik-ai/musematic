# Helm Overlay Contract: `values-e2e.yaml`

**Feature**: 071-e2e-kind-testing
**Date**: 2026-04-20
**File**: `tests/e2e/cluster/values-e2e.yaml`

This overlay is the ONLY differentiator between an E2E deployment and a production deployment (SC-010, Reminder 26). It is passed to `helm install` via `-f values-e2e.yaml` and ONLY overrides keys below. Every other key inherits from `deploy/helm/platform/values.yaml`.

A chart-identity test in CI enumerates `tests/e2e/` and fails if any `Chart.yaml` is found — preventing future chart forks.

---

## Global

| Key | Production default | E2E override | Rationale |
|---|---|---|---|
| `global.environment` | `production` | `e2e` | Toggles environment-aware defaults downstream |
| `global.domain` | `platform.yourcompany.com` | `localhost` | Ingress + CORS configuration |

---

## Data stores (scaled to 16 GB runner budget)

### PostgreSQL (via CloudNativePG)

| Key | Production | E2E |
|---|---|---|
| `postgresql.replicaCount` | 3 | 1 |
| `postgresql.persistence.size` | 100 Gi | 2 Gi |
| `postgresql.resources.requests.memory` | 2 Gi | 256 Mi |
| `postgresql.resources.limits.memory` | 4 Gi | 512 Mi |
| `postgresql.extraUsers[0].name` | — | `e2e_reader` |
| `postgresql.extraUsers[0].grants` | — | `SELECT` on all platform tables |

### Redis (cluster disabled for E2E)

| Key | Production | E2E |
|---|---|---|
| `redis.replicaCount` | 6 (3 master + 3 replica) | 1 |
| `redis.cluster.enabled` | `true` | `false` |

**Note**: E2E uses Redis standalone (`REDIS_TEST_MODE=standalone`) — matches the existing CLAUDE.md convention for tests.

### Kafka (single broker, KRaft)

| Key | Production | E2E |
|---|---|---|
| `kafka.broker.count` | 3 | 1 |
| `kafka.broker.kraftMode` | `true` | `true` |
| `kafka.resources.requests.memory` | 4 Gi | 512 Mi |
| `kafka.resources.limits.memory` | 8 Gi | 1 Gi |

### Qdrant / Neo4j / ClickHouse / OpenSearch

All scaled to 1 replica. OpenSearch sets `discovery.type=single-node`.

| Key | Production | E2E |
|---|---|---|
| `qdrant.replicaCount` | 3 | 1 |
| `neo4j.replicaCount` | 3 (causal cluster) | 1 |
| `neo4j.persistence.size` | 50 Gi | 1 Gi |
| `clickhouse.replicaCount` | 3 | 1 |
| `opensearch.replicaCount` | 3 | 1 |
| `opensearch.config."discovery.type"` | (unset) | `single-node` |

### Object storage (MinIO in-cluster)

| Key | Production | E2E |
|---|---|---|
| `objectStorage.provider` | `s3` (or user choice) | `minio` |
| `objectStorage.minio.enabled` | `false` | `true` |
| `objectStorage.minio.replicas` | — | 1 |
| `objectStorage.minio.persistence.size` | — | 2 Gi |
| `objectStorage.s3Endpoint` | `https://s3.amazonaws.com` | `http://minio:9000` |
| `objectStorage.s3AccessKey` | (secret) | `minioadmin` |
| `objectStorage.s3SecretKey` | (secret) | `minioadmin` |

Note: The control-plane and satellite services use the SAME generic S3 client code regardless of provider (Principle XVI, Reminder 25). The E2E overlay just happens to point at an in-cluster MinIO.

---

## Control plane + satellites

| Key | Production | E2E |
|---|---|---|
| `controlPlane.replicaCount` | 3 per profile | 1 per profile |
| `controlPlane.profiles` | all 8 | `[api, scheduler, worker, websocket, context, reasoning, agentops, testing]` |
| `runtimeController.replicaCount` | 3 | 1 |
| `runtimeController.warmPool.enabled` | `true` | `true` |
| `runtimeController.warmPool.size` | 10 | 2 |
| `reasoningEngine.replicaCount` | 3 | 1 |
| `sandboxManager.replicaCount` | 2 | 1 |

**Resource budgets**: Each control-plane pod sized at `requests: {memory: 256 Mi, cpu: 100m}, limits: {memory: 512 Mi, cpu: 500m}`. Fits ~4 pods per worker node on the reference runner.

---

## UI + exposed endpoints

| Key | Production | E2E |
|---|---|---|
| `ui.replicaCount` | 3 | 1 |
| `ui.nodeEnv` | `production` | `development` |
| `ui.service.type` | `ClusterIP` (ingress-fronted) | `NodePort` |
| `ui.service.nodePort` | — | `30080` |
| `api.service.type` | `ClusterIP` | `NodePort` |
| `api.service.nodePort` | — | `30081` |
| `websocket.service.type` | `ClusterIP` | `NodePort` |
| `websocket.service.nodePort` | — | `30082` |

NodePorts are mapped to host ports via kind-config extraPortMappings (30080→8080, 30081→8081, 30082→8082).

---

## Features

| Key | Production default | E2E |
|---|---|---|
| `features.e2eMode` | `false` | `true` |
| `features.zeroTrustVisibility` | `false` (existing deployments) | `true` (catch regressions) |

**`features.e2eMode: true`** is the master switch:

- Sets `FEATURE_E2E_MODE=true` env var in control-plane pods.
- Creates `e2e-chaos-sa` ServiceAccount + Role in platform-execution + platform-data namespaces.
- Creates dedicated `e2e_reader` PostgreSQL user.
- Mounts the `/api/v1/_e2e/*` router.

**Safety check**: the control-plane pod startup refuses to boot with `features.e2eMode: true` if `global.environment == "production"` — a belt-and-suspenders guard against accidental enablement in prod.

---

## Mock LLM

| Key | Production | E2E |
|---|---|---|
| `mockLLM.enabled` | `false` | `true` |
| `mockLLM.defaultResponsesConfigMap` | — | `mock-llm-defaults` (created by chart when enabled) |

When `mockLLM.enabled: true`:

- Sets `MOCK_LLM_ENABLED=true` env var.
- Control-plane LLM router (`common/llm/router.py`) selects `MockLLMProvider`.
- ConfigMap `mock-llm-defaults` is mounted as `/etc/platform/mock-llm-defaults.json` with per-prompt-template defaults.

---

## Autoscaling

| Key | Production | E2E |
|---|---|---|
| `autoscaling.enabled` | `true` | `false` |

Disabling HPA gives predictable performance measurements (FR-014) and avoids flaky resource-pressure tests.

---

## Ingress

| Key | Production | E2E |
|---|---|---|
| `ingress.enabled` | `true` | `false` |

E2E uses NodePort services directly via kind port mappings — no ingress controller needed.

---

## Network Policies

Production applies default-deny NetworkPolicies per namespace. E2E inherits these — critical for Principle VII (simulation isolation) and Principle IX (zero-trust visibility) to exercise in tests.

---

## Complete `values-e2e.yaml` sketch

```yaml
global:
  environment: e2e
  domain: localhost

postgresql:
  replicaCount: 1
  persistence: { size: 2Gi }
  resources:
    requests: { memory: 256Mi, cpu: 100m }
    limits: { memory: 512Mi, cpu: 500m }
  extraUsers:
    - name: e2e_reader
      grants: "SELECT ON ALL TABLES IN SCHEMA public"

redis:
  replicaCount: 1
  cluster: { enabled: false }

kafka:
  broker: { count: 1, kraftMode: true }
  resources:
    requests: { memory: 512Mi, cpu: 200m }
    limits: { memory: 1Gi, cpu: 1 }

qdrant: { replicaCount: 1 }
neo4j: { replicaCount: 1, persistence: { size: 1Gi } }
clickhouse: { replicaCount: 1 }
opensearch:
  replicaCount: 1
  config: { "discovery.type": "single-node" }

objectStorage:
  provider: minio
  minio: { enabled: true, replicas: 1, persistence: { size: 2Gi } }
  s3Endpoint: http://minio:9000
  s3AccessKey: minioadmin
  s3SecretKey: minioadmin

controlPlane:
  replicaCount: 1
  profiles: [api, scheduler, worker, websocket, context, reasoning, agentops, testing]
runtimeController:
  replicaCount: 1
  warmPool: { enabled: true, size: 2 }
reasoningEngine: { replicaCount: 1 }
sandboxManager: { replicaCount: 1 }

ui:
  replicaCount: 1
  nodeEnv: development
  service: { type: NodePort, nodePort: 30080 }
api:
  service: { type: NodePort, nodePort: 30081 }
websocket:
  service: { type: NodePort, nodePort: 30082 }

features:
  e2eMode: true
  zeroTrustVisibility: true

mockLLM:
  enabled: true

autoscaling: { enabled: false }
ingress: { enabled: false }
```

---

## Chart-identity test (SC-010 enforcement)

```python
# tests/e2e/test_chart_identity.py
from pathlib import Path

def test_no_separate_chart_yaml_in_e2e():
    """SC-010: E2E must NOT have its own Helm chart — overlay only."""
    e2e_root = Path(__file__).parent
    offending = list(e2e_root.rglob("Chart.yaml"))
    assert not offending, f"Separate Chart.yaml found in tests/e2e/: {offending}"
```

This test runs in the pytest suite and fails the build if a chart ever appears.
