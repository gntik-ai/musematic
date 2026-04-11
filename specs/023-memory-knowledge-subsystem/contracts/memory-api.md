# API Contracts: Memory and Knowledge Subsystem

**Feature**: 023-memory-knowledge-subsystem  
**Date**: 2026-04-11  
**Base path**: `/api/v1/memory`  
**Auth**: JWT Bearer (all endpoints require `workspace_id` claim)

---

## REST Endpoints

### 1. Write Memory Entry

**POST** `/api/v1/memory/entries`

Writes a new memory entry through the write gate. Performs authorization, rate limit, contradiction, retention, and optional differential privacy checks before storage.

**Request Body**:
```json
{
  "content": "Customer ACME Corp prefers invoice terms NET-30.",
  "scope": "per_agent",
  "namespace": "finance-ops",
  "source_authority": 0.9,
  "retention_policy": "permanent",
  "ttl_seconds": null,
  "execution_id": null,
  "tags": ["customer", "payment-terms"]
}
```

**Response** `201 Created`:
```json
{
  "memory_entry_id": "uuid",
  "contradiction_detected": false,
  "conflict_id": null,
  "privacy_applied": false,
  "rate_limit_remaining_min": 58,
  "rate_limit_remaining_hour": 497
}
```

**Error Responses**:
- `403 Forbidden` — agent not authorized to write to namespace/scope
- `409 Conflict` — contradiction detected (includes `conflict_id` in response body, write still succeeds)
- `422 Unprocessable Entity` — retention policy mismatch or invalid scope for this agent
- `429 Too Many Requests` — rate limit exceeded (`Retry-After` header with cooldown seconds)

---

### 2. Retrieve Memory (Hybrid Search)

**POST** `/api/v1/memory/retrieve`

Performs hybrid retrieval across vector, keyword, and graph sources with reciprocal rank fusion.

**Request Body**:
```json
{
  "query_text": "What are ACME's payment preferences?",
  "scope_filter": null,
  "agent_fqn_filter": null,
  "top_k": 10,
  "include_contradictions": true,
  "rrf_k": 60
}
```

**Response** `200 OK`:
```json
{
  "results": [
    {
      "memory_entry_id": "uuid",
      "content": "Customer ACME Corp prefers invoice terms NET-30.",
      "scope": "per_agent",
      "agent_fqn": "finance-ops:kyc-verifier",
      "source_authority": 0.9,
      "rrf_score": 0.048,
      "recency_factor": 1.0,
      "final_score": 0.048,
      "sources_contributed": ["vector", "keyword"],
      "contradiction_flag": false,
      "conflict_ids": []
    }
  ],
  "partial_sources": [],
  "query_time_ms": 142.3
}
```

---

### 3. Get Memory Entry

**GET** `/api/v1/memory/entries/{entry_id}`

**Response** `200 OK`: `MemoryEntryResponse`

---

### 4. List Memory Entries

**GET** `/api/v1/memory/entries`

**Query Parameters**: `scope` (enum), `agent_fqn` (string), `page` (int), `page_size` (int, max 100)

**Response** `200 OK`:
```json
{
  "items": [...],
  "total": 145,
  "page": 1,
  "page_size": 20
}
```

---

### 5. Delete Memory Entry

**DELETE** `/api/v1/memory/entries/{entry_id}`

Soft-deletes the entry from PostgreSQL and removes the Qdrant point. Only the writing agent or workspace admin can delete.

**Response** `204 No Content`

---

### 6. Transfer Memory Scope

**POST** `/api/v1/memory/entries/{entry_id}/transfer`

Copies a memory entry to a different scope with provenance preservation. Requires transfer authorization.

**Request Body**:
```json
{
  "target_scope": "per_workspace",
  "target_namespace": "finance-ops"
}
```

**Response** `201 Created`: `WriteGateResult` (new `memory_entry_id` for the transferred copy)

---

### 7. List Evidence Conflicts

**GET** `/api/v1/memory/conflicts`

**Query Parameters**: `status` (enum: open, dismissed, resolved), `page`, `page_size`

**Response** `200 OK`: Paginated list of `EvidenceConflictResponse`

---

### 8. Resolve Evidence Conflict

**POST** `/api/v1/memory/conflicts/{conflict_id}/resolve`

Requires workspace admin or operator role.

**Request Body**:
```json
{
  "action": "dismiss",
  "resolution_notes": "Confirmed: NET-30 is correct, NET-60 was a data entry error."
}
```

**Response** `200 OK`: `EvidenceConflictResponse`

---

### 9. Record Trajectory

**POST** `/api/v1/memory/trajectories`

Called by the execution bounded context after execution completion.

**Request Body**: `TrajectoryRecordCreate`

**Response** `201 Created`: `TrajectoryRecordResponse`

---

### 10. Get Trajectory

**GET** `/api/v1/memory/trajectories/{trajectory_id}`

**Response** `200 OK`: `TrajectoryRecordResponse`

---

### 11. Nominate Pattern

**POST** `/api/v1/memory/patterns`

Nominates a trajectory (or a standalone piece of content) as a pattern candidate.

**Request Body**: `PatternNomination`

**Response** `201 Created`: `PatternAssetResponse`

---

### 12. Review Pattern

**POST** `/api/v1/memory/patterns/{pattern_id}/review`

Approve or reject a pending pattern. Requires workspace admin role.

**Request Body**: `PatternReview`

**Response** `200 OK`: `PatternAssetResponse`

On approval: creates a `MemoryEntry` in `per_workspace` scope with the pattern content and links `pattern_assets.memory_entry_id`.

---

### 13. List Patterns

**GET** `/api/v1/memory/patterns`

**Query Parameters**: `status` (enum: pending, approved, rejected), `page`, `page_size`

**Response** `200 OK`: Paginated list of `PatternAssetResponse`

---

### 14. Create Knowledge Node

**POST** `/api/v1/memory/graph/nodes`

**Request Body**: `KnowledgeNodeCreate`

**Response** `201 Created`: `KnowledgeNodeResponse`

Creates the node in both PostgreSQL (metadata) and Neo4j (graph structure). Atomic: if Neo4j write fails, PostgreSQL record is rolled back.

---

### 15. Create Knowledge Edge

**POST** `/api/v1/memory/graph/edges`

**Request Body**: `KnowledgeEdgeCreate`

**Response** `201 Created`: `KnowledgeEdgeResponse`

---

### 16. Traverse Knowledge Graph

**POST** `/api/v1/memory/graph/traverse`

**Request Body**: `GraphTraversalQuery`

**Response** `200 OK`: `GraphTraversalResponse`

Falls back gracefully if Neo4j is unavailable (returns empty `paths` with `partial_sources: ["graph"]` indicator).

---

### 17. Get Provenance Chain

**GET** `/api/v1/memory/graph/nodes/{node_id}/provenance`

Returns the full creation and transformation chain for a knowledge node by traversing backward through provenance edges.

**Response** `200 OK`: `GraphTraversalResponse`

---

## Internal Interface

### `retrieve_for_context()`

Consumed by the context engineering service (`LongTermMemoryAdapter` in feature 022).

```python
async def retrieve_for_context(
    self,
    query_text: str,
    agent_fqn: str,
    workspace_id: UUID,
    goal_id: UUID | None,
    top_k: int = 10,
) -> list[RetrievalResult]:
    """
    In-process hybrid retrieval optimized for context assembly.
    Uses the same vector + keyword + graph pipeline as the REST endpoint
    but with a tighter 800ms timeout (context assembly budget).
    Returns top_k results sorted by final_score descending.
    Partial source failures are silently tolerated (partial_sources logged but not raised).
    """
```

**Called from**: `apps/control-plane/src/platform/context_engineering/adapters.py` — `LongTermMemoryAdapter.fetch()`

**Not exposed via HTTP** — in-process function call only, consistent with §I (modular monolith, no HTTP between contexts).

---

## Events

**Topic**: `memory.events`  
**Envelope**: Canonical `EventEnvelope` from feature 013

| Event Type | Payload | Trigger |
|---|---|---|
| `memory.written` | `MemoryWrittenPayload` | Successful write gate completion |
| `memory.conflict.detected` | `ConflictDetectedPayload` | Evidence conflict created |
| `memory.pattern.promoted` | `PatternPromotedPayload` | Pattern approved by reviewer |
| `memory.consolidation.completed` | `ConsolidationCompletedPayload` | Consolidation worker completes a run |
