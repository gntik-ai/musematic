# Quickstart: Analytics and Cost Intelligence

**Feature**: 020-analytics-cost-intelligence  
**Date**: 2026-04-11

## Prerequisites

- Control plane running with auth + workspaces + execution bounded contexts (features 014, 018, execution)
- Kafka cluster running (feature 003)
- ClickHouse running (feature 007)
- PostgreSQL running (feature 001)

## ClickHouse Setup

The `clickhouse_setup.py` script is idempotent and runs automatically at startup. To run manually:

```bash
cd apps/control-plane
python -m src.platform.analytics.clickhouse_setup
```

This creates:
- `analytics_usage_events` (base table)
- `analytics_quality_events` (base table)
- `analytics_usage_hourly` (materialized view)
- `analytics_usage_daily` (materialized view)
- `analytics_usage_monthly` (materialized view)

## PostgreSQL Migration

```bash
cd apps/control-plane
alembic upgrade head
# Runs migration 005_analytics_cost_models.py
# Creates analytics_cost_models table + seed pricing data
```

## Running the Analytics Consumer

The `AnalyticsPipelineConsumer` runs as part of the `worker` runtime profile:

```bash
cd apps/control-plane
python entrypoints/worker_main.py
# Analytics consumer starts automatically via lifespan
```

Or run directly for development:

```bash
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
CLICKHOUSE_HOST=localhost \
CLICKHOUSE_PORT=8123 \
python -c "
import asyncio
from src.platform.analytics.consumer import AnalyticsPipelineConsumer
consumer = AnalyticsPipelineConsumer(...)
asyncio.run(consumer.start())
"
```

## Running the API

Analytics endpoints are part of the main API profile:

```bash
cd apps/control-plane
uvicorn src.platform.main:app --host 0.0.0.0 --port 8000
```

## Sample API Calls

```bash
# Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"operator@example.com","password":"password123"}' \
  | jq -r '.access_token')

WORKSPACE_ID="a3bb189e-8bf9-3888-9912-ace4e6543002"

# 1. Query daily usage for last 30 days
curl -s "http://localhost:8000/api/v1/analytics/usage?\
workspace_id=${WORKSPACE_ID}&\
start_time=2026-03-11T00:00:00Z&\
end_time=2026-04-11T00:00:00Z&\
granularity=daily" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 2. Get cost intelligence (last 30 days)
curl -s "http://localhost:8000/api/v1/analytics/cost-intelligence?\
workspace_id=${WORKSPACE_ID}&\
start_time=2026-03-11T00:00:00Z&\
end_time=2026-04-11T00:00:00Z" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 3. Get optimization recommendations
curl -s "http://localhost:8000/api/v1/analytics/recommendations?\
workspace_id=${WORKSPACE_ID}" \
  -H "Authorization: Bearer $TOKEN" | jq .

# 4. Get 30-day cost forecast
curl -s "http://localhost:8000/api/v1/analytics/cost-forecast?\
workspace_id=${WORKSPACE_ID}&horizon_days=30" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

## Running Tests

```bash
cd apps/control-plane

# Unit tests (no external dependencies)
pytest tests/unit/test_analytics_*.py -v

# Integration tests (requires running ClickHouse, Kafka, PostgreSQL)
pytest tests/integration/test_analytics_*.py -v --asyncio-mode=auto

# Full analytics test suite
pytest tests/ -k "analytics" --cov=src/platform/analytics --cov-report=term -v
```

## Integration Test Scenarios

### Scenario 1: Pipeline Ingestion

```python
async def test_usage_event_ingested(kafka_producer, clickhouse_client):
    # Produce a workflow.runtime event
    await kafka_producer.produce("workflow.runtime", execution_event(
        execution_id="exec-001",
        agent_fqn="test-ns:test-agent",
        model_id="gpt-4o",
        input_tokens=1000,
        output_tokens=200,
        workspace_id=TEST_WORKSPACE_ID
    ))
    
    # Wait for consumer to process (max 5s)
    await asyncio.wait_for(
        poll_until(lambda: clickhouse_has_event("exec-001")), timeout=5.0
    )
    
    # Verify in ClickHouse
    rows = await clickhouse_client.query(
        "SELECT * FROM analytics_usage_events WHERE execution_id = 'exec-001'"
    )
    assert len(rows.result_rows) == 1
    assert rows.result_rows[0][3] == "test-ns:test-agent"  # agent_fqn
```

### Scenario 2: Usage Rollup Query

```python
async def test_usage_rollup_daily(client, seeded_usage_data, valid_token):
    response = await client.get(
        f"/api/v1/analytics/usage?workspace_id={TEST_WORKSPACE_ID}"
        f"&start_time=2026-04-01T00:00:00Z"
        f"&end_time=2026-04-11T00:00:00Z&granularity=daily",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["granularity"] == "daily"
    assert len(data["items"]) > 0
    # Verify totals match seeded data
    total_cost = sum(item["cost_usd"] for item in data["items"])
    assert abs(total_cost - EXPECTED_TOTAL_COST) < 0.01
```

### Scenario 3: Recommendations Engine

```python
async def test_model_switch_recommendation(client, seeded_model_comparison_data, valid_token):
    # Data seeded: agent "test-ns:agent-a" has runs on expensive and cheap models
    # with similar quality scores
    response = await client.get(
        f"/api/v1/analytics/recommendations?workspace_id={TEST_WORKSPACE_ID}",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 200
    recs = response.json()["recommendations"]
    model_switch_recs = [r for r in recs if r["recommendation_type"] == "model_switch"]
    assert len(model_switch_recs) > 0
    assert model_switch_recs[0]["estimated_savings_usd_per_month"] > 0
    assert model_switch_recs[0]["confidence"] in ["high", "medium", "low"]
```

### Scenario 4: Workspace Authorization

```python
async def test_cross_workspace_access_denied(client, valid_token):
    other_workspace_id = "00000000-0000-0000-0000-000000000001"
    response = await client.get(
        f"/api/v1/analytics/usage?workspace_id={other_workspace_id}"
        f"&start_time=2026-04-01T00:00:00Z&end_time=2026-04-11T00:00:00Z",
        headers={"Authorization": f"Bearer {valid_token}"}
    )
    assert response.status_code == 403
```

## Seeding Cost Model Pricing

The migration seeds initial pricing. To add/update pricing:

```sql
-- Deactivate old pricing
UPDATE analytics_cost_models
SET is_active = false, valid_until = NOW()
WHERE model_id = 'gpt-4o' AND is_active = true;

-- Insert new pricing
INSERT INTO analytics_cost_models 
  (id, model_id, provider, display_name, 
   input_token_cost_usd, output_token_cost_usd, 
   is_active, valid_from)
VALUES 
  (gen_random_uuid(), 'gpt-4o', 'openai', 'GPT-4o',
   0.0000025, 0.0000100, true, NOW());
```

## ClickHouse Verification

```sql
-- Check table counts
SELECT count() FROM analytics_usage_events;
SELECT count() FROM analytics_quality_events;

-- Verify daily rollup is populated
SELECT 
    day,
    countMerge(execution_count_state) AS executions,
    sumMerge(cost_usd_state) AS total_cost
FROM analytics_usage_daily
WHERE workspace_id = 'a3bb189e-8bf9-3888-9912-ace4e6543002'
GROUP BY day
ORDER BY day DESC
LIMIT 10;
```
