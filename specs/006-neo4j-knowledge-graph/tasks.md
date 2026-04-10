# Tasks: Neo4j Knowledge Graph

**Input**: Design documents from `specs/006-neo4j-knowledge-graph/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory scaffolding and add dependencies before any story work begins.

- [x] T001 Create `deploy/helm/neo4j/` directory with `templates/` subdirectory and `deploy/neo4j/` directory for the Cypher init script
- [x] T002 [P] Add `neo4j>=5.0` to `apps/control-plane/pyproject.toml` under `[project.dependencies]`
- [x] T003 [P] Add `NEO4J_URL: str | None = None`, `NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50`, and `GRAPH_MODE: str = "auto"` fields to `apps/control-plane/src/platform/common/config.py` in the `Settings` class — `GRAPH_MODE` accepts `"auto"`, `"neo4j"`, or `"local"`; in auto mode, `NEO4J_URL` presence determines the active mode

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Exception classes and shared data types used by all graph operations.

**⚠️ CRITICAL**: No user story work on the Python client can begin until this phase is complete.

- [x] T004 Add Neo4j exception hierarchy to `apps/control-plane/src/platform/common/exceptions.py`: base `Neo4jClientError(Exception)`, `Neo4jConstraintViolationError(Neo4jClientError)`, `Neo4jNodeNotFoundError(Neo4jClientError)`, `Neo4jConnectionError(Neo4jClientError)`, `HopLimitExceededError(Neo4jClientError)` — include docstrings per class
- [x] T005 [P] Define `PathResult` frozen dataclass (`nodes: list[dict[str, Any]]`, `relationships: list[dict[str, Any]]`, `length: int`) and stub `AsyncNeo4jClient` class (all methods raise `NotImplementedError`) and empty `AsyncLocalGraphClient` class in `apps/control-plane/src/platform/common/clients/neo4j.py`

**Checkpoint**: Exception hierarchy and `PathResult` type are importable — all user story phases can now begin.

---

## Phase 3: User Story 1 — Platform Operator Deploys Graph Database Cluster (Priority: P1) 🎯 MVP

**Goal**: A production-ready 3-node Neo4j Enterprise causal cluster (1 leader + 2 followers) or single-node Community dev deployment, deployable via a single Helm command.

**Independent Test**: `helm install musematic-neo4j deploy/helm/neo4j -n platform-data -f values.yaml -f values-prod.yaml` completes; `kubectl rollout status statefulset/musematic-neo4j -n platform-data` shows 3 pods Running; Bolt port 7687 accepts connections; admin browser responds at port 7474.

- [x] T006 [US1] Create `deploy/helm/neo4j/Chart.yaml` with `apiVersion: v2`, `name: musematic-neo4j`, `version: 0.1.0`, `description: Neo4j graph database for Musematic platform`; add `dependencies` entry: `name: neo4j`, `repository: https://helm.neo4j.com/neo4j`, pinned to an exact version (e.g., `5.21.0`)
- [x] T007 [P] [US1] Create `deploy/helm/neo4j/values.yaml` with shared defaults: `neo4j.edition: community`, `neo4j.minimumClusterSize: 1`, `neo4j.name: musematic-neo4j`, `neo4j.password: ""` (populated from Secret), `neo4j.acceptLicenseAgreement: "yes"`, `neo4j.resources.requests.memory: 3Gi`, `neo4j.resources.requests.cpu: "1"`, `neo4j.resources.limits.memory: 4Gi`, `neo4j.resources.limits.cpu: "2"`, `neo4j.config.server.memory.heap.initial_size: "1G"`, `neo4j.config.server.memory.heap.max_size: "2G"`, `neo4j.config.server.memory.pagecache.size: "1G"`, `neo4j.config.dbms.security.procedures.unrestricted: "apoc.*"`, `neo4j.config.dbms.security.procedures.allowlist: "apoc.*"`, `neo4j.env.NEO4J_PLUGINS: '["apoc"]'`, `persistence.storageClassName: standard`, `persistence.size: 20Gi`, `service.type: ClusterIP`, `service.boltPort: 7687`, `service.httpPort: 7474`, `schemaInit.enabled: true`, `backup.enabled: true`, `backup.schedule: "0 3 * * *"`, `backup.bucket: backups`, `backup.prefix: neo4j`, `networkPolicy.enabled: true`
- [x] T008 [P] [US1] Create `deploy/helm/neo4j/values-prod.yaml` with production overrides: `neo4j.edition: enterprise`, `neo4j.minimumClusterSize: 3`, `persistence.size: 100Gi`, `neo4j.resources.requests.memory: 6Gi`, `neo4j.resources.requests.cpu: "2"`, `neo4j.resources.limits.memory: 8Gi`, `neo4j.resources.limits.cpu: "4"`, `networkPolicy.enabled: true`
- [x] T009 [P] [US1] Create `deploy/helm/neo4j/values-dev.yaml` with development overrides: `neo4j.edition: community`, `neo4j.minimumClusterSize: 1`, `persistence.size: 10Gi`, `neo4j.resources.requests.memory: 1Gi`, `neo4j.resources.requests.cpu: "500m"`, `networkPolicy.enabled: false`, `backup.enabled: false`
- [x] T010 [US1] Create `deploy/helm/neo4j/templates/secret-credentials.yaml` — `Secret` named `neo4j-credentials` in `{{ .Release.Namespace }}` with key `NEO4J_PASSWORD`; use Helm `lookup` to avoid regenerating the password on upgrades: `{{ (lookup "v1" "Secret" .Release.Namespace "neo4j-credentials").data.NEO4J_PASSWORD | default (randAlphaNum 32 | b64enc) }}`; reference this Secret in the Neo4j StatefulSet via values override `neo4j.passwordFrom.secretKeyRef.name: neo4j-credentials`, `neo4j.passwordFrom.secretKeyRef.key: NEO4J_PASSWORD`

**Checkpoint**: `helm lint deploy/helm/neo4j` passes; `helm template deploy/helm/neo4j -f values.yaml -f values-prod.yaml | grep replicas` shows 3 replicas; `helm template ... -f values-dev.yaml` shows 1 replica Community edition.

---

## Phase 4: User Story 2 — Platform Initializes Schema Constraints and Indexes (Priority: P1)

**Goal**: All 5 uniqueness constraints and 3 performance indexes exist after a single idempotent init run; re-running produces no errors.

**Independent Test**: Run schema init Job; `SHOW CONSTRAINTS` returns 5 constraints (`agent_id`, `workflow_id`, `fleet_id`, `hypothesis_id`, `memory_id`); `SHOW INDEXES` includes `memory_workspace`, `evidence_hypothesis`, `relationship_type`; re-running init Job exits 0 with no duplicate error.

- [x] T011 [US2] Create `deploy/neo4j/init.cypher` with the full idempotent schema: (1) `CREATE CONSTRAINT agent_id IF NOT EXISTS FOR (a:Agent) REQUIRE a.id IS UNIQUE;`, (2) `CREATE CONSTRAINT workflow_id IF NOT EXISTS FOR (w:Workflow) REQUIRE w.id IS UNIQUE;`, (3) `CREATE CONSTRAINT fleet_id IF NOT EXISTS FOR (f:Fleet) REQUIRE f.id IS UNIQUE;`, (4) `CREATE CONSTRAINT hypothesis_id IF NOT EXISTS FOR (h:Hypothesis) REQUIRE h.id IS UNIQUE;`, (5) `CREATE CONSTRAINT memory_id IF NOT EXISTS FOR (m:Memory) REQUIRE m.id IS UNIQUE;`, (6) `CREATE INDEX memory_workspace IF NOT EXISTS FOR (m:Memory) ON (m.workspace_id);`, (7) `CREATE INDEX evidence_hypothesis IF NOT EXISTS FOR (e:Evidence) ON (e.hypothesis_id);`, (8) `CREATE INDEX relationship_type IF NOT EXISTS FOR ()-[r:RELATES_TO]-() ON (r.type);`
- [x] T012 [US2] Create `deploy/helm/neo4j/templates/schema-init-job.yaml` — Kubernetes `Job` with annotations `helm.sh/hook: post-install,post-upgrade` and `helm.sh/hook-weight: "5"`; wrapped in `{{- if .Values.schemaInit.enabled }}`; uses the Neo4j container image (`{{ .Values.schemaInit.image }}`); includes an init container that polls `bolt://musematic-neo4j.{{ .Release.Namespace }}:7687` until Neo4j accepts connections (retries every 5 seconds, max 60 retries); main container runs `cypher-shell -u neo4j -p $NEO4J_PASSWORD -a bolt://musematic-neo4j.{{ .Release.Namespace }}:7687 -f /scripts/init.cypher`; mounts `deploy/neo4j/init.cypher` via ConfigMap and `NEO4J_PASSWORD` from `neo4j-credentials` Secret; `restartPolicy: OnFailure`

**Checkpoint**: After `helm install`, `kubectl get jobs -n platform-data -l app=neo4j-schema-init` shows `COMPLETIONS 1/1`; running the Job again with `kubectl create job --from=...` exits 0 — idempotency confirmed.

---

## Phase 5: User Story 3 — Services Create and Traverse Graph Relationships (Priority: P1)

**Goal**: Python services can create nodes and relationships, execute workspace-scoped multi-hop traversal queries (up to 3+ hops), and receive path results with workspace isolation enforced.

**Independent Test**: Create 5 node types and 10 relationships across 2 workspaces; run 3-hop traversal with `workspace_id` filter; verify results contain only nodes from that workspace; verify workspace isolation (zero cross-workspace leakage).

- [x] T013 [US3] Implement `AsyncNeo4jClient.__init__` in `apps/control-plane/src/platform/common/clients/neo4j.py`: detect mode from `settings.GRAPH_MODE` and `settings.NEO4J_URL`; in `"neo4j"` mode, create `self._driver = AsyncGraphDatabase.driver(settings.NEO4J_URL, max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE)`; in `"local"` mode, instantiate `self._local = AsyncLocalGraphClient(settings)`; store `self._mode: str`
- [x] T014 [P] [US3] Implement `run_query(cypher, params={}, workspace_id=None)` in `apps/control-plane/src/platform/common/clients/neo4j.py`: in neo4j mode, open `async with self._driver.session() as session` and `result = await session.run(cypher, {**params, "workspace_id": workspace_id} if workspace_id else params)`; collect records as `list[dict]` via `[dict(r) for r in await result.data()]`; wrap `neo4j.exceptions.ConstraintError` → `Neo4jConstraintViolationError`, `ServiceUnavailable` → `Neo4jConnectionError`, all others → `Neo4jClientError`
- [x] T015 [P] [US3] Implement `create_node(label, properties)` in `apps/control-plane/src/platform/common/clients/neo4j.py`: build and run `CREATE (n:{label} $props) RETURN n.id AS id` with `props=properties`; return the `id` property string; raise `Neo4jConstraintViolationError` on `ConstraintError`; validate that `properties` contains `"id"` and `"workspace_id"` — raise `ValueError` if missing
- [x] T016 [P] [US3] Implement `create_relationship(from_id, to_id, rel_type, properties={})` in `apps/control-plane/src/platform/common/clients/neo4j.py`: run `MATCH (a {id: $from_id}), (b {id: $to_id}) CREATE (a)-[r:{rel_type} $props]->(b) RETURN type(r)`; raise `Neo4jNodeNotFoundError` if the MATCH returns no results (check result count before `CREATE`); validate `rel_type` is a non-empty uppercase string
- [x] T017 [US3] Implement `traverse_path(start_id, rel_types, max_hops, workspace_id)` in `apps/control-plane/src/platform/common/clients/neo4j.py`: in neo4j mode, build Cypher `MATCH path = (start {id: $start_id})-[r:{rels}*1..{max_hops}]->(n) WHERE n.workspace_id = $workspace_id RETURN path` where `{rels}` is `"|".join(rel_types)` (empty = `*`); convert each `path` record to `PathResult` (nodes as `[dict(node) for node in path.nodes]`, relationships as `[dict(rel) for rel in path.relationships]`, length as `len(path.relationships)`); return `list[PathResult]`; in local mode, delegate to `self._local.traverse_path(...)`
- [x] T018 [US3] Implement `health_check()` and `close()` in `apps/control-plane/src/platform/common/clients/neo4j.py`: `health_check` in neo4j mode runs `CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition` and returns `{"status": "ok", "mode": "neo4j", "version": versions[0], "edition": edition}`; on any exception returns `{"status": "error", "mode": "neo4j", "error": str(e)}`; in local mode returns `{"status": "ok", "mode": "local"}`; `close()` calls `await self._driver.close()` in neo4j mode, no-op in local mode
- [x] T019 [US3] Write integration test `apps/control-plane/tests/integration/test_neo4j_basic.py` using testcontainers Neo4j container (or `NEO4J_TEST_MODE` env var): (1) create 5 `Agent` nodes across 2 workspaces; (2) create 3 `COORDINATES` relationships; (3) `traverse_path` with `workspace_id="ws-A"` returns only `ws-A` nodes; (4) `traverse_path` with `workspace_id="ws-B"` returns only `ws-B` nodes; (5) `health_check()` returns `{"status": "ok", "mode": "neo4j"}`; (6) duplicate `Agent.id` create raises `Neo4jConstraintViolationError`; (7) `create_relationship` with nonexistent `from_id` raises `Neo4jNodeNotFoundError`
- [x] T020 [US3] Write integration test `apps/control-plane/tests/integration/test_neo4j_traversal.py`: (1) build `Hypothesis → Evidence → Evidence` chain (3-hop path); (2) `traverse_path(start_id="h-001", rel_types=["SUPPORTS","DERIVED_FROM"], max_hops=3, workspace_id="ws-test")` returns paths of length ≥ 2; (3) `run_query("MATCH (n) WHERE n.workspace_id = $workspace_id RETURN n", workspace_id="ws-A")` returns zero results from `ws-B`; (4) configurable `max_hops` up to 5 works in neo4j mode (not capped)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_neo4j_basic.py apps/control-plane/tests/integration/test_neo4j_traversal.py -v` all pass.

---

## Phase 6: User Story 4 — Advanced Graph Algorithms Support Complex Queries (Priority: P2)

**Goal**: `shortest_path()` returns the minimum-hop path between two nodes using APOC; `CALL apoc.help('path')` confirms APOC is available.

**Independent Test**: Create a graph with 2 paths between node A and node C (direct 1-hop vs. 2-hop via B); `shortest_path(A, C)` returns a `PathResult` with `length=1`; `CALL apoc.help('path')` returns results (APOC available).

- [x] T021 [US4] Implement `shortest_path(from_id, to_id, rel_types=[])` in `apps/control-plane/src/platform/common/clients/neo4j.py`: in neo4j mode, run `MATCH (a {id: $from_id}), (b {id: $to_id}), path = shortestPath((a)-[{rels}*]-(b)) RETURN path` where `{rels}` is `r:{"|".join(rel_types)}` if types provided else `r`; return `PathResult` if path found, `None` if MATCH returns no result; in local mode raise `NotImplementedError("shortest_path not available in local mode")`
- [x] T022 [US4] Write integration test `apps/control-plane/tests/integration/test_neo4j_apoc.py`: (1) create graph with direct `A→C` (weight 1) and indirect `A→B→C` (weight 2) paths; (2) `shortest_path("a","c", rel_types=["COORDINATES"])` returns `PathResult(length=1)` (direct path); (3) `run_query("CALL apoc.help('path') YIELD name RETURN name LIMIT 1")` returns a non-empty result (APOC available); (4) `shortest_path("a","z")` returns `None` (no path); (5) request neighborhood via `run_query("MATCH (n {id: $id})-[*1..2]-(neighbor) RETURN DISTINCT neighbor", params={"id": "a"})` returns correct 2-hop neighborhood

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_neo4j_apoc.py -v` all pass including APOC availability assertion.

---

## Phase 7: User Story 5 — Operator Backs Up and Restores Graph Data (Priority: P2)

**Goal**: Daily backup CronJob dumps the Neo4j database and uploads to `backups/neo4j/{date}/neo4j.dump` in object storage; restore procedure documented and tested.

**Independent Test**: Run `backup_neo4j_dump.py`; verify dump file appears in `backups/neo4j/` in object storage within 15 minutes; manually trigger restore per quickstart.md step 10; verify node counts match pre-backup counts.

- [x] T023 [US5] Create `apps/control-plane/scripts/backup_neo4j_dump.py` — async script that: (1) runs `neo4j-admin database dump --database=neo4j --to-path=/dumps/` via `subprocess.run` inside a Job container that has access to the Neo4j data volume; (2) uploads the resulting `/dumps/neo4j.dump` to `s3://{BACKUP_BUCKET}/neo4j/{YYYY-MM-DD}/neo4j.dump` via `aioboto3`; (3) reads `BACKUP_BUCKET` (default `"backups"`), `MINIO_ENDPOINT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` from environment; (4) logs dump size and upload duration; (5) exits 0 on success, 1 on any failure; note: this script runs inside a Kubernetes Job pod with `neo4j-admin` available — it does not connect via Bolt
- [x] T024 [P] [US5] Create `deploy/helm/neo4j/templates/backup-cronjob.yaml` — `CronJob` with `schedule: {{ .Values.backup.schedule }}` (default `"0 3 * * *"`), wrapped in `{{- if .Values.backup.enabled }}`; runs using the Neo4j container image (which includes `neo4j-admin`); mounts the Neo4j data PVC at `/data` read-only and a writable `/dumps` volume (emptyDir); runs `neo4j-admin database dump --database=neo4j --to-path=/dumps/ && python3 /scripts/backup_neo4j_dump.py`; mounts `NEO4J_PASSWORD` from `neo4j-credentials` Secret and MinIO credentials from `minio-platform-credentials` Secret; `restartPolicy: OnFailure`

**Checkpoint**: `helm template deploy/helm/neo4j -f values.yaml -f values-prod.yaml | grep "kind: CronJob"` outputs 1 CronJob; `helm template ... -f values-dev.yaml | grep "kind: CronJob"` outputs nothing (backup disabled in dev).

---

## Phase 8: User Story 6 — Network Access Is Restricted to Authorized Namespaces (Priority: P2)

**Goal**: Bolt (7687) and HTTP (7474) accessible from `platform-control` and `platform-execution`; metrics (7474) accessible from `platform-observability`; inter-pod cluster ports (5000, 7000) accessible within `platform-data`; all other namespaces blocked.

**Independent Test**: Deploy with `networkPolicy.enabled: true`; pod in `platform-control` can connect on 7687; pod in `default` namespace connection times out on 7687.

- [x] T025 [US6] Create `deploy/helm/neo4j/templates/network-policy.yaml` — one `NetworkPolicy` wrapped in `{{- if .Values.networkPolicy.enabled }}`: `podSelector: {app.kubernetes.io/name: neo4j}`; five ingress rules: (1) ports 7687+7474 from `platform-control` namespaceSelector; (2) ports 7687+7474 from `platform-execution` namespaceSelector; (3) port 7474 from `platform-observability` namespaceSelector (metrics scrape only); (4) ports 5000+7000+7687 from same `podSelector` within `platform-data` (causal cluster inter-pod: discovery port 5000, backup port 7000, Bolt 7687 for cluster routing)

**Checkpoint**: `helm template deploy/helm/neo4j -f values.yaml -f values-prod.yaml | grep "kind: NetworkPolicy"` outputs 1; `helm template ... -f values-dev.yaml | grep "kind: NetworkPolicy"` outputs nothing (disabled in dev).

---

## Phase 9: User Story 7 — Local Mode Falls Back to Simplified Graph Queries (Priority: P2)

**Goal**: When `NEO4J_URL` is unset (or `GRAPH_MODE=local`), all graph queries execute via SQLAlchemy recursive CTEs against PostgreSQL; 3-hop traversal works correctly; queries with more than 3 hops raise `HopLimitExceededError`.

**Independent Test**: Set `GRAPH_MODE=local` (or leave `NEO4J_URL` unset); `health_check()` returns `{"status": "ok", "mode": "local"}`; `traverse_path(..., max_hops=3)` returns correctly structured `PathResult` list; `traverse_path(..., max_hops=4)` raises `HopLimitExceededError`.

- [x] T026 [US7] Implement `AsyncLocalGraphClient` in `apps/control-plane/src/platform/common/clients/neo4j.py`: (1) `__init__(settings)` receives a `Settings` instance and stores the SQLAlchemy async engine; (2) `traverse_path(start_id, rel_types, max_hops, workspace_id)` — raises `HopLimitExceededError("local mode supports max 3 hops")` if `max_hops > 3`; executes a SQLAlchemy recursive CTE using `text()` against `graph_nodes` and `graph_edges` tables (see contracts/python-neo4j-client.md for CTE structure); filters by `workspace_id`; returns `list[PathResult]` with same structure as neo4j mode; (3) `create_node(label, properties)` — inserts into `graph_nodes(id, label, properties JSONB, workspace_id)` and returns `properties["id"]`; (4) `create_relationship(from_id, to_id, rel_type, properties)` — inserts into `graph_edges(from_id, to_id, rel_type, properties JSONB)`; (5) `health_check()` — returns `{"status": "ok", "mode": "local"}`; (6) `shortest_path(...)` — raises `NotImplementedError("shortest_path not available in local mode")`
- [x] T027 [US7] Write integration test `apps/control-plane/tests/integration/test_neo4j_local_mode.py`: set `GRAPH_MODE=local` (no `NEO4J_URL`); (1) `health_check()` returns `{"mode": "local"}`; (2) create 3 nodes and 2 relationships in `graph_nodes`/`graph_edges` tables; (3) `traverse_path(start_id, ["DEPENDS_ON"], max_hops=2, workspace_id="ws-test")` returns non-empty `list[PathResult]` with correct `length`; (4) `traverse_path(..., max_hops=4, ...)` raises `HopLimitExceededError`; (5) results from local mode have same `PathResult` shape as neo4j mode (same field names, types); (6) `shortest_path(...)` raises `NotImplementedError`

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_neo4j_local_mode.py -v` all pass; no `NEO4J_URL` required to run these tests.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, linting, type checking, Helm lint.

- [ ] T028 [P] Run `helm lint deploy/helm/neo4j` and fix any linting errors; run `helm dependency update deploy/helm/neo4j` to download the pinned Neo4j chart version and commit `Chart.lock`; verify `helm template` renders valid YAML for both prod and dev values files
- [x] T029 [P] Run `ruff check apps/control-plane/src/platform/common/clients/neo4j.py apps/control-plane/scripts/backup_neo4j_dump.py` and fix all violations; ensure all public functions have type annotations
- [x] T030 [P] Run `mypy apps/control-plane/src/platform/common/clients/neo4j.py` in strict mode; fix all type errors; add `# type: ignore[import-untyped]` with comment for any missing `neo4j` driver stubs
- [x] T031 [P] Write integration test `apps/control-plane/tests/integration/test_neo4j_constraints.py`: (1) run schema init Cypher against test Neo4j; verify all 5 constraints and 3 indexes exist via `SHOW CONSTRAINTS` and `SHOW INDEXES`; (2) attempt to create two `Agent` nodes with same `id` → second `create_node` raises `Neo4jConstraintViolationError`; (3) run schema init again → no error (idempotency)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks all Python client work**
- **US1 (Phase 3)**: Depends on Phase 1 (Helm dirs) — Helm only, no Python dependency
- **US2 (Phase 4)**: Depends on US1 (cluster must be deployable before schema init Job makes sense); Cypher file (T011) can be written immediately
- **US3 (Phase 5)**: Depends on Foundational (types, exceptions) and US1+US2 (cluster with schema for integration tests)
- **US4 (Phase 6)**: Depends on US3 (uses `run_query` for APOC calls; needs working cluster)
- **US5 (Phase 7)**: Depends on US1 (cluster for CronJob) and feature 004 (object storage for S3 upload)
- **US6 (Phase 8)**: Depends on US1 (NetworkPolicy is part of cluster Helm chart)
- **US7 (Phase 9)**: Depends on Foundational (exception types); `AsyncLocalGraphClient` is independent of Neo4j cluster
- **Polish (Phase 10)**: Depends on all phases complete

### Dependency Graph

```
Phase 1 (Setup)
    ├── Phase 2 (Foundational: exceptions + data types)
    │       ├── Phase 5 (US3: Graph CRUD + traversal)
    │       │       └── Phase 6 (US4: APOC + shortest path)
    │       └── Phase 9 (US7: Local mode fallback) ← independent of cluster
    └── Phase 3 (US1: Helm chart + cluster)
            ├── Phase 4 (US2: Schema init Job)
            │       └── Phase 5 (US3: Integration tests need schema)
            ├── Phase 7 (US5: Backup CronJob)
            └── Phase 8 (US6: Network policy)

Phase 10 (Polish): depends on all phases above
```

### User Story Dependencies

- **US1 (P1)**: Can start after Setup (Phase 1) — Helm-only, no Python required
- **US2 (P1)**: T011 (init.cypher) can start immediately; T012 (schema-init-job) needs US1 cluster templates
- **US3 (P1)**: Needs Foundational (Phase 2) for client types; needs US2 schema for constraint tests
- **US4 (P2)**: Needs US3 working client (`run_query`, driver connected)
- **US5 (P2)**: Needs US1 Helm chart for CronJob template; backup script is independent
- **US6 (P2)**: Needs US1 Helm chart for NetworkPolicy template
- **US7 (P2)**: Needs Foundational exception types; fully independent of Neo4j cluster

### Parallel Opportunities

- **Phase 1**: T002, T003 in parallel after T001 (directory creation)
- **Phase 3 (US1)**: T007, T008, T009 in parallel after T006 (Chart.yaml) — all are separate values files
- **Phase 5 (US3)**: T014, T015, T016 in parallel after T013 (`__init__`) — different methods in same file (coordinate)
- **Phase 7 (US5)**: T023 (backup script) and T024 (CronJob template) in parallel
- **US7 + US5 + US6**: Can all proceed in parallel after US1 chart is scaffolded
- **Phase 10**: T028, T029, T030, T031 all in parallel

---

## Parallel Example: Phase 5 (US3 — Graph CRUD + Traversal)

```
# Sequential: T013 (AsyncNeo4jClient.__init__) must complete first

# Parallel group after T013 (different methods, no dependencies):
Task T014: run_query method
Task T015: create_node method
Task T016: create_relationship method

# Sequential after T014+T015+T016:
Task T017: traverse_path method (uses run_query)
Task T018: health_check + close
Task T019: integration test test_neo4j_basic.py
Task T020: integration test test_neo4j_traversal.py
```

---

## Implementation Strategy

### MVP (User Stories 1–3 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T005)
3. Complete Phase 3: US1 — Cluster (T006–T010)
4. Complete Phase 4: US2 — Schema Init (T011–T012)
5. Complete Phase 5: US3 — Graph CRUD + Traversal (T013–T020)
6. **STOP and VALIDATE**: Cluster deployed, schema initialized, nodes/relationships created and traversed with workspace isolation

### Incremental Delivery

After MVP:
1. Add US4 (APOC shortest path) → 2 tasks → test advanced algorithms
2. Add US5 (Backup) → 2 tasks → test dump upload to object storage
3. Add US6 (Network policy) → 1 task → test namespace isolation
4. Add US7 (Local mode) → 2 tasks → test CTE fallback without Neo4j
5. Polish → quality gates

### Parallel Team Strategy

With multiple developers after Phase 1 + 2:
- Developer A: US1 (Helm chart) → US2 (schema init)
- Developer B: US7 (local mode fallback — fully independent of cluster)
- Developer C: US5 + US6 (backup + network policy, Helm templates)

All merge after US1 completes, then US3 integration tests run against the deployed cluster.

---

## Notes

- [P] tasks use different files with no dependencies on incomplete tasks
- `helm dependency update deploy/helm/neo4j` must run before `helm install` to download the Neo4j sub-chart (`Chart.lock` must be committed)
- Integration tests require either a running Neo4j instance or `testcontainers` Neo4j image; set `NEO4J_TEST_MODE=testcontainers` to use testcontainers
- Local mode tests (US7) do NOT require a running Neo4j — they run against PostgreSQL only; set `GRAPH_MODE=local` in the test environment
- Schema init Cypher uses `IF NOT EXISTS` (Neo4j 5.x+) — safe to re-run; the Job can be triggered manually via `kubectl create job --from=...`
- `backup_neo4j_dump.py` runs inside a Job pod that has `neo4j-admin` in its PATH (Neo4j container image) — it does NOT use the Bolt driver
- Feature 004 (minio-object-storage) must be deployed before the backup CronJob can upload dumps; backup is disabled in dev values
- Neo4j Enterprise is required for causal clustering (3-node prod); Community Edition supports only a single standalone node (dev)
- APOC is installed via `NEO4J_PLUGINS=["apoc"]` env var at container startup — APOC availability is verified in US4 integration tests
- `workspace_filter` is enforced at the method level in `traverse_path` and `create_node` — `run_query` is unrestricted (caller must include WHERE clause manually)
- Cross-workspace relationships (nodes from different workspaces linked by a relationship) are allowed but excluded from workspace-scoped `traverse_path` results by default
