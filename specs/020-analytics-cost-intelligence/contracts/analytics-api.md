# REST API Contracts: Analytics and Cost Intelligence

**Feature**: 020-analytics-cost-intelligence  
**Date**: 2026-04-11  
**Base path**: `/api/v1/analytics`  
**Authentication**: Bearer JWT (all endpoints require authenticated user)

---

## Endpoints

### 1. GET /api/v1/analytics/usage

Query aggregated usage data for a workspace, filtered by time range, agent, and model.

**Authorization**: User must be a member of the requested workspace.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace_id` | UUID | Yes | Workspace to query |
| `start_time` | ISO 8601 datetime | Yes | Start of query window (inclusive) |
| `end_time` | ISO 8601 datetime | Yes | End of query window (inclusive) |
| `granularity` | string | No | `hourly` / `daily` / `monthly` (default: `daily`) |
| `agent_fqn` | string | No | Filter by specific agent (e.g., `finance-ops:kyc-verifier`) |
| `model_id` | string | No | Filter by model (e.g., `gpt-4o`) |
| `limit` | integer | No | Max items returned (default: 100, max: 1000) |
| `offset` | integer | No | Pagination offset (default: 0) |

**Response 200**:

```json
{
  "workspace_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "granularity": "daily",
  "start_time": "2026-04-01T00:00:00Z",
  "end_time": "2026-04-11T00:00:00Z",
  "total": 42,
  "items": [
    {
      "period": "2026-04-10T00:00:00Z",
      "workspace_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
      "agent_fqn": "finance-ops:kyc-verifier",
      "model_id": "gpt-4o",
      "provider": "openai",
      "execution_count": 47,
      "input_tokens": 125400,
      "output_tokens": 34200,
      "total_tokens": 159600,
      "cost_usd": 4.788,
      "avg_duration_ms": 2340.5,
      "self_correction_loops": 12
    }
  ]
}
```

**Response 400**: `workspace_id` missing or `start_time` > `end_time`  
**Response 403**: User not a member of the workspace  
**Response 422**: Invalid parameter format

---

### 2. GET /api/v1/analytics/cost-intelligence

Returns cost-per-quality analysis for all agents in a workspace, ranked by cost efficiency.

**Authorization**: User must be a member of the requested workspace.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace_id` | UUID | Yes | Workspace to analyze |
| `start_time` | ISO 8601 datetime | Yes | Analysis window start |
| `end_time` | ISO 8601 datetime | Yes | Analysis window end |

**Response 200**:

```json
{
  "workspace_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "period_start": "2026-03-11T00:00:00Z",
  "period_end": "2026-04-11T00:00:00Z",
  "agents": [
    {
      "agent_fqn": "finance-ops:risk-scorer",
      "model_id": "claude-3-5-haiku",
      "provider": "anthropic",
      "total_cost_usd": 12.45,
      "avg_quality_score": 0.91,
      "cost_per_quality": 13.68,
      "execution_count": 320,
      "efficiency_rank": 1
    },
    {
      "agent_fqn": "finance-ops:kyc-verifier",
      "model_id": "gpt-4o",
      "provider": "openai",
      "total_cost_usd": 87.30,
      "avg_quality_score": 0.89,
      "cost_per_quality": 98.09,
      "execution_count": 890,
      "efficiency_rank": 2
    },
    {
      "agent_fqn": "finance-ops:doc-extractor",
      "model_id": "gpt-4o",
      "provider": "openai",
      "total_cost_usd": 145.60,
      "avg_quality_score": null,
      "cost_per_quality": null,
      "execution_count": 1240,
      "efficiency_rank": 3
    }
  ]
}
```

**Notes**:
- Agents without quality scores have `avg_quality_score: null` and `cost_per_quality: null`
- Agents ranked by `cost_per_quality` ascending (most efficient first); null last
- Same agent FQN on multiple models appears as separate entries

**Response 400**: `workspace_id` missing or window invalid  
**Response 403**: User not a member

---

### 3. GET /api/v1/analytics/recommendations

Returns actionable optimization recommendations for a workspace based on historical data.

**Authorization**: User must be a member of the requested workspace.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace_id` | UUID | Yes | Workspace to analyze |

**Response 200**:

```json
{
  "workspace_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "generated_at": "2026-04-11T14:30:00Z",
  "recommendations": [
    {
      "recommendation_type": "model_switch",
      "agent_fqn": "finance-ops:kyc-verifier",
      "title": "Switch to claude-3-5-haiku for cost savings",
      "description": "Based on 450 executions, finance-ops:kyc-verifier achieves similar quality (0.89 avg) on claude-3-5-haiku vs. gpt-4o (0.91 avg), at 68% lower cost.",
      "estimated_savings_usd_per_month": 234.50,
      "confidence": "high",
      "data_points": 450,
      "supporting_data": {
        "current_model": "gpt-4o",
        "suggested_model": "claude-3-5-haiku",
        "current_avg_quality": 0.91,
        "suggested_avg_quality": 0.89,
        "current_avg_cost_per_execution": 0.098,
        "suggested_avg_cost_per_execution": 0.031
      }
    },
    {
      "recommendation_type": "self_correction_tuning",
      "agent_fqn": "finance-ops:doc-extractor",
      "title": "High self-correction loop count",
      "description": "finance-ops:doc-extractor averages 4.2 self-correction loops per execution — 2.8x above the workspace average of 1.5. Consider reviewing the agent's output contracts or increasing its reasoning budget.",
      "estimated_savings_usd_per_month": 89.20,
      "confidence": "medium",
      "data_points": 67,
      "supporting_data": {
        "agent_avg_loops": 4.2,
        "workspace_avg_loops": 1.5,
        "excess_ratio": 2.8,
        "cost_per_retry": 0.043
      }
    }
  ]
}
```

**Response 400**: `workspace_id` missing  
**Response 403**: User not a member

---

### 4. GET /api/v1/analytics/cost-forecast

Returns a projected cost forecast for the next 7, 30, or 90 days based on historical trends.

**Authorization**: User must be a member of the requested workspace.

**Query Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `workspace_id` | UUID | Yes | Workspace to forecast |
| `horizon_days` | integer | No | Forecast horizon: 7, 30, or 90 (default: 30) |

**Response 200**:

```json
{
  "workspace_id": "a3bb189e-8bf9-3888-9912-ace4e6543002",
  "horizon_days": 30,
  "generated_at": "2026-04-11T14:30:00Z",
  "trend_direction": "increasing",
  "high_volatility": false,
  "data_points_used": 30,
  "warning": null,
  "total_projected_low": 1240.50,
  "total_projected_expected": 1487.30,
  "total_projected_high": 1734.10,
  "daily_forecast": [
    {
      "date": "2026-04-12T00:00:00Z",
      "projected_cost_usd_low": 38.50,
      "projected_cost_usd_expected": 46.20,
      "projected_cost_usd_high": 53.90
    },
    {
      "date": "2026-04-13T00:00:00Z",
      "projected_cost_usd_low": 39.10,
      "projected_cost_usd_expected": 46.90,
      "projected_cost_usd_high": 54.70
    }
  ]
}
```

**Insufficient data example**:

```json
{
  "workspace_id": "a3bb189e-...",
  "horizon_days": 30,
  "generated_at": "2026-04-11T14:30:00Z",
  "trend_direction": "stable",
  "high_volatility": false,
  "data_points_used": 4,
  "warning": "Insufficient historical data — forecast based on 4 days of data. Accuracy will improve with more history.",
  "total_projected_low": 140.00,
  "total_projected_expected": 175.00,
  "total_projected_high": 210.00,
  "daily_forecast": [ ... ]
}
```

**Response 400**: `workspace_id` missing or `horizon_days` not in [7, 30, 90]  
**Response 403**: User not a member

---

## Internal Service Interface

The analytics bounded context exposes one internal interface used by other contexts:

### get_workspace_cost_summary(workspace_id, days_back) → dict

Used by the notifications context to check budget threshold crossings.

```python
async def get_workspace_cost_summary(
    workspace_id: UUID,
    days_back: int = 30
) -> dict:
    """Returns: {
        "total_cost_usd": float,
        "period_start": datetime,
        "period_end": datetime,
        "execution_count": int,
        "avg_daily_cost_usd": float
    }"""
```

---

## Error Response Format

All error responses follow the platform standard:

```json
{
  "error_code": "WORKSPACE_NOT_FOUND",
  "message": "Workspace a3bb189e-... not found or you do not have access",
  "details": {}
}
```

| HTTP Status | error_code | Meaning |
|-------------|------------|---------|
| 400 | `INVALID_PARAMETERS` | Missing required params or invalid values |
| 403 | `WORKSPACE_ACCESS_DENIED` | User not a workspace member |
| 404 | `WORKSPACE_NOT_FOUND` | Workspace does not exist |
| 503 | `ANALYTICS_STORE_UNAVAILABLE` | ClickHouse temporarily unreachable |
