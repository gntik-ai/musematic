# Research: Simulation Controller — Isolated Simulation Environments

**Feature**: 012-simulation-controller  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: Go Service Architecture — Satellite Binary at `services/simulation-controller/`

**Decision**: The simulation controller is an independent Go binary at `services/simulation-controller/`, communicating via gRPC on port 50055 (`google.golang.org/grpc 1.67+`) per the constitution gRPC Service Registry. It deploys to the `platform-simulation` Kubernetes namespace. Standard Go layout: `cmd/simulation-controller/main.go`, `internal/` (private packages), `api/grpc/` (gRPC server handler), `pkg/` (shared helpers).

**Rationale**: Constitution §VII mandates simulation isolation in `platform-simulation` namespace and the gRPC Service Registry explicitly defines `SimulationControlService` at port 50055 in `platform-simulation`. The simulation controller is a natural satellite: it manages Kubernetes pod lifecycle (`client-go 0.31+`), enforces isolation via NetworkPolicy, and handles artifact collection — all workloads that match the Go satellite pattern established by the runtime-controller (009) and sandbox-manager (010).

**Alternatives considered**:
- Extending the sandbox manager: Different isolation model (sandbox runs in `platform-execution`, simulation pods must be in `platform-simulation`). Separate service avoids cross-namespace confusion. Rejected.
- Python implementation: Pod lifecycle management and streaming are better served by Go's goroutines than asyncio. Consistent with the established satellite pattern. Rejected.

---

## Decision 2: Pod Isolation Strategy — Namespace + NetworkPolicy + Label Enforcement

**Decision**: All simulation pods are created in the `platform-simulation` Kubernetes namespace with:
1. **Label**: `simulation=true` on every pod, used for policy selection and artifact tagging
2. **NetworkPolicy**: A deny-all egress policy to production namespaces (`platform-control`, `platform-execution`, `platform-edge`) applied to all pods with `simulation=true` label. Allows egress to `platform-simulation` (intra-namespace) and `platform-data` (for simulation-artifacts bucket, Kafka `simulation.events` topic)
3. **Environment variable**: `SIMULATION=true` injected into every container env, `SIMULATION_BUCKET=simulation-artifacts`
4. **RBAC**: The simulation controller's ServiceAccount holds a ClusterRole with pod create/delete/list/watch rights scoped to `platform-simulation` only

The NetworkPolicy blocks all egress to production namespaces. The simulation bucket env var ensures agents write to `simulation-artifacts` not the production bucket (enforced client-side by the injected config, not by the controller).

**Rationale**: Constitution §VII requires network policies preventing access to production namespaces. Namespace-scoped NetworkPolicy with label selectors is the Kubernetes-native mechanism. Using both the namespace and the label as selectors provides defense in depth. RBAC scoping prevents the controller from accidentally touching production namespaces.

**Alternatives considered**:
- Pod Security Policy / Pod Security Standards only: Does not block network egress. Rejected — network isolation requires NetworkPolicy.
- Separate cluster for simulation: Overkill for this platform scale. Rejected.
- Application-level "simulation mode" flag without network isolation: Insufficient — network isolation must be enforced at the infrastructure layer per §VII. Rejected.

---

## Decision 3: Simulation State — In-Memory Map + PostgreSQL Cold State (No Redis)

**Decision**: Simulation lifecycle state is held in an in-process `sync.Map` (simulation_id → `SimulationState` struct) for fast status queries, with PostgreSQL as the system-of-record. Unlike the runtime controller's heartbeat-based ephemeral state, simulations are coarse-grained (create/run/terminate) and do not require sub-millisecond state access. PostgreSQL tables:
- `simulations`: simulation_id, agent_config_json, status, namespace, pod_name, created_at, started_at, completed_at, terminated_at, error_message
- `simulation_artifacts`: artifact_id, simulation_id, object_key, filename, size_bytes, content_type, created_at
- `ate_sessions`: session_id, simulation_id, scenarios_json, created_at, completed_at
- `ate_results`: result_id, session_id, scenario_id, passed, quality_score, latency_ms, cost, safety_compliant, error_message, created_at

On service restart: re-list pods in `platform-simulation` namespace with `simulation=true` label to rebuild in-memory state for any running simulations.

**Rationale**: Simulations run for seconds to minutes, not milliseconds. PostgreSQL provides ACID guarantees for simulation records and ATE results (which are system-of-record data for the trust framework). In-memory map eliminates network round-trips for status queries (SC-012: < 100ms). On restart, pod listing via `client-go` reconstructs state from Kubernetes — the authoritative source for running pods.

**Alternatives considered**:
- Redis for hot state: Unnecessary for simulation-granularity state; adds a Redis dependency this service doesn't otherwise need. Rejected.
- PostgreSQL only for status queries: Too slow for frequent status polling under 20+ concurrent simulations. Rejected.

---

## Decision 4: Artifact Collection — kubectl exec tar → MinIO `simulation-artifacts` Bucket

**Decision**: Artifact collection uses the same pattern as the sandbox manager (010): `kubectl exec` with `remotecommand` (SPDY) to run `tar -czf - /output /workspace` inside the simulation pod, then stream the tarball to MinIO at `simulation-artifacts/{simulation_id}/{filename}`. Every object is uploaded with object metadata: `x-amz-meta-simulation=true`, `x-amz-meta-simulation-id={simulation_id}`. Metadata row inserted to `simulation_artifacts` table.

**Rationale**: The remotecommand pattern is already established in the sandbox manager. Reusing it keeps cross-service consistency. MinIO object metadata tags ensure all artifacts are traceable to their simulation. The separate bucket (`simulation-artifacts`) enforces FR-004 at the storage layer, not just at the application layer.

**Alternatives considered**:
- Sidecar artifact collector: Adds pod complexity and requires the agent pod spec to include the sidecar. Rejected — exec-based collection is simpler and already proven.
- Shared bucket with simulation prefix only: A misconfiguration could still write to production prefixes. Separate bucket provides a hard boundary. Rejected.

---

## Decision 5: Event Streaming — Server-Streaming gRPC + Kafka `simulation.events`

**Decision**: `StreamSimulationEvents` is a server-streaming gRPC method (client sends request with simulation_id, server pushes events). Events are generated from two sources:
1. **Pod watch**: `client-go` `Watch()` on pods in `platform-simulation` with `simulation-id={id}` label selector — pod phase changes, container state transitions, OOM events
2. **Internal publisher**: Simulation controller publishes lifecycle events (CREATED, STARTED, COMPLETED, FAILED, TERMINATED, ARTIFACT_COLLECTED) to an in-process fan-out registry

All events are also emitted to Kafka `simulation.events` topic (keyed by `simulation_id`) for downstream consumers (the Python `simulation/` bounded context). Events carry `simulation=true` flag in all metadata fields.

**Rationale**: Constitution Kafka Topics Registry mandates `simulation.events` topic keyed by `simulation_id`. Server-streaming gRPC matches the pattern used by sandbox-manager's `StreamSandboxLogs`. The pod Watch provides real-time Kubernetes-level events without polling. Fan-out registry handles multiple concurrent subscribers.

**Alternatives considered**:
- Redis Pub/Sub for events: Would add Redis dependency this service doesn't need. Fan-out registry is simpler for same-binary subscribers. Rejected.
- Polling-based status: Adds latency, wastes CPU. Watch-based is push-driven. Rejected.

---

## Decision 6: Accredited Testing Environment (ATE) — Specialized Simulation with Pre-loaded Scenarios

**Decision**: `CreateAccreditedTestEnv` creates a regular simulation pod in `platform-simulation` with two additions:
1. **ConfigMap injection**: Test scenarios (JSON array), golden datasets (MinIO references), and evaluation scorer config are mounted as a ConfigMap into the ATE pod at `/ate/scenarios.json`, `/ate/datasets/`, `/ate/scorers/`
2. **Sequential execution loop**: The ATE pod runs an agent-runner binary (pre-baked into the ATE image) that iterates scenarios sequentially; after each scenario the runner calls back to the simulation controller via a unidirectional gRPC stream (the `StreamSimulationEvents` stream is used to deliver per-scenario results as structured events)

ATE results are written to `ate_results` table. After completion, the controller collects all results and produces a structured JSON report uploaded to `simulation-artifacts/{simulation_id}/ate-report.json`. The report conforms to a fixed schema: `{session_id, agent_id, scenarios: [{scenario_id, passed, quality_score, latency_ms, cost, safety_compliant, error?}], summary: {total, passed, failed}}`.

**Rationale**: Reusing the simulation pod creation path avoids duplicating isolation logic. ConfigMap-based scenario injection is the Kubernetes-native way to inject read-only configuration. Sequential execution (not concurrent) matches the spec requirement ("run agent against all scenarios sequentially"). The structured JSON report is stored in the simulation bucket — consistent with FR-004 and FR-009.

**Alternatives considered**:
- Separate ATE pod image: Tightly couples the controller to a specific image. Rejected — scenarios and datasets are injected via ConfigMap, the agent image is caller-supplied.
- gRPC bidirectional streaming for ATE execution: More complex; the ATE runner only needs to push results to the controller, not receive commands mid-stream. Rejected.
- Storing ATE results only in PostgreSQL: Large reports could exceed column size limits. MinIO for the full report + PostgreSQL for per-result metadata is the established pattern. Rejected.

---

## Decision 7: Orphan Detection — Periodic Label-Based Pod Listing

**Decision**: A background goroutine runs every 60 seconds, listing all pods in `platform-simulation` with label `simulation=true`. For each pod, the controller checks if the simulation_id from the `simulation-id` pod label exists in the in-memory map. If not (orphaned pod — controller restarted and state was not rebuilt, or a failed creation left a pod), the pod is scheduled for deletion. State rebuild on startup also uses this pod list to reconnect running simulations.

**Rationale**: Same orphan detection pattern as the sandbox manager (010). Label-based listing is O(n) over only simulation pods — not all pods in the cluster. The 60-second interval balances resource reclamation latency against API server load. State rebuild on startup is necessary because simulation pods can survive a controller restart.

**Alternatives considered**:
- Kubernetes finalizers: Ensures cleanup even when the controller is not running at termination time. More complex to implement. Left as a future enhancement — for v1, the orphan scanner is sufficient. Rejected for v1 complexity.
- StatefulSets for simulations: Overkill; simulations are ephemeral, not stateful replicas. Rejected.

---

## Decision 8: gRPC Methods — 6 RPCs on Port 50055

**Decision**: `SimulationControlService` exposes 6 RPCs:
1. `CreateSimulation(CreateSimulationRequest) → SimulationHandle` — unary; creates pod in `platform-simulation`, inserts DB row, returns handle
2. `GetSimulationStatus(GetSimulationStatusRequest) → SimulationStatus` — unary; reads in-memory state
3. `StreamSimulationEvents(StreamSimulationEventsRequest) → stream SimulationEvent` — server-streaming; pod Watch + fan-out registry
4. `TerminateSimulation(TerminateSimulationRequest) → TerminateResult` — unary; deletes pod, cleans NetworkPolicy, updates DB
5. `CollectSimulationArtifacts(CollectSimulationArtifactsRequest) → ArtifactCollectionResult` — unary; exec tar → MinIO upload, updates artifact rows
6. `CreateAccreditedTestEnv(CreateATERequest) → ATEHandle` — unary; creates specialized simulation pod with ConfigMap-injected scenarios

**Rationale**: 6 methods cleanly map to the 5 user stories. The split between `CreateSimulation` and `CreateAccreditedTestEnv` keeps ATE configuration (scenarios, datasets) out of the general simulation creation path. All methods are unary except the event stream, which requires server-streaming.

**Alternatives considered**:
- Merging CreateSimulation and CreateAccreditedTestEnv with an `ate_config` optional field: Clutters the general API with ATE-specific fields. Rejected — separate methods are cleaner.
- Bidirectional streaming for events: Server doesn't need to receive messages from the client after the initial subscription. Rejected.
