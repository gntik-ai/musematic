# API Contracts: Scientific Discovery Orchestration

All endpoints require `Authorization: Bearer <access_token>` and are workspace-scoped.  
Base path: `/api/v1/discovery`  
Responses use JSON. Timestamps are ISO 8601. IDs are UUIDs.

---

## Discovery Session Endpoints

### Create Discovery Session
```
POST /api/v1/discovery/sessions
body: DiscoverySessionCreateRequest
→ DiscoverySessionResponse  (201 Created)
```

**DiscoverySessionCreateRequest**:
```json
{
  "workspace_id": "uuid",
  "research_question": "string (required, 1–5000 chars)",
  "corpus_refs": [{"type": "dataset|literature", "ref_id": "string", "description": "string"}],
  "config": {
    "k_factor": 32,
    "convergence_threshold": 0.05,
    "max_cycles": 10,
    "min_hypotheses": 3
  }
}
```

### Get Discovery Session
```
GET /api/v1/discovery/sessions/{session_id}
→ DiscoverySessionResponse
```

### List Discovery Sessions
```
GET /api/v1/discovery/sessions
  ?workspace_id={id}&status=active|converged|halted|iteration_limit_reached&limit={n}&cursor={cursor}
→ { items: DiscoverySessionResponse[], next_cursor: string | null }
```

### Halt Discovery Session
```
POST /api/v1/discovery/sessions/{session_id}/halt
body: { reason: string }
→ DiscoverySessionResponse
```

---

## GDE Cycle Endpoints

### Run GDE Cycle
```
POST /api/v1/discovery/sessions/{session_id}/cycle
→ GDECycleResponse  (202 Accepted — cycle runs asynchronously)
Errors: 409 if session already has a running cycle; 409 if session not in 'active' status
```

### Get Cycle Status
```
GET /api/v1/discovery/cycles/{cycle_id}
→ GDECycleResponse
```

---

## Hypothesis Endpoints

### List Hypotheses (with Elo leaderboard)
```
GET /api/v1/discovery/sessions/{session_id}/hypotheses
  ?workspace_id={id}&status=active|merged|retired&order_by=elo_desc|created_at&limit={n}&cursor={cursor}
→ { items: HypothesisResponse[], next_cursor: string | null }
```

**HypothesisResponse**:
```json
{
  "hypothesis_id": "uuid",
  "session_id": "uuid",
  "title": "string",
  "description": "string",
  "reasoning": "string",
  "confidence": 0.85,
  "generating_agent_fqn": "string",
  "status": "active",
  "elo_score": 1052.4,
  "rank": 1,
  "wins": 5,
  "losses": 2,
  "draws": 1,
  "cluster_id": "cluster_0 | null",
  "created_at": "ISO8601"
}
```

### Get Hypothesis
```
GET /api/v1/discovery/hypotheses/{hypothesis_id}
→ HypothesisResponse
```

---

## Critique Endpoints

### Get Critiques for Hypothesis
```
GET /api/v1/discovery/hypotheses/{hypothesis_id}/critiques
→ { items: HypothesisCritiqueResponse[], aggregated: HypothesisCritiqueResponse | null }
```

**HypothesisCritiqueResponse**:
```json
{
  "critique_id": "uuid",
  "hypothesis_id": "uuid",
  "reviewer_agent_fqn": "string",
  "is_aggregated": false,
  "scores": {
    "consistency": {"score": 0.8, "confidence": 0.9, "reasoning": "string"},
    "novelty": {"score": 0.7, "confidence": 0.85, "reasoning": "string"},
    "testability": {"score": 0.9, "confidence": 0.95, "reasoning": "string"},
    "evidence_support": {"score": 0.6, "confidence": 0.7, "reasoning": "string"},
    "impact": {"score": 0.75, "confidence": 0.8, "reasoning": "string"}
  },
  "composite_summary": null,
  "created_at": "ISO8601"
}
```

---

## Tournament Endpoints

### Get Tournament Leaderboard
```
GET /api/v1/discovery/sessions/{session_id}/leaderboard
  ?workspace_id={id}&limit={n}
→ { items: LeaderboardEntryResponse[], session_id: string, total_hypotheses: int }
```

### List Tournament Rounds
```
GET /api/v1/discovery/sessions/{session_id}/tournament-rounds
  ?workspace_id={id}&limit={n}&cursor={cursor}
→ { items: TournamentRoundResponse[], next_cursor: string | null }
```

---

## Experiment Endpoints

### Design Experiment for Hypothesis
```
POST /api/v1/discovery/hypotheses/{hypothesis_id}/experiment
body: { workspace_id: string }
→ DiscoveryExperimentResponse  (201 Created)
```

### Get Experiment
```
GET /api/v1/discovery/experiments/{experiment_id}
→ DiscoveryExperimentResponse
```

### Execute Approved Experiment
```
POST /api/v1/discovery/experiments/{experiment_id}/execute
→ DiscoveryExperimentResponse  (202 Accepted)
Errors: 409 if governance_status != 'approved'; 409 if already running/completed
```

---

## Provenance Endpoints

### Get Hypothesis Provenance
```
GET /api/v1/discovery/hypotheses/{hypothesis_id}/provenance
  ?workspace_id={id}&depth={n}
→ ProvenanceGraphResponse
```

**ProvenanceGraphResponse**:
```json
{
  "hypothesis_id": "uuid",
  "nodes": [
    {"id": "uuid", "type": "hypothesis|evidence|agent|experiment", "label": "string", "properties": {}}
  ],
  "edges": [
    {"from": "uuid", "to": "uuid", "type": "GENERATED_BY|SUPPORTS|CONTRADICTS|REFINED_FROM|INCONCLUSIVE_FOR", "properties": {}}
  ]
}
```

---

## Proximity Cluster Endpoints

### Get Proximity Clusters
```
GET /api/v1/discovery/sessions/{session_id}/clusters
  ?workspace_id={id}
→ { items: HypothesisClusterResponse[], landscape_status: "normal|saturated|low_data" }
```

### Trigger Proximity Computation
```
POST /api/v1/discovery/sessions/{session_id}/compute-proximity
→ 202 Accepted
Errors: 409 if computation already running
```

---

## Error Responses

```json
{ "code": "...", "message": "...", "details": {} }
```

| HTTP | Code | When |
|------|------|------|
| 400 | `VALIDATION_ERROR` | Invalid request body |
| 403 | `AUTHORIZATION_ERROR` | Insufficient workspace role |
| 404 | `NOT_FOUND` | Session, hypothesis, experiment, or cycle not found |
| 409 | `SESSION_ALREADY_RUNNING` | Cycle already active or session not in active status |
| 409 | `EXPERIMENT_NOT_APPROVED` | Experiment execution attempted before governance approval |
| 412 | `INSUFFICIENT_HYPOTHESES` | Tournament requires at least 2 active hypotheses |
