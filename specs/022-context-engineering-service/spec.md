# Feature Specification: Context Engineering Service

**Feature Branch**: `022-context-engineering-service`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement deterministic context assembly from multiple sources, quality scoring, provenance tracking, budget enforcement, compaction strategies, privacy filtering, context A/B testing, and drift monitoring."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Deterministic Context Assembly with Provenance (Priority: P1)

An agent execution begins a new step. The runtime requests a context bundle from the context engineering service, providing the execution ID, step ID, the agent's context engineering profile, and a budget envelope. The context assembler gathers context elements from multiple sources in a deterministic order: system instructions (including the agent's mandatory purpose and optional approach text from the registry), workflow state, short-term conversation history, long-term memory (retrieved via semantic similarity), tool outputs from prior steps, connector payloads, workspace metadata, and prior reasoning traces. If the agent is acting within a workspace goal, the assembler also pulls the full goal conversation history (workspace super-context) for that Goal ID. Each context element is tagged with provenance metadata — its origin source, timestamp, authority score, and any policy justification for inclusion. The assembled context bundle is deterministic: given the same inputs at the same point in time, the service produces the same output. The assembly record is persisted for auditability.

**Why this priority**: Without context assembly, agents have no input to reason over. This is the core function of the service — every agent execution depends on it. Provenance is included at P1 because it is foundational to trust and debugging.

**Independent Test**: Configure a context engineering profile that references system instructions, conversation history, and long-term memory sources. Trigger an assembly for a mock execution step. Verify the returned context bundle contains elements from all specified sources in the correct order. Verify each element has provenance metadata (origin, timestamp, authority). Trigger the same assembly again with identical inputs — verify the output is byte-for-byte identical (deterministic). Verify an assembly record is persisted. For a goal-oriented execution, verify the workspace goal history is included as a context source.

**Acceptance Scenarios**:

1. **Given** an agent with a context engineering profile specifying 3 context sources, **When** context assembly is requested for a step, **Then** the returned bundle contains elements from all 3 sources in the profile-defined order
2. **Given** the same execution state and profile, **When** assembly is requested twice, **Then** both bundles are identical (deterministic output)
3. **Given** an agent registered with purpose and approach fields, **When** context is assembled, **Then** the purpose is always included in the system prompt section and approach is included if present
4. **Given** an agent acting within workspace goal GID-123, **When** context is assembled, **Then** the workspace goal conversation history for GID-123 is included as a context source
5. **Given** a completed assembly, **When** the assembly record is queried, **Then** it contains the full provenance chain for every element (origin, timestamp, authority score, policy justification)

---

### User Story 2 — Quality Scoring and Budget Enforcement with Compaction (Priority: P1)

After assembling the raw context, the service computes a quality score for the bundle based on multiple dimensions: relevance to the current task brief, freshness of information, authority of sources, contradiction density (penalizing conflicting information), token efficiency (information density per token), and coverage of the task brief's key topics. The quality score is attached to the assembly record. Simultaneously, the budget enforcer checks the bundle against the budget envelope — which specifies maximum token count, maximum cost, and maximum source count at the step, execution, and agent levels. If the bundle exceeds any budget constraint, the compactor automatically applies strategies to bring it within limits: relevance-based truncation (drop least-relevant elements first), priority eviction (lower-priority sources removed first), hierarchical compression (summarize sections while preserving key information), and semantic deduplication (remove near-duplicate information). After compaction, quality is re-scored on the compacted bundle.

**Why this priority**: Quality scoring and budget enforcement are essential for every assembly — without them, agents receive unbounded, unscored context that wastes tokens and money. Compaction ensures the system degrades gracefully rather than failing when context is too large.

**Independent Test**: Assemble a context bundle that exceeds the token budget by 2x. Verify the quality score is computed before compaction. Verify the compactor reduces the bundle to within budget. Verify the quality score is re-computed after compaction. Verify the compacted bundle still contains the highest-priority elements. Verify the budget check passes on the final bundle. Try an assembly with a very small budget — verify compaction produces a usable (non-empty) bundle with the most critical context.

**Acceptance Scenarios**:

1. **Given** a freshly assembled context bundle, **When** quality scoring runs, **Then** a score is produced with sub-scores for relevance, freshness, authority, contradiction density, token efficiency, and task brief coverage
2. **Given** a bundle of 10,000 tokens and a budget of 5,000 tokens, **When** budget enforcement runs, **Then** the compactor reduces the bundle to ≤ 5,000 tokens
3. **Given** compaction is applied, **When** the compacted bundle is examined, **Then** the highest-priority and most-relevant elements are retained while lower-priority elements were evicted or summarized
4. **Given** a bundle with near-duplicate information from two sources, **When** semantic deduplication runs, **Then** only one copy is retained with provenance from both sources
5. **Given** a bundle within budget, **When** budget enforcement checks, **Then** no compaction is applied and the bundle passes through unchanged

---

### User Story 3 — Privacy Filtering (Priority: P1)

Before the context bundle is finalized, a privacy filter applies data minimization and eligibility controls based on the active policies for the workspace and agent. Context elements that contain data the agent is not authorized to see — based on data classification, workspace membership, or explicit exclusion rules — are stripped from the bundle. The filter logs what was removed and why (provenance for exclusion). Privacy filtering is mandatory and cannot be bypassed, even if the agent's profile requests a source that contains restricted data.

**Why this priority**: Privacy filtering is a security and compliance boundary. Delivering unauthorized data to an agent violates zero-trust principles (constitution §IX). It must ship with the initial context assembly to prevent any window where agents receive unrestricted context.

**Independent Test**: Configure two context sources: one with unrestricted data and one with data classified as "confidential." Configure the agent without access to confidential data. Assemble context — verify the confidential source is excluded. Verify the exclusion is logged with the reason "data classification: confidential, agent not authorized." Verify the remaining context passes quality scoring and budget checks normally.

**Acceptance Scenarios**:

1. **Given** a context source containing confidential data and an agent without confidential data access, **When** context is assembled, **Then** the confidential data is excluded from the bundle
2. **Given** privacy filtering removes elements, **When** the assembly record is examined, **Then** each exclusion is logged with the reason and the policy that triggered it
3. **Given** an agent with a profile requesting a restricted source, **When** context is assembled, **Then** the privacy filter overrides the profile and excludes the restricted data
4. **Given** all sources pass privacy checks, **When** filtering runs, **Then** no elements are removed and the bundle passes through unchanged

---

### User Story 4 — Context Drift Monitoring and Alerting (Priority: P2)

The context engineering service tracks quality score trends over time for each agent and workspace. Quality scores from every assembly are recorded in the analytics store. A drift monitor periodically analyzes these trends. When the rolling average quality score for an agent drops below a significance threshold (mean minus 2 standard deviations over the last 7 days), the system generates a drift alert. The alert includes the affected agent, the degradation metric, a comparison of recent vs. historical quality, and suggested investigation actions. Drift alerts are emitted as events so that operators and the notifications system can react.

**Why this priority**: Drift monitoring is important for ongoing quality assurance but not blocking for initial agent execution. Agents can operate without drift monitoring — it becomes critical once the platform is running at scale with many agents over time.

**Independent Test**: Seed quality scores for an agent over 7 days with a stable mean of 0.8. Submit a series of assemblies with quality scores at 0.5 (below mean - 2*stddev). Verify a drift alert is generated. Verify the alert identifies the correct agent, shows the degradation, and compares recent vs. historical quality. Verify the alert is emitted as an event.

**Acceptance Scenarios**:

1. **Given** an agent with 7 days of quality scores averaging 0.8 (stddev 0.05), **When** recent assemblies produce scores averaging 0.6, **Then** a drift alert is generated
2. **Given** quality scores remain within normal range, **When** the drift monitor runs, **Then** no alert is generated
3. **Given** a drift alert is generated, **When** the alert is examined, **Then** it includes the agent identifier, degradation metric, historical mean, recent mean, and suggested investigation actions
4. **Given** a drift alert, **When** it is emitted, **Then** it is published as an event that operators and notification systems can subscribe to

---

### User Story 5 — Context A/B Testing (Priority: P2)

A platform operator creates a context A/B test to compare two different context engineering profiles against the same tasks. The test defines a control profile (the current production configuration) and a variant profile (the experimental configuration). During the test period, incoming assembly requests for the specified agent or workspace are randomly assigned to control or variant groups. Both profiles produce context bundles for the same execution steps, and their quality scores, token usage, and downstream execution outcomes are tracked. At the end of the test, the operator reviews the comparison to decide whether to adopt the variant profile.

**Why this priority**: A/B testing is valuable for optimizing context quality but not required for basic operation. Agents work fine with a single profile — A/B testing is an optimization and experimentation capability.

**Independent Test**: Create an A/B test with a control profile (3 sources) and a variant profile (5 sources, with summarization compaction). Trigger 10 assembly requests for the test agent. Verify approximately half are assigned to control and half to variant. Verify both groups produce valid context bundles. Verify quality scores and token counts are tracked separately for each group. End the test — verify comparison results show the per-group metrics.

**Acceptance Scenarios**:

1. **Given** an A/B test with control and variant profiles, **When** assembly requests arrive, **Then** they are randomly assigned to control or variant with approximately equal distribution
2. **Given** an active A/B test, **When** assemblies complete, **Then** quality scores, token usage, and cost are tracked separately for each group
3. **Given** a completed A/B test, **When** the operator reviews results, **Then** a comparison shows per-group quality means, token usage, cost, and statistical significance
4. **Given** no active A/B test for an agent, **When** assembly is requested, **Then** the default profile is used without any test overhead

---

### User Story 6 — Context Engineering Profile Management (Priority: P3)

A platform administrator creates and manages context engineering profiles that define how context is assembled for specific agents, agent types, or workspaces. A profile specifies which context sources to include (and their priority order), budget constraints (token limits, cost limits, source count limits), compaction strategy preferences (which strategies to apply and in what order), and privacy filter overrides. Profiles can be assigned to individual agents, to agent role types, or to workspaces as defaults. Multiple profiles can exist per workspace, enabling operators to fine-tune context assembly for different agent types or use cases.

**Why this priority**: Profile management is the configuration layer on top of the working engine. Basic context assembly works with sensible defaults — explicit profile management enhances control but is not required for the core flow.

**Independent Test**: Create a profile specifying 4 context sources with explicit priority order, a 4,000-token budget, and relevance-truncation as the primary compaction strategy. Assign the profile to an agent. Trigger assembly for that agent — verify the profile's configuration is applied (correct sources, budget enforced, compaction strategy used). Create a workspace-level default profile — verify it applies to agents without an explicit profile assignment.

**Acceptance Scenarios**:

1. **Given** a context engineering profile, **When** it is assigned to an agent, **Then** all subsequent assemblies for that agent use the profile's source list, budget, and compaction preferences
2. **Given** a workspace-level default profile, **When** an agent without an explicit profile requests assembly, **Then** the workspace default is used
3. **Given** an agent with an explicit profile and a workspace default, **When** assembly is requested, **Then** the agent-specific profile takes precedence
4. **Given** a profile update, **When** the next assembly is requested, **Then** the updated profile is applied immediately

---

### Edge Cases

- What happens when a context source is temporarily unavailable during assembly? The assembler skips the unavailable source, logs a warning with the source identifier, includes what is available, and marks the assembly record with a "partial_sources" flag. Assembly succeeds with reduced context rather than failing entirely.
- What happens when budget constraints are so tight that compaction would produce an empty bundle? The compactor retains at least the system instructions (including purpose and approach) and the most recent conversation turn, even if they exceed the budget. The assembly record is flagged as "budget_exceeded_minimum" and an event is emitted.
- What happens when quality score drops to zero? A zero score indicates no relevant context was found. The assembly succeeds (agents may still operate with minimal context), but a warning event is emitted and the assembly record is flagged.
- What happens when a context A/B test is active but the test agent is also involved in a workspace goal? Both control and variant assemblies include the workspace super-context — the A/B test varies only the profile-controlled sources, not the mandatory super-context.
- What happens when a privacy filter excludes all elements from a source? The source appears in the provenance chain as "fully excluded by privacy filter [policy reference]." The assembly continues with remaining sources.
- What happens when the same information appears in multiple sources (e.g., both conversation history and long-term memory)? Semantic deduplication during compaction removes the lower-authority duplicate while preserving provenance from both sources in the retained element.
- What happens when an assembly request arrives with no profile assigned to the agent or workspace? The service uses a built-in default profile with sensible settings (all standard sources enabled, generous token budget, standard compaction strategy). The assembly proceeds normally.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST assemble context from multiple sources in a deterministic order defined by the context engineering profile
- **FR-002**: The system MUST support the following context sources: system instructions, workflow state, short-term conversation history, long-term memory (vector retrieval), tool outputs, connector payloads, workspace metadata, and prior reasoning traces
- **FR-003**: The system MUST include the agent's purpose field (mandatory) and approach field (if present) in the system instructions section of every assembled context
- **FR-004**: The system MUST include workspace goal conversation history (super-context) when assembling context for an agent acting within a workspace goal
- **FR-005**: The system MUST attach provenance metadata to every context element: origin source, timestamp, authority score, and policy justification for inclusion
- **FR-006**: The system MUST persist an assembly record for every context assembly, containing the full provenance chain, quality score, budget usage, and any compaction actions taken
- **FR-007**: The system MUST compute a quality score for every assembled context bundle, evaluating: relevance, freshness, authority, contradiction density, token efficiency, and task brief coverage
- **FR-008**: The system MUST enforce budget constraints (maximum token count, maximum cost, maximum source count) at step, execution, and agent levels
- **FR-009**: The system MUST automatically compact context bundles that exceed budget constraints using configurable strategies: relevance truncation, priority eviction, hierarchical compression, and semantic deduplication
- **FR-010**: The system MUST re-score quality after compaction and include both pre- and post-compaction scores in the assembly record
- **FR-011**: The system MUST retain at least the system instructions and most recent conversation turn even when compaction cannot meet the budget (minimum viable context)
- **FR-012**: The system MUST apply privacy filters to exclude context elements that the agent is not authorized to access based on data classification, workspace membership, or explicit exclusion policies
- **FR-013**: The system MUST log every privacy filter exclusion with the reason and triggering policy in the assembly record
- **FR-014**: Privacy filtering MUST be mandatory and non-bypassable — no configuration or profile can disable it
- **FR-015**: The system MUST track quality score trends over time per agent and per workspace in the analytics store
- **FR-016**: The system MUST detect quality drift when the rolling average quality score drops below the significance threshold (mean minus 2 standard deviations over the analysis window) and generate a drift alert
- **FR-017**: Drift alerts MUST include the affected agent, degradation metric, historical comparison, and suggested investigation actions, and MUST be emitted as events
- **FR-018**: The system MUST support context A/B tests comparing two context engineering profiles for the same agent or workspace
- **FR-019**: During an active A/B test, assembly requests MUST be randomly assigned to control or variant groups with approximately equal distribution
- **FR-020**: The system MUST track quality scores, token usage, and cost separately for each A/B test group and provide a comparison interface
- **FR-021**: The system MUST support context engineering profile CRUD — creating, reading, updating, and deleting profiles with source lists, budget constraints, compaction strategy preferences, and privacy overrides
- **FR-022**: The system MUST support profile assignment at agent level, agent role type level, and workspace level, with agent-specific profiles taking precedence over workspace defaults
- **FR-023**: Profile updates MUST take effect immediately on the next assembly request
- **FR-024**: The system MUST provide a built-in default profile used when no profile is explicitly assigned
- **FR-025**: The system MUST handle unavailable context sources gracefully — skipping them, logging a warning, and marking the assembly record with a partial-sources flag

### Key Entities

- **ContextAssemblyRecord**: A persistent record of a single context assembly operation. Contains the execution ID, step ID, profile used, sources queried, elements included/excluded, quality scores (pre- and post-compaction), budget usage, compaction actions taken, and the full provenance chain. Used for auditability and drift analysis.
- **ContextQualityScore**: A multi-dimensional quality assessment of a context bundle. Contains sub-scores for relevance, freshness, authority, contradiction density, token efficiency, and task brief coverage, plus an aggregate score. Computed before and after compaction.
- **ContextProvenanceEntry**: Metadata attached to each context element. Records the origin source type, source identifier, timestamp of the information, authority score (how trustworthy the source is), and the policy justification for including (or excluding) the element.
- **ContextBudgetEnvelope**: Budget constraints for a context assembly. Specifies maximum token count, maximum cost, and maximum source count at step, execution, and agent levels. Determines when compaction is triggered.
- **ContextCompactionStrategy**: A named compaction approach with configuration. Types include relevance truncation (drop least-relevant), priority eviction (drop lowest-priority source), hierarchical compression (summarize), and semantic deduplication (merge near-duplicates). Strategies are ordered in a profile.
- **ContextEngineeringProfile**: Configuration defining how context is assembled for an agent or workspace. Specifies which sources to include and their priority order, budget constraints, compaction strategy sequence, and privacy filter configuration. Assignable to agents, role types, or workspaces.
- **ContextAbTest**: A comparison experiment between two context engineering profiles. Defines control profile, variant profile, test duration, target agent or workspace, and tracks per-group metrics (quality, tokens, cost).
- **ContextDriftAlert**: A notification generated when quality trends degrade beyond the significance threshold. Contains the affected agent or workspace, degradation metrics, historical vs. recent comparison, and suggested actions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Context assembly completes within 500 milliseconds for bundles with up to 5 context sources and within 2 seconds for bundles with all 8 source types
- **SC-002**: Given identical inputs at the same point in time, context assembly produces identical output 100% of the time (strict determinism)
- **SC-003**: Quality scores are computed for 100% of context assemblies — zero unscored assemblies
- **SC-004**: Budget enforcement reduces over-budget bundles to within limits in 100% of cases while preserving the minimum viable context (system instructions + most recent turn)
- **SC-005**: Privacy filtering is applied to 100% of assemblies — zero assemblies bypass filtering
- **SC-006**: Drift alerts are generated within 5 minutes of the quality degradation threshold being crossed
- **SC-007**: Context A/B test group assignment achieves a 50/50 split within a 5% margin over 100 or more assemblies
- **SC-008**: The system supports at least 1,000 context assemblies per minute under concurrent load without degradation
- **SC-009**: Every context element is traceable to its provenance — zero elements without origin, timestamp, and authority metadata
- **SC-010**: Test coverage of the context engineering service is at least 95%

## Assumptions

- The vector memory service (Qdrant, feature 005) is operational for long-term memory retrieval. Embeddings for semantic retrieval are generated and stored by the memory bounded context.
- The analytics store (ClickHouse, feature 007) is operational for quality score time-series storage and drift analysis.
- The agent registry service (feature 021) is operational for retrieving agent purpose and approach fields.
- The workspaces service (feature 018) provides workspace goal conversation history via in-process service interface.
- Workflow state and conversation history are available via the execution bounded context's service interface.
- Privacy policies are managed by the policies bounded context and available via in-process service interface. The specific policy model used to determine data classification and access is resolved through the policies service.
- The Kafka event topic for context engineering events is `context_engineering.events` (using the canonical EventEnvelope from feature 013).
- Budget constraints (token counts, costs) are denominated in the same units used by the reasoning engine and analytics service for consistency.
- The default context engineering profile uses sensible defaults: all standard sources enabled, token budget of 8,192 tokens, standard compaction strategy (relevance truncation → priority eviction → semantic deduplication), and no privacy overrides.
- Context assembly latency targets (SC-001) exclude external service call time (e.g., Qdrant vector retrieval, which has its own SLA). The 500ms/2s targets measure the assembly, scoring, filtering, and compaction logic only.
- The drift monitor analysis window defaults to 7 days and the significance threshold defaults to mean minus 2 standard deviations. Both are configurable per workspace.
