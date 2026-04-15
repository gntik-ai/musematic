# Data Model: Scientific Discovery Orchestration

**Feature**: 039-scientific-discovery-orchestration  
**Storage**: PostgreSQL 16 (8 tables) + Redis sorted sets + Neo4j graph + Qdrant collection

---

## PostgreSQL Tables

### 1. `discovery_sessions`

Top-level container for a discovery workflow.

```python
class DiscoverySession(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_sessions"

    research_question: Mapped[str]
    corpus_refs: Mapped[list]            # JSONB: [{type: "dataset|literature", ref_id, description}]
    config: Mapped[dict]                 # JSONB: {k_factor, convergence_threshold, max_cycles, min_hypotheses}
    status: Mapped[str]                  # "active" | "converged" | "halted" | "iteration_limit_reached"
    current_cycle: Mapped[int]           # 0-based
    convergence_metrics: Mapped[dict | None]  # JSONB: {stable_rounds, last_top_elo, delta}
    initiated_by: Mapped[UUID]           # FK → auth.users.id

    __table_args__ = (
        Index("ix_discovery_sessions_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('active', 'converged', 'halted', 'iteration_limit_reached')",
            name="ck_session_status"
        ),
    )
```

---

### 2. `discovery_hypotheses`

A scientific conjecture within a discovery session.

```python
class Hypothesis(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_hypotheses"

    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    cycle_id: Mapped[UUID | None]        # FK → discovery_gde_cycles.id (cycle that produced this)
    title: Mapped[str]
    description: Mapped[str]
    reasoning: Mapped[str]               # Supporting rationale from generating agent
    confidence: Mapped[float]            # 0.0–1.0 (agent self-assessed)
    generating_agent_fqn: Mapped[str]
    status: Mapped[str]                  # "active" | "merged" | "retired"
    merged_into_id: Mapped[UUID | None]  # FK → discovery_hypotheses.id (if merged)
    qdrant_point_id: Mapped[str | None]  # UUID string in Qdrant discovery_hypotheses collection
    cluster_id: Mapped[str | None]       # Cluster assignment from proximity analysis

    __table_args__ = (
        Index("ix_hypotheses_session_id", "session_id"),
        Index("ix_hypotheses_workspace_status", "workspace_id", "status"),
        CheckConstraint(
            "status IN ('active', 'merged', 'retired')",
            name="ck_hypothesis_status"
        ),
        CheckConstraint("confidence >= 0.0 AND confidence <= 1.0", name="ck_confidence"),
    )
```

---

### 3. `discovery_critiques`

Structured multi-dimensional evaluation by a reviewer agent.

```python
class HypothesisCritique(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_critiques"

    hypothesis_id: Mapped[UUID]          # FK → discovery_hypotheses.id
    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    reviewer_agent_fqn: Mapped[str]
    scores: Mapped[dict]                 # JSONB: {consistency: {score, confidence, reasoning},
                                         #          novelty: {...}, testability: {...},
                                         #          evidence_support: {...}, impact: {...}}
    composite_summary: Mapped[dict | None] # JSONB: {per_dimension_averages, disagreement_flags}
    is_aggregated: Mapped[bool]          # True if this row is an aggregation of multiple critiques

    __table_args__ = (
        Index("ix_critiques_hypothesis_id", "hypothesis_id"),
    )
```

---

### 4. `discovery_tournament_rounds`

A single pairwise comparison round within a GDE cycle.

```python
class TournamentRound(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_tournament_rounds"

    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    cycle_id: Mapped[UUID | None]        # FK → discovery_gde_cycles.id
    round_number: Mapped[int]
    pairwise_results: Mapped[list]       # JSONB: [{hyp_a_id, hyp_b_id, outcome: "a_wins|b_wins|draw", reasoning}]
    elo_changes: Mapped[list]            # JSONB: [{hypothesis_id, old_elo, new_elo, delta}]
    bye_hypothesis_id: Mapped[UUID | None]  # Hypothesis that received a bye (odd count)
    status: Mapped[str]                  # "completed" | "in_progress" | "failed"

    __table_args__ = (
        Index("ix_tournament_rounds_session_id", "session_id"),
    )
```

---

### 5. `discovery_elo_scores`

Persistent Elo score record per hypothesis (Redis is the hot state).

```python
class EloScore(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_elo_scores"

    hypothesis_id: Mapped[UUID]          # FK → discovery_hypotheses.id (unique per session)
    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    current_score: Mapped[float]         # Default 1000.0
    wins: Mapped[int]                    # Default 0
    losses: Mapped[int]                  # Default 0
    draws: Mapped[int]                   # Default 0
    score_history: Mapped[list]          # JSONB: [{round_number, score, timestamp}]

    __table_args__ = (
        UniqueConstraint("hypothesis_id", "session_id", name="uq_elo_hypothesis_session"),
        Index("ix_elo_scores_session_id", "session_id"),
    )
```

---

### 6. `discovery_experiments`

Experiment plans linked to hypotheses.

```python
class DiscoveryExperiment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_experiments"

    hypothesis_id: Mapped[UUID]          # FK → discovery_hypotheses.id
    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    plan: Mapped[dict]                   # JSONB: {objective, methodology, expected_outcomes,
                                         #          required_data, resources, success_criteria, code}
    governance_status: Mapped[str]       # "pending" | "approved" | "rejected"
    governance_violations: Mapped[list]  # JSONB: [{policy_id, rule_id, description}]
    execution_status: Mapped[str]        # "not_started" | "running" | "completed" | "failed" | "timeout"
    sandbox_execution_id: Mapped[str | None]   # From SandboxManagerClient
    results: Mapped[dict | None]         # JSONB: {stdout, exit_code, artifacts, evidence_type, interpretation}
    designed_by_agent_fqn: Mapped[str]

    __table_args__ = (
        Index("ix_experiments_hypothesis_id", "hypothesis_id"),
        Index("ix_experiments_session_id", "session_id"),
        CheckConstraint(
            "governance_status IN ('pending', 'approved', 'rejected')",
            name="ck_governance_status"
        ),
        CheckConstraint(
            "execution_status IN ('not_started', 'running', 'completed', 'failed', 'timeout')",
            name="ck_execution_status"
        ),
    )
```

---

### 7. `discovery_gde_cycles`

State for a single generate-debate-evolve iteration.

```python
class GDECycle(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_gde_cycles"

    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    cycle_number: Mapped[int]            # 1-based
    status: Mapped[str]                  # "running" | "completed" | "failed"
    generation_count: Mapped[int]        # Hypotheses generated in this cycle
    debate_record: Mapped[dict]          # JSONB: [{hypothesis_id, for_arguments: [...], against_arguments: [...]}]
    refinement_count: Mapped[int]        # Hypotheses refined in this cycle
    convergence_metric: Mapped[float | None]  # Top Elo change % vs previous cycle
    converged: Mapped[bool]              # True if convergence threshold met

    __table_args__ = (
        Index("ix_gde_cycles_session_id", "session_id"),
        UniqueConstraint("session_id", "cycle_number", name="uq_cycle_session_number"),
    )
```

---

### 8. `discovery_hypothesis_clusters`

Proximity clustering results (written by APScheduler background task).

```python
class HypothesisCluster(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "discovery_hypothesis_clusters"

    session_id: Mapped[UUID]             # FK → discovery_sessions.id
    cluster_label: Mapped[str]           # Unique label within session (e.g., "cluster_0")
    centroid_description: Mapped[str]    # Human-readable theme summary (from LLM or most central hypothesis title)
    hypothesis_count: Mapped[int]
    density_metric: Mapped[float]        # Average intra-cluster cosine similarity
    classification: Mapped[str]          # "normal" | "over_explored" | "gap"
    hypothesis_ids: Mapped[list]         # JSONB: [uuid, ...]
    computed_at: Mapped[datetime]

    __table_args__ = (
        Index("ix_clusters_session_id", "session_id"),
        CheckConstraint(
            "classification IN ('normal', 'over_explored', 'gap')",
            name="ck_cluster_classification"
        ),
    )
```

---

## Redis Hot State

```
leaderboard:{session_id}
  Type: Sorted Set
  Members: hypothesis_id (string UUID)
  Scores: Elo score (float)
  Updated: after every pairwise comparison
  TTL: session active duration + 24h buffer

lock:discovery:elo:{session_id}
  Type: String
  Value: lock token
  TTL: 10s (via lock_acquire.lua)
  Used: atomic Elo batch update after tournament round
```

---

## Neo4j Graph

**Node Labels and Properties**:

```cypher
// Hypothesis node
(:HypothesisNode {
  hypothesis_id: "uuid",
  workspace_id: "uuid",
  session_id: "uuid",
  title: "string",
  status: "active|merged|retired"
})

// Agent node (discovery participant)
(:DiscoveryAgentNode {
  agent_fqn: "string",
  workspace_id: "uuid"
})

// Evidence node (experiment results or literature)
(:EvidenceNode {
  evidence_id: "uuid",
  workspace_id: "uuid",
  session_id: "uuid",
  source_type: "experiment|literature|reasoning",
  summary: "string",
  confidence: 0.0-1.0
})
```

**Relationship Types**:

```cypher
(h:HypothesisNode)-[:GENERATED_BY {cycle_number, timestamp}]->(a:DiscoveryAgentNode)
(h:HypothesisNode)-[:REFINED_FROM {cycle_number, changes_summary}]->(h2:HypothesisNode)
(e:EvidenceNode)-[:SUPPORTS {confidence}]->(h:HypothesisNode)
(e:EvidenceNode)-[:CONTRADICTS {confidence}]->(h:HypothesisNode)
(e:EvidenceNode)-[:INCONCLUSIVE_FOR]->(h:HypothesisNode)
(h:HypothesisNode)-[:SIMILAR_TO {similarity_score}]->(h2:HypothesisNode)
```

---

## Qdrant Collection

**Collection**: `discovery_hypotheses`

```python
VectorParams(size=1536, distance=Distance.COSINE)
HnswConfigDiff(m=16, ef_construct=128, full_scan_threshold=10000)
PayloadSchemaType.KEYWORD indexes: ["workspace_id", "session_id", "cluster_id", "status"]
```

Point structure:
```python
PointStruct(
  id=str(hypothesis_uuid),
  vector=embedding_list,  # 1536-dimensional
  payload={
    "workspace_id": str,
    "session_id": str,
    "hypothesis_id": str,
    "title": str,
    "cluster_id": str | None,
    "status": "active|merged|retired"
  }
)
```

---

## Kafka Event Schema

**Topic**: `discovery.events`  
**Key**: `session_id` (string UUID)

```json
{
  "event_id": "uuid",
  "event_type": "session_started|hypothesis_generated|critique_completed|tournament_round_completed|cycle_completed|session_converged|session_halted|experiment_designed|experiment_completed|proximity_computed",
  "session_id": "uuid",
  "workspace_id": "uuid",
  "actor_id": "uuid | null",
  "timestamp": "ISO8601",
  "payload": {}
}
```

---

## State Transitions

### DiscoverySession.status
```
active → converged          (convergence threshold met)
active → halted             (operator manually halted)
active → iteration_limit_reached  (max_cycles reached without convergence)
```

### DiscoveryExperiment.governance_status
```
pending → approved   (policy evaluation passes)
pending → rejected   (policy violations found)
```

### DiscoveryExperiment.execution_status
```
not_started → running     (submitted to sandbox)
running → completed       (sandbox returns exit_code 0)
running → failed          (sandbox returns non-zero exit_code)
running → timeout         (execution exceeds timeout)
```
