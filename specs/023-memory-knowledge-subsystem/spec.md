# Feature Specification: Memory and Knowledge Subsystem

**Feature Branch**: `023-memory-knowledge-subsystem`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement scoped vector memory, hybrid retrieval coordinator, trajectory capture, pattern store, knowledge graph operations, memory write gate with contradiction detection, and consolidation workers."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Scoped Memory Storage and Retrieval (Priority: P1)

An agent executing a task needs to store new knowledge (a fact, insight, or observation) as a memory entry. The agent writes a memory through the memory write gate, which verifies the agent is authorized to write to the target scope, checks that the write does not violate rate limits, and enforces namespace restrictions (agents can only write to namespaces they own or have been granted access to). The memory is embedded as a vector and stored with metadata (workspace ID, agent FQN, scope, timestamp, source authority, content hash). Scopes control visibility: a per-agent memory is visible only to the writing agent, a per-workspace memory is visible to all agents in the workspace, and a shared-orchestrator memory is visible to all orchestrator-role agents across the workspace. When the same agent (or another authorized agent) later needs relevant context, it queries the memory store with a natural-language query. The system retrieves the most relevant memories by combining vector similarity, recency weighting, and source authority scoring.

**Why this priority**: Without memory storage and retrieval, agents have no persistent knowledge across executions. This is the absolute foundation — every other memory feature builds on the ability to write and read scoped memory entries.

**Independent Test**: As agent "ns-a:agent-1", write a memory entry "Customer ACME Corp prefers invoice terms NET-30" to per-agent scope. Query with "What are ACME's payment preferences?" — verify the memory is returned with high relevance. As agent "ns-a:agent-2", query the same — verify no results (per-agent scope isolates). Write a workspace-scoped memory. Query as a different agent in the same workspace — verify the memory is returned. Write a memory exceeding the rate limit — verify the write is rejected.

**Acceptance Scenarios**:

1. **Given** an authorized agent, **When** it writes a memory to per-agent scope, **Then** the memory is stored with the correct workspace ID, agent FQN, scope, and timestamp
2. **Given** a stored per-agent memory, **When** the owning agent queries with a semantically similar query, **Then** the memory is returned ranked by relevance
3. **Given** a per-agent memory, **When** a different agent queries, **Then** the memory is not returned (scope isolation)
4. **Given** a workspace-scoped memory, **When** any agent in the same workspace queries, **Then** the memory is returned
5. **Given** an agent that has exceeded the write rate limit, **When** it attempts to write another memory, **Then** the write is rejected with a rate limit error
6. **Given** an agent attempting to write to a namespace it does not own, **When** the write is submitted, **Then** the write gate rejects it with an authorization error

---

### User Story 2 — Hybrid Retrieval with Rank Fusion (Priority: P1)

A platform component (such as the context engineering service) needs to retrieve the most relevant knowledge for an agent's current task. The retrieval coordinator queries three sources: vector memory (semantic similarity), keyword index (exact term matching), and the knowledge graph (structured relationships and facts). Each source returns ranked results independently. The coordinator merges results using reciprocal rank fusion — a method that combines rankings from multiple sources without requiring comparable scores. The merged results are further adjusted by recency scoring (more recent memories rank higher), source authority weighting (higher-authority sources rank higher), and contradiction detection (conflicting memories are flagged). The final ranked list is returned to the caller.

**Why this priority**: Hybrid retrieval is the primary read path for the context engineering service (feature 022). Without it, agents can only do simple vector search — missing keyword matches and graph relationships that are critical for accurate context assembly.

**Independent Test**: Store 3 memories: one about "ACME Corp NET-30 terms" (keyword match for "ACME"), one about "preferred payment methods" (semantically similar), one graph node linking "ACME" to "NET-30" via "has_terms" relationship. Query "ACME payment terms" — verify all 3 sources contribute results. Verify the fused ranking places the most relevant result first. Verify a contradiction flag appears if two memories state conflicting terms for the same entity.

**Acceptance Scenarios**:

1. **Given** relevant memories in vector, keyword, and graph stores, **When** a retrieval query is issued, **Then** results from all three sources are combined using reciprocal rank fusion
2. **Given** two memories with the same relevance but different timestamps, **When** retrieval runs, **Then** the more recent memory ranks higher (recency bias)
3. **Given** two memories from sources of different authority, **When** retrieval runs, **Then** the higher-authority source's memory ranks higher
4. **Given** two memories with conflicting claims about the same entity, **When** retrieval runs, **Then** both are returned with a contradiction flag indicating the conflict
5. **Given** results from only 2 of 3 sources (one source unavailable), **When** retrieval runs, **Then** results from available sources are fused and a partial-sources warning is attached

---

### User Story 3 — Memory Write Gate with Contradiction Detection (Priority: P1)

Before any memory is written, the memory write gate performs a series of checks to ensure data quality and security. Authorization: the agent must be permitted to write to the target scope and namespace. Rate limiting: the agent's write rate must not exceed configured limits (per minute and per hour). Contradiction check: the system compares the incoming memory against existing memories for the same entity/topic — if a direct contradiction is found, the write is flagged as an evidence conflict and the caller is notified. The conflicting memories are preserved (not overwritten) with conflict metadata attached. Retention enforcement: the write gate checks that the memory's retention policy (permanent, time-limited, session-only) is valid for the target scope. Differential privacy: if configured for the workspace, the write gate applies noise injection to numerical data before storage.

**Why this priority**: The write gate is a security and data quality boundary. Without it, agents could pollute each other's memory, flood the store with unlimited writes, or introduce contradictions silently. This must ship alongside storage (US1) to prevent any window of unguarded writes.

**Independent Test**: Write a memory "ACME terms are NET-30." Then write "ACME terms are NET-60." — verify the second write triggers a contradiction flag with a reference to the first memory. Verify both memories are stored (no overwrite). Attempt a write from an unauthorized agent — verify rejection. Write 100 memories in 1 second — verify rate limit triggered after the configured threshold. Write a memory with retention "permanent" to a session-only scope — verify rejection.

**Acceptance Scenarios**:

1. **Given** a new memory that contradicts an existing memory on the same topic, **When** the write gate processes it, **Then** both memories are preserved, an evidence conflict record is created linking them, and the caller is notified of the contradiction
2. **Given** an agent exceeding the write rate limit, **When** it submits a write, **Then** the write is rejected and the remaining cooldown period is communicated
3. **Given** a memory with retention "permanent" targeting a session-only scope, **When** the write gate validates, **Then** the write is rejected with a retention policy mismatch error
4. **Given** a workspace with differential privacy enabled, **When** a memory containing numerical data is written, **Then** calibrated noise is applied before storage
5. **Given** an authorized agent writing to a valid scope and namespace within rate limits, **When** no contradictions exist, **Then** the memory is stored successfully

---

### User Story 4 — Knowledge Graph Operations (Priority: P2)

The memory subsystem manages a knowledge graph representing structured relationships between entities — agents, tools, concepts, facts, and provenance chains. Platform components can create nodes (representing entities with typed attributes), create relationships between nodes (with relationship types and metadata), traverse the graph with multi-hop queries (e.g., "find all agents that have used tool X on data type Y within the last 30 days"), and query provenance chains (tracing the origin and transformation of a piece of knowledge through multiple agents). Graph operations respect workspace scoping — queries only see nodes and edges belonging to the querying workspace. The knowledge graph is a write path companion to vector memory: structured facts go to the graph, unstructured knowledge goes to vector memory.

**Why this priority**: The knowledge graph enriches retrieval with structured relationships but is not strictly required for basic memory operations. Vector memory (US1) and hybrid retrieval (US2) can function without the graph source — graph results are additive. Graph operations become critical once provenance chains and dependency analysis are needed.

**Acceptance Scenarios**:

1. **Given** an entity "ACME Corp" with attributes, **When** a node is created, **Then** the node is stored with its type, attributes, and workspace scope
2. **Given** two nodes "ACME Corp" and "NET-30", **When** a relationship "has_terms" is created, **Then** the edge is stored with metadata and is traversable
3. **Given** a multi-hop query "find all agents connected to tool X through execution nodes", **When** the query is executed, **Then** all matching paths are returned up to the configured depth limit
4. **Given** a provenance chain (agent A created fact → agent B refined it → agent C validated it), **When** provenance is queried, **Then** the full chain is returned with timestamps and actor identities
5. **Given** a cross-workspace graph query attempt, **When** executed, **Then** only nodes and edges belonging to the querying workspace are visible

**Independent Test**: Create nodes "Agent-A", "Tool-DocExtractor", "Fact-ACME-NET30" and edges "Agent-A --used--> Tool-DocExtractor" and "Tool-DocExtractor --produced--> Fact-ACME-NET30". Query "what did Agent-A produce?" with 2-hop traversal — verify "Fact-ACME-NET30" returned. Query provenance of "Fact-ACME-NET30" — verify full creation chain shown. Query from a different workspace — verify zero results.

---

### User Story 5 — Trajectory Capture and Pattern Promotion (Priority: P2)

After an agent completes an execution, the system captures the full trajectory — the ordered sequence of actions the agent took, including inputs, outputs, tool invocations, intermediate reasoning snapshots, and final verdicts. Trajectories are stored as immutable records for later analysis. When a trajectory is identified as exemplary (e.g., by an evaluator or operator), it can be promoted to a pattern — a reusable template that other agents can reference. Pattern promotion follows an approval workflow: a candidate pattern is nominated from a trajectory, reviewed by an authorized user or evaluation system, and either approved (becoming a published pattern) or rejected. Published patterns are discoverable via the retrieval coordinator and can inform future agent context assembly.

**Why this priority**: Trajectory capture enables post-hoc analysis and learning. Pattern promotion enables knowledge transfer between agents. Both are valuable for improving agent quality over time but are not blocking for basic agent execution — agents can operate without capturing trajectories or referencing patterns.

**Independent Test**: Execute an agent task (mocked). Verify a trajectory record is created with the full action sequence, I/O, and timestamps. Nominate the trajectory as a pattern candidate — verify the candidate is created in "pending" status. Approve the candidate — verify it transitions to "published" and becomes discoverable via retrieval. Reject a different candidate — verify it transitions to "rejected" and is not discoverable.

**Acceptance Scenarios**:

1. **Given** a completed agent execution, **When** trajectory capture runs, **Then** an immutable trajectory record is created with ordered actions, inputs, outputs, tool invocations, reasoning snapshots, and verdicts
2. **Given** an exemplary trajectory, **When** an operator nominates it as a pattern, **Then** a pattern candidate is created in "pending" approval status
3. **Given** a pending pattern candidate, **When** an authorized reviewer approves it, **Then** the pattern transitions to "published" and becomes discoverable via retrieval
4. **Given** a pending pattern candidate, **When** a reviewer rejects it, **Then** the pattern transitions to "rejected" with a reason, and it is not discoverable
5. **Given** a published pattern, **When** the retrieval coordinator queries for relevant knowledge, **Then** the pattern appears in results with its trajectory provenance

---

### User Story 6 — Cross-Scope Memory Transfer and Consolidation (Priority: P3)

An orchestrator agent or platform operator wants to transfer specific memories from one scope to another — for example, promoting a valuable per-agent memory to workspace scope so all agents benefit. Cross-scope transfers go through the write gate (with additional authorization checks) and preserve the original memory's provenance. Separately, a background consolidation process periodically reviews stored memories to distill recurring patterns, merge near-duplicates, and promote validated knowledge from agent-level to workspace-level scope. Consolidation follows a pipeline: retrieve candidate memories → judge relevance and consistency → distill into consolidated entries → promote scope if appropriate. Consolidation is a background operation that does not block real-time memory operations.

**Why this priority**: Cross-scope transfer and consolidation are optimization features. The system works without them — agents accumulate knowledge in their own scopes and workspace-level knowledge is set manually. These features automate knowledge management for long-running, many-agent deployments.

**Independent Test**: Create 3 agent-scoped memories with similar content across different agents in the same workspace. Run the consolidation worker. Verify a single consolidated workspace-scoped memory is created that distills the common knowledge. Verify the original agent-scoped memories have provenance references to the consolidated entry. Manually transfer a per-agent memory to workspace scope — verify authorization check runs, provenance preserved, and the memory is now visible to all workspace agents.

**Acceptance Scenarios**:

1. **Given** a per-agent memory that an orchestrator wants to share, **When** a cross-scope transfer is initiated, **Then** the memory is copied to the target scope with provenance linking back to the original
2. **Given** a cross-scope transfer request, **When** the requesting agent lacks transfer authorization, **Then** the transfer is rejected
3. **Given** multiple similar agent-scoped memories across agents, **When** consolidation runs, **Then** a distilled workspace-scoped memory is created and the originals reference the consolidated entry
4. **Given** consolidation produces a candidate, **When** the candidate contradicts an existing workspace memory, **Then** the conflict is flagged and both are preserved with conflict metadata
5. **Given** consolidation is running, **When** real-time memory writes occur simultaneously, **Then** writes proceed without blocking or delay

---

### Edge Cases

- What happens when the vector store is temporarily unavailable during a write? The memory write gate returns a retriable error. No partial state is persisted. The caller can retry with exponential backoff.
- What happens when the knowledge graph is unavailable during hybrid retrieval? The retrieval coordinator falls back to vector + keyword sources only, returns results with a partial-sources flag, and logs the graph unavailability.
- What happens when a memory's embedding cannot be generated (embedding model unavailable)? The write is queued in an embedding job queue and stored as "pending_embedding." The memory is not retrievable via vector search until the embedding completes, but the raw text is available via keyword search immediately.
- What happens when contradiction detection produces a false positive? Both the new and existing memories are stored with a contradiction flag. An authorized operator can review and dismiss the conflict, removing the flag without deleting either memory.
- What happens when a consolidation worker encounters a memory that was deleted between retrieval and distillation? The worker skips the deleted memory and continues with remaining candidates. The consolidated output reflects only memories that exist at distillation time.
- What happens when differential privacy noise injection significantly alters the semantic meaning of a memory? The system preserves the original (unmodified) text in a restricted-access provenance record and stores only the privacy-filtered version in the main memory store. The original is accessible only to workspace admins for audit purposes.
- What happens when a cross-scope transfer targets a scope the agent doesn't have visibility to? The transfer is rejected by the write gate with a scope authorization error. No data is copied.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST store memory entries as vector embeddings with metadata including workspace ID, agent FQN, scope, timestamp, source authority, content hash, and retention policy
- **FR-002**: The system MUST enforce memory scoping: per-agent (visible only to the writing agent), per-workspace (visible to all workspace agents), and shared-orchestrator (visible to all orchestrator-role agents in the workspace)
- **FR-003**: The system MUST support memory retrieval by semantic similarity, combining vector similarity scores with recency weighting and source authority scoring
- **FR-004**: The system MUST implement hybrid retrieval combining vector similarity, keyword matching, and knowledge graph traversal using reciprocal rank fusion
- **FR-005**: The system MUST detect contradictions between incoming memory writes and existing memories on the same topic, flagging conflicts without overwriting existing entries
- **FR-006**: The system MUST enforce a memory write gate that validates authorization, rate limits, namespace restrictions, retention policy compatibility, and optionally applies differential privacy before storage
- **FR-007**: The system MUST rate-limit memory writes per agent with configurable per-minute and per-hour thresholds
- **FR-008**: The system MUST support namespace-scoped memory writes where agents can only write to namespaces they own or have been granted access to
- **FR-009**: The system MUST manage a knowledge graph supporting node creation, edge creation, multi-hop traversal up to a configurable depth limit, and provenance chain queries
- **FR-010**: The system MUST enforce workspace isolation on all knowledge graph queries — no cross-workspace visibility
- **FR-011**: The system MUST capture execution trajectories as immutable records containing ordered actions, inputs, outputs, tool invocations, reasoning snapshots, and verdicts
- **FR-012**: The system MUST support pattern promotion from trajectories through an approval workflow (pending → approved/rejected) with only approved patterns being discoverable via retrieval
- **FR-013**: The system MUST support cross-scope memory transfers with additional authorization checks and provenance preservation
- **FR-014**: The system MUST run background consolidation workers that distill recurring patterns from similar agent-scoped memories and optionally promote consolidated entries to workspace scope
- **FR-015**: Consolidation MUST NOT block real-time memory reads or writes
- **FR-016**: The system MUST handle unavailable memory sources gracefully — continuing with available sources and attaching partial-source indicators to results
- **FR-017**: The system MUST queue embedding generation as background jobs when the embedding model is unavailable, making memories available via keyword search immediately and via vector search once embedding completes
- **FR-018**: The system MUST publish events when memories are written, contradictions detected, patterns promoted, and consolidation completed
- **FR-019**: All memory endpoints and internal interfaces MUST enforce workspace-scoped access control
- **FR-020**: The system MUST support memory retention policies: permanent, time-limited (configurable TTL), and session-only (deleted when execution ends)

### Key Entities

- **MemoryEntry**: A single piece of knowledge stored in the memory subsystem. Contains the text content, vector embedding, workspace ID, agent FQN, scope (per-agent, per-workspace, shared-orchestrator), namespace, source authority score, content hash, retention policy, and provenance metadata. The primary unit of storage and retrieval.
- **MemoryScope**: The visibility boundary for a memory entry. Determines which agents can read the entry. Scopes are per-agent (private), per-workspace (shared among all workspace agents), and shared-orchestrator (shared among orchestrator-role agents only).
- **MemoryWriteRequest**: A validated write request that has passed through the write gate. Contains the source memory content, target scope and namespace, the writing agent's identity, and the results of all gate checks (authorization, rate limit, contradiction, retention, privacy).
- **EvidenceConflict**: A record linking two memory entries that contain contradictory claims about the same topic or entity. Contains references to both memories, the detected conflict description, resolution status (open, dismissed, resolved), and reviewer identity if resolved.
- **EmbeddingJob**: A queued job for generating a vector embedding for a memory entry. Created when the embedding model is temporarily unavailable. Tracks the memory entry ID, job status (pending, processing, completed, failed), and retry count.
- **TrajectoryRecord**: An immutable record of an agent's complete execution sequence. Contains the execution ID, agent FQN, ordered list of actions with inputs/outputs, tool invocation records, reasoning snapshots, final verdicts, and timestamps. Used for post-hoc analysis and pattern nomination.
- **PatternAsset**: A promoted trajectory or distilled piece of knowledge that has been approved for reuse. Contains the source trajectory reference, extracted pattern content, approval status (pending, approved, rejected), reviewer identity, and discovery metadata (tags, description).
- **KnowledgeNode**: A typed entity in the knowledge graph with attributes, workspace scope, and creation provenance. Examples: agents, tools, concepts, facts, organizations.
- **KnowledgeEdge**: A typed relationship between two knowledge graph nodes with metadata, timestamp, and workspace scope. Examples: "used", "produced", "has_terms", "contradicts".

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Memory writes through the write gate complete within 500 milliseconds (excluding embedding generation)
- **SC-002**: Vector similarity retrieval returns results within 200 milliseconds for collections of up to 1 million entries
- **SC-003**: Hybrid retrieval (combining 3 sources with rank fusion) returns fused results within 1 second
- **SC-004**: Contradiction detection identifies conflicting memories with at least 85% accuracy on known-contradiction test sets
- **SC-005**: Knowledge graph multi-hop queries (up to 3 hops) return results within 500 milliseconds
- **SC-006**: Scope isolation is enforced on 100% of reads and writes — zero cross-scope leakage
- **SC-007**: Memory write gate blocks 100% of unauthorized writes, rate-exceeded writes, and invalid retention requests — zero unguarded writes
- **SC-008**: Trajectory capture records 100% of execution actions — zero dropped actions
- **SC-009**: Pattern promotion workflow maintains correct state transitions 100% of the time — no orphaned or stuck candidates
- **SC-010**: Test coverage of the memory and knowledge subsystem is at least 95%

## Assumptions

- The vector store service (Qdrant, feature 005) is operational for embedding storage and similarity search. Collections are created at startup if they do not exist.
- The knowledge graph service (Neo4j, feature 006) is operational for structured relationship storage and traversal queries.
- Embedding generation is performed by calling a model provider API (configurable in PlatformSettings). The default embedding model produces 1536-dimensional vectors (configurable).
- The keyword search component uses PostgreSQL full-text search for memory entries — this is an internal implementation detail scoped to the memory bounded context's own tables, not user-facing search (which uses OpenSearch per constitution §III).
- Workspace membership and authorization are provided by the workspaces bounded context (feature 018) via in-process service interface.
- Agent identity and namespace ownership are provided by the registry bounded context (feature 021) via in-process service interface.
- Rate limiting for memory writes uses Redis counters with sliding window, consistent with the rate limiting pattern from feature 014 (auth bounded context).
- The Kafka event topic for memory events is `memory.events` (using the canonical EventEnvelope from feature 013).
- Consolidation workers run as background tasks via APScheduler (every 15 minutes by default, configurable). They do not block real-time operations.
- Differential privacy noise injection uses a simple Laplace mechanism with configurable epsilon. It is opt-in per workspace, not enabled by default.
- The reciprocal rank fusion constant `k` defaults to 60 (standard RRF constant). Configurable per workspace.
- Memory retention enforcement (TTL-based deletion) is handled by a background cleaner task that runs hourly.
