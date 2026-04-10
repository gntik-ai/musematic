# Feature Specification: Simulation Controller — Isolated Simulation Environments

**Feature Branch**: `012-simulation-controller`  
**Created**: 2026-04-10  
**Status**: Draft  
**Input**: User description: "Go Simulation Controller — isolated simulation environments for agent and fleet testing against synthetic data without production side effects, accredited testing environments"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Simulation Environment Creation (Priority: P1)

When a platform operator or agent developer needs to test an agent against synthetic data, the platform creates a fully isolated simulation environment. The simulation runs in a separate namespace with strict network controls that prevent any communication with production services. All environment variables include a simulation flag so every component knows it is operating in test mode. The simulation writes artifacts only to a dedicated simulation bucket, never to production storage. Resource usage is accounted separately so simulation workloads do not affect production quotas.

**Why this priority**: Simulation creation is the entry point for all simulation workflows. Without it, no other simulation capability (monitoring, artifact collection, ATEs) can function.

**Independent Test**: Request a new simulation — verify a pod is created in the simulation namespace, confirm the pod cannot reach production services (network policy blocks egress), verify the simulation flag appears in environment variables, and confirm resource accounting is separate from production.

**Acceptance Scenarios**:

1. **Given** a simulation creation request with valid agent configuration, **When** the simulation is provisioned, **Then** a pod is created in the dedicated simulation namespace with all isolation controls applied
2. **Given** a newly created simulation pod, **When** the pod attempts to reach a production service, **Then** the connection is denied by network policy
3. **Given** a simulation creation request, **When** the pod starts, **Then** every environment variable includes the simulation flag (`SIMULATION=true`)
4. **Given** a running simulation, **When** the agent writes output, **Then** all data is directed to the simulation-specific artifact bucket, not the production bucket
5. **Given** production workloads consuming resources, **When** a simulation is created, **Then** simulation resource usage is tracked under a separate quota and does not reduce the production resource pool

---

### User Story 2 — Simulation Monitoring and Termination (Priority: P1)

Platform operators need to monitor the state of running simulations and terminate them when testing is complete or when they need to reclaim resources. Querying simulation status returns current phase, elapsed time, resource consumption, and any error conditions. Terminating a simulation performs full cleanup — deleting pods, cleaning up network policies, releasing resources — and leaves no orphaned objects in the cluster.

**Why this priority**: Without lifecycle management, simulations would accumulate and waste cluster resources. Termination and cleanup are essential for operational hygiene.

**Independent Test**: Create a simulation, query its status to confirm it is running, then terminate it. Verify the pod is deleted, resources are released, and no orphaned Kubernetes objects remain in the simulation namespace.

**Acceptance Scenarios**:

1. **Given** a running simulation, **When** the status is queried, **Then** the response includes current phase, elapsed time, resource usage, pod status, and any errors
2. **Given** a running simulation, **When** termination is requested, **Then** the pod is deleted, network policies are cleaned up, and resource accounting is updated
3. **Given** a terminated simulation, **When** the status is queried after cleanup, **Then** the status reflects a terminal state with final resource totals
4. **Given** a simulation pod that has crashed, **When** the status is queried, **Then** the response accurately reflects the failure state with error details
5. **Given** multiple simulations in the namespace, **When** one is terminated, **Then** only that simulation's resources are cleaned up — other simulations are unaffected

---

### User Story 3 — Simulation Artifact Collection (Priority: P2)

After a simulation completes (or during execution), operators need to collect simulation outputs — logs, generated files, agent responses, evaluation results. All collected artifacts are tagged with `simulation=true` metadata to prevent any confusion with production data. Artifacts are stored in a dedicated simulation bucket with the simulation ID as a key prefix for easy retrieval and cleanup.

**Why this priority**: Artifact collection enables post-simulation analysis and is required for ATE result reporting, but simulations can run and be observed without artifact collection being fully operational.

**Independent Test**: Run a simulation that produces output files, collect artifacts, verify they appear in the simulation bucket with correct tags and metadata. Confirm artifacts are NOT in any production bucket.

**Acceptance Scenarios**:

1. **Given** a completed simulation with output files, **When** artifact collection is requested, **Then** all simulation outputs are uploaded to the simulation artifact bucket with the simulation ID prefix
2. **Given** collected simulation artifacts, **When** artifact metadata is inspected, **Then** every artifact has `simulation=true` tag and references the source simulation ID
3. **Given** a simulation that produced artifacts, **When** the production artifact bucket is inspected, **Then** no simulation artifacts appear there
4. **Given** a simulation that is still running, **When** artifact collection is requested, **Then** currently available outputs are collected without disrupting the running simulation

---

### User Story 4 — Real-Time Simulation Event Streaming (Priority: P2)

Operators and monitoring dashboards need real-time visibility into simulation execution. The platform provides a streaming interface that pushes simulation events (state changes, agent actions, errors, resource usage updates) as they occur. Events include the simulation flag and are routed to a simulation-specific event stream, separate from production events.

**Why this priority**: Event streaming provides observability during simulation runs but is not required for the core create/monitor/terminate lifecycle.

**Independent Test**: Subscribe to events for a simulation, trigger simulation state changes, verify events arrive in real time with correct simulation tagging. Confirm events do NOT appear on production event streams.

**Acceptance Scenarios**:

1. **Given** a running simulation, **When** a subscriber connects to the event stream, **Then** simulation events are received in real time as they occur
2. **Given** simulation events being emitted, **When** the event metadata is inspected, **Then** every event includes `simulation=true` and the simulation ID
3. **Given** simulation events being emitted, **When** the production event backbone is inspected, **Then** simulation events do NOT appear on production topics
4. **Given** a simulation that terminates, **When** the final events are sent, **Then** the subscriber stream is closed gracefully after the terminal event

---

### User Story 5 — Accredited Testing Environment (Priority: P2)

Agent developers and trust engineers need a standardized way to validate agent behavior before deployment. The platform creates Accredited Testing Environments (ATEs) — pre-configured sandboxes with standard test scenarios, golden datasets, and evaluation scorers. The ATE runs the agent against all scenarios sequentially, collects per-scenario results (pass/fail, quality scores, latency, cost, safety compliance), and produces a structured report. ATEs inherit all simulation isolation guarantees.

**Why this priority**: ATEs are a specialized use of simulation environments. They depend on US1 (simulation creation) and US3 (artifact collection) being operational but add significant value for the trust and certification workflow.

**Independent Test**: Create an ATE with 3 test scenarios and a golden dataset. Run an agent through it. Verify a structured JSON report is produced with per-scenario pass/fail, quality scores, latency, cost, and safety metrics. Verify the ATE pod had no access to production services.

**Acceptance Scenarios**:

1. **Given** a request to create an ATE with specified scenarios and golden datasets, **When** the environment is provisioned, **Then** a simulation pod is created with all test scenarios, datasets, and evaluation scorers pre-loaded
2. **Given** a provisioned ATE, **When** the agent is executed against it, **Then** all scenarios are run sequentially and per-scenario results are collected
3. **Given** a completed ATE execution, **When** results are retrieved, **Then** a structured report includes per-scenario pass/fail, quality scores, latency, cost, and safety compliance metrics
4. **Given** an ATE pod, **When** network access is tested, **Then** the pod cannot reach production services (full simulation isolation inherited)
5. **Given** a completed ATE, **When** teardown is requested, **Then** all ATE resources are fully cleaned up with no orphaned objects

---

### Edge Cases

- What happens when the simulation namespace does not exist at startup? The service creates the namespace with the required labels and network policies on first use.
- What happens when a simulation pod crashes mid-execution? The simulation status transitions to FAILED with error details captured, and resources are marked for cleanup.
- What happens when artifact collection is requested but the pod has already been terminated? The service attempts to retrieve any artifacts that were persisted before termination; uncollected ephemeral outputs are lost and the response indicates partial collection.
- What happens when the simulation-artifacts bucket does not exist? The service creates it with appropriate tagging policies at startup.
- What happens when two ATEs are requested for the same agent concurrently? Each ATE runs independently in its own pod with isolated state — concurrent execution is supported.
- What happens when an ATE scenario produces no output? The scenario is marked as FAILED with a "no output" reason in the structured report.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create simulation environments in a dedicated, isolated namespace separate from production workloads
- **FR-002**: System MUST apply network policies that deny all egress from simulation pods to production namespaces
- **FR-003**: System MUST inject a simulation flag (`SIMULATION=true`) into all simulation pod environment variables
- **FR-004**: System MUST direct all simulation artifact writes to a simulation-specific storage bucket, never to production storage
- **FR-005**: System MUST track simulation resource usage separately from production resource quotas
- **FR-006**: System MUST return current simulation status including phase, elapsed time, resource consumption, and error conditions
- **FR-007**: System MUST fully clean up all simulation resources (pods, network policies, volumes) on termination with no orphaned objects
- **FR-008**: System MUST stream simulation events in real time to subscribed clients
- **FR-009**: System MUST tag all simulation events and artifacts with the simulation ID and `simulation=true` metadata
- **FR-010**: System MUST ensure simulation events do NOT appear on production event streams
- **FR-011**: System MUST collect simulation artifacts from completed or running simulations and persist them to the simulation bucket
- **FR-012**: System MUST support creating Accredited Testing Environments (ATEs) pre-configured with test scenarios, golden datasets, and evaluation scorers
- **FR-013**: System MUST execute ATE scenarios sequentially against the agent under test and collect per-scenario results
- **FR-014**: System MUST produce a structured report from ATE execution containing per-scenario pass/fail, quality scores, latency, cost, and safety compliance
- **FR-015**: System MUST apply full simulation isolation to all ATE environments (same network policies, same namespace, same artifact bucket)
- **FR-016**: System MUST fully clean up ATE environments after test completion
- **FR-017**: System MUST provide a health check endpoint indicating service readiness and dependency health
- **FR-018**: System MUST propagate trace context for distributed tracing across all operations
- **FR-019**: System MUST block all connector, tool, and external API access from simulation pods — only mock responses are permitted

### Key Entities

- **Simulation**: A running or completed simulation environment with a unique ID, associated agent configuration, current phase (CREATING, RUNNING, COMPLETED, FAILED, TERMINATED), resource accounting, and creation metadata
- **SimulationArtifact**: An output collected from a simulation run, stored in the simulation bucket with simulation ID prefix, tagged with `simulation=true`, including file path, size, and content type
- **AccreditedTestEnv**: A specialized simulation pre-loaded with test scenarios, golden datasets, and evaluation scorers, producing a structured result report on completion
- **ATEScenario**: An individual test case within an ATE, with input data, expected behavior criteria, and scoring configuration
- **ATEResult**: A per-scenario result containing pass/fail, quality score, latency measurement, cost, and safety compliance assessment
- **SimulationEvent**: A timestamped event from a simulation run (state change, agent action, error, resource update) tagged with simulation ID and `simulation=true`

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Simulation environment creation completes within 60 seconds from request to pod ready
- **SC-002**: Network isolation is enforced with zero successful connections from simulation pods to production namespaces (verified by integration test)
- **SC-003**: All simulation artifacts carry `simulation=true` metadata with zero exceptions
- **SC-004**: Simulation termination completes full cleanup within 30 seconds leaving zero orphaned objects
- **SC-005**: Simulation events are delivered to subscribers within 500 milliseconds of occurrence
- **SC-006**: Simulation resource usage is tracked separately with zero impact on production quota accounting
- **SC-007**: ATE execution produces a complete structured report for all configured scenarios
- **SC-008**: ATE environments inherit full simulation isolation (verified by same network policy tests as regular simulations)
- **SC-009**: System handles at least 20 concurrent simulations without resource contention or performance degradation
- **SC-010**: Service binary image is smaller than 50MB
- **SC-011**: Automated test suite achieves at least 95% code coverage
- **SC-012**: Simulation status queries respond within 100 milliseconds

## Assumptions

- The simulation controller runs as a standalone Go satellite service, separate from the control plane
- The `platform-simulation` Kubernetes namespace is the designated isolation boundary per constitution §3.7
- Simulation pods use the same pod template patterns as the sandbox manager (feature 010) but with additional isolation controls
- Mock responses for blocked connectors and tools are provided by a sidecar or injected stub, not by this service (this service only enforces the block)
- Golden datasets and test scenarios for ATEs are supplied by the caller (control plane), not maintained by this service
- Object storage for simulation artifacts uses a separate bucket (`simulation-artifacts`) from production buckets
- The event backbone (Kafka) has a dedicated simulation topic separate from production topics
- Resource quotas for the simulation namespace are configured by the platform administrator, not by this service
