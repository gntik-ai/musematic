# Feature Specification: Observability Stack

**Feature Branch**: `047-observability-stack`  
**Created**: 2026-04-17  
**Status**: Draft  
**Input**: User description for deploying a unified observability stack with metrics collection, distributed tracing, alerting, and pre-built dashboards across all platform services.  
**Requirements Traceability**: TR-079–083 (Observability), FR-120 (Live execution view), FR-299 (Diagnostics views)

## User Scenarios & Testing

### User Story 1 - Monitor Service Health and Performance (Priority: P1)

An operator opens the platform overview dashboard and immediately sees the health status of every running service — control plane, satellite services, and data stores. For each service, they see request rates, error rates, and latency percentiles. If a service is degraded, the dashboard highlights it in red. The operator can drill down into any service to see detailed metrics over time. All metrics update in near-real-time without refreshing.

**Why this priority**: Service health visibility is the foundation of all operational awareness. Without knowing whether services are up and performing within acceptable bounds, operators cannot detect issues, plan capacity, or make informed decisions about the platform's state. Every other observability capability builds on top of this baseline.

**Independent Test**: Deploy the observability stack alongside the platform. Verify the overview dashboard shows all services. Generate traffic to any service. Verify request rate, error rate, and latency metrics update within 30 seconds of the traffic.

**Acceptance Scenarios**:

1. **Given** all platform services are running, **When** the operator opens the platform overview dashboard, **Then** every service appears with its current health status (healthy/degraded/down), request rate, error rate, and p95 latency.
2. **Given** a service begins returning errors, **When** its error rate exceeds the threshold, **Then** the dashboard transitions the service indicator from green to red within 60 seconds.
3. **Given** a service is completely unreachable, **When** the metrics scraper fails to collect from it, **Then** the dashboard marks it as "down" and displays the last known metrics with a staleness indicator.
4. **Given** the operator selects a specific service on the dashboard, **When** they drill down, **Then** they see detailed time-series charts for request rate, error rate, latency distribution (p50/p95/p99), and resource utilization over a configurable time range.

---

### User Story 2 - Trace Requests Across Services (Priority: P1)

A developer is investigating a slow workflow execution. They search for the execution's correlation ID in the trace viewer and see the complete request path — from the API gateway through the control plane, into the reasoning engine via gRPC, and back. Each span shows the service name, operation, duration, and any errors. The developer identifies that the reasoning engine's convergence loop took 3.2 seconds of a 4.1-second total, pinpointing the bottleneck. Trace context propagates seamlessly across HTTP, gRPC, and Kafka event boundaries.

**Why this priority**: Distributed tracing is essential for debugging in a multi-service architecture. Without it, operators are blind to cross-service latency, cannot identify bottlenecks, and spend hours manually correlating logs. Tracing directly enables the live execution view (FR-120) and diagnostics (FR-299).

**Independent Test**: Trigger a workflow execution that exercises the control plane and at least one satellite service. Search for the execution's correlation ID in the trace viewer. Verify spans from both services appear in a single trace tree with correct parent-child relationships.

**Acceptance Scenarios**:

1. **Given** a request enters the control plane API, **When** it calls the reasoning engine via gRPC, **Then** a single trace captures spans from both services with correct parent-child relationships.
2. **Given** a workflow execution produces a Kafka event consumed by another bounded context, **When** the consumer processes the event, **Then** the consumer's processing span is linked to the producer's trace via the trace context embedded in the event envelope.
3. **Given** a completed workflow execution, **When** the developer searches the trace viewer by correlation ID, **Then** the full trace tree is returned showing all participating services, operations, and durations.
4. **Given** a trace with an error, **When** the developer views the trace, **Then** the error span is highlighted with the error message, exception type, and stack trace (if available).
5. **Given** a long-running reasoning loop, **When** the developer views the trace, **Then** the convergence iterations appear as child spans with individual durations, enabling identification of the slowest iteration.

---

### User Story 3 - Receive Alerts for Critical Conditions (Priority: P1)

An on-call operator receives a notification that a critical alert has fired — a service has been unreachable for more than 5 minutes, the Kafka consumer lag on a topic exceeds acceptable levels, or reasoning budget exhaustion events are spiking. Each alert includes the condition that triggered it, the current metric value, the threshold, and a link to the relevant dashboard for investigation. Alerts are routed to the configured notification channel.

**Why this priority**: Alerting transforms observability from reactive to proactive. Without automated alerts, operators must manually watch dashboards — this doesn't scale and misses off-hours incidents. Alerting ensures critical issues are surfaced immediately to the right person.

**Independent Test**: Stop a platform service. Verify the "service down" alert fires within the configured evaluation window. Verify the alert contains the service name, the condition ("not reachable for >5 minutes"), and a dashboard link.

**Acceptance Scenarios**:

1. **Given** a service has been unreachable for longer than the alerting threshold, **When** the alert rule evaluates, **Then** a "service down" alert fires with the service name, duration of outage, and a link to the service detail dashboard.
2. **Given** Kafka consumer lag exceeds the configured threshold for a topic, **When** the alert evaluates, **Then** a "consumer lag high" alert fires with the topic name, current lag count, and threshold.
3. **Given** reasoning budget exhaustion events exceed a rate threshold, **When** the alert evaluates, **Then** a "budget exhaustion spike" alert fires with the event rate, affected workspace, and a link to the reasoning dashboard.
4. **Given** an alert has been firing for longer than the resolved timeout, **When** the underlying condition recovers, **Then** the alert transitions to "resolved" and a recovery notification is sent.
5. **Given** multiple alerts fire simultaneously, **When** they are displayed, **Then** they are grouped by severity (critical > warning > info) with the most severe at the top.

---

### User Story 4 - View Domain-Specific Dashboards (Priority: P2)

A platform engineer opens the workflow execution dashboard to understand execution patterns. They see active executions, step latency distributions, and failure rates over time. They switch to the reasoning engine dashboard and see budget utilization, convergence rates, mode distribution, and tree-of-thought branch counts. Each dashboard is purpose-built for its domain, showing the metrics that matter most for that component. Seven dashboards cover the platform's operational domains.

**Why this priority**: Domain-specific dashboards enable specialized investigations beyond the overview. An operator diagnosing slow executions needs different metrics than one investigating fleet health. These dashboards depend on the metrics infrastructure (US1) being in place first.

**Independent Test**: Open each of the seven dashboards. Verify each renders with at least one data series from real service metrics. Verify dashboard filters (time range, workspace) function correctly.

**Acceptance Scenarios**:

1. **Given** the workflow execution dashboard is opened, **When** executions are running, **Then** the dashboard shows active execution count, step latency histogram, step failure rate, and execution throughput over the selected time range.
2. **Given** the reasoning engine dashboard is opened, **When** reasoning requests have been processed, **Then** the dashboard shows budget utilization percentage, convergence rate, reasoning mode distribution pie chart, and tree-of-thought branch count over time.
3. **Given** the data stores dashboard is opened, **When** data stores are operational, **Then** it shows per-store metrics — connection pool usage, query latency, storage utilization, and replication lag (where applicable) — for all 8 data stores.
4. **Given** the fleet health dashboard is opened, **When** fleets are active, **Then** it shows fleet status distribution, member health summary, and degraded operations count over time.
5. **Given** the cost intelligence dashboard is opened, **When** cost data has been aggregated, **Then** it shows cost per agent, cost per workspace, cost per model, trend lines, and optimization suggestion counts.
6. **Given** the self-correction dashboard is opened, **When** self-correction loops have executed, **Then** it shows convergence rate percentage, average iterations per loop, and cost per correction over time.
7. **Given** any dashboard is open, **When** the operator changes the time range filter, **Then** all panels on the dashboard update to reflect the selected time range within 5 seconds.

---

### User Story 5 - Propagate Trace Context Through Kafka Events (Priority: P2)

A developer modifies the event pipeline to add a new bounded context consumer. The trace context automatically propagates through Kafka events without the developer writing any tracing boilerplate. When the new consumer processes events, its processing spans appear in the same trace as the producer's spans. The correlation ID from the event envelope is indexed and searchable in the trace viewer, enabling bi-directional lookup — from a trace to its Kafka events and from a Kafka event to its originating trace.

**Why this priority**: Kafka is the backbone of inter-context communication. Without trace propagation through events, traces break at every async boundary — the operator sees fragments instead of complete request lifecycles. This depends on the tracing infrastructure (US2) being operational first.

**Independent Test**: Produce an event to a Kafka topic with trace context. Consume it in another service. Verify the consumer's processing span is a child of the producer's publish span in the trace viewer.

**Acceptance Scenarios**:

1. **Given** a service produces a Kafka event with an active trace context, **When** the consumer processes the event, **Then** the consumer's processing span is linked to the producer's trace (either as a child span or a linked span).
2. **Given** an event is produced with a correlation ID in the event envelope, **When** the developer searches the trace viewer by that correlation ID, **Then** the trace containing that event's processing is returned.
3. **Given** a chain of events (service A produces event, consumed by service B, which produces another event, consumed by service C), **When** all events carry trace context, **Then** the full chain is visible in a single trace tree in the trace viewer.

---

### User Story 6 - Access Observability in Local Development Mode (Priority: P3)

A developer running the platform in local mode can see basic metrics and traces without deploying the full observability stack. Traces from local services are collected and viewable through a lightweight local interface. This enables developers to debug trace propagation and verify instrumentation without a Kubernetes cluster.

**Why this priority**: Developers need to verify their instrumentation works before deploying to a cluster. Without local observability support, they must deploy to Kubernetes just to see if their traces are being emitted — creating a slow feedback loop. This is a convenience feature that depends on all other observability capabilities being production-ready first.

**Independent Test**: Start the platform in local mode. Trigger a request. Verify traces appear in the local trace viewer.

**Acceptance Scenarios**:

1. **Given** the platform is running in local mode, **When** the developer triggers a request, **Then** the request trace is collected and viewable through a local interface within 10 seconds.
2. **Given** the local observability interface is running, **When** the developer opens it, **Then** they see recent traces with service names, operations, and durations — no configuration beyond starting local mode is required.

---

### Edge Cases

- What happens when the metrics collector is down? Services continue operating normally — metric emission is fire-and-forget and does not block service requests. Dashboards show a gap in data for the outage period.
- What happens when the trace collector is overloaded? The collector applies backpressure via the memory limiter processor. Services with full export buffers begin dropping spans with a "spans dropped" counter incremented. Sampling rate can be reduced to alleviate pressure.
- What happens when a Kafka event lacks trace context (legacy event)? The consumer creates a new root span for processing. The trace viewer shows the consumer's processing as an independent trace — no error, just no linkage.
- What happens when alert notification delivery fails? Alerts remain in "firing" state in the alerting system. The operator can view all active alerts directly in the alerting interface even if external notifications were not delivered.
- What happens when dashboards render with no data (newly deployed service)? Panels display a "no data" indicator rather than an error. As soon as the service emits its first metric, the panel begins rendering.
- What happens when two services use different trace context formats? The collector normalizes trace context to W3C Trace Context format. Services using B3 or other propagation formats are bridged automatically by the collector.

## Requirements

### Functional Requirements

- **FR-001**: The observability stack MUST be deployed in a dedicated namespace isolated from application workloads
- **FR-002**: All platform services (control plane, satellite services) MUST emit telemetry (metrics, traces) to the observability stack without requiring application-level code changes beyond initial instrumentation
- **FR-003**: The metrics collector MUST scrape metrics from all services across all platform namespaces (platform-control, platform-execution, platform-simulation, platform-data) with a scrape interval of no more than 30 seconds
- **FR-004**: The trace collector MUST accept traces via both gRPC and HTTP protocols and store them for at least 7 days
- **FR-005**: Trace context MUST propagate across HTTP requests, gRPC calls, and Kafka events using the platform's canonical event envelope
- **FR-006**: The system MUST provide 7 pre-built dashboards: Platform Overview, Workflow Execution, Reasoning Engine, Data Stores, Fleet Health, Cost Intelligence, and Self-Correction
- **FR-007**: Each dashboard MUST support time range selection and auto-refresh at configurable intervals
- **FR-008**: The Platform Overview dashboard MUST display health status, request rate, error rate, and latency for every platform service
- **FR-009**: Alert rules MUST be defined for: service unreachable, high error rate (>5% of requests), Kafka consumer lag exceeding threshold, workflow execution failure spike, reasoning budget exhaustion spike, self-correction non-convergence, and fleet degraded operation
- **FR-010**: Each alert MUST include the condition, current metric value, threshold, severity level, and a link to the relevant dashboard
- **FR-011**: Alerts MUST transition to "resolved" when the triggering condition recovers
- **FR-012**: The trace viewer MUST support searching traces by correlation ID, service name, operation name, minimum duration, and time range
- **FR-013**: The metrics collector MUST apply backpressure and memory limits to prevent collector resource exhaustion from overwhelming metric volumes
- **FR-014**: Telemetry emission MUST be non-blocking — a failure in the observability stack MUST NOT cause application service failures or degraded latency
- **FR-015**: The system MUST support a lightweight local development mode for basic trace collection without the full stack deployment
- **FR-016**: All dashboards MUST load within 5 seconds and update panels within 5 seconds of a time range or filter change

### Key Entities

- **Telemetry Signal**: A unit of observability data emitted by a service — one of three types: metric (a numeric measurement at a point in time), trace span (a timed operation within a distributed request), or log entry (a structured text record). Each signal carries the emitting service name, timestamp, and the active correlation ID.
- **Trace**: A tree of spans representing a complete distributed request lifecycle. Has a globally unique trace identifier, a root span, child spans across multiple services, total duration, and an overall status (ok/error). Linked to a correlation ID for cross-referencing with Kafka events.
- **Alert Rule**: A condition evaluated periodically against collected metrics. Has a name, the metric expression being evaluated, a threshold, evaluation interval, severity (critical/warning/info), a notification target, and a dashboard link. Transitions between "inactive", "pending", and "firing" states.
- **Dashboard**: A collection of visualization panels focused on a specific operational domain. Has a title, a set of panels (each with a metric query and visualization type), time range controls, and optional filter variables (workspace, service, model).
- **Dashboard Panel**: A single visualization within a dashboard — has a title, metric query expression, visualization type (time-series, gauge, stat, bar, pie, table), thresholds for color coding, and a refresh interval.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Operators can see the health status of any platform service within 60 seconds of an issue occurring
- **SC-002**: Developers can find the root cause of a cross-service latency issue within 5 minutes using the trace viewer, without accessing individual service logs
- **SC-003**: Critical alerts (service down, high error rate) reach the on-call operator within 5 minutes of the condition first occurring
- **SC-004**: All 7 domain dashboards render with real data from production services — no empty or placeholder panels
- **SC-005**: Trace context is preserved across 100% of HTTP, gRPC, and Kafka event boundaries in the platform
- **SC-006**: The observability stack adds no more than 2% overhead to service request latency (p99)
- **SC-007**: Metrics and trace data is retained for at least 7 days, enabling retrospective investigation of past incidents
- **SC-008**: Local development mode provides trace visibility with zero additional infrastructure setup beyond starting the platform

## Assumptions

- All platform services already include instrumentation libraries (opentelemetry-sdk for Python, go.opentelemetry.io/otel for Go) as declared in their dependencies — this feature deploys the collection and visualization infrastructure, not the per-service instrumentation code
- The Kubernetes cluster has sufficient resources in the `platform-observability` namespace for the observability stack (estimated: 2 CPU cores, 4 GB RAM for collector + storage + visualization combined)
- Kafka events use the canonical EventEnvelope model which already includes fields for trace context propagation (trace_id, span_id, trace_flags)
- Alert notification routing (email, Slack, PagerDuty) is configurable but the specific notification integrations are out of scope for this feature — alerts are visible in the alerting interface regardless
- Dashboard provisioning is declarative (dashboards defined as configuration, not manually created through a UI)
- The existing Helm chart infrastructure (`deploy/helm/`) is available for deploying observability components
- Metric cardinality is managed by the services — the observability stack does not limit which metrics are emitted but applies memory limits to prevent collector crashes
- Log aggregation (centralized log collection, indexing, and search) is out of scope — this feature covers metrics, traces, and dashboards only
