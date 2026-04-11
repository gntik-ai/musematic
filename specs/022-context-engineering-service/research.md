# Research Notes: Context Engineering Service

**Feature**: 022-context-engineering-service  
**Date**: 2026-04-11  
**Phase**: 0 — Resolve unknowns before design

---

## Decision 1: Storage split — PostgreSQL (configuration + records) + ClickHouse (quality time-series)

**Decision**: Use PostgreSQL for all configuration entities (`ContextEngineeringProfile`, `ContextAbTest`, profile assignments) and assembly records (`ContextAssemblyRecord` with JSONB provenance chain). Use ClickHouse for quality score time-series (the `context_quality_scores` table), since drift detection requires rolling statistical analysis over days of data — exactly the OLAP workload ClickHouse excels at.

**Rationale**: PostgreSQL (constitution §III) is the ACID system-of-record for configuration. Quality score time-series is OLAP data (mean, stddev, windowed aggregations over 7 days) — the same pattern as analytics in feature 020. Storing thousands of per-assembly quality scores in PostgreSQL would create a table that is expensive to aggregate.

**Alternatives considered**: All in PostgreSQL — rejected because rolling mean/stddev over 7 days of per-assembly scores is a ClickHouse workload, not a PostgreSQL workload (constitution §III: "Never compute rollups in PostgreSQL"). Redis for quality scores — rejected because Redis is for hot state, not historical time-series.

---

## Decision 2: Deterministic assembly via sorted source fetching with deterministic seeds

**Decision**: Determinism is achieved by: (a) fetching sources in a fixed profile-defined order, (b) using a deterministic seed derived from `(execution_id, step_id)` for any pseudo-random operations (e.g., A/B test group assignment), (c) sorting long-term memory results by (score DESC, element_id ASC) to break ties identically, (d) storing the full assembled bundle in the `ContextAssemblyRecord` so repeat requests can serve from cache rather than re-assembling. The assembly record stores the full resolved context, not just the sources — this is the source of truth for determinism verification.

**Rationale**: Determinism requires eliminating all sources of non-determinism: random operations, floating-point tie-breaking, source ordering. Storing the resolved bundle in the assembly record achieves strict reproducibility. The spec requires "same inputs at same point in time → same output" (SC-002).

**Alternatives considered**: Pure in-memory re-assembly with deterministic ordering — fragile; tie-breaking in vector similarity scores is undefined without an explicit secondary sort. Hashing the inputs and returning cached result — correct but requires storage and cache invalidation; instead we just record the full output.

---

## Decision 3: Quality scorer — pure Python heuristics (no ML model)

**Decision**: The quality scorer is implemented as a pure Python `QualityScorer` class using rule-based heuristics. Relevance: cosine similarity between element embedding vectors and the task brief embedding (pre-computed at assembly time via Qdrant nearest-neighbor). Freshness: exponential decay from element timestamp to now. Authority: static weight table per source type (system instructions: 1.0, long-term memory: 0.7, conversation history: 0.8, tool outputs: 0.9, workflow state: 0.85, connector payloads: 0.6, workspace metadata: 0.5, reasoning traces: 0.75). Contradiction density: count of elements where the same key claim appears with contradictory values. Token efficiency: unique information units / total tokens. Task brief coverage: keyword overlap between task brief terms and element content. Aggregate: weighted average of sub-scores with configurable weights in `PlatformSettings`.

**Rationale**: No ML model avoids a training dependency and is consistent with constitution §VI (no ML libraries for internal tooling). Pure Python is auditable and testable. The heuristics are good enough for drift detection and relative comparison purposes.

**Alternatives considered**: Embedding-based quality model (fine-tuned on human labels) — requires training infrastructure; overkill for this use case. LLM-based quality scoring — introduces latency, cost, and non-determinism; violates SC-002.

---

## Decision 4: Budget enforcement and compaction execution order

**Decision**: Compaction strategies are applied in the order defined in the `ContextEngineeringProfile.compaction_strategies` list (default: `[relevance_truncation, priority_eviction, semantic_deduplication]`). Each strategy is applied until the bundle fits within budget or all strategies are exhausted. Hierarchical compression (summarization) is only in the strategy list if explicitly configured — it requires an LLM call and should be opt-in to avoid unexpected costs. The minimum viable context (system instructions + most recent conversation turn) is protected from all compaction strategies and is always retained even if it exceeds the budget.

**Rationale**: Strategy order matters. Relevance truncation first is the cheapest and most reversible. Semantic deduplication runs after to avoid deduplicating elements that will be truncated anyway. Hierarchical compression is opt-in because it requires an external LLM call. The minimum viable context protection implements FR-011.

**Alternatives considered**: Run all strategies simultaneously — creates dependency ordering issues. Fixed strategy order for all profiles — inflexible for different agent types (e.g., code agents may prefer different compaction than conversational agents).

---

## Decision 5: Privacy filter — policy service interface (read-only, in-process)

**Decision**: The privacy filter calls `policies_service.get_active_context_policies(workspace_id, agent_id)` in-process to retrieve the list of active context eligibility policies. Each policy specifies: a data classification level (public, internal, confidential, restricted), an allowed set of agent role types or specific agent FQNs, and an action (include or exclude). The filter evaluates each context element against the policy set, excluding any element whose data classification exceeds the agent's allowed classification level. Exclusions are logged as `ContextProvenanceEntry` records with `action: excluded` and the triggering policy ID.

**Rationale**: In-process service call (not HTTP) maintains the modular monolith pattern (constitution §I, §IV). The policies service is authoritative for all policy enforcement. Logging exclusions as provenance entries is consistent with the provenance model already established for inclusions.

**Alternatives considered**: Checking policies at context source fetch time — correct but couples the source adapters to policy logic; better to apply a single post-assembly filter. Caching policy decisions in Redis — appropriate for high-frequency checks, but the policy list per agent changes infrequently; a 60-second in-memory TTL cache in the service is sufficient.

---

## Decision 6: Drift monitor — APScheduler background task, ClickHouse statistical query

**Decision**: A drift monitor background task runs every 5 minutes via APScheduler (already in the tech stack). It queries ClickHouse: for each `agent_fqn`, compute `AVG(quality_score)` and `STDDEV(quality_score)` over `[now - 7 days, now - 1 day]` (historical window), then compare to `AVG(quality_score)` over `[now - 1 day, now]` (recent window). If `recent_avg < historical_avg - 2 * historical_stddev`, generate a `ContextDriftAlert`. Alerts are emitted as Kafka events on `context_engineering.events` and stored in PostgreSQL (for API retrieval). The analysis window (7 days default) and significance threshold (2 stddev default) are configurable in `PlatformSettings`.

**Rationale**: 5-minute polling meets the SC-006 requirement (alerts within 5 minutes). APScheduler is already in the stack (constitution §2.1). ClickHouse is the right store for the rolling statistical query. Storing alerts in PostgreSQL allows them to be queried via API without needing to re-derive them.

**Alternatives considered**: Kafka Streams for real-time drift detection — significantly more complex; 5-minute batch polling is sufficient for the alert SLA. Z-score anomaly detection on individual scores — too noisy; rolling window mean comparison is more robust.

---

## Decision 7: A/B test group assignment — deterministic hash of (test_id, execution_id)

**Decision**: Group assignment for an A/B test uses `hashlib.sha256(f"{test_id}:{execution_id}".encode()).hexdigest()[-8:]` converted to int mod 2 (0 = control, 1 = variant). This gives: deterministic assignment (same execution always gets same group, supporting reproducibility), good distribution (SHA-256 is uniformly distributed), and no external dependency (no Redis or database lookup for assignment). The assignment is stored in the `ContextAssemblyRecord` for auditability.

**Rationale**: Hash-based assignment is deterministic and achieves 50/50 split over large N (spec SC-007). No shared state required — each assembly can compute its group independently. Storing the group in the assembly record satisfies FR-019 tracking requirement.

**Alternatives considered**: Random assignment with Redis counter — achieves perfect 50/50 but requires a Redis write per assembly; adds latency and shared state. User/agent-level sticky assignment (always same group) — better for experience consistency but harder to analyze (confounding by agent behavior differences).

---

## Decision 8: Assembly record storage — PostgreSQL with JSONB provenance chain

**Decision**: `ContextAssemblyRecord` is stored in PostgreSQL as a table with fixed columns for indexed fields (execution_id, step_id, agent_fqn, workspace_id, quality_score_aggregate, token_count, created_at) and a JSONB column `provenance_chain` for the full per-element provenance. The raw assembled bundle (text content) is stored in MinIO (`context-assembly-records` bucket) with the key `{workspace_id}/{execution_id}/{step_id}/bundle.json` — only the metadata and provenance live in PostgreSQL.

**Rationale**: Full bundle text can be large (up to 8,192 tokens = ~32KB). Storing it in PostgreSQL as TEXT would bloat the table. JSONB for the provenance chain enables `->` path queries for debugging. MinIO for bundle content follows the same pattern as feature 009 (TaskPlanRecord). Indexed columns enable efficient drift monitor queries and assembly record API retrieval.

**Alternatives considered**: Full bundle in PostgreSQL TEXT — bloats table, slow scans for large deployments. JSONB for entire record — correct but JSONB is not indexed as efficiently as fixed columns for range queries on quality_score or created_at.

---

## Decision 9: Context source adapters — async adapter interface pattern

**Decision**: Each context source is implemented as an async adapter class implementing `ContextSourceAdapter` protocol: `async def fetch(execution_id, step_id, budget) → list[ContextElement]`. Adapters: `SystemInstructionsAdapter`, `WorkflowStateAdapter`, `ConversationHistoryAdapter`, `LongTermMemoryAdapter` (Qdrant), `ToolOutputsAdapter`, `ConnectorPayloadsAdapter`, `WorkspaceMetadataAdapter`, `ReasoningTracesAdapter`, `WorkspaceGoalHistoryAdapter` (super-context). The assembler receives adapters via dependency injection and calls them in the order specified by the profile. Adapters that fail raise `ContextSourceUnavailableError`, which the assembler catches to apply the partial-sources pattern.

**Rationale**: Adapter pattern decouples source implementation from assembly orchestration. Dependency injection makes each adapter independently testable with mocks. All adapters are async, consistent with the constitution. The adapter list is open for extension without changing the assembler.

**Alternatives considered**: Strategy pattern with single class — similar but less idiomatic for DI. Direct service calls in assembler — tightly couples assembler to each source; harder to test and maintain.

---

## Decision 10: New Kafka topic `context_engineering.events`

**Decision**: Register `context_engineering.events` as a new Kafka topic. Events emitted: `context_engineering.assembly.completed` (after every successful assembly — carries quality score, token count, agent_fqn, workspace_id for downstream analytics), `context_engineering.drift.detected` (when drift alert generated), `context_engineering.budget.exceeded_minimum` (when compaction cannot meet budget but serves minimum viable context). All events use canonical `EventEnvelope` from feature 013.

**Rationale**: Same pattern as `analytics.events` (020), `registry.events` (021). The assembly-completed event feeds the analytics pipeline. The constitution requires Kafka for async event coordination (§III).

**Alternatives considered**: Direct ClickHouse insert from assembler for quality scores — creates cross-boundary coupling; Kafka consumer (analytics bounded context) should own the ClickHouse insert. Writing drift alerts directly to PostgreSQL without Kafka event — misses the notification/subscription pathway.

---

## Decision 11: Internal interface — synchronous in-process function

**Decision**: `assemble_context(execution_id, step_id, profile, budget) → ContextBundle` is exposed as a synchronous (from the caller's perspective) async function via `ContextEngineeringService`. Called by the execution bounded context via in-process service interface injection. The function returns a `ContextBundle` dataclass containing the ordered list of `ContextElement` objects with provenance, plus the quality score, token count, and assembly record ID. No HTTP or gRPC — purely in-process per constitution §I (modular monolith, in-process service interfaces).

**Rationale**: In-process call avoids network overhead on the critical path (latency SLA: 500ms for 5 sources). Constitution §I requires in-process service interfaces for bounded context communication within the monolith.

**Alternatives considered**: gRPC service — appropriate only for Go satellites (constitution §II); Python context engineering is in the monolith. HTTP API — adds latency and serialization overhead; wrong for in-process communication.

---

## Decision 12: ClickHouse setup for quality score time-series

**Decision**: Create `context_quality_scores` ClickHouse table (MergeTree, partitioned by month) via idempotent `context_engineering_clickhouse_setup.py` at startup. Schema: `agent_fqn String`, `workspace_id UUID`, `assembly_id UUID`, `quality_score Float32`, `quality_subscores JSON`, `token_count UInt32`, `ab_test_id Nullable(UUID)`, `ab_test_group Nullable(String)`, `created_at DateTime`. Drift monitor queries use `quantile(0.5)` and `stddevPop()` ClickHouse aggregation functions. No materialized views needed — drift query runs on raw scores with WHERE clause on time window.

**Rationale**: Same idempotent startup script pattern as feature 020 (`clickhouse_setup.py`) and feature 021 (`registry_opensearch_setup.py`). MergeTree with month partition is standard for time-series. No MVs needed because drift monitor runs infrequently (every 5 minutes) and the query is simple enough to run directly on the raw table.

**Alternatives considered**: PostgreSQL for quality scores — rejected by constitution §III (no OLAP in PostgreSQL). ClickHouse AggregatingMergeTree MV — unnecessary for 5-minute polling; adds migration complexity.
