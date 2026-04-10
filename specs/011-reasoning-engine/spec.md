# Feature Specification: Reasoning Engine — Reasoning Orchestration, Budget Tracking, Self-Correction

**Feature Branch**: `011-reasoning-engine`  
**Created**: 2026-04-10  
**Status**: Draft  
**Input**: User description: "Go Reasoning Engine — reasoning mode selection, budget tracking, chain-of-thought trace coordination, tree-of-thought branch management, self-correction convergence detection"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Reasoning Mode Selection (Priority: P1)

When an agent execution begins, the platform must decide which reasoning strategy to use for the task. The reasoning engine accepts the task brief, any policy constraints, and the available budget, then returns the recommended reasoning mode (direct response, chain-of-thought, tree-of-thought, reactive, code-as-reasoning, or debate) along with how the budget should be allocated across reasoning steps. The selection considers task complexity, available resources, and any workspace or agent-level policy overrides.

**Why this priority**: Mode selection is the entry point for all reasoning workflows. Without it, no other reasoning capability (budgets, traces, trees, corrections) can be dispatched correctly.

**Independent Test**: Submit a simple factual question — system selects direct mode. Submit a complex multi-step analysis task — system selects chain-of-thought or tree-of-thought. Submit a task with a policy override forcing a specific mode — system respects the override.

**Acceptance Scenarios**:

1. **Given** a task brief with low complexity, **When** mode selection is requested, **Then** the system returns the direct reasoning mode with minimal budget allocation
2. **Given** a task brief with high complexity and multi-step requirements, **When** mode selection is requested, **Then** the system returns chain-of-thought or tree-of-thought mode with proportionally higher budget
3. **Given** a task brief with a policy constraint specifying a required mode, **When** mode selection is requested, **Then** the system returns the policy-mandated mode regardless of complexity analysis
4. **Given** a task brief that exceeds the available budget for the recommended mode, **When** mode selection is requested, **Then** the system downgrades to a less expensive mode that fits within the budget

---

### User Story 2 — Real-Time Budget Tracking and Enforcement (Priority: P1)

Each reasoning execution operates within a budget envelope that tracks token usage, round count, cost, and elapsed time. The platform allocates the budget at execution start and atomically decrements it as resources are consumed. When budget thresholds are crossed (80%, 90%, 100%), the platform emits warning events. When the budget is exhausted, the reasoning execution is terminated or downgraded. Budget operations must be atomic even under high concurrency (100+ simultaneous budget decrements).

**Why this priority**: Budget enforcement prevents runaway reasoning costs and is a hard requirement for multi-tenant operation. Without it, a single execution could consume unlimited resources.

**Independent Test**: Allocate a budget with max_tokens=1000, submit 10 decrements of 100 tokens each. Verify used_tokens reaches 1000, threshold events fire at 800 and 900, and a final "exceeded" event fires at 1000. Run 100 concurrent decrements and verify no tokens are lost or double-counted.

**Acceptance Scenarios**:

1. **Given** a newly allocated budget envelope, **When** the status is queried, **Then** all counters are at zero and the budget is active
2. **Given** an active budget with used_tokens at 79%, **When** a decrement of 2% is applied, **Then** the 80% threshold event is emitted within 100 milliseconds
3. **Given** 100 concurrent decrement operations on the same budget, **When** all operations complete, **Then** the total used_tokens equals the sum of all individual decrements (no race conditions)
4. **Given** an active budget with used_tokens at 99%, **When** a decrement that would exceed 100% is applied, **Then** the decrement is rejected and a "budget exceeded" event is emitted
5. **Given** a budget with a time limit, **When** the elapsed time exceeds the limit, **Then** a "time exceeded" event is emitted and further operations are rejected

---

### User Story 3 — Chain-of-Thought Trace Coordination (Priority: P1)

During chain-of-thought reasoning, the runtime produces a stream of trace events (reasoning steps, intermediate conclusions, token counts). The reasoning engine receives these events in real-time via a streaming interface, persists metadata for querying, stores large payloads (full reasoning dumps) in object storage, and forwards events to downstream consumers via the event backbone for observability and analytics.

**Why this priority**: Trace coordination is essential for observability, debugging, and the explainability requirement of the trust framework. Without it, reasoning execution is opaque.

**Independent Test**: Start a reasoning execution, stream 10 trace events. Verify all 10 are persisted in cold storage with metadata, large payloads are in object storage, and events appear in the event backbone topic.

**Acceptance Scenarios**:

1. **Given** an active reasoning execution, **When** trace events are streamed, **Then** each event's metadata is persisted to cold storage within 1 second
2. **Given** a trace event with a payload exceeding 64KB, **When** the event is received, **Then** the payload is stored in object storage and only a reference is persisted in cold storage
3. **Given** trace events being received, **When** events are processed, **Then** each event is forwarded to the event backbone for downstream consumers
4. **Given** a stream of 1000 trace events, **When** the stream completes, **Then** a summary acknowledgment is returned with total events received, events persisted, and any failures

---

### User Story 4 — Tree-of-Thought Branch Management (Priority: P2)

For complex reasoning tasks requiring exploration of multiple hypotheses, the platform supports tree-of-thought execution. Multiple reasoning branches execute concurrently, each exploring a different approach. Each branch tracks its hypothesis, quality score, and token cost. When a branch exceeds its individual budget, it is automatically pruned. After all branches complete (or are pruned), the platform evaluates and ranks them by a configurable scoring function (quality-to-cost ratio by default) and returns the best branch.

**Why this priority**: Tree-of-thought is a powerful but advanced reasoning strategy. The platform can function with direct and chain-of-thought modes alone; tree-of-thought adds depth for complex tasks.

**Independent Test**: Create 5 branches with different hypotheses. Set a low individual branch budget — verify 2 branches are pruned when they exceed it. Evaluate remaining 3 branches — verify the highest quality/cost branch is selected.

**Acceptance Scenarios**:

1. **Given** a tree-of-thought execution with max concurrency of 5, **When** 5 branches are created, **Then** all 5 execute concurrently and their state is tracked independently
2. **Given** a branch that has consumed more tokens than its individual budget, **When** the next budget check occurs, **Then** the branch is automatically pruned and its status is set to "pruned"
3. **Given** 3 completed branches with different quality scores and token costs, **When** evaluation is requested, **Then** the branch with the best quality-to-cost ratio is selected
4. **Given** all branches are pruned before any completes, **When** evaluation is requested, **Then** the system returns a "no viable branches" result with the best partial result

---

### User Story 5 — Self-Correction Convergence Detection (Priority: P2)

When an agent produces output that does not meet quality requirements, the platform runs a self-correction loop. Each iteration receives a quality score, and the platform computes the improvement delta between consecutive iterations. The loop converges (terminates successfully) when the quality delta falls below a configurable epsilon for two consecutive iterations, indicating diminishing returns. If the maximum iteration count or cost cap is reached before convergence, the loop terminates and optionally escalates to human review.

**Why this priority**: Self-correction is a core differentiator for agent intelligence but depends on budget tracking (US2) and trace coordination (US3) being in place.

**Independent Test**: Start a correction loop with epsilon=0.01 and max_iterations=10. Submit scores [0.5, 0.7, 0.78, 0.80, 0.805, 0.808]. Verify convergence is detected at iteration 6 (delta 0.003 < 0.01 for second consecutive time). In a separate test, submit scores that never converge and verify budget-exceeded termination at max_iterations.

**Acceptance Scenarios**:

1. **Given** a self-correction loop with epsilon=0.01, **When** two consecutive iterations have quality delta < 0.01, **Then** the system returns CONVERGED
2. **Given** a self-correction loop, **When** the iteration count reaches max_iterations, **Then** the system returns BUDGET_EXCEEDED regardless of convergence
3. **Given** a self-correction loop, **When** the cumulative cost exceeds the cost cap, **Then** the system returns BUDGET_EXCEEDED
4. **Given** a non-converged loop that has exhausted its budget, **When** the loop terminates, **Then** an escalation event is emitted if escalation is configured
5. **Given** each iteration in a correction loop, **When** the quality score is submitted, **Then** the full iteration history (all scores, deltas, durations) is persisted for forensic analysis

---

### User Story 6 — Budget Event Streaming (Priority: P2)

Operators and monitoring systems need real-time visibility into budget consumption across all active reasoning executions. The platform provides a streaming interface that pushes budget events (threshold warnings at 80%, 90%, 100%; budget allocations; budget completions) as they occur. Multiple subscribers can watch the same execution's budget events concurrently.

**Why this priority**: Essential for observability and operational alerting but not required for basic reasoning execution.

**Independent Test**: Subscribe to budget events for an execution, then trigger budget decrements that cross 80% and 90% thresholds. Verify both threshold events are received in order. Open a second subscriber — verify both receive the same events.

**Acceptance Scenarios**:

1. **Given** an active budget, **When** a threshold is crossed (80%, 90%, 100%), **Then** subscribers receive a threshold event within 100 milliseconds
2. **Given** multiple concurrent subscribers for the same execution, **When** a budget event occurs, **Then** all subscribers receive the event
3. **Given** a subscriber that connects after some events have already occurred, **When** events continue, **Then** only future events are delivered (no replay of past events)
4. **Given** a budget that reaches completion (execution ends), **When** the budget is closed, **Then** all subscriber streams are closed gracefully

---

### Edge Cases

- What happens when the reasoning engine restarts while budgets are active? Active budgets persist in the hot state store with TTL; the engine re-reads them on startup. No budget state is lost.
- What happens when a budget decrement arrives after the budget is already exhausted? The decrement is rejected atomically, and a "budget exceeded" error is returned to the caller.
- What happens when a tree-of-thought branch's goroutine panics? The panic is recovered, the branch is marked as failed with the panic message, and remaining branches continue unaffected.
- What happens when trace events arrive faster than they can be persisted? Events are buffered in-memory (configurable buffer size, default 10,000). If the buffer overflows, oldest events are dropped and a counter tracks dropped events.
- What happens when the scoring function returns equal scores for multiple branches? Ties are broken by lower token cost, then by earlier creation time.
- What happens when convergence epsilon is set to zero? The loop can only converge if two consecutive iterations produce exactly equal quality scores, which effectively disables convergence detection — the loop runs to max_iterations.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST select a reasoning mode from at least 6 options (direct, chain-of-thought, tree-of-thought, reactive, code-as-reasoning, debate) based on task complexity and constraints
- **FR-002**: System MUST accept policy overrides that force a specific reasoning mode regardless of complexity analysis
- **FR-003**: System MUST allocate reasoning budgets with configurable limits on tokens, rounds, cost, and time
- **FR-004**: System MUST atomically decrement budgets under concurrent access (no double-counting, no lost updates)
- **FR-005**: System MUST emit threshold events when budget consumption crosses 80%, 90%, and 100%
- **FR-006**: System MUST reject further operations on an exhausted budget
- **FR-007**: System MUST automatically clean up budget state after execution completion using TTL-based expiry
- **FR-008**: System MUST receive streaming trace events from reasoning executions and persist metadata
- **FR-009**: System MUST store trace payloads exceeding 64KB in object storage, retaining only a reference in the metadata store
- **FR-010**: System MUST forward all trace events to the event backbone for downstream consumers
- **FR-011**: System MUST support creating and tracking multiple concurrent tree-of-thought branches with configurable max concurrency
- **FR-012**: System MUST automatically prune branches that exceed their individual budget allocation
- **FR-013**: System MUST evaluate completed branches using a configurable scoring function and return the best result
- **FR-014**: System MUST persist branch payloads to object storage
- **FR-015**: System MUST detect convergence in self-correction loops when quality delta < epsilon for two consecutive iterations
- **FR-016**: System MUST terminate self-correction loops when iteration count or cost cap is exceeded, regardless of convergence
- **FR-017**: System MUST emit an escalation event when a self-correction loop fails to converge within budget
- **FR-018**: System MUST persist full iteration history (scores, deltas, durations) for each self-correction loop
- **FR-019**: System MUST provide a streaming interface for budget events with support for multiple concurrent subscribers
- **FR-020**: System MUST provide a query interface for current budget status
- **FR-021**: System MUST propagate trace context for distributed tracing across all operations
- **FR-022**: System MUST provide health check endpoints indicating service readiness and dependency health
- **FR-023**: System MUST downgrade the reasoning mode if the recommended mode exceeds the available budget

### Key Entities

- **ReasoningMode**: A named reasoning strategy (DIRECT, CHAIN_OF_THOUGHT, TREE_OF_THOUGHT, REACT, CODE_AS_REASONING, DEBATE) with associated default budget allocation and complexity thresholds
- **BudgetEnvelope**: A tracked resource allocation with limits and current usage across four dimensions (tokens, rounds, cost, time), associated with an execution and step
- **ReasoningTrace**: A sequence of timestamped events capturing the reasoning process, with metadata for querying and full payloads for deep analysis
- **TreeBranch**: An independent reasoning hypothesis within a tree-of-thought execution, with its own quality score, token cost, and lifecycle status (active, completed, pruned, failed)
- **SelfCorrectionLoop**: An iterative refinement process with configurable convergence criteria (epsilon, max iterations, cost cap), producing an ordered history of quality scores
- **BudgetEvent**: A notification of a budget state change (threshold crossed, budget allocated, budget completed, budget exceeded) with timestamp and execution context

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Budget check operations complete within 1 millisecond at the 99th percentile
- **SC-002**: Budget threshold events are delivered within 100 milliseconds of the threshold being crossed
- **SC-003**: Concurrent budget decrements (100 simultaneous operations on the same budget) produce correct totals with zero race conditions
- **SC-004**: Reasoning mode selection responds within 50 milliseconds for any task brief
- **SC-005**: Trace events are persisted within 1 second of receipt
- **SC-006**: Tree-of-thought supports at least 10 concurrent branches per execution
- **SC-007**: Self-correction convergence detection correctly identifies convergence within 1 iteration of the mathematical threshold
- **SC-008**: Service binary image is smaller than 50MB
- **SC-009**: Automated test suite achieves at least 95% code coverage
- **SC-010**: System handles at least 100 concurrent reasoning executions each with their own budget
- **SC-011**: Budget state survives service restarts (no active budget data lost)
- **SC-012**: All reasoning lifecycle events are emitted to the event backbone within 500 milliseconds

## Assumptions

- The reasoning engine runs as a standalone service, separate from the control plane; the control plane has thin coordination layers that delegate all hot-path execution to this service
- Hot state (active budgets, convergence metrics, branch scores) is stored in a separate caching layer from cold state (completed traces, correction records)
- Large payloads (full chain-of-thought dumps, tree-of-thought branch payloads, correction artifacts) are stored in object storage, not in the metadata store
- The scoring function for tree-of-thought branch evaluation defaults to quality-to-cost ratio; custom scoring functions are out of scope for v1
- Reasoning mode selection heuristics (complexity analysis) are rule-based in v1; ML-based mode selection is out of scope
- The event backbone is available for all lifecycle events; if the backbone is temporarily unreachable, events are buffered and retried
- Code-as-reasoning mode delegates actual code execution to the sandbox manager (feature 010); this service only selects the mode and tracks the budget
- Budget dimensions are additive (tokens, rounds, cost, time are tracked independently); a budget is exhausted when ANY dimension reaches its limit
