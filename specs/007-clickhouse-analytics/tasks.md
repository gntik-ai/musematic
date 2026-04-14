# Tasks: ClickHouse Analytics

**Input**: Design documents from `specs/007-clickhouse-analytics/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create directory scaffolding and add dependencies before any story work begins.

- [x] T001 Create `deploy/helm/clickhouse/templates/` and `deploy/clickhouse/init/` directories
- [x] T002 [P] Add `clickhouse-connect>=0.8` to `apps/control-plane/pyproject.toml` under `[project.dependencies]`
- [x] T003 [P] Add `CLICKHOUSE_URL: str | None = None`, `CLICKHOUSE_USER: str = "default"`, `CLICKHOUSE_PASSWORD: str = ""`, `CLICKHOUSE_DATABASE: str = "default"`, `CLICKHOUSE_INSERT_BATCH_SIZE: int = 1000`, `CLICKHOUSE_INSERT_FLUSH_INTERVAL: float = 5.0` fields to `apps/control-plane/src/platform/common/config.py` in the `Settings` class

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Exception classes and shared client stub used by all analytics operations.

**⚠️ CRITICAL**: No user story work on the Python client can begin until this phase is complete.

- [x] T004 Add ClickHouse exception hierarchy to `apps/control-plane/src/platform/common/exceptions.py`: base `ClickHouseClientError(Exception)`, `ClickHouseConnectionError(ClickHouseClientError)` (raised when `CLICKHOUSE_URL` not set or HTTP failure), `ClickHouseQueryError(ClickHouseClientError)` (query execution errors: syntax, timeout, type mismatch) — include docstrings per class
- [x] T005 [P] Define stub `AsyncClickHouseClient` class (all methods raise `NotImplementedError`) and stub `BatchBuffer` class (all methods raise `NotImplementedError`) in `apps/control-plane/src/platform/common/clients/clickhouse.py`; raise `ClickHouseConnectionError` in `__init__` if `settings.CLICKHOUSE_URL` is `None`

**Checkpoint**: Exception hierarchy and client stubs are importable — all user story phases can now begin.

---

## Phase 3: User Story 1 — Platform Operator Deploys Analytics Database Cluster (Priority: P1) 🎯 MVP

**Goal**: A production-ready ClickHouse cluster (2 replicas + 3 Keeper nodes) or single-node dev deployment, deployable via a single Helm command. Schema init Job runs automatically post-install.

**Independent Test**: `helm install musematic-clickhouse deploy/helm/clickhouse -n platform-data -f values.yaml -f values-prod.yaml` completes; 2 ClickHouse pods and 3 Keeper pods Running; `curl http://localhost:8123/ping` returns `Ok.`; `curl http://localhost:8123/play` returns the Play UI HTML.

- [x] T006 [US1] Create `deploy/helm/clickhouse/Chart.yaml` with `apiVersion: v2`, `name: musematic-clickhouse`, `version: 0.1.0`, `description: ClickHouse OLAP analytics for Musematic platform` — no external chart dependencies (custom StatefulSet chart)
- [x] T007 [P] [US1] Create `deploy/helm/clickhouse/values.yaml` with shared defaults: `clickhouse.image: clickhouse/clickhouse-server:24.3`, `clickhouse.replicaCount: 2`, `clickhouse.keeper.enabled: true`, `clickhouse.keeper.replicaCount: 3`, `clickhouse.keeper.image: clickhouse/clickhouse-keeper:24.3`, `clickhouse.auth.user: default`, `clickhouse.auth.password: ""`, `clickhouse.resources.requests.memory: 4Gi`, `clickhouse.resources.requests.cpu: "2"`, `clickhouse.resources.limits.memory: 8Gi`, `clickhouse.resources.limits.cpu: "4"`, `clickhouse.config.max_memory_usage: "4000000000"`, `clickhouse.config.max_insert_block_size: 1048576`, `persistence.storageClassName: standard`, `persistence.size: 50Gi`, `service.type: ClusterIP`, `service.httpPort: 8123`, `service.nativePort: 9000`, `schemaInit.enabled: true`, `schemaInit.image: clickhouse/clickhouse-server:24.3`, `backup.enabled: true`, `backup.schedule: "0 4 * * *"`, `backup.image: altinity/clickhouse-backup:2.5`, `backup.bucket: backups`, `backup.prefix: clickhouse`, `networkPolicy.enabled: true`
- [x] T008 [P] [US1] Create `deploy/helm/clickhouse/values-prod.yaml` with production overrides: `clickhouse.replicaCount: 2`, `clickhouse.keeper.enabled: true`, `clickhouse.keeper.replicaCount: 3`, `persistence.size: 100Gi`, `clickhouse.resources.requests.memory: 8Gi`, `clickhouse.resources.requests.cpu: "4"`, `clickhouse.resources.limits.memory: 16Gi`, `networkPolicy.enabled: true`
- [x] T009 [P] [US1] Create `deploy/helm/clickhouse/values-dev.yaml` with development overrides: `clickhouse.replicaCount: 1`, `clickhouse.keeper.enabled: false`, `persistence.size: 20Gi`, `clickhouse.resources.requests.memory: 2Gi`, `clickhouse.resources.requests.cpu: "1"`, `networkPolicy.enabled: false`, `backup.enabled: false`
- [x] T010 [US1] Create `deploy/helm/clickhouse/templates/secret-credentials.yaml` — `Secret` named `clickhouse-credentials` with key `CLICKHOUSE_PASSWORD`; use Helm `lookup` to avoid regenerating on upgrades: `{{ (lookup "v1" "Secret" .Release.Namespace "clickhouse-credentials").data.CLICKHOUSE_PASSWORD | default (randAlphaNum 32 | b64enc) }}`
- [x] T011 [US1] Create `deploy/helm/clickhouse/templates/configmap-server.yaml` — `ConfigMap` containing `config.xml` overrides for ClickHouse server: sets `<max_memory_usage>`, `<max_insert_block_size>`, `<listen_host>0.0.0.0</listen_host>`, `<http_port>8123</http_port>`, `<tcp_port>9000</tcp_port>`, `<interserver_http_port>9009</interserver_http_port>`, and (in prod) `<zookeeper>` section pointing to Keeper service at `musematic-clickhouse-keeper.{{ .Release.Namespace }}:9181`
- [x] T012 [US1] Create `deploy/helm/clickhouse/templates/statefulset-server.yaml` — `StatefulSet` with `replicas: {{ .Values.clickhouse.replicaCount }}`; ClickHouse server container using `{{ .Values.clickhouse.image }}`; mounts `clickhouse-credentials` Secret as `CLICKHOUSE_PASSWORD` env var; mounts `configmap-server` at `/etc/clickhouse-server/config.d/`; `volumeClaimTemplates` for data PVC (`{{ .Values.persistence.size }}`); readiness probe: HTTP GET `/ping` port 8123; liveness probe: HTTP GET `/ping` port 8123 with 60s initial delay
- [x] T013 [P] [US1] Create `deploy/helm/clickhouse/templates/statefulset-keeper.yaml` — `StatefulSet` wrapped in `{{- if .Values.clickhouse.keeper.enabled }}`; `replicas: {{ .Values.clickhouse.keeper.replicaCount }}` (3 in prod); ClickHouse Keeper image; mounts keeper config with Raft peer addresses for each pod; `volumeClaimTemplates` for Keeper data PVC (5Gi)
- [x] T014 [P] [US1] Create `deploy/helm/clickhouse/templates/configmap-keeper.yaml` — ConfigMap wrapped in `{{- if .Values.clickhouse.keeper.enabled }}` with Keeper config: `<server_id>` via pod ordinal (using `downwardAPI` or pod name suffix), `<raft_configuration>` listing all 3 Keeper peers at `musematic-clickhouse-keeper-{0,1,2}.musematic-clickhouse-keeper.{{ .Release.Namespace }}:9234`
- [x] T015 [P] [US1] Create `deploy/helm/clickhouse/templates/service-server.yaml` — `Service` (ClusterIP) exposing ports 8123 (HTTP) and 9000 (TCP); create `deploy/helm/clickhouse/templates/service-keeper.yaml` — headless `Service` for Keeper pod DNS resolution on port 9181

**Checkpoint**: `helm lint deploy/helm/clickhouse` passes; `helm template -f values-prod.yaml` shows 2 ClickHouse + 3 Keeper replicas; `helm template -f values-dev.yaml` shows 1 ClickHouse, no Keeper.

---

## Phase 4: User Story 2 — Platform Initializes Analytics Tables and Materialized Views (Priority: P1)

**Goal**: All 4 analytics tables, 1 rollup target table, and 1 materialized view exist after a single idempotent init run; re-running produces no errors; materialized view auto-populates on insert.

**Independent Test**: Run schema init Job; `SHOW TABLES` returns all 6 tables/views; insert a row into `usage_events`; query `usage_hourly` — row with correct aggregation exists; re-run init Job — exits 0 with no duplicate error.

- [x] T016 [US2] Create `deploy/clickhouse/init/001-usage-events.sql` — `CREATE TABLE IF NOT EXISTS usage_events (event_id UUID, workspace_id UUID, user_id UUID, agent_id UUID, workflow_id Nullable(UUID), execution_id Nullable(UUID), provider String, model String, input_tokens UInt32, output_tokens UInt32, reasoning_tokens UInt32 DEFAULT 0, cached_tokens UInt32 DEFAULT 0, estimated_cost Decimal64(6), context_quality_score Nullable(Float32), reasoning_depth Nullable(UInt8), event_time DateTime64(3)) ENGINE = MergeTree() PARTITION BY toYYYYMM(event_time) ORDER BY (workspace_id, event_time, agent_id) TTL event_time + INTERVAL 365 DAY;` — use `ReplicatedMergeTree('/clickhouse/tables/{shard}/usage_events', '{replica}')` in prod (controlled via `{engine}` macro or separate prod SQL file)
- [x] T017 [P] [US2] Create `deploy/clickhouse/init/002-behavioral-drift.sql` — `CREATE TABLE IF NOT EXISTS behavioral_drift (agent_id UUID, revision_id UUID, metric_name String, metric_value Float64, baseline_value Float64, deviation Float64, measured_at DateTime64(3)) ENGINE = MergeTree() PARTITION BY toYYYYMM(measured_at) ORDER BY (agent_id, metric_name, measured_at) TTL measured_at + INTERVAL 180 DAY;`
- [x] T018 [P] [US2] Create `deploy/clickhouse/init/003-fleet-performance.sql` — `CREATE TABLE IF NOT EXISTS fleet_performance (fleet_id UUID, metric_name String, metric_value Float64, member_count UInt16, measured_at DateTime64(3)) ENGINE = MergeTree() PARTITION BY toYYYYMM(measured_at) ORDER BY (fleet_id, metric_name, measured_at);`
- [x] T019 [P] [US2] Create `deploy/clickhouse/init/004-self-correction-analytics.sql` — `CREATE TABLE IF NOT EXISTS self_correction_analytics (execution_id UUID, agent_id UUID, loop_id UUID, iterations UInt8, converged UInt8, initial_quality Float32, final_quality Float32, total_cost Decimal64(6), completed_at DateTime64(3)) ENGINE = MergeTree() PARTITION BY toYYYYMM(completed_at) ORDER BY (agent_id, completed_at);`
- [x] T020 [US2] Create `deploy/clickhouse/init/005-usage-hourly.sql` — `CREATE TABLE IF NOT EXISTS usage_hourly (workspace_id UUID, agent_id UUID, provider String, model String, hour DateTime, total_input_tokens UInt64, total_output_tokens UInt64, total_reasoning_tokens UInt64, total_cost Decimal128(6), event_count UInt64, avg_context_quality Float64) ENGINE = SummingMergeTree() PARTITION BY toYYYYMM(hour) ORDER BY (workspace_id, agent_id, provider, model, hour);` — must be created BEFORE the materialized view
- [x] T021 [US2] Create `deploy/clickhouse/init/006-usage-hourly-mv.sql` — `CREATE MATERIALIZED VIEW IF NOT EXISTS usage_hourly_mv TO usage_hourly AS SELECT workspace_id, agent_id, provider, model, toStartOfHour(event_time) AS hour, sum(input_tokens) AS total_input_tokens, sum(output_tokens) AS total_output_tokens, sum(reasoning_tokens) AS total_reasoning_tokens, sum(estimated_cost) AS total_cost, count() AS event_count, avg(context_quality_score) AS avg_context_quality FROM usage_events GROUP BY workspace_id, agent_id, provider, model, hour;`
- [x] T022 [US2] Create `deploy/helm/clickhouse/templates/schema-init-job.yaml` — Kubernetes `Job` with annotations `helm.sh/hook: post-install,post-upgrade` and `helm.sh/hook-weight: "5"`; wrapped in `{{- if .Values.schemaInit.enabled }}`; uses `{{ .Values.schemaInit.image }}`; init container polls `http://musematic-clickhouse.{{ .Release.Namespace }}:8123/ping` until ready (retries every 5s, max 60 retries); main container runs `clickhouse-client --host musematic-clickhouse.{{ .Release.Namespace }} --port 9000 --user default --password $CLICKHOUSE_PASSWORD --multiquery < /scripts/all-tables.sql`; mounts all 6 SQL files via ConfigMap (`deploy/clickhouse/init/`) and `CLICKHOUSE_PASSWORD` from `clickhouse-credentials` Secret; `restartPolicy: OnFailure`

**Checkpoint**: After `helm install`, `kubectl get jobs -n platform-data -l app=clickhouse-schema-init` shows `COMPLETIONS 1/1`; `SHOW TABLES` lists all 6; re-run produces no errors.

---

## Phase 5: User Story 3 — Services Insert and Query Analytics Data (Priority: P1)

**Goal**: Python services can insert analytics events via `insert_batch`, execute workspace-scoped SELECT queries, and receive correct results with workspace isolation.

**Independent Test**: Insert 1000 events across 3 workspaces; query with `workspace_id` filter; verify only matching rows returned; verify partition pruning via `EXPLAIN`.

- [x] T023 [US3] Implement `AsyncClickHouseClient.__init__` in `apps/control-plane/src/platform/common/clients/clickhouse.py`: raise `ClickHouseConnectionError("CLICKHOUSE_URL not configured")` if `settings.CLICKHOUSE_URL` is `None`; create `self._client = clickhouse_connect.get_async_client(host=..., port=8123, username=settings.CLICKHOUSE_USER, password=settings.CLICKHOUSE_PASSWORD, database=settings.CLICKHOUSE_DATABASE)` parsed from `settings.CLICKHOUSE_URL`; store `self._settings = settings`
- [x] T024 [US3] Implement `execute_query(sql, params={})` in `apps/control-plane/src/platform/common/clients/clickhouse.py`: call `await self._client.query(sql, parameters=params)`; convert result to `list[dict]` via `[dict(zip(result.column_names, row)) for row in result.result_rows]`; wrap `clickhouse_connect.driver.exceptions.Error` → `ClickHouseQueryError`
- [x] T025 [P] [US3] Implement `execute_command(sql, params={})` in `apps/control-plane/src/platform/common/clients/clickhouse.py`: call `await self._client.command(sql, parameters=params)`; return `None`; wrap exceptions → `ClickHouseQueryError`
- [x] T026 [P] [US3] Implement `insert_batch(table, data, column_names)` in `apps/control-plane/src/platform/common/clients/clickhouse.py`: convert `data` (list of dicts) to columnar format: `rows = [[row[col] for col in column_names] for row in data]`; call `await self._client.insert(table, rows, column_names=column_names)`; wrap exceptions → `ClickHouseQueryError`
- [x] T027 [P] [US3] Implement `health_check()` and `close()` in `apps/control-plane/src/platform/common/clients/clickhouse.py`: `health_check` calls `execute_query("SELECT version() AS version, uptime() AS uptime_seconds")` and returns `{"status": "ok", "version": rows[0]["version"], "uptime_seconds": rows[0]["uptime_seconds"]}`; on exception returns `{"status": "error", "error": str(e)}`; `close()` calls `self._client.close()`
- [x] T028 [US3] Write integration test `apps/control-plane/tests/integration/test_clickhouse_basic.py` using testcontainers ClickHouse container (or `CLICKHOUSE_TEST_MODE` env var): (1) insert 100 usage events across 3 workspaces; (2) query with `WHERE workspace_id = ...` → assert only correct workspace rows returned; (3) query without workspace filter → all rows returned; (4) `health_check()` returns `{"status": "ok"}`; (5) invalid SQL raises `ClickHouseQueryError`; (6) insert with wrong column count raises `ClickHouseQueryError`

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_clickhouse_basic.py -v` all pass.

---

## Phase 6: User Story 4 — Platform Computes Materialized Rollups Automatically (Priority: P1)

**Goal**: Inserting usage events automatically populates `usage_hourly` rollup; hourly aggregations are consistent with raw data sums; rollup queries return in under 200ms.

**Independent Test**: Insert 100 events for same workspace/agent/hour; query `usage_hourly` → 1 row with correct sums and event_count=100; insert 50 more for same hour → rollup updates correctly.

- [x] T029 [US4] Write integration test `apps/control-plane/tests/integration/test_clickhouse_materialized.py`: (1) insert 100 usage events for a fixed `workspace_id`, `agent_id`, `provider`, `model`, and `hour`; (2) query `SELECT total_input_tokens, event_count FROM usage_hourly WHERE workspace_id = ... AND hour = ...`; assert `event_count == 100` and `total_input_tokens == sum of inserted input_tokens`; (3) insert 50 more events for the same group → re-query → assert `event_count == 150`; (4) insert events for a different workspace → verify they appear in a separate `usage_hourly` row; (5) assert rollup query completes in < 200ms (using `time.perf_counter()`)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_clickhouse_materialized.py -v` all pass; all assertions including latency check.

---

## Phase 7: User Story 5 — Operator Backs Up and Restores Analytics Data (Priority: P2)

**Goal**: Daily backup CronJob uploads all table data to `backups/clickhouse/{date}/` in object storage; restore procedure documented and operational.

**Independent Test**: Run `clickhouse-backup` CronJob manually; verify backup appears in object storage; drop a table; run restore; verify row counts match.

- [x] T030 [US5] Create `deploy/helm/clickhouse/templates/configmap-backup.yaml` — `ConfigMap` wrapped in `{{- if .Values.backup.enabled }}` containing `clickhouse-backup` config YAML: `general.remote_storage: s3`, `s3.bucket: {{ .Values.backup.bucket }}`, `s3.path: {{ .Values.backup.prefix }}/`, `s3.endpoint: http://musematic-minio.platform-data:9000`, `s3.access_key: ...` (from Secret ref), `s3.secret_key: ...` (from Secret ref), `clickhouse.username: default`, `clickhouse.password: ...` (from Secret ref), `clickhouse.host: musematic-clickhouse.{{ .Release.Namespace }}`
- [x] T031 [P] [US5] Create `deploy/helm/clickhouse/templates/backup-cronjob.yaml` — `CronJob` with `schedule: {{ .Values.backup.schedule }}` (default `"0 4 * * *"`), wrapped in `{{- if .Values.backup.enabled }}`; uses `{{ .Values.backup.image }}` (`altinity/clickhouse-backup:2.5`); runs `clickhouse-backup create_remote --all`; mounts `configmap-backup` ConfigMap at `/etc/clickhouse-backup/config.yml`; mounts `CLICKHOUSE_PASSWORD` from `clickhouse-credentials` and MinIO credentials from `minio-platform-credentials`; `restartPolicy: OnFailure`

**Checkpoint**: `helm template deploy/helm/clickhouse -f values-prod.yaml | grep "kind: CronJob"` outputs 1; `helm template -f values-dev.yaml | grep "kind: CronJob"` outputs nothing.

---

## Phase 8: User Story 6 — Network Access Is Restricted to Authorized Namespaces (Priority: P2)

**Goal**: HTTP (8123) and TCP (9000) accessible from `platform-control` and `platform-execution`; metrics (8123) accessible from `platform-observability`; inter-replica (9000, 9009) and Keeper (9181, 9234, 9444) accessible within `platform-data`; all other namespaces blocked.

**Independent Test**: Deploy with `networkPolicy.enabled: true`; pod in `platform-control` → `curl /ping` succeeds; pod in `default` namespace → connection times out.

- [x] T032 [US6] Create `deploy/helm/clickhouse/templates/network-policy.yaml` — one `NetworkPolicy` wrapped in `{{- if .Values.networkPolicy.enabled }}`: `podSelector: {app.kubernetes.io/name: clickhouse}`; six ingress rules: (1) ports 8123+9000 from `platform-control` namespaceSelector; (2) ports 8123+9000 from `platform-execution` namespaceSelector; (3) port 8123 from `platform-observability` (metrics); (4) ports 9000+9009 from same `podSelector` within `platform-data` (inter-replica data exchange); (5) ports 9181+9234+9444 from `platform-data` podSelector matching Keeper pods (Keeper client + Raft)

**Checkpoint**: `helm template -f values-prod.yaml | grep "kind: NetworkPolicy"` outputs 1; `helm template -f values-dev.yaml | grep "kind: NetworkPolicy"` outputs nothing.

---

## Phase 9: User Story 7 — TTL Automatically Evicts Expired Data (Priority: P2)

**Goal**: `usage_events` TTL (365 days) and `behavioral_drift` TTL (180 days) are correctly configured; TTL eviction removes stale data on merge; `fleet_performance` and `self_correction_analytics` have no TTL.

**Independent Test**: Insert a row with `event_time = now() - INTERVAL 400 DAY`; force a merge; verify row is gone. Query `system.tables` for TTL expression on `usage_events` and `behavioral_drift` — verify 365-day and 180-day TTL present.

- [x] T033 [US7] Write integration test `apps/control-plane/tests/integration/test_clickhouse_partition.py`: (1) verify TTL on `usage_events`: `SELECT ttl_expression FROM system.tables WHERE name = 'usage_events'` → assert result contains `365`; (2) verify TTL on `behavioral_drift`: assert `ttl_expression` contains `180`; (3) verify NO TTL on `fleet_performance` and `self_correction_analytics`: assert `ttl_expression` is empty/null; (4) verify partition key on `usage_events`: `SELECT partition_key FROM system.tables WHERE name = 'usage_events'` → assert `toYYYYMM(event_time)`; (5) verify `EXPLAIN` partition pruning: execute `EXPLAIN PLAN SELECT count() FROM usage_events WHERE event_time >= '2026-04-01' AND event_time < '2026-05-01'` — assert output indicates partition filter applied

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_clickhouse_partition.py -v` all pass.

---

## Phase 10: User Story 3 (continued) — BatchBuffer for Efficient Event Ingestion

**Purpose**: Implement `BatchBuffer` for use by Kafka consumers (US3 continuation — batch insert utility is a core P1 deliverable per user input).

**Goal**: `BatchBuffer` accumulates rows and flushes via `insert_batch` when max size reached or timer fires; `stop()` flushes remaining rows.

- [x] T034 [US3] Implement `BatchBuffer.__init__`, `add`, `flush`, `start`, `stop` in `apps/control-plane/src/platform/common/clients/clickhouse.py`: `__init__(client, table, column_names, max_size=1000, flush_interval=5.0)` stores params; `add(row)` appends to `self._buffer: list[dict]`, calls `flush()` if `len(self._buffer) >= self._max_size`; `flush()` calls `await self._client.insert_batch(self._table, self._buffer, self._column_names)` then clears buffer — no-op if buffer empty; `start()` creates `self._task = asyncio.create_task(self._flush_loop())` where loop calls `flush()` every `self._flush_interval` seconds; `stop()` cancels task and awaits final `flush()`
- [x] T035 [US3] Write integration test `apps/control-plane/tests/integration/test_clickhouse_batch_buffer.py`: (1) `BatchBuffer` with `max_size=50` — add 120 rows → verify 2 auto-flushes happen (rows 50 and 100), remaining 20 flushed by `stop()`; (2) `BatchBuffer` with `flush_interval=0.1` — add 10 rows, wait 0.2s → verify timer flush occurred; (3) `stop()` flushes remaining rows even if `max_size` not reached; (4) concurrent `add()` calls are safe (asyncio single-threaded, no lock needed)

**Checkpoint**: `pytest apps/control-plane/tests/integration/test_clickhouse_batch_buffer.py -v` all pass.

---

## Phase 11: Polish & Cross-Cutting Concerns

**Purpose**: Quality gates, linting, type checking, Helm lint.

- [X] T036 [P] Run `helm lint deploy/helm/clickhouse` and fix any linting errors; verify `helm template` renders valid YAML for both prod and dev values
- [x] T037 [P] Run `ruff check apps/control-plane/src/platform/common/clients/clickhouse.py` and fix all violations; ensure all public methods have type annotations
- [x] T038 [P] Run `mypy apps/control-plane/src/platform/common/clients/clickhouse.py` in strict mode; fix type errors; add `# type: ignore[import-untyped]` with comment for any missing `clickhouse-connect` stubs
- [x] T039 [P] Create `deploy/helm/clickhouse/templates/configmap-init-scripts.yaml` — `ConfigMap` that bundles all 6 SQL files from `deploy/clickhouse/init/` for mounting into the schema init Job; verify the schema init Job (T022) references this ConfigMap correctly and executes scripts in order 001–006

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks all Python client work**
- **US1 (Phase 3)**: Depends on Phase 1 (dirs created); Helm-only, independent of Python work
- **US2 (Phase 4)**: SQL scripts (T016–T021) independent of cluster; init Job (T022) needs US1 chart templates
- **US3 (Phase 5)**: Depends on Foundational (client types); integration tests need US1+US2 (cluster + tables)
- **US4 (Phase 6)**: Depends on US3 (uses `insert_batch` for test data; needs materialized view from US2)
- **US3 BatchBuffer (Phase 10)**: Depends on US3 Phase 5 (`insert_batch` must be implemented first)
- **US5 (Phase 7)**: Depends on US1 Helm chart for CronJob template; independent of Python client
- **US6 (Phase 8)**: Depends on US1 Helm chart for NetworkPolicy template
- **US7 (Phase 9)**: Depends on US2 (tables must exist for TTL/partition verification)
- **Polish (Phase 11)**: Depends on all phases complete

### Dependency Graph

```
Phase 1 (Setup)
    ├── Phase 2 (Foundational: exceptions + client stubs)
    │       ├── Phase 5 (US3: execute_query + insert_batch)
    │       │       ├── Phase 6 (US4: materialized view consistency test)
    │       │       └── Phase 10 (US3 BatchBuffer)
    │       └── (US7 integration tests need US2 tables)
    └── Phase 3 (US1: Helm chart + cluster)
            ├── Phase 4 (US2: SQL init scripts + init Job)
            │       └── Phase 9 (US7: TTL/partition verification)
            ├── Phase 7 (US5: Backup CronJob)
            └── Phase 8 (US6: Network policy)

Phase 11 (Polish): depends on all phases above
```

### User Story Dependencies

- **US1 (P1)**: Can start after Setup — Helm only
- **US2 (P1)**: SQL files independent; init Job template needs US1 chart; integration with US3 for MV test
- **US3 (P1)**: Needs Foundational (Phase 2) for client stubs; integration tests need US1+US2
- **US4 (P1)**: Needs US3 working `insert_batch` + US2 materialized view
- **US5 (P2)**: Needs US1 for CronJob template; backup tool is independent
- **US6 (P2)**: Needs US1 for NetworkPolicy template
- **US7 (P2)**: Needs US2 for table TTL verification; integration test needs running ClickHouse

### Parallel Opportunities

- **Phase 1**: T002, T003 in parallel after T001
- **Phase 3 (US1)**: T007, T008, T009, T013, T014, T015 in parallel after T006
- **Phase 4 (US2)**: T017, T018, T019 in parallel after T016 (other base tables)
- **Phase 5 (US3)**: T025, T026, T027 in parallel after T024 (`execute_query`)
- **Phase 7 + 8**: T030+T031 (backup) and T032 (network policy) in parallel
- **Phase 11**: T036, T037, T038, T039 all in parallel

---

## Parallel Example: Phase 5 (US3 — Insert/Query)

```
# Sequential: T023 (AsyncClickHouseClient.__init__) must complete first

# After T023, parallel:
Task T024: execute_query method
Task T025: execute_command method
Task T026: insert_batch method
Task T027: health_check + close

# Sequential after all above:
Task T028: integration test test_clickhouse_basic.py
```

---

## Implementation Strategy

### MVP (User Stories 1–4 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T005)
3. Complete Phase 3: US1 — Cluster (T006–T015)
4. Complete Phase 4: US2 — Table Init (T016–T022)
5. Complete Phase 5: US3 — Insert/Query (T023–T028)
6. Complete Phase 6: US4 — Materialized View (T029)
7. Complete Phase 10: BatchBuffer (T034–T035)
8. **STOP and VALIDATE**: Cluster deployed, tables initialized, insert/query working, rollup auto-computed

### Incremental Delivery

After MVP:
1. Add US5 (Backup) → 2 tasks → test clickhouse-backup CronJob
2. Add US6 (Network policy) → 1 task → test namespace isolation
3. Add US7 (TTL verification) → 1 test task → verify table TTL config
4. Polish → quality gates

### Parallel Team Strategy

With multiple developers after Phase 1 + 2:
- Developer A: US1 (Helm chart) → US2 (SQL init scripts + Job)
- Developer B: US3 (Python client) → US4 (materialized view test)
- Developer C: US5 + US6 (backup + network policy, Helm templates)

---

## Notes

- [P] tasks use different files with no dependencies on incomplete tasks
- The ClickHouse Keeper StatefulSet (3 nodes) is only deployed in production (`keeper.enabled: true`). In dev, `MergeTree` requires no Keeper.
- SQL init scripts are numbered (001–006) and must be executed in order — `005-usage-hourly.sql` MUST precede `006-usage-hourly-mv.sql` because the materialized view writes to the target table
- Integration tests require either a running ClickHouse instance or `testcontainers` ClickHouse image (`clickhouse/clickhouse-server`); set `CLICKHOUSE_TEST_MODE=testcontainers`
- `insert_batch` uses `clickhouse-connect`'s columnar insert (not row-by-row) — this is the high-throughput path for Kafka consumer ingestion
- `BatchBuffer` is designed for use by Kafka consumers in the `analytics` bounded context (downstream) — the buffer itself is a standalone utility in the client module
- Feature 003 (Kafka) provides the event backbone; this feature does NOT implement Kafka consumers — the client and batch buffer are the integration point
- Feature 004 (MinIO) must be deployed before the backup CronJob can upload; backup is disabled in dev values
- `SummingMergeTree` for `usage_hourly` auto-sums numeric columns during merges — queries should use `sum(total_input_tokens)` not `total_input_tokens` directly to account for pre-merge partial sums
- ClickHouse has no local mode fallback — `CLICKHOUSE_URL` must be set or `ClickHouseConnectionError` is raised at construction time
