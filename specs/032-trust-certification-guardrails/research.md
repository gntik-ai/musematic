# Research: Trust, Certification, and Guardrails

**Feature**: 032-trust-certification-guardrails  
**Date**: 2026-04-12

This document records all design decisions made during Phase 0 research, resolving all unknowns before implementation planning.

---

## Decision 1: Single `trust/` bounded context (no separate `guardrails/`)

**Decision**: All trust and guardrail functionality lives in the existing `trust/` bounded context (`apps/control-plane/src/platform/trust/`). Guardrails are not split into a separate bounded context.

**Rationale**: The constitution's repository structure already designates `trust/` for "Certification, evidence, trust tiers, proof chain". Guardrail outcomes feed directly into certification evidence and trust signals — separating them would require cross-boundary service calls or Kafka events for fundamentally synchronous in-process enforcement. The guardrail pipeline is invoked synchronously in the API path before agent execution proceeds.

**Alternatives considered**: Separate `guardrails/` bounded context — rejected because it would fragment the trust domain model and require synchronous cross-boundary calls that bypass §IV.

---

## Decision 2: Pre-screener as in-process rule-based classifier (no external model)

**Decision**: `SafetyPreScreenerService` uses compiled regex patterns + keyword sets loaded in-process. Versioned rule definitions are stored as JSON in MinIO (full content) with metadata in PostgreSQL. Active rules are hot-loaded into each process's in-memory compiled pattern cache when `prescreener.rule_set.activated` Kafka event fires.

**Rationale**: SC-004 requires <10ms per input, which rules out any external API call or subprocess. A compiled Python regex engine is sub-millisecond in-process. Rules are human-readable, auditable, and version-controlled. The spec explicitly offers "rule-based system" as a valid choice.

**Alternatives considered**: Local quantized ONNX model — rejected for latency unpredictability and Docker image size increase; external safety API (Anthropic/OpenAI moderation) — violates <10ms requirement.

---

## Decision 3: Circuit breaker counters in Redis with Lua script (not PostgreSQL)

**Decision**: Circuit breaker uses a Redis sorted set per agent (`trust:cb:{agent_id}`) where each guardrail block is recorded as a ZADD entry (score = Unix timestamp). A Lua script atomically: (1) removes entries older than `time_window_seconds`, (2) adds the new entry, (3) counts remaining entries, (4) returns count. If count exceeds threshold, a circuit breaker state flag is set in Redis with a configurable TTL, and a `circuit_breaker.activated` Kafka event fires. The BlockedActionRecord is written to PostgreSQL synchronously for audit purposes.

**Rationale**: Circuit breaker must evaluate within microseconds per §III (Redis for all hot state). PostgreSQL transactions add 5–10ms per check — unacceptable on a blocking path. Lua script provides atomic check-and-update without race conditions.

**Alternatives considered**: PostgreSQL counter — rejected for latency; in-process counter — rejected per §III (Redis for shared hot state, not application memory).

---

## Decision 4: Observer-Judge-Enforcer agents are regular platform agents (identified by FQN)

**Decision**: Observer, judge, and enforcer are regular platform agents registered in the agent registry (feature 021), identified by their FQN (per §VIII). The `OJEPipelineConfig` stores arrays of FQNs for each role. The OJE pipeline invokes them via the interactions system (feature 024) with a `trust_pipeline_context` flag, which causes responses to be interpreted as structured judge verdicts (JSON). Enforcer actions are executed by `OJEPipelineService` based on the verdict type.

**Rationale**: Reuses the existing agent framework and interaction system rather than defining a new invocation mechanism. FQN addressing is mandatory per §VIII. Calling agents via the interaction system creates a natural audit trail.

**Alternatives considered**: Direct Python function call to a dedicated OJE service — rejected because it would tie enforcement to the platform runtime rather than making it configurable with any registered agent.

---

## Decision 5: ATE execution delegates to SimulationControlService gRPC (feature 012)

**Decision**: `ATEService` calls `SimulationControlService.CreateSimulation` (gRPC port 50055) to create an ATE pod in the `platform-simulation` namespace. The ATE configuration (test scenarios, golden dataset refs, scoring config) is passed as the simulation payload. ATE results arrive via the `simulation.events` Kafka topic (`event_type: simulation.completed`). Results are stored as `CertificationEvidenceRef` entries and large payloads written to MinIO (`trust-evidence` bucket).

**Rationale**: The Simulation Controller already provides namespace isolation per §VII and is the designated satellite for simulation workloads. Reusing it avoids duplicating Kubernetes pod lifecycle management in the control plane.

**Alternatives considered**: Direct Kubernetes pod creation from control plane — rejected per §VII (simulation isolation) and §I (Go satellites handle pod lifecycle); new ATE satellite service — rejected as overkill given the Simulation Controller already exists.

---

## Decision 6: Trust score computation is event-driven (Kafka consumer in `worker` profile)

**Decision**: Trust score recomputation is triggered by Kafka events on `trust.events` (certification state changes, guardrail blocks, behavioral signals). The `TrustTierService` in the `worker` profile consumes these events and recomputes the weighted trust score using: certification_status (weight 0.50) + guardrail_pass_rate (weight 0.35) + behavioral_conformance (weight 0.15). Computed score and tier are written to `trust_tiers` table in PostgreSQL.

**Rationale**: SC-007 requires updates within 30 seconds of signal change — event-driven consumption is well within this window. Synchronous recomputation on every read would add latency to all marketplace queries.

**Alternatives considered**: ClickHouse rollup — rejected because this is structured relational aggregation (3 signals), not time-series OLAP; synchronous on-read computation — rejected for marketplace query latency.

---

## Decision 7: Recertification triggers via Kafka consumers + APScheduler (expiry)

**Decision**: 
- Consume `registry.events` (event_type `agent_revision.published`) in the `worker` profile → create `RecertificationTrigger` with type `revision_changed`
- Consume `policy.events` (event_type `policy.updated`) in the `worker` profile → create trigger with type `policy_changed`
- APScheduler daily job in `trust-certifier` profile scans certifications with `expires_at < now() + threshold` → create trigger with type `expiry_approaching`
- Guardrail pipeline failure path → create trigger with type `conformance_failed` synchronously
- Deduplication: PostgreSQL unique constraint on `(agent_id, agent_revision_id, trigger_type, processed=false)` with `ON CONFLICT DO NOTHING`

**Rationale**: Kafka events are the authoritative source for revision/policy changes per §III. APScheduler for expiry scanning is the established platform pattern (feature 013 scaffold).

**Alternatives considered**: Database polling for revision changes — rejected per §III (Kafka for all async event coordination).

---

## Decision 8: Guardrail pipeline is synchronous in-process (all 6 layers)

**Decision**: `GuardrailPipelineService` executes all 6 layers as synchronous in-process async functions. Policy checks (tool control, memory write validation) call `PolicyGovernanceEngine` from feature 028 via internal Python service interface. Output sanitization delegates to the existing `OutputSanitizer` from feature 028. No external calls except possibly output moderation (see Decision 9).

**Rationale**: The guardrail pipeline is blocking — the request cannot proceed until all layers clear. In-process async function calls minimize latency and are the correct inter-context pattern per §IV. SC-003 (500ms total) is achievable in-process.

**Alternatives considered**: Asynchronous guardrail (non-blocking) — rejected because guardrails must block dangerous requests before they execute; separate guardrail microservice — rejected per §I (modular monolith).

---

## Decision 9: Output moderation uses a configurable provider (default: regex + keyword, optional LLM call)

**Decision**: Output moderation layer uses a two-stage approach: (1) fast regex/keyword check (pre-screener style, in-process), (2) optional LLM-based moderation call via `httpx` if configured. The LLM moderation call uses the same provider as the agent's model (injected via config) but is a separate call with a lightweight moderation prompt. If the moderation provider is not configured, only stage 1 runs.

**Rationale**: Regex/keyword moderation covers obvious unsafe content quickly. LLM-based moderation handles nuanced cases. Making the LLM stage optional avoids making the platform dependent on a specific moderation service.

**Alternatives considered**: Always-LLM moderation — adds 50-200ms latency on every output, exceeding SC-003; no output moderation — violates the spec requirement.

---

## Decision 10: Privacy impact assessment delegates to PolicyGovernanceEngine (feature 028)

**Decision**: `PrivacyAssessmentService` calls `PolicyGovernanceEngine.check_privacy_compliance(context_assembly)` via in-process service interface. No separate privacy policy storage in `trust/` — all privacy policies live in the `policies/` bounded context (feature 028).

**Rationale**: Avoids duplicating policy storage and evaluation logic. Privacy policies are a subtype of policy, fitting naturally in the governance engine. In-process interface per §IV.

**Alternatives considered**: Separate privacy policy tables in `trust/` — rejected as it would create policy fragmentation across two bounded contexts.

---

## Decision 11: Blocked action records written synchronously; Kafka event fires post-commit

**Decision**: `BlockedActionRecord` is written to PostgreSQL synchronously within the guardrail pipeline execution (same async call). After the database transaction commits, a `guardrail.blocked` event is published to `trust.events` for downstream consumers (trust score updates, notifications). Input context is stored as a SHA-256 hash + first 500 chars preview (never full payload, to avoid storing potentially sensitive content at rest).

**Rationale**: Audit durability before block response (SC-005 within 1 second). The 500-char preview preserves investigability without full sensitive content storage. Kafka fire-and-forget is acceptable for downstream updates (trust score, notifications) — they tolerate eventual consistency.

**Alternatives considered**: Async write only — rejected because audit must be durable before the response is returned.

---

## Decision 12: Proof chain as PostgreSQL linked structure (no Neo4j)

**Decision**: `trust_proof_links` table stores `(trust_signal_id, proof_type, proof_reference_type, proof_reference_id)`. Signal provenance is navigable via indexed foreign key joins. Neo4j is not used for this feature.

**Rationale**: The trust proof chain is a simple DAG (signal → one or more source events). It does not require arbitrary graph traversal queries — PostgreSQL with indexed FK joins handles all needed lookups efficiently. Neo4j would be disproportionate for this use case.

**Alternatives considered**: Neo4j provenance graph — rejected because the proof chain topology is shallow (2 levels max) and doesn't benefit from graph traversal algorithms.

---

## Decision 13: Alembic migration 032 creates all 12 tables

**Decision**: Single migration file `032_trust_certifications.py` creates all 12 tables in one migration to avoid partial state issues. Tables are created in dependency order: certifications → evidence_refs → tiers → signals → proof_links → recertification_triggers → blocked_action_records → ate_configurations → guardrail_pipeline_configs → oje_pipeline_configs → circuit_breaker_configs → prescreener_rule_sets.

**Rationale**: All tables are logically within the same bounded context and have no cross-context dependencies in their schema (only `agent_id` foreign keys referencing `agent_id` UUID, not the registry table itself).

---

## Decision 14: Kafka topics and new event types

**Decision**:
- **Produce** on `trust.events` (existing topic in Kafka registry)
- **Consume** from: `registry.events` (revision.published), `policy.events` (policy.updated), `workflow.runtime` (execution failures for circuit breaker), `simulation.events` (simulation.completed for ATE results)
- **New event types on `trust.events`**: `certification.created`, `certification.activated`, `certification.revoked`, `certification.expired`, `certification.superseded`, `trust_tier.updated`, `guardrail.blocked`, `circuit_breaker.activated`, `recertification.triggered`, `prescreener.rule_set.activated`

---

## Decision 15: Runtime profiles

- `api` profile: handles all synchronous guardrail pipeline requests and certification REST API
- `worker` profile: Kafka consumers for recertification triggers, trust score recomputation, ATE result processing
- `trust-certifier` profile: APScheduler jobs for expiry scanning, pre-screener rule hot-reloading
