# Data Model: Neo4j Knowledge Graph

**Feature**: 006-neo4j-knowledge-graph  
**Date**: 2026-04-09

---

## Graph Schema: Node Labels

All nodes MUST include `id` (unique per label) and `workspace_id` (for tenant isolation). Cross-workspace relationships are allowed but excluded from workspace-scoped queries by default.

### `Agent`

Represents a registered agent in the knowledge graph.

| Property | Type | Constraint/Index | Notes |
|---------|------|-----------------|-------|
| `id` | `string` | UNIQUE (constraint) | UUID — maps to `AgentProfile.id` |
| `workspace_id` | `string` | — | Tenant scoping |
| `fqn` | `string` | — | Fully qualified name `namespace:local_name` |
| `lifecycle_state` | `string` | — | `draft`, `published`, `deprecated` |

**Constraint**: `CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;`

---

### `Workflow`

Represents a compiled workflow definition.

| Property | Type | Constraint/Index | Notes |
|---------|------|-----------------|-------|
| `id` | `string` | UNIQUE (constraint) | UUID — maps to `WorkflowDefinition.id` |
| `workspace_id` | `string` | — | Tenant scoping |
| `name` | `string` | — | Human-readable |
| `status` | `string` | — | `draft`, `active`, `archived` |

**Constraint**: `CREATE CONSTRAINT workflow_id IF NOT EXISTS FOR (w:Workflow) REQUIRE w.id IS UNIQUE;`

---

### `Fleet`

Represents a fleet of coordinated agents.

| Property | Type | Constraint/Index | Notes |
|---------|------|-----------------|-------|
| `id` | `string` | UNIQUE (constraint) | UUID — maps to `Fleet.id` |
| `workspace_id` | `string` | — | Tenant scoping |
| `name` | `string` | — | Fleet name |
| `topology` | `string` | — | `star`, `mesh`, `hierarchical` |

**Constraint**: `CREATE CONSTRAINT fleet_id IF NOT EXISTS FOR (f:Fleet) REQUIRE f.id IS UNIQUE;`

---

### `Hypothesis`

Represents a scientific discovery hypothesis.

| Property | Type | Constraint/Index | Notes |
|---------|------|-----------------|-------|
| `id` | `string` | UNIQUE (constraint) | UUID — maps to `Hypothesis.id` |
| `workspace_id` | `string` | — | Tenant scoping |
| `status` | `string` | — | `open`, `supported`, `refuted`, `inconclusive` |
| `confidence` | `float` | — | 0.0–1.0 |

**Constraint**: `CREATE CONSTRAINT hypothesis_id IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.id IS UNIQUE;`

---

### `Memory`

Represents a memory entry stored in the knowledge graph.

| Property | Type | Constraint/Index | Notes |
|---------|------|-----------------|-------|
| `id` | `string` | UNIQUE (constraint) | UUID — maps to `MemoryEntry.id` |
| `workspace_id` | `string` | INDEX | Tenant scoping — `memory_workspace` index |
| `scope` | `string` | — | `workspace`, `agent`, `execution` |
| `memory_type` | `string` | — | `semantic`, `episodic`, `procedural` |
| `agent_id` | `string` | — | Owning agent UUID |

**Constraint**: `CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;`  
**Index**: `CREATE INDEX memory_workspace IF NOT EXISTS FOR (m:Memory) ON (m.workspace_id);`

---

### `Evidence`

Represents a piece of discovery evidence supporting or refuting a hypothesis.

| Property | Type | Constraint/Index | Notes |
|---------|------|-----------------|-------|
| `id` | `string` | — | UUID (no uniqueness constraint — Evidence is not a core entity type) |
| `workspace_id` | `string` | — | Tenant scoping |
| `hypothesis_id` | `string` | INDEX | Links to `Hypothesis.id` — `evidence_hypothesis` index |
| `source_url` | `string` | — | Optional provenance source |
| `confidence` | `float` | — | 0.0–1.0 |
| `polarity` | `string` | — | `supporting`, `refuting`, `neutral` |

**Index**: `CREATE INDEX evidence_hypothesis IF NOT EXISTS FOR (e:Evidence) ON (e.hypothesis_id);`

---

## Graph Schema: Relationship Types

All relationships may include `workspace_id` for explicit cross-workspace tagging. Workspace-scoped queries filter on both node and relationship `workspace_id`.

| Relationship | From | To | Properties | Notes |
|-------------|------|-----|-----------|-------|
| `DEPENDS_ON` | `Workflow` | `Agent` | `weight: float` | Workflow step depends on an agent |
| `DEPENDS_ON` | `Workflow` | `Workflow` | `weight: float` | Sub-workflow dependency |
| `MEMBER_OF` | `Agent` | `Fleet` | — | Agent belongs to a fleet |
| `COORDINATES` | `Agent` | `Agent` | `protocol: string` | Direct agent coordination |
| `PRODUCED_BY` | `Memory` | `Agent` | `execution_id: string` | Memory produced by an agent run |
| `RELATES_TO` | any | any | `type: string`, `weight: float` | Generic relationship | 
| `SUPPORTS` | `Evidence` | `Hypothesis` | `confidence: float` | Evidence supports hypothesis |
| `REFUTES` | `Evidence` | `Hypothesis` | `confidence: float` | Evidence refutes hypothesis |
| `DERIVED_FROM` | `Evidence` | `Evidence` | — | Evidence provenance chain |
| `CITES` | `Hypothesis` | `Hypothesis` | — | Hypothesis dependency |

**Index on `RELATES_TO`**: `CREATE INDEX relationship_type IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.type);`

---

## Full Schema Init Script (Cypher)

Located at: `deploy/neo4j/init.cypher`

```cypher
// Uniqueness constraints on core entity ID fields
CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;
CREATE CONSTRAINT workflow_id IF NOT EXISTS FOR (w:Workflow) REQUIRE w.id IS UNIQUE;
CREATE CONSTRAINT fleet_id IF NOT EXISTS FOR (f:Fleet) REQUIRE f.id IS UNIQUE;
CREATE CONSTRAINT hypothesis_id IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.id IS UNIQUE;
CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;

// Performance indexes
CREATE INDEX memory_workspace IF NOT EXISTS FOR (m:Memory) ON (m.workspace_id);
CREATE INDEX evidence_hypothesis IF NOT EXISTS FOR (e:Evidence) ON (e.hypothesis_id);
CREATE INDEX relationship_type IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.type);
```

**Idempotency**: All statements use `IF NOT EXISTS` (Neo4j 5.x+). Safe to re-run on upgrade.

---

## Helm Values Schema

```yaml
# deploy/helm/neo4j/values.yaml (shared defaults)
neo4j:
  edition: community             # override: enterprise in values-prod.yaml
  minimumClusterSize: 1          # override: 3 in values-prod.yaml
  name: musematic-neo4j

  # Authentication
  password: ""                   # set from Secret: neo4j-credentials
  acceptLicenseAgreement: "yes"  # required for Enterprise

  # Memory config (configurable)
  resources:
    requests:
      memory: 3Gi
      cpu: "1"
    limits:
      memory: 4Gi
      cpu: "2"

  config:
    server.memory.heap.initial_size: "1G"
    server.memory.heap.max_size: "2G"
    server.memory.pagecache.size: "1G"
    dbms.security.procedures.unrestricted: "apoc.*"   # allow APOC
    dbms.security.procedures.allowlist: "apoc.*"

  env:
    NEO4J_PLUGINS: '["apoc"]'    # auto-install APOC at startup

persistence:
  storageClassName: standard
  size: 20Gi                     # override: 100Gi in values-prod.yaml

service:
  type: ClusterIP
  boltPort: 7687
  httpPort: 7474

schemaInit:
  enabled: true
  image: neo4j:5-enterprise      # same image as server (has cypher-shell)

backup:
  enabled: true
  schedule: "0 3 * * *"          # daily at 03:00 UTC (configurable)
  bucket: "backups"
  prefix: "neo4j"

networkPolicy:
  enabled: true
```

---

## Kubernetes Resources

### Production Resources

| Resource | Kind | Count |
|---------|------|-------|
| StatefulSet (Neo4j cluster) | `StatefulSet` | 1 (3 pods) |
| PersistentVolumeClaims | `PVC` | 3 (one per pod) |
| `Secret` (credentials) | `Secret` | 1 (`neo4j-credentials`) |
| Schema init `Job` | `Job` | 1 (Helm post-install/post-upgrade hook) |
| Backup `CronJob` | `CronJob` | 1 (daily) |
| `NetworkPolicy` | `NetworkPolicy` | 1 |
| `Service` (ClusterIP) | `Service` | 1 |

### Development Resources

| Resource | Kind | Count |
|---------|------|-------|
| StatefulSet (single node) | `StatefulSet` | 1 (1 pod) |
| PersistentVolumeClaim | `PVC` | 1 |
| `Secret` (credentials) | `Secret` | 1 |
| Schema init `Job` | `Job` | 1 |

### Namespace: `platform-data`

All Neo4j infrastructure lives in `platform-data`.

### Port Reference

| Port | Protocol | Purpose |
|------|----------|---------|
| 7687 | Bolt | Application queries (async driver) |
| 7474 | HTTP | Admin browser + Prometheus `/metrics` |
| 5000 | TCP | Causal cluster communication (inter-pod) |
| 7000 | TCP | Causal cluster backup/discovery (inter-pod) |

### Service Reference

| Service Name | Port | Target |
|-------------|------|--------|
| `musematic-neo4j` | 7687, 7474 | Bolt API + admin HTTP |

---

## AsyncNeo4jClient Interface

Located at: `apps/control-plane/src/platform/common/clients/neo4j.py`

```
AsyncNeo4jClient
├── run_query(cypher: str, params: dict, workspace_id: str | None) → list[dict]
│       # Execute arbitrary Cypher; workspace_id prepended as $workspace_id param
├── create_node(label: str, properties: dict) → str
│       # Creates a node and returns its id
├── create_relationship(from_id: str, to_id: str, rel_type: str, properties: dict) → None
│       # Creates a directed relationship between two nodes
├── traverse_path(start_id: str, rel_types: list[str], max_hops: int, workspace_id: str) → list[PathResult]
│       # Multi-hop traversal with workspace scoping
├── shortest_path(from_id: str, to_id: str, rel_types: list[str]) → PathResult | None
│       # APOC-backed shortest path (delegates to apoc.algo.dijkstra or shortestPath())
├── health_check() → dict[str, Any]
│       # Returns {"status": "ok", "mode": "neo4j" | "local"}
└── close() → None
│       # Close driver connection

PathResult:
├── nodes: list[dict]      # ordered node properties along path
├── relationships: list[dict]  # ordered relationship properties
└── length: int            # number of hops

HopLimitExceededError(Exception):
    # Raised in local mode when max_hops > 3
```

**Mode detection**: If `NEO4J_URL` is unset or `GRAPH_MODE=local`, all methods route to `AsyncLocalGraphClient` which uses SQLAlchemy CTEs against PostgreSQL. Same return types, raised `HopLimitExceededError` for > 3 hops.
