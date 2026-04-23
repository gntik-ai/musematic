# Feature Specification: Advanced Reasoning Modes and Trace Export

**Feature Branch**: `064-reasoning-modes-and-trace`  
**Created**: 2026-04-19  
**Status**: Draft  
**Input**: Brownfield extension. Adds two new reasoning techniques to the existing reasoning engine — DEBATE (Chain of Debates) for multi-agent adversarial deliberation, and SELF_CORRECTION for iterative refinement — alongside the existing COT, TOT, and REACT modes. Introduces a compute_budget parameter that bounds total reasoning depth (steps, branches, iterations) on any mode, giving platform operators a direct control for the Scaling Inference Law trade-off. Adds a structured reasoning trace export endpoint so compliance, support, and AI engineers can audit, replay, and analyze the exact reasoning path every execution followed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — AI Engineer Runs a DEBATE Reasoning Session (Priority: P1)

An AI engineer configures an agent or workflow step with reasoning mode `DEBATE` and a participant list of two or more agent FQNs. When the step executes, the reasoning engine orchestrates the participants through structured rounds: each agent first states an initial **position**, then **critiques** the peers' positions, then issues a **rebuttal**, then a **synthesis** round attempts consensus. The round loop ends when consensus is detected (all participants converge on the same synthesized position) or the configured round limit is reached. The engineer sees each round's contributions attributed to the specific participant and the final debate outcome with a `consensus_reached` flag.

**Why this priority**: DEBATE is a proven technique for surfacing implicit assumptions and reducing single-agent bias on contested questions (policy decisions, cross-domain trade-offs, open research questions). It is the primary new capability of this feature and unlocks value that no current reasoning mode delivers. P1 because without DEBATE, the feature is purely a trace-export tool on existing modes.

**Independent Test**: Configure a step with mode=`DEBATE`, two participants, round_limit=3. Submit an execution where the question is "Should the system prefer latency or accuracy for this workload?". Verify the debate transcript contains a position round, a critique round, and either a consensus-triggered synthesis or a round-limit-triggered synthesis. Verify each step in the transcript identifies the participating agent, the round number, the step type (position/critique/rebuttal/synthesis), and the content.

**Acceptance Scenarios**:

1. **Given** a DEBATE step with two participants and round_limit=5, **When** the step executes and participants converge at round 3, **Then** the debate terminates at round 3 with `consensus_reached=true` and the transcript contains positions, critiques, rebuttals, and synthesis.
2. **Given** a DEBATE step with three participants and round_limit=3, **When** no consensus is reached, **Then** the debate terminates at round 3 with `consensus_reached=false` and the synthesis step records the unresolved positions for operator follow-up.
3. **Given** a DEBATE step configured with zero or one participant, **When** the configuration is saved, **Then** the configuration is rejected with a validation error (DEBATE requires at least two participants).
4. **Given** a DEBATE in progress, **When** one participant fails to respond within the per-turn timeout, **Then** the debate records the missed turn, continues with remaining participants, and flags the failure in the transcript.
5. **Given** a completed DEBATE step, **When** the trace export is requested, **Then** the export returns the full debate transcript in structured JSON with every round's contributions attributed by agent and round.

---

### User Story 2 — AI Engineer Configures SELF_CORRECTION Iterative Refinement (Priority: P1)

An AI engineer configures a step with reasoning mode `SELF_CORRECTION` and a `max_iterations` limit. The reasoning engine produces an initial answer, evaluates it against quality criteria (critique-self), and iteratively refines the answer. Each iteration records the prior answer, the self-critique, and the refined answer. The loop terminates when the quality score stabilizes (no material improvement between iterations) or the max_iterations cap is reached.

**Why this priority**: Self-correction is the foundational technique for reducing first-draft errors in generation tasks (writing, coding, structured extraction). It composes naturally with the existing correction_loop subsystem and is a commonly-requested capability for quality-sensitive workflows. P1 because it delivers immediate value on every refinement-style task and is the second cornerstone of the "reasoning modes" expansion.

**Independent Test**: Configure a step with mode=`SELF_CORRECTION`, max_iterations=4. Submit an execution where the task is "Generate a JSON that matches this schema". Introduce a deliberate schema-mismatching initial answer. Verify the engine iterates (≥2 iterations), each iteration's critique identifies the schema mismatch, and the final answer satisfies the schema or the max_iterations cap is reached with the last answer and final critique recorded.

**Acceptance Scenarios**:

1. **Given** a SELF_CORRECTION step with max_iterations=5, **When** the answer stabilizes at iteration 3, **Then** the loop terminates at iteration 3 and the transcript records exactly 3 iterations.
2. **Given** a SELF_CORRECTION step with max_iterations=3, **When** the answer has not stabilized by iteration 3, **Then** the loop terminates at the cap and the transcript includes the final non-stabilized answer with the last critique.
3. **Given** a SELF_CORRECTION configuration with max_iterations=0 or negative, **When** the configuration is saved, **Then** the configuration is rejected with a validation error.
4. **Given** a SELF_CORRECTION step where each iteration is producing a worse critique score, **When** the degradation threshold is crossed, **Then** the loop terminates early with a `degradation_detected` flag and the best-scoring intermediate answer is returned.
5. **Given** a completed SELF_CORRECTION step, **When** the trace export is requested, **Then** every iteration's prior answer, critique, and refined answer is returned in order with quality scores.

---

### User Story 3 — Platform Operator Bounds Reasoning Cost via compute_budget (Priority: P1)

A platform operator configures a `compute_budget` on a reasoning step or at the workflow level. The budget is a dimensionless fraction (0.0–1.0 or an equivalent normalized form) that caps the total reasoning work: combined steps for CoT, combined branches for ToT, combined rounds for DEBATE, combined iterations for SELF_CORRECTION, combined cycles for REACT. When the budget is reached, the reasoning engine terminates the current mode gracefully and returns the best-so-far result with a `compute_budget_exhausted` flag. The operator monitors budget utilization (`compute_budget_used`) on every trace to understand how often each mode saturates the budget.

**Why this priority**: The Scaling Inference Law states that reasoning quality scales with compute, but costs scale faster than returns past a certain point. Without a budget control, reasoning-heavy workloads are cost-unpredictable. P1 because cost predictability is a non-negotiable requirement for enterprise adoption — a feature that ships without a budget would give operators no way to cap reasoning spend at step granularity.

**Independent Test**: Configure a ToT step with compute_budget=0.25 (a very low budget). Submit an execution. Verify the tree is pruned well before exhaustion (total branches evaluated < half of the mode's default maximum). Verify the trace reports `compute_budget_used` between 0.20 and 0.25 and `compute_budget_exhausted=true`. Re-run with compute_budget=1.0 on the same question; verify compute_budget_used is lower (the mode completes naturally before saturating) and `compute_budget_exhausted=false`.

**Acceptance Scenarios**:

1. **Given** a reasoning step with compute_budget=0.50, **When** the step executes and reaches half of the mode's configured maximum work, **Then** the engine terminates the mode and returns the best-so-far answer with `compute_budget_exhausted=true`.
2. **Given** a reasoning step with no compute_budget configured, **When** the step executes, **Then** the mode runs to its natural termination condition (consensus, stabilization, or default mode limit) and `compute_budget_used` still reports the normalized actual work.
3. **Given** a compute_budget outside the valid range (negative or greater than 1.0 in the normalized form), **When** the configuration is saved, **Then** the configuration is rejected with a validation error.
4. **Given** DEBATE, SELF_CORRECTION, COT, TOT, and REACT modes, **When** each is run with compute_budget=0.30 on equivalent tasks, **Then** all five modes respect the budget (none exceeds it by more than a defined tolerance) and the exhaustion flag is set on whichever modes terminated by budget exhaustion.
5. **Given** a step-level budget and a workflow-level budget, **When** the step runs, **Then** the stricter (lower) budget is applied and the trace records which scope the effective limit came from.

---

### User Story 4 — Operator Exports Structured Reasoning Trace for Audit (Priority: P2)

A compliance, support, or AI engineer investigator needs to understand how a specific execution arrived at its answer. They query the trace export endpoint for the execution. The endpoint returns a structured JSON trace: the reasoning technique used, every reasoning step in order (with type — `position`, `critique`, `thought`, `action`, `observation`, etc. — the participating agent, the content, any tool call, a quality score, tokens used, and a timestamp), the total tokens consumed, the fraction of compute_budget used, and whether consensus (for DEBATE) or stabilization (for SELF_CORRECTION) was reached. The trace can be downloaded, filed in a ticket, or post-processed for aggregate analysis.

**Why this priority**: Structured traces are the foundation of reasoning explainability (Layer 4 of the trust framework). Without a canonical trace export, each reasoning mode's artifacts live in disparate shapes across the system and compliance cannot audit or compare them. P2 because the reasoning modes themselves (US1–US3) must exist first to have anything to export; once modes exist, the export is a thin query over persisted artifacts. Still P2 (not P3) because audit is a hard requirement for enterprise and compliance workloads.

**Independent Test**: Run three separate executions: one with DEBATE, one with SELF_CORRECTION, one with REACT. Query the trace export for each. Verify each response contains `execution_id`, `technique`, `steps` array with the correct step types for that technique, `total_tokens`, `compute_budget_used`, and the technique-appropriate flags (`consensus_reached` for DEBATE, stabilization status for SELF_CORRECTION). Verify the trace JSON is well-formed, the `steps` array is sorted by step_number, and each step has a valid ISO-8601 timestamp.

**Acceptance Scenarios**:

1. **Given** a completed execution of any supported reasoning mode, **When** the trace export is requested, **Then** the response is a structured JSON object conforming to the canonical trace schema with all required fields populated.
2. **Given** a trace export request for an execution that has not yet completed its reasoning step, **When** the request arrives, **Then** the response returns the partial trace with `status=in_progress` and a `last_updated_at` timestamp.
3. **Given** a trace export request for an execution by a user without permission to view the execution, **When** the request arrives, **Then** the request is rejected with an authorization error and no trace data is disclosed.
4. **Given** a trace export request for a non-existent execution, **When** the request arrives, **Then** the response is a 404-equivalent not-found error.
5. **Given** a trace for a DEBATE step, **When** exported, **Then** each step in the `steps` array carries `agent_fqn` identifying the participant, and rounds are distinguishable (step types: `position`, `critique`, `rebuttal`, `synthesis`).
6. **Given** a trace for a REACT step, **When** exported, **Then** each cycle is represented as a `thought → action → observation` triplet and the tool call invoked is captured in the `tool_call` field of the action step.

---

### User Story 5 — Platform Operator Observes Real-Time Reasoning Progress (Priority: P3)

A platform operator watches a dashboard showing in-flight reasoning activity. As DEBATE rounds complete and REACT cycles complete, the engine emits `reasoning.debate.round_completed` and `reasoning.react.cycle_completed` events with the round/cycle number, the step summary, and the running budget utilization. The operator sees these events stream in near-real-time and can correlate them to executions. This gives operators a way to detect stalled reasoning, runaway loops, and degraded performance without polling the trace export endpoint.

**Why this priority**: Real-time observability is valuable but not a functional prerequisite — the trace export (US4) already allows post-hoc analysis. P3 because the events are a thin addition to a reasoning pipeline that is already observable via traces; they are primarily a convenience for dashboard/alerting use cases.

**Independent Test**: Start a DEBATE execution with 3 participants and round_limit=4. Subscribe to the event stream filtered by execution_id. Verify each round completion emits exactly one `reasoning.debate.round_completed` event with the round number, participant list, and aggregated step count for the round. Start a REACT execution; verify each cycle emits `reasoning.react.cycle_completed` with the cycle number and the observation summary.

**Acceptance Scenarios**:

1. **Given** a DEBATE in progress, **When** round N completes, **Then** exactly one `reasoning.debate.round_completed` event is emitted with round_number=N, participant list, consensus_status, and running compute_budget_used.
2. **Given** a REACT in progress, **When** a thought-action-observation cycle completes, **Then** exactly one `reasoning.react.cycle_completed` event is emitted with cycle_number, tool invoked (if any), and a summary of the observation.
3. **Given** an event consumer falls behind, **When** events continue to be emitted, **Then** the reasoning pipeline is NOT blocked (event emission is best-effort — reasoning correctness is not gated on event delivery).
4. **Given** a DEBATE or REACT that terminates by compute_budget exhaustion, **When** the final round/cycle event is emitted, **Then** it carries `terminated_by=compute_budget_exhausted`.

---

### Edge Cases

- **DEBATE with an odd number of participants and a tie in synthesis**: The synthesis step records a "no-consensus" outcome; the tie-breaking strategy is deferred to the caller (no implicit majority vote).
- **SELF_CORRECTION oscillates between two answers indefinitely**: Oscillation detection treats oscillation as lack of stabilization; the loop continues until max_iterations and returns the answer with the best quality score.
- **REACT action produces an observation that is itself a tool error**: The observation records the error; the next thought step is expected to handle or escalate; the cycle is not retried automatically.
- **compute_budget=0.0 is configured explicitly**: Rejected at save time — explicit zero is not a valid reasoning budget; the caller must either omit the parameter or specify a positive fraction.
- **Trace export requested for an execution whose reasoning artifacts have been garbage-collected by retention**: Returns a 410-equivalent with a clear "trace not available" message; retention windows are configurable.
- **DEBATE participant list references an agent that has been revoked or archived**: DEBATE configuration save is rejected at validation time; in-flight debates whose participants are revoked mid-flight continue with remaining participants and flag the revocation.
- **Very large trace JSON**: Trace responses can grow large on long DEBATE or SELF_CORRECTION sessions. A per-response size limit (configurable) with optional pagination or artifact-download fallback ensures bounded payload size.
- **compute_budget at workflow scope exceeds the sum of step-scope budgets**: Step budgets remain in force for each individual step; workflow-scope budget acts as an aggregate cap that terminates further reasoning once total consumed work reaches the workflow cap.
- **Trace export concurrent with reasoning still writing**: The exporter returns a consistent snapshot of artifacts written so far; it does not block reasoning progression.
- **Two modes requested simultaneously (e.g., DEBATE with nested SELF_CORRECTION inside each participant)**: Out of Scope for this release — nested reasoning modes are not supported; configuration must specify a single top-level mode.
- **Reasoning events consumer downstream is slow**: Events accumulate in the event bus; reasoning pipeline continues unaffected; operator dashboard lag is the only observable consequence.
- **Trace export without permission**: Returns 403; no fields of the trace leaked, not even metadata (size, technique) — to prevent information disclosure.
- **DEBATE per-turn timeout shorter than some participant's natural response time**: The slow participant misses the turn; transcript flags the missed turn; the debate continues with remaining participants.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The reasoning engine MUST support a `DEBATE` reasoning mode that orchestrates at least two participating agents through structured rounds: position, critique, rebuttal, synthesis.
- **FR-002**: DEBATE mode MUST be configurable with: participant list (≥ 2 agent FQNs), round_limit (≥ 1), and per-turn timeout (defaults applied when unset).
- **FR-003**: DEBATE mode MUST detect consensus (all participants converge on a synthesized position) and terminate at the earliest round where consensus is detected.
- **FR-004**: DEBATE mode MUST terminate at the configured round_limit even when consensus is not reached; the transcript MUST record `consensus_reached=false` and preserve all unresolved positions.
- **FR-005**: DEBATE configurations with fewer than 2 participants, round_limit < 1, or non-existent/archived participant FQNs MUST be rejected at save time with clear validation errors.
- **FR-006**: When a DEBATE participant misses a turn (timeout or failure), the transcript MUST record the missed turn and the debate MUST continue with remaining participants.
- **FR-007**: The reasoning engine MUST support a `SELF_CORRECTION` reasoning mode that iteratively refines an initial answer using self-critique.
- **FR-008**: SELF_CORRECTION mode MUST be configurable with `max_iterations` (≥ 1).
- **FR-009**: SELF_CORRECTION mode MUST detect answer stabilization (no material improvement between iterations per a configurable threshold) and terminate at stabilization.
- **FR-010**: SELF_CORRECTION mode MUST terminate at max_iterations even when the answer has not stabilized; the last answer and final critique MUST be returned.
- **FR-011**: SELF_CORRECTION mode MUST detect quality degradation (successive iterations producing worse critique scores beyond a configurable threshold) and return the best-scoring intermediate answer with a `degradation_detected` flag.
- **FR-012**: All reasoning mode requests MUST accept an optional `compute_budget` parameter that bounds total reasoning work in a normalized form comparable across modes.
- **FR-013**: The effective compute_budget applied to a step MUST be the stricter of the step-scope and workflow-scope budgets when both are configured; the trace MUST record which scope the effective limit came from.
- **FR-014**: When compute_budget is exhausted during reasoning, the mode MUST terminate gracefully and return the best-so-far result with `compute_budget_exhausted=true`.
- **FR-015**: compute_budget configurations outside the valid normalized range (including explicit zero, negative values, or greater than 1.0) MUST be rejected at save time with clear validation errors.
- **FR-016**: The reasoning engine MUST emit a `reasoning.debate.round_completed` event on each completed DEBATE round, carrying round number, participant list, consensus status, and running compute_budget_used.
- **FR-017**: The reasoning engine MUST emit a `reasoning.react.cycle_completed` event on each completed REACT cycle, carrying cycle number, tool invoked (if any), observation summary, and running compute_budget_used.
- **FR-018**: Event emission MUST be best-effort from the reasoning pipeline's perspective — reasoning correctness MUST NOT be blocked by slow event consumers.
- **FR-019**: The reasoning engine MUST persist reasoning artifacts (debate transcripts, SELF_CORRECTION iterations, REACT cycles, COT traces, TOT trees) as structured records retrievable by execution identifier.
- **FR-020**: The platform MUST expose a reasoning trace export endpoint that, given an execution identifier, returns a structured JSON trace conforming to the canonical trace schema.
- **FR-021**: The trace schema MUST include: `execution_id`, `technique` (DEBATE/COT/TOT/REACT/SELF_CORRECTION), `steps` array (each step having step_number, type, agent_fqn, content, tool_call, quality_score, tokens_used, timestamp), `total_tokens`, `compute_budget_used`, and technique-appropriate flags (`consensus_reached` for DEBATE, stabilization/degradation flags for SELF_CORRECTION).
- **FR-022**: Trace export for an execution still in progress MUST return the partial trace with `status=in_progress` and `last_updated_at`; trace export for a completed execution MUST return `status=complete`.
- **FR-023**: Trace export for an execution the caller is not authorized to view MUST be denied with an authorization error that discloses no trace metadata.
- **FR-024**: Trace export for an execution whose reasoning artifacts have been removed by retention MUST return a "trace not available" error distinct from "execution not found".
- **FR-025**: The trace step types MUST cover the vocabulary of all supported modes: `position`, `critique`, `rebuttal`, `synthesis` (DEBATE); `thought`, `action`, `observation` (REACT); `iteration_input`, `iteration_critique`, `iteration_output` (SELF_CORRECTION); `branch`, `prune`, `merge` (TOT); `step` (COT).
- **FR-026**: The trace export response MUST enforce a per-response size limit; oversized traces MUST be paginated or available via artifact download rather than returning a truncated body.
- **FR-027**: Each reasoning mode's default work limit (rounds, iterations, branches, cycles, steps) MUST be overrideable on a per-step basis; the overrides MUST be bounded by per-workspace policy caps to prevent runaway costs.
- **FR-028**: The trace schema MUST remain backward compatible: new fields are additive; existing consumers parsing the schema MUST NOT break when new step types are added.
- **FR-029**: Reasoning mode selection for a step MUST continue to support the existing explicit-mode and auto-select code paths; DEBATE and SELF_CORRECTION MUST be addable as explicit selections without affecting the auto-selector's current default behavior for existing workloads.
- **FR-030**: The reasoning engine MUST continue to honour all existing reasoning-budget tracking and convergence-detection behaviors for modes untouched by this feature (COT, TOT, REACT); those modes MUST accept the new compute_budget parameter as an additional constraint without altering their existing semantics.

### Key Entities

- **Debate Session**: A single DEBATE execution. Carries participant list, round_limit, per-turn timeout, termination reason (consensus/round_limit/budget_exhausted), a linked transcript of rounds.
- **Debate Round**: One position-critique-rebuttal-synthesis cycle within a Debate Session. Carries round_number, per-participant contributions, and round-level consensus status.
- **Self-Correction Session**: A single SELF_CORRECTION execution. Carries max_iterations, the iteration series (prior answer, critique, refined answer, quality score each), termination reason (stabilized/max_iterations/degradation_detected/budget_exhausted).
- **REACT Cycle**: One thought-action-observation triplet within a REACT execution.
- **Reasoning Trace**: The structured, schema-conforming export of an execution's reasoning path — independent of the specific mode, usable for audit, replay, and analysis. Contains execution_id, technique, ordered steps, aggregate metrics, and termination flags.
- **Compute Budget**: A normalized control value applied to any reasoning mode that bounds total reasoning work. Scope: step-level, workflow-level. The effective applied budget is the stricter of configured scopes.
- **Reasoning Step** (trace-level entity): A single atomic record in the trace — an agent's contribution or an engine action — with step_number, type, agent_fqn, content, tool_call, quality_score, tokens_used, and timestamp.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of DEBATE sessions terminate either at consensus or at the configured round_limit — none run indefinitely.
- **SC-002**: 100% of DEBATE sessions that detect consensus emit a transcript whose last synthesis step is marked as consensus-triggered.
- **SC-003**: 100% of SELF_CORRECTION sessions terminate at stabilization, max_iterations, or degradation detection — none run indefinitely.
- **SC-004**: 100% of reasoning sessions respect the configured compute_budget within a defined tolerance (≤ 10% overshoot in normalized terms) and report `compute_budget_used` on every trace.
- **SC-005**: 100% of invalid reasoning configurations (bad participant list, bad max_iterations, compute_budget out of range, non-existent agent FQN) are rejected at save time with a clear validation error.
- **SC-006**: 100% of completed reasoning executions produce a structured trace retrievable via the trace export endpoint; for executions that started before this feature shipped, the absence of artifacts results in a clear "trace not available" rather than a malformed response.
- **SC-007**: Trace export returns in under 2 seconds at p95 for traces with up to 200 reasoning steps.
- **SC-008**: 100% of DEBATE round completions and REACT cycle completions emit exactly one corresponding event (no duplicates, no missed completions).
- **SC-009**: Event emission delay does not affect reasoning correctness: reasoning pipeline throughput remains within 5% of baseline regardless of event consumer lag.
- **SC-010**: 100% of unauthorized trace export requests are denied with no trace data, metadata, or structure leakage.
- **SC-011**: Existing reasoning workloads (COT, TOT, REACT pre-feature) continue to operate unchanged; regression tests over pre-existing scenarios produce identical results when compute_budget is not specified.
- **SC-012**: DEBATE termination-by-consensus is deterministic for identical inputs: re-running the same debate with the same participants and prompts yields the same consensus round number within the engine's reproducibility guarantees.
- **SC-013**: For SELF_CORRECTION on a controlled test suite of schema-validation tasks, ≥ 70% of initial answers that fail schema validation are corrected within 3 iterations.

## Assumptions

- The reasoning engine is an existing component with prior COT, TOT, and REACT mode infrastructure; DEBATE and SELF_CORRECTION are added as new modes alongside, not replacements.
- Agent FQNs referenced in DEBATE participant lists are resolved via the existing agent registry; participant availability (not revoked, not archived) is validated at configuration save time.
- Quality scoring for SELF_CORRECTION critique and convergence detection reuses the existing quality-evaluator subsystem rather than defining new scoring criteria.
- compute_budget is a normalized fraction that maps to each mode's native capacity dimension (tokens for COT; branches for TOT; rounds for DEBATE; iterations for SELF_CORRECTION; cycles for REACT). Exact mapping is operator-tunable per mode.
- The trace export endpoint is a read-only projection over persisted reasoning artifacts; it does not trigger reasoning or re-execution.
- Reasoning artifact retention is operator-configurable with a safe default (30 days for trace artifacts); traces beyond the retention window are garbage-collected and return "not available" on subsequent queries.
- Events (`reasoning.debate.round_completed`, `reasoning.react.cycle_completed`) use the existing event envelope infrastructure; they are additive topics/event types that do not conflict with existing reasoning events.
- Authorization for trace export reuses the existing execution-view RBAC (any caller authorized to view an execution is authorized to view its trace).
- Per-turn DEBATE timeouts and per-iteration SELF_CORRECTION timeouts default to values that match the existing reasoning timeout defaults; explicit overrides are permitted within policy caps.
- Workflow-scope compute_budget is configured on the workflow version (co-located with other per-workflow reasoning settings); step-scope is configured on the step definition.
- Nested reasoning modes (e.g., DEBATE whose participants each run SELF_CORRECTION internally) are explicitly Out of Scope for this release.
- The canonical trace schema is versioned: consumers read a `schema_version` field and can handle forward-compatible additions.

## Dependencies

- Existing reasoning engine with COT, TOT, REACT, and convergence-detection subsystems.
- Existing agent registry for FQN resolution and participant validation.
- Existing quality-evaluator subsystem for SELF_CORRECTION critique scoring.
- Existing workflow execution engine (step configuration + execution dispatch).
- Existing event bus and event envelope infrastructure (for new reasoning.* event types).
- Existing RBAC/permission system for trace export authorization.
- Existing object storage for persisting large reasoning artifacts (debate transcripts, REACT cycles).
- Existing reasoning-budget tracking (to be composed with, not replaced by, the new compute_budget).

## Out of Scope

- Nested reasoning modes (e.g., DEBATE whose each participant runs SELF_CORRECTION internally).
- New scoring or quality-evaluation models; SELF_CORRECTION reuses the existing quality evaluator.
- UI surfaces for authoring debate configurations, browsing traces, or visualizing debate rounds; this feature defines the data model and API that future UI features can consume.
- Streaming incremental trace deltas; the trace export is a snapshot of persisted artifacts, not a change feed (the real-time events in US5 cover streaming observation).
- Automatic mode selection changes for DEBATE or SELF_CORRECTION in the existing heuristic mode selector; explicit mode selection is required for the new modes in this release.
- Custom consensus-detection strategies for DEBATE beyond the built-in semantic convergence check; pluggable strategies are deferred.
- Cross-execution aggregated reasoning analytics (e.g., "how often does DEBATE reach consensus on this question class"); analytics pipelines are separate features.
- Adversarial/red-team DEBATE variants with malicious-participant detection; DEBATE assumes cooperative participants in this release.
- Trace export from external/federated reasoning providers; this feature covers platform-native reasoning only.
