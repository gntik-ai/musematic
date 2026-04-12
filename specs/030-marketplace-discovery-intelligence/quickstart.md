# Quickstart & Test Scenarios: Marketplace Discovery and Intelligence

**Feature**: 030-marketplace-discovery-intelligence  
**Date**: 2026-04-12

These scenarios define the minimal test cases needed to verify each user story can be demonstrated end-to-end. They are also used as the basis for integration tests.

---

## Scenario 1: Keyword Search Returns Relevant Agents

**Story**: US1 — Agent Search and Filtering  
**Verifies**: FR-001, SC-001

**Setup**:
- Agents in OpenSearch index: `finance-ops:report-analyzer` (capabilities: financial_analysis, document_parsing), `hr-tools:resume-screener` (capabilities: nlp, document_classification)
- User workspace has visibility grant for both agents

**Request**:
```
POST /api/v1/marketplace/search
{ "query": "analyze financial reports" }
```

**Expected**:
- `report-analyzer` appears in top-3 results
- `resume-screener` relevance score is lower or absent
- `has_results: true`

---

## Scenario 2: Semantic Search — Zero Keyword Overlap

**Story**: US1  
**Verifies**: FR-002, SC-002

**Setup**:
- Agent `finance-ops:ap-handler` with description "automated accounts payable handler" in Qdrant with finance-domain embedding

**Request**:
```
POST /api/v1/marketplace/search
{ "query": "invoice processor" }
```

**Expected**:
- `ap-handler` appears in results despite no keyword overlap
- `relevance_score > 0` derived from Qdrant semantic match

---

## Scenario 3: Visibility Filtering Enforced

**Story**: US1  
**Verifies**: FR-003, SC-011

**Setup**:
- Agent `secret-ops:classified-agent` exists in registry but NOT in user's workspace visibility config

**Request**:
```
POST /api/v1/marketplace/search
{ "query": "classified" }
```

**Expected**:
- `classified-agent` does NOT appear in results
- No 403 — just absent from results

---

## Scenario 4: Faceted Filter Narrows Results

**Story**: US1  
**Verifies**: FR-004

**Setup**:
- 5 agents visible: 2 at maturity_level=1, 3 at maturity_level=3

**Request**:
```
POST /api/v1/marketplace/search
{ "query": "", "maturity_level_min": 2 }
```

**Expected**:
- Only 3 agents returned (maturity 3)
- Level-1 agents not in response

---

## Scenario 5: Empty Query Returns Popularity-Ordered Browse

**Story**: US1  
**Verifies**: FR-005

**Request**:
```
POST /api/v1/marketplace/search
{ "query": "" }
```

**Expected**:
- All agents within visibility scope returned
- Ordered by `invocation_count_30d` descending
- `has_results: true` if any agents, `false` if none

---

## Scenario 6: Comparison View — 3 Agents With Differences Highlighted

**Story**: US2  
**Verifies**: FR-006, FR-007, SC-004

**Setup**: 3 agents with different maturity levels and same trust_tier

**Request**:
```
GET /api/v1/marketplace/compare?agent_ids=uuid1,uuid2,uuid3
```

**Expected**:
- All 8 attributes present for each agent
- `maturity_level.differs = true` (different values)
- `trust_tier.differs = false` (same value)
- Response in < 1 second

---

## Scenario 7: Comparison Rejects Invalid Counts

**Story**: US2  
**Verifies**: FR-008

**Request (1 agent)**:
```
GET /api/v1/marketplace/compare?agent_ids=uuid1
```

**Expected**: 400 with `"error": "COMPARISON_RANGE_INVALID"`

**Request (5 agents)**:
```
GET /api/v1/marketplace/compare?agent_ids=uuid1,uuid2,uuid3,uuid4,uuid5
```

**Expected**: 400 with `"error": "COMPARISON_RANGE_INVALID"`

---

## Scenario 8: Quality Profile — Agent With Execution History

**Story**: US3  
**Verifies**: FR-009, SC-005

**Setup**:
- Kafka consumer has processed 100 `step.completed` events → `success_count=95`, `failure_count=5`
- 1 `evaluation.scored` event with score=80.0
- 10 `step.self_corrected` events

**Request**:
```
GET /api/v1/marketplace/agents/{agent_id}/quality
```

**Expected**:
```json
{
  "has_data": true,
  "success_rate": 0.95,
  "quality_score_avg": 80.0,
  "self_correction_rate": 0.10,
  "source_unavailable": false
}
```

---

## Scenario 9: Quality Profile — No Execution History

**Story**: US3  
**Verifies**: FR-010

**Setup**: Agent exists in registry but has never been invoked

**Expected**:
```json
{
  "has_data": false,
  "success_rate": null,
  "quality_score_avg": null,
  "self_correction_rate": null,
  "satisfaction_avg": null
}
```

---

## Scenario 10: Quality Profile — Stale Data Banner

**Story**: US3  
**Verifies**: FR-012

**Setup**: `source_unavailable_since` is set (>5 minutes ago), last data exists

**Expected**:
```json
{
  "has_data": true,
  "success_rate": 0.91,
  "source_unavailable": true,
  "last_updated_at": "<past timestamp>"
}
```

---

## Scenario 11: Personalized Recommendations — Finance User

**Story**: US4  
**Verifies**: FR-013, SC-006

**Setup**:
- User A has invoked 5 finance agents in the past 30 days
- Similar users (CF) have also used `finance-ops:tax-optimizer` (not yet used by User A)

**Request**:
```
GET /api/v1/marketplace/recommendations?limit=10
```

**Expected**:
- `tax-optimizer` appears in recommendations with `recommendation_type: "collaborative"`
- At least 2 agents not previously used by User A

---

## Scenario 12: Fallback Recommendations — New User

**Story**: US4  
**Verifies**: FR-016

**Setup**: User B has no invocation history

**Expected**:
- `recommendation_type: "fallback"` in response
- Recommendations based on workspace popularity

---

## Scenario 13: Contextual Suggestions — Workflow Step

**Story**: US6  
**Verifies**: FR-024, SC-007

**Request**:
```
POST /api/v1/marketplace/contextual-suggestions
{
  "context_type": "workflow_step",
  "context_text": "sentiment analysis of customer feedback",
  "workspace_id": "uuid",
  "max_results": 5
}
```

**Expected**:
- Agents with NLP/sentiment capabilities returned
- `has_results: true`

---

## Scenario 14: Contextual Suggestions — No Matches

**Story**: US6  
**Verifies**: FR-025

**Request**:
```
POST /api/v1/marketplace/contextual-suggestions
{
  "context_text": "quantum teleportation matrix inversion",
  "context_type": "workflow_step",
  "workspace_id": "uuid"
}
```

**Expected**:
```json
{ "suggestions": [], "has_results": false }
```

---

## Scenario 15: Submit Rating — Valid (Post-Invocation)

**Story**: US5  
**Verifies**: FR-018, FR-019, SC-009

**Setup**: User has 1+ invocations of `finance-ops:report-analyzer` in ClickHouse

**Request**:
```
POST /api/v1/marketplace/agents/{agent_id}/ratings
{ "score": 4, "review_text": "Great for financial analysis" }
```

**Expected**:
- 201 response with rating details
- Subsequent `GET /agents/{id}/quality` shows updated `satisfaction_avg` within 5 seconds

---

## Scenario 16: Submit Rating — Rejected (No Invocation History)

**Story**: US5  
**Verifies**: FR-023

**Setup**: User has never invoked the agent

**Expected**:
```json
{
  "error": "INVOCATION_REQUIRED",
  "message": "You must invoke this agent before submitting a rating."
}
```

HTTP 403

---

## Scenario 17: Update Existing Rating

**Story**: US5  
**Verifies**: FR-021

**Setup**: User already has a 3-star rating for agent

**Request**:
```
POST /api/v1/marketplace/agents/{agent_id}/ratings
{ "score": 5, "review_text": "Updated: even better after latest version" }
```

**Expected**:
- HTTP 200 (updated, not new)
- Aggregate count unchanged (still 1 rating for this user-agent pair)

---

## Scenario 18: Filter Reviews by Score

**Story**: US5  
**Verifies**: FR-020

**Setup**: Agent has 10 reviews: 4× five-star, 3× four-star, 3× three-star

**Request**:
```
GET /api/v1/marketplace/agents/{agent_id}/ratings?score=5
```

**Expected**: 4 results, all with `score: 5`

---

## Scenario 19: Trending Agents Computation

**Story**: US7  
**Verifies**: FR-026, FR-027, FR-028, SC-008

**Setup**:
- Agent X: 50 invocations this week, 5 last week → growth_rate = 10.0
- Agent Y: 1000 invocations this week, 990 last week → growth_rate = 1.01

**After daily trending job runs**:
```
GET /api/v1/marketplace/trending
```

**Expected**:
- Agent X appears with `trending_reason: "10x more invocations this week"`
- Agent Y absent (flat growth)
- `snapshot_date` matches today's date

---

## Scenario 20: Creator Analytics

**Story**: US5  
**Verifies**: FR-022, SC-010

**Setup**: Namespace owner queries analytics for their agent

**Request**:
```
GET /api/v1/marketplace/analytics/{agent_id}
```

**Expected**:
- `invocation_count_total`, `invocation_count_30d` with real counts from ClickHouse
- `common_failure_patterns` top-3 error types
- `invocation_trend` 30-day daily series
- Response in < 2 seconds

---

## Test Configuration Notes

- All search scenarios require OpenSearch `marketplace-agents` index pre-populated (feature 021 fixture)
- Semantic search scenarios require Qdrant `agent_embeddings` collection pre-populated
- Quality signal tests use direct database injection (no live Kafka broker needed in unit tests)
- Creator analytics tests mock ClickHouse client
- Visibility filter tests require workspace service mock returning specific FQN patterns
