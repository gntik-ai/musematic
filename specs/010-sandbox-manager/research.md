# Research: Sandbox Manager — Isolated Code Execution

**Feature**: 010-sandbox-manager  
**Date**: 2026-04-10  
**Phase**: 0 — Pre-design research

---

## Decision 1: Go Service Architecture — Satellite Binary at `services/sandbox-manager/`

**Decision**: The sandbox manager is an independent Go binary at `services/sandbox-manager/`, following the same satellite service pattern as `services/runtime-controller/` and `services/reasoning-engine/`. It exposes a gRPC server on port 50053 (`google.golang.org/grpc 1.67+`) and communicates with the Python control plane via gRPC. Standard Go layout: `cmd/sandbox-manager/main.go`, `internal/`, `api/grpc/`, `pkg/`.

**Rationale**: Constitution §3.2 establishes `services/sandbox-manager/` as a Go satellite service. The gRPC Service Registry assigns port 50053 in `platform-execution`. The sandbox manager requires concurrent pod lifecycle management, real-time log streaming, and background orphan cleanup — all workloads suited to Go's goroutine model.

**Alternatives considered**:
- Python control plane extension: would need synchronous Kubernetes API calls blocking the async event loop. Rejected — Go satellite is the mandated pattern.
- Kubernetes Operator with CRDs: adds webhook and CRD complexity not needed. Rejected — the service manages pods, not custom resources.

---

## Decision 2: Code Execution — `remotecommand` (Pod Exec) via client-go

**Decision**: Code is executed inside sandbox pods using `k8s.io/client-go/tools/remotecommand` — the same SPDY/WebSocket mechanism underlying `kubectl exec`. The sandbox manager creates a pod with a long-running shell process (e.g., `sleep infinity` or a lightweight exec-agent entrypoint), then for each `ExecuteSandboxStep` call, opens a `remotecommand` exec session piping the code via stdin and collecting stdout/stderr.

For multi-step execution: the pod stays alive between steps. Each step creates a new exec session. The exec writes a wrapper script that captures exit code, enforces the per-step timeout (via `timeout` command), and writes structured output.

**Timeout enforcement**: Dual-layer.
1. **Controller-side**: `context.WithTimeout` on the exec request — cancels the SPDY stream if the step exceeds the timeout. This handles the controller's own deadline.
2. **Pod-side**: The wrapper script uses `timeout <seconds>` to kill the user process. This handles runaway processes even if the controller connection drops.
3. **Pod-level**: `ActiveDeadlineSeconds` on the pod spec as a hard ceiling — Kubernetes kills the pod if total lifetime exceeds the maximum.

**Streaming support**: `remotecommand` supports `StreamOptions` with separate `Stdout` and `Stderr` `io.Writer` interfaces. These can be connected to gRPC stream writers for real-time log delivery.

**Rationale**: `remotecommand` is the official Kubernetes pod exec mechanism. It avoids running a sidecar agent (which would increase the sandbox image size and attack surface), avoids volume-based IPC (which has poor latency for multi-step), and natively supports streaming. The dual-layer timeout provides defense in depth — the controller can't be blocked by a runaway process, and the pod can't outlive its deadline.

**Alternatives considered**:
- Sidecar gRPC agent in pod: more flexible but increases image size, adds a network-accessible endpoint inside the pod (security risk for untrusted code), and requires building/maintaining a separate agent binary. Rejected.
- Volume-based IPC (write code to emptyDir, poll for results): high latency, no streaming, complex for multi-step. Rejected.
- `kubectl exec` subprocess: not idiomatic Go; loses structured error handling. Rejected.

---

## Decision 3: Security Hardening — Maximum Restriction Pod Spec

**Decision**: All sandbox pods run with the maximum possible restrictions:

**SecurityContext** (pod-level):
```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 65534       # nobody
  runAsGroup: 65534
  fsGroup: 65534
  seccompProfile:
    type: RuntimeDefault
```

**SecurityContext** (container-level):
```yaml
securityContext:
  allowPrivilegeEscalation: false
  readOnlyRootFilesystem: true
  capabilities:
    drop: ["ALL"]
```

**Pod-level settings**:
```yaml
automountServiceAccountToken: false
hostNetwork: false
hostPID: false
hostIPC: false
restartPolicy: Never
enableServiceLinks: false
```

**Rationale**: UID 65534 (`nobody`) is the conventional untrusted workload UID — no home directory, no shell ownership. `RuntimeDefault` seccomp is sufficient (blocks `ptrace`, `mount`, etc.) without requiring a custom Localhost profile. `enableServiceLinks: false` prevents leaking cluster service topology via `*_SERVICE_HOST` environment variables to untrusted code.

**Alternatives considered**:
- Custom seccomp Localhost profile: would allow finer-grained syscall blocking but requires distributing the profile to all nodes. RuntimeDefault is simpler and blocks the critical syscalls. Revisit if needed.
- gVisor/kata containers: maximum isolation but requires node-level runtime setup and increases launch latency. Out of scope for v1.

---

## Decision 4: Network Isolation — Label-Based NetworkPolicy

**Decision**: Two static NetworkPolicy resources (deployed via Helm chart):

1. **Deny-all default**: Matches all pods with label `musematic/sandbox: "true"`. Blocks all egress and ingress.
2. **Conditional egress allow**: Matches pods with additional label `musematic/network-allowed: "true"`. Allows egress to port 443 only. The egress destinations are not specified in the policy (any destination on 443) — finer-grained domain-based filtering requires an external proxy or service mesh, which is out of scope for v1.

When a sandbox creation request includes a network-enabled policy, the pod is created with `musematic/network-allowed: "true"` label and `dnsPolicy: ClusterFirst`. When no network is needed (default), the pod uses `dnsPolicy: None` with empty `dnsConfig` to prevent any DNS resolution.

**Rationale**: Label-based policies are operationally cleaner than creating/deleting per-pod NetworkPolicy objects. Two static policies + pod labels provide the deny-by-default/allow-by-exception pattern. `dnsPolicy: None` completely eliminates DNS traffic for isolated pods.

**Alternatives considered**:
- Per-pod NetworkPolicy: creates many small policy objects, requires cleanup, harder to manage. Rejected.
- Cilium/Calico FQDN-based policies: would allow domain-based egress allowlists but requires a specific CNI. Out of scope for v1.

---

## Decision 5: Filesystem Isolation — emptyDir Volumes with Size Limits

**Decision**: Three separate emptyDir volumes with size limits:

| Mount path | Purpose | sizeLimit |
|------------|---------|-----------|
| `/tmp` | Temp files, pip cache, node_modules | 256Mi |
| `/workspace` | User code working directory | 512Mi |
| `/output` | Artifacts for collection | 128Mi |

The main container's `readOnlyRootFilesystem: true` prevents writes outside these mounts. Each template adjusts the working directory: Python/Node/code-as-reasoning use `/workspace`, Go uses `/workspace/src`.

**Rationale**: Separate volumes for `/output` vs `/tmp` simplify artifact collection — the collector reads only `/output` without sifting through temp files. `sizeLimit` on emptyDir prevents disk abuse (kubelet evicts the pod when exceeded). Total writable space per sandbox: ~896Mi, which is generous for code execution but bounded.

**Alternatives considered**:
- Single emptyDir for all writable paths: simpler but complicates artifact collection. Rejected.
- PersistentVolumeClaim: unnecessary for ephemeral execution. Rejected.

---

## Decision 6: State Model — In-Memory + PostgreSQL Metadata + Kafka Events

**Decision**: Sandbox state is tracked in-memory (`sync.RWMutex`-protected map) for hot-path operations and persisted to PostgreSQL for observability metadata. Kafka events are emitted for all state transitions.

**State machine**:
```
CREATING → READY → EXECUTING ⇄ READY → COMPLETED
                                          ↓
   └──────────→ FAILED ←────────────────┘
                                          ↓
                    TERMINATED ←──────────┘
```

States:
- `creating`: Pod being created by Kubernetes
- `ready`: Pod running, accepting execution steps
- `executing`: Code currently running in the pod
- `completed`: All steps done, pod alive for artifact collection
- `failed`: Error (timeout, OOM, pod eviction, creation failure)
- `terminated`: Pod deleted, cleanup done

**PostgreSQL table** (`sandboxes`): Records sandbox_id, execution_id, workspace_id, template, state, created_at, terminated_at, total_steps, total_duration. This is for observability/analytics, not hot-path reads.

**Execution steps** are returned directly to the gRPC caller; they are NOT persisted to PostgreSQL. The step result (stdout, stderr, exit_code, duration) is part of the `ExecuteSandboxStepResponse`. If the caller needs to persist results, it does so.

**Rationale**: Sandboxes are ephemeral (seconds to minutes). In-memory state is sufficient for the controller's hot path. PostgreSQL persistence provides an audit trail for analytics (how many sandboxes, which templates, failure rates). Kafka events enable downstream consumers (monitoring, analytics) to react to sandbox lifecycle changes. Not persisting execution step results avoids storing potentially large stdout/stderr payloads in PostgreSQL.

**Alternatives considered**:
- PostgreSQL-only state (like runtime-controller): adds unnecessary latency for ephemeral resources. Runtime-controller needs PostgreSQL because runtimes can live for hours and survive controller restarts. Sandboxes live seconds. Rejected for hot path.
- In-memory only (no PostgreSQL): loses observability. Rejected.
- Persisting step results to PostgreSQL: stdout/stderr can be megabytes; inappropriate for PostgreSQL. If persistence is needed, artifacts go to MinIO. Rejected.

---

## Decision 7: Orphan Detection — Label-Based Pod Listing on Startup

**Decision**: On startup, the sandbox manager lists all pods in `platform-execution` with label `managed-by: sandbox-manager`. Any pod found that is not in the in-memory state map is an orphan from a previous controller instance. Orphaned pods are terminated immediately with a 5-second grace period.

A background goroutine also scans periodically (every 60 seconds) for orphaned pods, catching any that were missed during startup or created by a now-dead controller replica.

**Rationale**: Sandboxes are short-lived. A full reconciliation loop (like runtime-controller's 30s PostgreSQL-vs-Kubernetes comparison) is overkill. Label-based listing is simple, fast, and sufficient for cleanup. The periodic scan catches edge cases.

**Alternatives considered**:
- Full reconciliation loop with PostgreSQL comparison: runtime-controller's approach. Overly complex for ephemeral sandboxes. Rejected.
- Rely only on `ActiveDeadlineSeconds`: would eventually clean up pods but with potentially long delays. Rejected as sole mechanism.

---

## Decision 8: Artifact Collection — Pod File Copy + MinIO Upload

**Decision**: Artifact collection uses `k8s.io/client-go/kubernetes/typed/core/v1` to exec `tar czf - -C /output .` inside the sandbox pod, streaming the tar archive to the controller. The controller decompresses and uploads individual files to MinIO at `sandbox-artifacts/{execution_id}/{sandbox_id}/{filename}`.

For logs: pod logs are collected via the Kubernetes Pod log API (`GetLogs`), uploaded to MinIO at `sandbox-artifacts/{execution_id}/{sandbox_id}/logs.txt`.

**Rationale**: `tar` via exec avoids needing a volume mount on the controller. The controller streams the archive without storing the full payload in memory (chunked upload to MinIO). Individual file upload (not the tar archive) allows downstream consumers to access specific artifacts.

**Alternatives considered**:
- Shared PVC between controller and sandbox: requires PVC provisioning, not compatible with distroless/minimal sandbox images. Rejected.
- Sidecar uploader in sandbox pod: adds complexity and network access to the sandbox. Rejected.
- Direct MinIO access from sandbox pod: requires giving untrusted code access to object storage credentials. Rejected — security violation.

---

## Decision 9: Sandbox Templates — Config-Driven Pod Spec Resolution

**Decision**: Templates are defined as Go structs (not external config files) in `internal/templates/`. Each template specifies: container image, default resource limits, default timeout, working directory, exec command prefix, and any template-specific behavior (e.g., JSON parsing for code-as-reasoning).

Initial templates:

| Template | Image | Memory | CPU | Timeout | Notes |
|----------|-------|--------|-----|---------|-------|
| `python3.12` | `python:3.12-slim` | 256Mi | 500m | 30s | pip available in /tmp |
| `node20` | `node:20-slim` | 256Mi | 500m | 30s | npm available in /tmp |
| `go1.22` | `golang:1.22-alpine` | 512Mi | 1000m | 60s | Larger for compilation |
| `code-as-reasoning` | `python:3.12-slim` | 128Mi | 250m | 15s | JSON output wrapper |

The code-as-reasoning template wraps user code in a Python script that captures the output and emits it as structured JSON: `{"result": <stdout>, "error": <stderr>, "exit_code": <int>}`.

**Rationale**: Go structs for templates is simpler than external YAML config files for a small, known set of templates. Templates can be extended later by adding new structs. The images use slim/alpine variants to minimize download time.

**Alternatives considered**:
- ConfigMap-based templates: allows runtime changes without redeployment. Overkill for v1 with only 4 templates. Can be added later.
- Custom sandbox images (pre-built with agent tooling): increases image maintenance burden. Out of scope for v1.
