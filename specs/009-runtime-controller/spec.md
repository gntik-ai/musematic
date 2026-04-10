# Feature Specification: Runtime Controller — Agent Runtime Pod Lifecycle

**Feature Branch**: `009-runtime-controller`
**Created**: 2026-04-10
**Status**: Draft
**Input**: User description: Build and deploy the Go Runtime Controller that manages agent runtime pod lifecycle on Kubernetes: launch, inspect, stop, reconcile drift, stream events, manage warm pools, and handle heartbeats.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Execution Engine Launches and Manages Agent Runtimes (Priority: P1)

The execution engine requests the runtime controller to launch an agent runtime pod with a specific runtime contract (agent revision, model binding, policies, correlation context, reasoning configuration, context engineering profile, and reasoning budget envelope). The controller creates the pod with the agent package mounted read-only, applies resource limits, injects environment variables, and sets labels for tracking. The execution engine can later inspect the runtime's state (running, paused, stopped, failed), pause and resume it, or stop it gracefully. A graceful stop sends a termination signal and waits for a configurable grace period before forcibly killing the pod.

**Why this priority**: Without the ability to launch and manage runtime pods, no agent can execute. This is the foundational capability that all other stories and all downstream agent operations depend on.

**Independent Test**: Request a runtime launch with a valid runtime contract, verify the pod starts within 10 seconds (cold start), confirm the agent package is mounted read-only, verify resource limits are enforced, inspect the runtime state (expect "running"), stop it gracefully, and confirm the pod is terminated and state is "stopped".

**Acceptance Scenarios**:

1. **Given** a valid runtime contract, **When** the execution engine requests a launch, **Then** a runtime pod starts within 10 seconds with the agent package mounted read-only, resource limits enforced, and pod labels matching the contract metadata.
2. **Given** a running runtime, **When** the execution engine requests the runtime state, **Then** the controller returns the current state (running), pod status, and last heartbeat timestamp.
3. **Given** a running runtime, **When** the execution engine requests a pause, **Then** the runtime enters a paused state and stops processing but retains its pod and memory.
4. **Given** a paused runtime, **When** the execution engine requests a resume, **Then** the runtime returns to a running state and resumes processing.
5. **Given** a running runtime, **When** the execution engine requests a graceful stop, **Then** the controller sends a termination signal, waits for the configured grace period (default 30 seconds), and terminates the pod. The runtime state transitions to "stopped".
6. **Given** a running runtime, **When** the grace period expires without the pod stopping, **Then** the controller forcibly kills the pod and marks the runtime as "force-stopped".

---

### User Story 2 — Controller Automatically Reconciles Runtime State Drift (Priority: P1)

The runtime controller runs a continuous reconciliation loop that compares its tracked runtimes (persisted in the system-of-record database) against actual pod status on the container orchestrator. When discrepancies are found — orphaned pods (pods without a tracked runtime), missing pods (tracked runtimes whose pods no longer exist), or state mismatches (tracked state differs from actual pod phase) — the controller automatically corrects them: orphaned pods are terminated, missing pods are marked as failed, and state mismatches are updated to reflect reality. Drift events are emitted to the monitoring system for operator visibility.

**Why this priority**: Without reconciliation, runtimes can become orphaned (wasting resources) or stale (reporting incorrect state). This is critical for platform reliability and cost management.

**Independent Test**: Launch 5 runtimes, externally delete 2 pods (simulating crashes), and externally create 1 orphaned pod. Wait for one reconciliation cycle. Verify the 2 missing runtimes are marked as failed, the orphaned pod is terminated, and drift events are emitted.

**Acceptance Scenarios**:

1. **Given** a tracked runtime whose pod was externally terminated, **When** the reconciliation loop runs, **Then** the runtime is marked as "failed" with reason "pod_disappeared" and a drift event is emitted.
2. **Given** an orphaned pod with no matching tracked runtime, **When** the reconciliation loop runs, **Then** the orphaned pod is terminated and a drift event is emitted.
3. **Given** a tracked runtime in state "running" but whose pod is in phase "Failed", **When** the reconciliation loop runs, **Then** the tracked state is updated to "failed" and a drift event is emitted.
4. **Given** a reconciliation loop configured to run every 30 seconds, **When** the controller is running, **Then** the loop executes approximately every 30 seconds and completes within 5 seconds for up to 1,000 tracked runtimes.

---

### User Story 3 — Execution Engine Receives Real-Time Runtime Events (Priority: P1)

The execution engine subscribes to a real-time event stream from the runtime controller to receive lifecycle events (launched, paused, resumed, stopped, failed, heartbeat received, artifact collected) for one or more runtimes. Events are delivered with minimal latency so the execution engine can react to state changes (e.g., schedule the next step when the current step completes, trigger recovery when a runtime fails).

**Why this priority**: The execution engine needs real-time feedback to orchestrate multi-step workflows. Without event streaming, the engine would need to poll for state changes, adding latency and load.

**Independent Test**: Subscribe to events for a runtime, launch it, pause it, resume it, and stop it. Verify all 4 lifecycle events (launched, paused, resumed, stopped) are received in order with correct timestamps and runtime identifiers.

**Acceptance Scenarios**:

1. **Given** an active event subscription, **When** a runtime transitions from one state to another, **Then** a lifecycle event is delivered to the subscriber within 500 milliseconds.
2. **Given** an active event subscription for a specific runtime, **When** an unrelated runtime changes state, **Then** no event is delivered on this subscription (events are scoped).
3. **Given** multiple active subscriptions for the same runtime, **When** the runtime changes state, **Then** all subscribers receive the event.
4. **Given** a subscriber that disconnects and reconnects, **When** events occurred during the disconnection, **Then** the subscriber can request missed events by providing a last-seen event timestamp.

---

### User Story 4 — Warm Pool Enables Sub-2-Second Agent Launches (Priority: P2)

The runtime controller maintains a configurable warm pool of pre-initialized runtime pods per workspace and agent type. When a launch request arrives and a matching warm pod is available, the controller assigns it to the request and injects the runtime-specific configuration, achieving launch times under 2 seconds (compared to ~10 seconds for cold starts). Warm pods are recycled after a configurable idle timeout. Operators can configure pool sizes per workspace/agent-type combination.

**Why this priority**: Fast launch is important for interactive user experiences but not required for the controller to function. Cold start (10 seconds) is acceptable for batch and background executions.

**Independent Test**: Pre-warm 3 pods for a specific workspace and agent type. Request a launch — verify it completes in under 2 seconds. Request 3 more launches — verify the first 3 use warm pods and the 4th falls back to cold start.

**Acceptance Scenarios**:

1. **Given** a warm pool with available pods matching the request, **When** a launch is requested, **Then** the runtime starts in under 2 seconds using a warm pod.
2. **Given** an empty warm pool, **When** a launch is requested, **Then** the runtime starts via cold start (under 10 seconds) and the warm pool begins replenishing.
3. **Given** a warm pod that has been idle beyond the configured timeout, **When** the timeout expires, **Then** the warm pod is recycled (terminated and replaced with a fresh one).
4. **Given** a warm pool configured for 5 pods, **When** 3 pods are dispatched for active runtimes, **Then** the pool replenishes to maintain 5 available pods.

---

### User Story 5 — Controller Detects and Handles Dead Workers via Heartbeats (Priority: P2)

Running runtimes send periodic heartbeats to the controller. If a runtime's heartbeat is not received within a configurable timeout (default 60 seconds), the controller marks it as failed and initiates dead-worker handling: emitting a failure event, cleaning up the pod, and notifying the execution engine so it can trigger recovery or retry logic.

**Why this priority**: Heartbeat monitoring catches silent failures (runtimes that hang without crashing) that reconciliation alone cannot detect quickly. Important for production reliability but not needed for basic lifecycle management.

**Independent Test**: Launch a runtime, verify heartbeats are received. Simulate heartbeat loss by blocking heartbeat messages. Wait for the timeout. Verify the runtime is marked as failed and a dead-worker event is emitted.

**Acceptance Scenarios**:

1. **Given** a running runtime sending heartbeats every 15 seconds, **When** the heartbeat is received, **Then** the controller updates the last heartbeat timestamp.
2. **Given** a running runtime, **When** no heartbeat is received for 60 seconds (configurable), **Then** the controller marks the runtime as "failed" with reason "heartbeat_timeout" and emits a dead-worker event.
3. **Given** a runtime marked as dead-worker, **When** the controller handles it, **Then** the pod is terminated and the execution engine is notified to trigger recovery.
4. **Given** a temporarily slow runtime, **When** a heartbeat arrives just before the timeout, **Then** the timeout resets and the runtime remains in "running" state.

---

### User Story 6 — Controller Enforces Secrets Isolation from Agent LLM Context (Priority: P2)

When launching a runtime pod, the controller resolves secret references from the platform vault and injects secret values directly into the pod's filesystem or environment — accessible only by tool execution code. The LLM process within the agent receives only the secret reference names (e.g., `SECRETS_REF=api-key-ref`), never the actual values. Additionally, tool output sanitization strips known secret patterns from tool results before they return to the LLM context. This ensures that secrets never enter the LLM's context window, preventing exfiltration via prompt injection or tool misuse.

**Why this priority**: Critical for security and compliance, but the controller can launch pods without vault integration during initial development (using direct environment variables). Full secrets isolation is required before production deployment.

**Independent Test**: Launch a runtime with secret references. Inspect the pod's environment — verify the LLM process sees only reference names. Invoke a tool that returns a secret value in its output — verify the sanitizer strips it before the result reaches the LLM context.

**Acceptance Scenarios**:

1. **Given** a runtime contract with secret references, **When** the controller launches the pod, **Then** secret values are resolved from the vault and injected into the pod's filesystem, accessible only by tool execution code.
2. **Given** a running runtime, **When** the LLM process inspects its environment, **Then** it sees only `SECRETS_REF` entries (reference names), not secret values.
3. **Given** a tool that returns output containing a known secret pattern (API key, token), **When** the tool result is returned, **Then** the secret patterns are stripped before the result enters the LLM context.
4. **Given** a vault that is temporarily unavailable, **When** a launch is requested with secret references, **Then** the launch fails with a clear error indicating vault unavailability (no fallback to plaintext secrets).

---

### User Story 7 — Controller Persists Task Plans as Auditable Records Before Dispatch (Priority: P2)

Before dispatching an agent execution, the runtime controller persists a task plan record capturing: which agents and tools were considered for each step, which was selected and why, what parameters were injected and their provenance. This record is distinct from the reasoning trace (chain-of-thought during execution) and provides a pre-execution audit trail for explainability. Task plan records are stored in the system-of-record database (metadata) and object storage (full payload), linked to the execution ID and step ID.

**Why this priority**: Task plan persistence is required for Layer 4 (explainability) of the trust framework but does not block basic runtime lifecycle management.

**Independent Test**: Request a launch with a runtime contract that includes a task plan. Verify the task plan record is persisted before the pod starts. Retrieve the record by execution ID — verify it contains the expected agent/tool selection rationale and parameter provenance.

**Acceptance Scenarios**:

1. **Given** a launch request with a task plan, **When** the controller processes the request, **Then** the task plan record is persisted before the runtime pod is created.
2. **Given** a persisted task plan record, **When** queried by execution ID and step ID, **Then** the record is returned with all fields: considered agents, selected agent, selection rationale, injected parameters, and parameter provenance.
3. **Given** a task plan with a payload exceeding the database metadata size limit, **When** persisted, **Then** the metadata is stored in the database and the full payload is stored in object storage with a reference link.
4. **Given** a launch request without a task plan, **When** the controller processes it, **Then** the launch proceeds and a minimal task plan record is created noting "no task plan provided".

---

### User Story 8 — Controller Collects and Archives Runtime Artifacts (Priority: P2)

After a runtime completes execution, the controller collects output artifacts (execution logs, generated files, metrics snapshots) from the runtime pod and archives them to object storage. The execution engine can request artifact collection at any time, and the controller automatically collects artifacts before terminating a completed runtime. Artifacts are organized by execution ID in the object storage bucket.

**Why this priority**: Artifact collection is important for post-execution analysis and debugging but does not block basic runtime lifecycle management.

**Independent Test**: Launch a runtime that produces output files. Request artifact collection. Verify all artifacts are uploaded to object storage under the correct execution ID path. Terminate the runtime and verify artifacts are still accessible.

**Acceptance Scenarios**:

1. **Given** a completed runtime with output artifacts, **When** the execution engine requests artifact collection, **Then** all artifacts are uploaded to object storage under `artifacts/{execution_id}/`.
2. **Given** a runtime being gracefully stopped, **When** the stop is initiated, **Then** artifacts are collected before the pod is terminated.
3. **Given** collected artifacts, **When** the execution engine queries by execution ID, **Then** a manifest listing all collected artifacts (paths, sizes, timestamps) is returned.
4. **Given** a runtime that crashed without producing artifacts, **When** artifact collection is attempted, **Then** the controller captures available logs and pod status as the artifact set, with a note indicating incomplete execution.

---

### Edge Cases

- What happens when multiple launch requests arrive for the same execution ID? The controller rejects duplicate launches with a conflict error. Each execution ID maps to exactly one runtime. The execution engine must stop the existing runtime before launching a new one with the same execution ID.
- What happens when the controller itself restarts? On startup, the controller loads all tracked runtimes from the database and reconciles them against actual pod state. Runtimes that were being tracked by the previous instance are adopted. In-flight event subscriptions are lost and must be re-established by subscribers.
- What happens when the container orchestrator's API is unreachable? The controller enters a degraded mode: it continues accepting state queries from its database but rejects new launch/stop requests. It retries the orchestrator connection with exponential backoff. Drift events are emitted to alert operators.
- What happens when a warm pool pod is corrupted or enters an error state? The reconciliation loop detects the unhealthy warm pod, terminates it, and the warm pool manager replaces it with a fresh pod. A drift event is emitted.
- What happens when artifact collection fails mid-upload? The controller retries the upload with exponential backoff (3 attempts). If all retries fail, the artifact collection is marked as partial with a list of successfully uploaded and failed artifacts. The runtime can still be stopped — artifact failure does not block lifecycle operations.
- What happens when the vault is unavailable during pod launch? The launch fails immediately with a vault unavailability error. The controller does NOT fall back to plaintext secrets or skip secret injection — this is a hard security boundary.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST launch a runtime pod from a runtime contract containing agent revision, model binding, policies, correlation IDs, reasoning configuration, context engineering profile, and reasoning budget envelope.
- **FR-002**: System MUST mount the agent package as read-only storage in the runtime pod.
- **FR-003**: System MUST apply resource limits (CPU, memory) specified in the runtime contract to the pod.
- **FR-004**: System MUST support lifecycle operations: launch, inspect (get state), pause, resume, stop (graceful + force kill after grace period).
- **FR-005**: System MUST persist runtime state (running, paused, stopped, failed, force-stopped) to the system-of-record database.
- **FR-006**: System MUST run a reconciliation loop at a configurable interval (default 30 seconds) comparing tracked runtimes against actual pod state.
- **FR-007**: System MUST terminate orphaned pods (pods without tracked runtimes) during reconciliation.
- **FR-008**: System MUST mark tracked runtimes as failed when their pods no longer exist.
- **FR-009**: System MUST emit drift events to the monitoring system when reconciliation detects discrepancies.
- **FR-010**: System MUST provide a real-time event stream delivering lifecycle events (launched, paused, resumed, stopped, failed, heartbeat, artifact collected) scoped to specific runtimes.
- **FR-011**: System MUST maintain a configurable warm pool of pre-initialized runtime pods per workspace and agent type for sub-2-second launches.
- **FR-012**: System MUST recycle warm pool pods after a configurable idle timeout.
- **FR-013**: System MUST monitor heartbeats from running runtimes and mark runtimes as failed after a configurable timeout (default 60 seconds) without a heartbeat.
- **FR-014**: System MUST resolve secret references from the platform vault at pod launch time and inject secret values into the pod's filesystem or environment, never into the LLM context.
- **FR-015**: System MUST sanitize tool output to strip known secret patterns before results enter the LLM context.
- **FR-016**: System MUST persist a task plan record (metadata + full payload) linked to execution ID and step ID before dispatching a runtime pod.
- **FR-017**: System MUST collect runtime artifacts (logs, outputs, metrics) to object storage, organized by execution ID.
- **FR-018**: System MUST automatically collect artifacts before terminating a completed runtime.
- **FR-019**: System MUST expose health status (liveness and readiness) and operational metrics (launch count, active runtimes, reconciliation cycle time, warm pool utilization, heartbeat timeout count) to the monitoring system.
- **FR-020**: System MUST propagate distributed trace context across all service calls for end-to-end observability.
- **FR-021**: System MUST produce a container image under 100 MB.
- **FR-022**: System MUST reject duplicate launch requests for the same execution ID with a conflict error.

### Key Entities

- **Runtime**: A managed agent execution pod. Attributes: runtime ID, execution ID, step ID, agent revision, workspace ID, state (pending, running, paused, stopped, failed, force-stopped), resource limits, launch timestamp, last heartbeat, correlation context.
- **Runtime Contract**: The configuration bundle used to launch a runtime. Contains: agent revision, model binding, policy set, correlation IDs (workspace, conversation, interaction, execution, fleet, goal), reasoning config, context engineering profile, reasoning budget envelope, secret references.
- **Warm Pool Pod**: A pre-initialized runtime pod held in standby for fast dispatch. Attributes: workspace ID, agent type, pod identifier, creation timestamp, idle since timestamp.
- **Task Plan Record**: An auditable pre-execution record. Contains: execution ID, step ID, considered agents/tools, selected agent/tool, selection rationale, injected parameters, parameter provenance, timestamp. Metadata stored in database, full payload in object storage.
- **Runtime Event**: A lifecycle event emitted by the controller. Types: launched, paused, resumed, stopped, failed, heartbeat_received, heartbeat_timeout, artifact_collected, drift_detected. Contains: event ID, runtime ID, execution ID, event type, timestamp, details.
- **Runtime Artifact**: An output collected from a completed runtime. Attributes: execution ID, artifact path in object storage, file name, size, content type, collection timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Cold-start runtime launch completes in under 10 seconds from request to pod running state.
- **SC-002**: Warm-start runtime launch completes in under 2 seconds when a matching warm pool pod is available.
- **SC-003**: Reconciliation loop processes up to 1,000 tracked runtimes in under 5 seconds per cycle.
- **SC-004**: Orphaned pods are detected and terminated within 60 seconds (2 reconciliation cycles).
- **SC-005**: Lifecycle events are delivered to subscribers within 500 milliseconds of the state transition.
- **SC-006**: Heartbeat timeout accurately detects dead workers within the configured timeout window (±5 seconds).
- **SC-007**: Zero secret values are present in the LLM context — 100% of secret references resolve via vault, 100% of tool output is sanitized.
- **SC-008**: Task plan records are persisted with zero data loss — every dispatched runtime has a corresponding record.
- **SC-009**: Artifact collection uploads all runtime outputs to object storage before pod termination.
- **SC-010**: The controller maintains 99.9% availability measured over a 30-day window.
- **SC-011**: The container image is under 100 MB.
- **SC-012**: Test coverage is at or above 95% of the codebase.

## Assumptions

- The runtime controller is a standalone service deployed as a Kubernetes Deployment in the `platform-execution` namespace. It communicates with the Python control plane via gRPC (as defined by the constitution for Go satellite services).
- The container orchestrator is Kubernetes 1.28+ — the controller uses the Kubernetes API (via `client-go`) to create, inspect, and delete pods.
- Agent packages are stored in the platform's object storage (feature 004, MinIO) and mounted into runtime pods as read-only volumes.
- Runtime state is persisted in PostgreSQL (the system-of-record database). The controller connects directly to PostgreSQL for state persistence — it does not go through the Python control plane for writes.
- Secret references are resolved from Kubernetes Secrets or a vault (implementation detail). The critical constraint is that secret values never enter the LLM context.
- Task plan records store metadata in PostgreSQL and full payloads in object storage (feature 004, MinIO), linked by execution ID and step ID.
- Runtime events are emitted to the `runtime.lifecycle` Kafka topic (feature 003) for consumption by the execution engine and monitoring systems. The real-time event stream to individual subscribers is provided via the gRPC bidirectional streaming interface.
- The warm pool is managed in-memory by the controller, with pool configuration stored in PostgreSQL. If the controller restarts, the warm pool is rebuilt from scratch (existing warm pods are adopted during reconciliation).
- Tool output sanitization is performed by the tool gateway (a separate component within the agent pod), not by the runtime controller directly. The controller's responsibility is to configure the pod so that the sanitizer is active.
- The controller's container image uses a multi-stage build: a builder stage for compilation and a distroless runtime stage, targeting under 100 MB.
- Pause/resume is implemented by sending signals to the runtime process within the pod. If the runtime process does not support graceful pause, the pause operation is a no-op and the runtime continues running (documented in the event stream).
- The controller does NOT handle reasoning orchestration (that is the reasoning engine's responsibility), does NOT execute code directly (that is the sandbox manager's responsibility), and does NOT manage the tool gateway or model provider connections. It manages the pod lifecycle only.
