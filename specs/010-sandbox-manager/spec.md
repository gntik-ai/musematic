# Feature Specification: Sandbox Manager — Isolated Code Execution

**Feature Branch**: `010-sandbox-manager`  
**Created**: 2026-04-10  
**Status**: Draft  
**Input**: User description: "Go Sandbox Manager — isolated code execution pods for agent sandboxing and code-as-reasoning"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Execute Code in Isolated Sandbox (Priority: P1)

An agent runtime needs to execute untrusted code (tool output processing, data transformation, or validation logic) in a fully isolated environment. The platform creates a sandbox pod with the appropriate language template, sends the code for execution, and returns the results (stdout, stderr, exit code) without any risk to the host system or other tenants.

**Why this priority**: Code execution is the core value proposition of the Sandbox Manager. Without this, no other feature is meaningful. Agents cannot perform code-as-reasoning or tool execution safely.

**Independent Test**: Can be fully tested by creating a sandbox with the default template, executing a simple script (e.g., `print("hello")`), and verifying stdout/exit code are returned correctly.

**Acceptance Scenarios**:

1. **Given** a sandbox creation request with template `python3.12`, **When** the sandbox is created, **Then** the system returns a sandbox identifier and the sandbox is in a `ready` state within 15 seconds
2. **Given** a ready sandbox, **When** a code snippet is submitted for execution, **Then** the system returns stdout, stderr, and exit code within the configured timeout
3. **Given** a ready sandbox, **When** code execution completes, **Then** the sandbox can accept another execution step (multi-step support)
4. **Given** a sandbox creation request with an unknown template, **When** the request is processed, **Then** the system returns a clear error indicating the template is not available

---

### User Story 2 — Enforce Resource Limits and Timeouts (Priority: P1)

The platform enforces strict resource limits (memory, CPU) and execution timeouts on every sandbox. If code exceeds memory limits, the process is killed. If code exceeds the time limit, execution is terminated and a timeout error is returned. This prevents runaway code from consuming cluster resources or blocking agent workflows.

**Why this priority**: Without resource enforcement, a single malicious or buggy code snippet could consume cluster resources and affect other tenants. This is a safety-critical capability tied directly to P1.

**Independent Test**: Submit code that allocates excessive memory (should be OOM-killed) and code with an infinite loop (should be timed out). Verify both return appropriate error indicators.

**Acceptance Scenarios**:

1. **Given** a sandbox with 256MB memory limit, **When** code attempts to allocate 512MB, **Then** the process is killed and the execution result indicates an out-of-memory condition
2. **Given** a sandbox with 30-second timeout, **When** code runs an infinite loop, **Then** execution is terminated after 30 seconds and the result indicates a timeout
3. **Given** a sandbox with CPU limits, **When** code attempts to use more CPU than allocated, **Then** the code is throttled (not killed) and completes within degraded performance

---

### User Story 3 — Security Hardening and Network Isolation (Priority: P1)

All sandbox pods run with minimal privileges: non-root user, read-only root filesystem, all Linux capabilities dropped, and a restrictive security profile. Network access is disabled by default, preventing code from making outbound connections. When a specific policy allows it, controlled egress to a defined allowlist is permitted.

**Why this priority**: Security is non-negotiable for executing untrusted code. Without hardening, the sandbox is a liability rather than a safety mechanism. This must ship alongside code execution.

**Independent Test**: Execute code that attempts to open a network socket (should fail by default), write to the root filesystem (should fail), and escalate privileges (should fail). Verify all are blocked.

**Acceptance Scenarios**:

1. **Given** a sandbox with default security settings, **When** code attempts to open a network connection, **Then** the connection is refused
2. **Given** a sandbox with an egress allowlist policy specifying a single domain, **When** code connects to the allowed domain, **Then** the connection succeeds. **When** code connects to a non-allowed domain, **Then** the connection is refused
3. **Given** a sandbox, **When** code attempts to write to the root filesystem, **Then** the write fails
4. **Given** a sandbox, **When** code attempts to escalate privileges, **Then** the attempt is blocked

---

### User Story 4 — Code-as-Reasoning Execution (Priority: P2)

Agents use code execution as a reasoning strategy — writing and running code to compute answers, validate hypotheses, or process data. The platform provides a specialized template optimized for this pattern: smaller resource footprint, shorter timeout, and structured JSON output format so results integrate seamlessly back into the agent's reasoning chain.

**Why this priority**: Code-as-reasoning is a key differentiator for agent intelligence but depends on the basic execution infrastructure (US1-US3) being in place first.

**Independent Test**: Create a code-as-reasoning sandbox, execute a computation that outputs structured JSON, and verify the JSON is returned as a parsed result.

**Acceptance Scenarios**:

1. **Given** a sandbox created with the `code-as-reasoning` template, **When** code outputs valid JSON to stdout, **Then** the execution result includes the parsed structured output
2. **Given** a code-as-reasoning sandbox, **When** code outputs invalid JSON, **Then** the execution result includes the raw stdout and an indicator that structured parsing failed
3. **Given** a code-as-reasoning sandbox, **When** execution exceeds the 15-second timeout, **Then** the result indicates a timeout with partial output if available

---

### User Story 5 — Stream Sandbox Logs (Priority: P2)

Operators and debugging workflows need real-time visibility into sandbox execution. The platform provides a streaming log interface that delivers stdout and stderr lines as they are produced, without waiting for execution to complete.

**Why this priority**: Essential for debugging and observability but not required for basic sandbox functionality.

**Independent Test**: Start a sandbox, execute code that produces output over several seconds, and verify log lines arrive incrementally (not all at once at the end).

**Acceptance Scenarios**:

1. **Given** a running sandbox execution, **When** a log stream is requested, **Then** stdout and stderr lines are delivered in real-time as they are produced
2. **Given** a log stream for a completed execution, **When** the stream is opened, **Then** buffered logs from the completed execution are delivered and the stream closes
3. **Given** multiple concurrent subscribers for the same sandbox, **When** log lines are produced, **Then** all subscribers receive the same lines

---

### User Story 6 — Collect Sandbox Artifacts (Priority: P2)

After sandbox execution, output files (generated data, plots, processed results) need to be collected and persisted to object storage. The platform collects all files from a designated output directory within the sandbox, uploads them, and returns a manifest of collected artifacts.

**Why this priority**: Artifact collection extends sandbox utility beyond simple stdout capture but depends on basic execution working first.

**Independent Test**: Execute code that writes files to the output directory, trigger artifact collection, and verify files appear in object storage with correct metadata.

**Acceptance Scenarios**:

1. **Given** a sandbox where code has written files to `/output/`, **When** artifact collection is triggered, **Then** all files from `/output/` are uploaded to object storage and a manifest is returned listing each artifact with its path, size, and content type
2. **Given** an empty output directory, **When** artifact collection is triggered, **Then** the result indicates no artifacts were found (not an error)
3. **Given** artifact collection on a terminated sandbox, **When** the pod has been cleaned up, **Then** the system returns an error indicating the sandbox no longer exists

---

### User Story 7 — Automatic Sandbox Cleanup (Priority: P2)

Sandboxes are ephemeral. After execution completes, times out, or fails, the sandbox pod and its temporary volumes are automatically cleaned up. A background process also scans for orphaned sandboxes (pods that were not properly terminated) and removes them. This prevents resource leaks in the cluster.

**Why this priority**: Cleanup prevents resource leaks and is critical for production operation, but agents can function with manual termination during initial development.

**Independent Test**: Create a sandbox, let it time out, and verify the pod is automatically removed within the cleanup interval.

**Acceptance Scenarios**:

1. **Given** a sandbox that has completed execution, **When** the configurable cleanup delay expires, **Then** the pod and temporary volumes are automatically deleted
2. **Given** a sandbox that has exceeded its maximum lifetime, **When** the orphan scanner runs, **Then** the sandbox is force-terminated and cleaned up
3. **Given** a sandbox where the controller was restarted, **When** the orphan scanner starts, **Then** it discovers and cleans up any sandbox pods from the previous controller instance

---

### Edge Cases

- What happens when the cluster has insufficient resources to create a sandbox pod? The system returns a clear error indicating resource pressure, and the requesting agent can retry later.
- What happens when a sandbox pod is externally deleted (e.g., by a node eviction)? The system detects the missing pod and marks the sandbox as failed with reason "pod_evicted".
- What happens when code produces extremely large stdout output (e.g., 100MB)? Output is truncated at a configurable limit (default 10MB) with a truncation indicator.
- What happens when artifact collection is requested for a sandbox that is still running? Collection proceeds on available output files; a warning indicates the sandbox was still active.
- What happens when multiple execution steps are submitted concurrently to the same sandbox? Steps are serialized — only one executes at a time, additional requests are queued or rejected.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST create isolated sandbox environments from pre-defined language templates (at minimum: Python 3.12, Node.js 20, Go 1.22, code-as-reasoning)
- **FR-002**: System MUST execute submitted code within a sandbox and return stdout, stderr, and exit code
- **FR-003**: System MUST enforce memory limits per sandbox; exceeding the limit terminates the process with an out-of-memory indicator
- **FR-004**: System MUST enforce execution timeouts per sandbox; exceeding the timeout terminates the process with a timeout indicator
- **FR-005**: System MUST run all sandbox pods as non-root with a read-only root filesystem and all Linux capabilities dropped
- **FR-006**: System MUST disable network access for sandbox pods by default
- **FR-007**: System MUST support configurable egress allowlists when network access is enabled via policy
- **FR-008**: System MUST apply a restrictive security profile (seccomp RuntimeDefault) to all sandbox pods
- **FR-009**: System MUST support the code-as-reasoning template that expects structured JSON output and uses reduced resource limits and shorter timeouts
- **FR-010**: System MUST provide real-time log streaming from sandbox pods (stdout and stderr)
- **FR-011**: System MUST collect output artifacts from a designated directory within the sandbox and upload them to object storage
- **FR-012**: System MUST automatically clean up sandbox pods after execution completes, times out, or fails
- **FR-013**: System MUST detect and clean up orphaned sandbox pods (pods from previous controller instances or failed cleanups)
- **FR-014**: System MUST support multiple execution steps within a single sandbox session (sequential execution)
- **FR-015**: System MUST truncate stdout/stderr output at a configurable limit (default 10MB) to prevent memory exhaustion
- **FR-016**: System MUST persist sandbox execution metadata (creation time, template, resource limits, execution results, duration) for observability
- **FR-017**: System MUST emit lifecycle events when sandboxes are created, started, completed, failed, or cleaned up
- **FR-018**: System MUST support graceful termination (allowing in-progress execution to complete within a grace period) and forced termination
- **FR-019**: System MUST provide health check endpoints indicating the service's ability to create sandbox pods and reach required dependencies
- **FR-020**: System MUST propagate trace context for distributed tracing across sandbox operations

### Key Entities

- **Sandbox**: An isolated execution environment with a unique identifier, associated template, resource limits, network policy, current state (creating, ready, executing, completed, failed, terminated), and lifecycle timestamps
- **SandboxTemplate**: A named configuration defining the container image, default resource limits, default timeout, and any template-specific behavior (e.g., JSON output parsing for code-as-reasoning)
- **ExecutionStep**: A single code execution within a sandbox, including the submitted code, execution result (stdout, stderr, exit code), duration, and any structured output
- **Artifact**: An output file collected from a sandbox's output directory, with object storage path, filename, size, and content type

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Sandbox creation completes within 15 seconds for cold starts
- **SC-002**: Code execution results are returned within the configured timeout plus 5 seconds of overhead
- **SC-003**: Memory limit violations are detected and the process terminated within 5 seconds
- **SC-004**: Timeout violations terminate execution within 2 seconds of the configured limit
- **SC-005**: Orphaned sandboxes are detected and cleaned up within 120 seconds
- **SC-006**: Log streaming delivers lines with less than 2 seconds of latency from production
- **SC-007**: Artifact collection uploads files at a rate of at least 10MB/second
- **SC-008**: The service maintains stable operation with at least 50 concurrent sandboxes
- **SC-009**: Service binary image is smaller than 50MB
- **SC-010**: Automated test suite achieves at least 95% code coverage
- **SC-011**: No sandbox pod runs with root privileges, writable root filesystem, or unrestricted network access
- **SC-012**: All sandbox lifecycle events are emitted within 1 second of the state transition

## Assumptions

- The platform cluster has sufficient compute resources to run sandbox pods alongside other workloads; sandbox scheduling failures are handled gracefully but resource provisioning is outside scope
- Sandbox pods execute in the `platform-execution` namespace, shared with agent runtime pods but isolated via security contexts and network policies
- Object storage (MinIO) is available and accessible from the sandbox manager for artifact uploads; sandbox pods themselves do not access object storage directly
- Sandbox templates use publicly available container images (e.g., `python:3.12-slim`); custom images are out of scope for v1
- The sandbox manager runs as a separate service from the Runtime Controller; they do not share state but may run in the same namespace
- Agent code submitted for execution is assumed untrusted; the sandbox must protect against malicious code by design
- Dependencies (pip packages, npm modules, go modules) can be installed at sandbox creation time if specified in the request; installation time counts toward the sandbox creation timeout
- The sandbox manager does not persist sandbox state across service restarts — orphaned pods from a previous instance are cleaned up, not resumed
