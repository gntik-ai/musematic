# API Contract: Marketplace Discovery and Intelligence

**Feature**: 030-marketplace-discovery-intelligence  
**Date**: 2026-04-12  
**Router prefix**: `/api/v1/marketplace`  
**Auth**: JWT Bearer (all endpoints require authenticated user)

---

## Search and Browse

### `POST /api/v1/marketplace/search`

Search for agents using natural language + optional facet filters.

**Request body**:
```json
{
  "query": "analyze financial reports",
  "tags": ["finance"],
  "capabilities": [],
  "maturity_level_min": 2,
  "maturity_level_max": null,
  "trust_tier": ["certified", "trusted"],
  "certification_status": [],
  "cost_tier": [],
  "page": 1,
  "page_size": 20
}
```

**Response 200**:
```json
{
  "results": [
    {
      "agent_id": "uuid",
      "fqn": "finance-ops:report-analyzer",
      "name": "Report Analyzer",
      "description": "...",
      "capabilities": ["financial_analysis", "document_parsing"],
      "tags": ["finance", "reports"],
      "maturity_level": 3,
      "trust_tier": "certified",
      "certification_status": "compliant",
      "cost_tier": "metered",
      "quality_profile": {
        "success_rate": 0.94,
        "quality_score_avg": 82.5,
        "self_correction_rate": 0.08,
        "satisfaction_avg": 4.3,
        "satisfaction_count": 47,
        "certification_compliance": "compliant",
        "last_updated_at": "2026-04-12T10:00:00Z",
        "source_unavailable": false
      },
      "aggregate_rating": {
        "avg_score": 4.3,
        "review_count": 47
      },
      "relevance_score": 0.923
    }
  ],
  "total": 3,
  "page": 1,
  "page_size": 20,
  "query": "analyze financial reports",
  "has_results": true
}
```

**Response 200 (empty query — browse mode)**:
Same structure, `query` is `""`, results ordered by `invocation_count_30d` descending.

**Response 200 (no results)**:
```json
{
  "results": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "query": "xyzzy123",
  "has_results": false
}
```

**Notes**:
- Workspace visibility filter applied automatically from JWT workspace context
- Agents outside user's visibility scope never appear
- Empty `query` triggers popularity-ordered browse mode (FR-005)

---

### `GET /api/v1/marketplace/agents/{agent_id}`

Get a single agent's full marketplace listing.

**Response 200**: Single `AgentListingProjection` object (same fields as search result, no `relevance_score`)

**Response 403**: Agent exists but outside user's visibility scope  
**Response 404**: Agent not found in registry

---

### `GET /api/v1/marketplace/compare`

Side-by-side comparison of 2 to 4 agents.

**Query params**: `agent_ids=uuid1,uuid2,uuid3` (comma-separated, 2–4 values)

**Response 200**:
```json
{
  "agents": [
    {
      "agent_id": "uuid1",
      "fqn": "finance-ops:report-analyzer",
      "name": "Report Analyzer",
      "capabilities": { "value": ["financial_analysis", "parsing"], "differs": true },
      "maturity_level": { "value": 3, "differs": true },
      "trust_tier": { "value": "certified", "differs": false },
      "certification_status": { "value": "compliant", "differs": false },
      "quality_score_avg": { "value": 82.5, "differs": true },
      "cost_tier": { "value": "metered", "differs": false },
      "success_rate": { "value": 0.94, "differs": true },
      "user_rating_avg": { "value": 4.3, "differs": true }
    }
  ],
  "compared_count": 3
}
```

**Response 400**:
```json
{
  "error": "COMPARISON_RANGE_INVALID",
  "message": "Please select between 2 and 4 agents to compare.",
  "provided": 1
}
```

**Response 403**: One or more agents outside user's visibility scope

---

## Quality Signals

### `GET /api/v1/marketplace/agents/{agent_id}/quality`

Get full quality profile for an agent.

**Response 200**:
```json
{
  "agent_id": "uuid",
  "has_data": true,
  "success_rate": 0.94,
  "quality_score_avg": 82.5,
  "self_correction_rate": 0.08,
  "satisfaction_avg": 4.3,
  "satisfaction_count": 47,
  "certification_compliance": "compliant",
  "last_updated_at": "2026-04-12T10:00:00Z",
  "source_unavailable": false
}
```

**Response 200 (no data)**:
```json
{
  "agent_id": "uuid",
  "has_data": false,
  "success_rate": null,
  "quality_score_avg": null,
  "self_correction_rate": null,
  "satisfaction_avg": null,
  "satisfaction_count": 0,
  "certification_compliance": "uncertified",
  "last_updated_at": null,
  "source_unavailable": false
}
```

**Response 200 (stale data)**:
```json
{
  "has_data": true,
  "success_rate": 0.91,
  "last_updated_at": "2026-04-10T14:00:00Z",
  "source_unavailable": true
}
```

---

## Ratings and Reviews

### `POST /api/v1/marketplace/agents/{agent_id}/ratings`

Submit or update a rating for an agent (requires prior invocation).

**Request body**:
```json
{
  "score": 4,
  "review_text": "Great for financial analysis, handles edge cases well."
}
```

**Response 201 (created) / 200 (updated)**:
```json
{
  "rating_id": "uuid",
  "agent_id": "uuid",
  "user_id": "uuid",
  "score": 4,
  "review_text": "Great for financial analysis...",
  "created_at": "2026-04-12T10:00:00Z",
  "updated_at": "2026-04-12T10:00:00Z"
}
```

**Response 403**:
```json
{
  "error": "INVOCATION_REQUIRED",
  "message": "You must invoke this agent before submitting a rating."
}
```

**Response 422**: Validation error (score out of 1-5 range)

---

### `GET /api/v1/marketplace/agents/{agent_id}/ratings`

List reviews for an agent.

**Query params**:
- `score` (int, optional): Filter by exact score (1-5)
- `sort` (`recent` | `highest` | `lowest`, default: `recent`)
- `page` (int, default: 1)
- `page_size` (int, default: 20, max: 100)

**Response 200**:
```json
{
  "ratings": [
    {
      "rating_id": "uuid",
      "agent_id": "uuid",
      "user_id": "uuid",
      "score": 5,
      "review_text": "Excellent performance on quarterly reports.",
      "created_at": "2026-04-11T09:00:00Z",
      "updated_at": "2026-04-11T09:00:00Z"
    }
  ],
  "total": 47,
  "page": 1,
  "page_size": 20,
  "avg_score": 4.3
}
```

---

### `GET /api/v1/marketplace/analytics/{agent_id}`

Creator analytics dashboard for an agent. Only accessible by the agent's namespace owner.

**Response 200**:
```json
{
  "agent_id": "uuid",
  "agent_fqn": "finance-ops:report-analyzer",
  "invocation_count_total": 1250,
  "invocation_count_30d": 340,
  "avg_satisfaction": 4.3,
  "satisfaction_count": 47,
  "common_failure_patterns": [
    { "error_type": "timeout", "count": 12, "percentage": 15.4 },
    { "error_type": "validation_error", "count": 8, "percentage": 10.3 },
    { "error_type": "upstream_unavailable", "count": 3, "percentage": 3.8 }
  ],
  "invocation_trend": [
    { "date": "2026-03-14", "count": 8 },
    { "date": "2026-03-15", "count": 11 }
  ]
}
```

**Response 403**: Requesting user does not own the agent's namespace

---

## Recommendations

### `GET /api/v1/marketplace/recommendations`

Get personalized agent recommendations for the current user.

**Query params**:
- `limit` (int, default: 10, max: 20)
- `workspace_id` (UUID, optional — defaults to current workspace from JWT)

**Response 200**:
```json
{
  "recommendations": [
    {
      "agent": { /* AgentListingProjection */ },
      "score": 0.87,
      "reasoning": "Used by similar users in finance workspaces",
      "recommendation_type": "collaborative"
    }
  ],
  "recommendation_type": "personalized"
}
```

**Response 200 (fallback)**:
```json
{
  "recommendations": [ /* top agents by workspace popularity */ ],
  "recommendation_type": "fallback"
}
```

---

### `POST /api/v1/marketplace/contextual-suggestions`

Get agent suggestions based on current workbench context.

**Request body**:
```json
{
  "context_type": "workflow_step",
  "context_text": "Extract named entities from email body for CRM sync",
  "workspace_id": "uuid",
  "max_results": 5
}
```

**Response 200**:
```json
{
  "suggestions": [
    { /* AgentListingProjection */ }
  ],
  "has_results": true,
  "context_type": "workflow_step"
}
```

**Response 200 (no matches)**:
```json
{
  "suggestions": [],
  "has_results": false,
  "context_type": "workflow_step"
}
```

---

## Trending

### `GET /api/v1/marketplace/trending`

Get currently trending agents.

**Query params**:
- `limit` (int, default: 20, max: 20)
- `workspace_id` (UUID, optional)

**Response 200**:
```json
{
  "agents": [
    {
      "rank": 1,
      "agent": { /* AgentListingProjection */ },
      "trending_score": 8.2,
      "growth_rate": 10.3,
      "invocations_this_week": 103,
      "invocations_last_week": 10,
      "trending_reason": "10x more invocations this week",
      "satisfaction_delta": 0.4
    }
  ],
  "snapshot_date": "2026-04-12",
  "total": 15
}
```

---

## Internal Service Interfaces

### Consumed by other bounded contexts

```python
# Called by workflows/ and execution/ when assembling context
MarketplaceSearchService.get_listing(agent_id: UUID, workspace_id: UUID) -> AgentListingProjection

# Called by workbenches/ BFF layer
MarketplaceRecommendationService.get_contextual_suggestions(
    request: ContextualSuggestionRequest,
    user_id: UUID
) -> ContextualSuggestionResponse
```

### Kafka consumed (quality aggregate pipeline)

| Topic | Event type | Handler |
|---|---|---|
| `workflow.runtime` | `step.completed`, `step.failed`, `step.self_corrected` | `quality_service.handle_execution_event` |
| `evaluation.events` | `evaluation.scored` | `quality_service.handle_evaluation_event` |
| `trust.events` | `certification.status_changed` | `quality_service.handle_trust_event` |

### Kafka produced

| Topic | Key | Events |
|---|---|---|
| `marketplace.events` | `agent_id` | `marketplace.rating.created`, `marketplace.rating.updated`, `marketplace.trending_updated` |
