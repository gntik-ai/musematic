# Implementation Plan: Neo4j Knowledge Graph

**Branch**: `006-neo4j-knowledge-graph` | **Date**: 2026-04-09 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/006-neo4j-knowledge-graph/spec.md`

## Summary

Deploy Neo4j 5.x as the dedicated graph database for the Agentic Mesh Platform. The implementation delivers: a Helm chart wrapping the official `neo4j/neo4j` chart (3-node Enterprise causal cluster for prod, single Community node for dev), an idempotent Cypher schema initialization Job (5 uniqueness constraints + 3 performance indexes), APOC plugin installation via `NEO4J_PLUGINS` env var, a daily backup CronJob uploading `neo4j-admin` dumps to object storage, a network policy restricting Bolt access to authorized namespaces, and a basic Python async client wrapper (`neo4j-python-driver 5.x`, `AsyncGraphDatabase`) with workspace-scoped traversal and a PostgreSQL CTE fallback for local mode.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: `neo4j-python-driver 5.x` (`AsyncGraphDatabase`), Helm 3.x (`neo4j/neo4j` official chart), APOC plugin (via `NEO4J_PLUGINS` env var)  
**Storage**: Neo4j 5.x (graph database, StatefulSet — no operator)  
**Testing**: pytest + pytest-asyncio 8.x + testcontainers (Neo4j) for integration tests  
**Target Platform**: Kubernetes 1.28+ (`platform-data` namespace)  
**Project Type**: Infrastructure (Helm chart) + library (Python Neo4j client) + scripts  
**Performance Goals**: 3-hop traversal < 100ms p99 for graphs with ≤ 1M nodes; shortest path < 500ms for ≤ 1M nodes  
**Constraints**: Workspace-scoped queries mandatory; Bolt auth required; backup to object storage (feature 004 dependency); local mode fallback limited to 3 hops via PostgreSQL CTEs  
**Scale/Scope**: 6 node types, 10 relationship types, 3 production pods, 5 constraints, 3 indexes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Gate | Check | Status |
|------|-------|--------|
| Python version | Python 3.12+ per constitution §2.1 | PASS |
| Neo4j client | `neo4j-python-driver 5.x` per constitution §2.1 | PASS |
| Async driver | `AsyncGraphDatabase` per constitution §2.1 | PASS |
| Neo4j technology | Neo4j 5.x per constitution §2.4 | PASS |
| Namespace: data store | `platform-data` per constitution | PASS |
| Namespace: clients | `platform-control`, `platform-execution` per constitution | PASS |
| Namespace: observability | `platform-observability` per constitution (metrics scrape) | PASS |
| No graph queries in PostgreSQL | Constitution AD-3.3 — except local mode fallback (explicitly excepted) | PASS |
| No vectors in Neo4j | Constitution AD-3.3 — vectors in Qdrant only | PASS |
| Helm chart conventions | No operator sub-dependencies — StatefulSet direct via official chart | PASS |
| Async everywhere | `AsyncGraphDatabase.driver()` + `async with session` throughout | PASS |
| Secrets not in LLM context | Neo4j password managed via Kubernetes Secret `neo4j-credentials` | PASS |
| Observability | Neo4j Prometheus metrics at `:7474/metrics` | PASS |
| Backup storage | Feature 004 (minio-object-storage) dependency documented | PASS |
| Local mode exception | SQLAlchemy CTEs only in `AsyncLocalGraphClient` (local mode only) | PASS — constitution AD-3.3 explicit exception |

All gates pass. Proceeding to Phase 1.

## Project Structure

### Documentation (this feature)

```text
specs/006-neo4j-knowledge-graph/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output (node types, relationship types, schema, client interface)
├── quickstart.md        # Phase 1 output (deployment and testing guide)
├── contracts/
│   ├── neo4j-cluster.md           # Cluster infrastructure contract
│   └── python-neo4j-client.md    # Python client interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
deploy/helm/neo4j/
├── Chart.yaml                  # Chart metadata, neo4j/neo4j dependency pinned to exact version
├── values.yaml                 # Shared defaults (APOC plugin, memory config, auth)
├── values-prod.yaml            # Production overrides (Enterprise, 3 nodes, 100Gi PVC)
├── values-dev.yaml             # Development overrides (Community, 1 node, 20Gi PVC)
└── templates/
    ├── secret-credentials.yaml # Secret: neo4j-credentials with NEO4J_PASSWORD
    ├── schema-init-job.yaml    # Helm post-install/post-upgrade Job (cypher-shell)
    ├── network-policy.yaml     # NetworkPolicy (Bolt 7687, HTTP 7474, inter-pod 5000/7000)
    └── backup-cronjob.yaml     # CronJob running neo4j-admin dump + S3 upload daily

deploy/neo4j/
└── init.cypher                 # Idempotent Cypher: 5 constraints + 3 indexes (IF NOT EXISTS)

apps/control-plane/src/platform/common/clients/neo4j.py
    # AsyncNeo4jClient using neo4j-python-driver 5.x with AsyncGraphDatabase.driver()
    # Methods: run_query, create_node, create_relationship, traverse_path,
    #          shortest_path, health_check, close
    # Data types: PathResult
    # Exceptions: Neo4jClientError, Neo4jConstraintViolationError,
    #             Neo4jNodeNotFoundError, Neo4jConnectionError, HopLimitExceededError
    # AsyncLocalGraphClient (local mode fallback, SQLAlchemy CTEs, max 3 hops)

apps/control-plane/scripts/
└── backup_neo4j_dump.py        # neo4j-admin dump + S3 upload script (used by CronJob)

apps/control-plane/tests/integration/
├── test_neo4j_basic.py         # Create nodes, relationships, basic traversal, workspace isolation
├── test_neo4j_traversal.py     # Multi-hop traversal, path ordering, cross-workspace exclusion
├── test_neo4j_apoc.py          # APOC shortest path, path expansion, neighborhood aggregation
├── test_neo4j_local_mode.py    # Local mode CTE fallback, 3-hop limit, HopLimitExceededError
└── test_neo4j_constraints.py   # Constraint violation, idempotent schema init
```

**Structure Decision**: Python client at `apps/control-plane/src/platform/common/clients/neo4j.py` (pre-defined in constitution §4 repo structure). Scripts in `apps/control-plane/scripts/` (alongside control plane package to share its `neo4j` dependency). Helm chart at `deploy/helm/neo4j/` consistent with features 001–005. Cypher init script at `deploy/neo4j/init.cypher` (separate from Helm to allow standalone execution).

Note: The Neo4j StatefulSet is deployed via the official `neo4j/neo4j` Helm chart as a dependency. The `deploy/helm/neo4j/` wrapper chart adds the Secret, schema init Job, backup CronJob, and NetworkPolicy.

## Implementation Phases

### Phase 0: Research (Complete)

All technical decisions resolved in [research.md](research.md):
- Neo4j as StatefulSet (no operator) — official `neo4j/neo4j` Helm chart
- APOC installed via `NEO4J_PLUGINS=["apoc"]` env var (official mechanism)
- Schema init via `cypher-shell` Job with `IF NOT EXISTS` for idempotency
- Backup via `neo4j-admin database dump` + Python S3 upload script
- Network policy: ports 7687 (Bolt), 7474 (HTTP), 5000/7000 (cluster inter-pod)
- Python client: `neo4j-python-driver 5.x` with `AsyncGraphDatabase`
- Local mode: SQLAlchemy recursive CTEs, max 3 hops, same return types
- Dev: Community Edition (no clustering); Prod: Enterprise (causal cluster)

### Phase 1: Design & Contracts (Complete)

Artifacts generated:
- [data-model.md](data-model.md) — Node types (6), relationship types (10), full Cypher schema, Helm values schema, `AsyncNeo4jClient` interface
- [contracts/neo4j-cluster.md](contracts/neo4j-cluster.md) — Cluster infrastructure contract
- [contracts/python-neo4j-client.md](contracts/python-neo4j-client.md) — Python client interface contract
- [quickstart.md](quickstart.md) — 14-section deployment and testing guide

### Phase 2: Implementation (tasks.md — generated by /speckit.tasks)

**P1 — US1**: Neo4j cluster deployment (Helm chart, StatefulSet, Secret, APOC)  
**P1 — US2**: Schema initialization (init.cypher, schema-init Job, idempotency test)  
**P1 — US3**: Graph CRUD + traversal (AsyncNeo4jClient, workspace filter, integration tests)  
**P2 — US4**: Advanced algorithms (shortest_path with APOC, neighborhood aggregation)  
**P2 — US5**: Backup/restore (backup-cronjob, backup_neo4j_dump.py, restore docs)  
**P2 — US6**: Network policy (NetworkPolicy template)  
**P2 — US7**: Local mode fallback (AsyncLocalGraphClient, CTE queries, HopLimitExceededError)

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Deployment model | Official Neo4j Helm chart as chart dependency | No operator available; official chart is best-maintained |
| Edition | Community (dev), Enterprise (prod) | Causal clustering requires Enterprise Edition |
| APOC installation | `NEO4J_PLUGINS=["apoc"]` env var | Official Neo4j mechanism; no custom image needed |
| Schema init | `cypher-shell` Job with `IF NOT EXISTS` | Idempotent; `cypher-shell` included in Neo4j image |
| Backup mechanism | `neo4j-admin database dump` + Python S3 upload | Official backup tool; reuses platform `aioboto3` client |
| Python client | `AsyncGraphDatabase.driver()` | Constitution-mandated async driver |
| Workspace isolation | Caller-enforced filter in `run_query`; built-in in high-level methods | Consistent with Qdrant workspace_filter pattern |
| Local mode | SQLAlchemy recursive CTEs, max 3 hops | Constitution AD-3.3 explicit exception; PostgreSQL always available |

## Dependencies

- **Upstream**: Feature 001 (postgresql-schema-foundation) — local mode CTE fallback; Feature 004 (minio-object-storage) — backup dump upload to `backups/neo4j/`
- **Downstream**: All bounded contexts using knowledge graph, provenance chains, workflow dependency analysis, fleet coordination graphs
- **Parallel with**: Qdrant (005), Kafka (003), Redis (002) — no dependency relationship
- **Blocks**: Knowledge graph views, discovery evidence provenance, GraphRAG, hypothesis store provenance

## Complexity Tracking

No constitution violations. The local mode PostgreSQL CTE fallback is explicitly excepted by constitution AD-3.3 ("except in local mode fallback"). Standard complexity for this feature. Neo4j has no operator — documented in spec assumptions as a known pattern consistent with Qdrant (feature 005).
