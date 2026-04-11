# Quickstart: Context Engineering Service

**Feature**: 022-context-engineering-service  
**Date**: 2026-04-11

---

## Prerequisites

- PostgreSQL with migration `007_context_engineering` applied
- ClickHouse with `context_quality_scores` table created at startup
- MinIO with `context-assembly-records` bucket
- Kafka with `context_engineering.events` topic
- Qdrant (for long-term memory source)
- Control plane API + scheduler profile started

---

## Setup

```bash
cd apps/control-plane
make migrate
# Applies 007_context_engineering.py — context_engineering_profiles,
# context_profile_assignments, context_assembly_records, context_ab_tests, context_drift_alerts

# Verify ClickHouse table created at startup
curl http://localhost:8123/?query=DESCRIBE+context_quality_scores
```

---

## Sample Workflows

### Create a context engineering profile

```bash
curl -X POST http://localhost:8000/api/v1/context-engineering/profiles \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "executor-profile",
    "source_config": [
      {"source_type": "system_instructions", "priority": 100, "enabled": true, "max_elements": 1},
      {"source_type": "conversation_history", "priority": 80, "enabled": true, "max_elements": 15},
      {"source_type": "tool_outputs", "priority": 90, "enabled": true, "max_elements": 10}
    ],
    "budget_config": {"max_tokens_step": 4096},
    "compaction_strategies": ["relevance_truncation", "priority_eviction"]
  }'

# Expect 201 with profile ID
```

### Assign profile to an agent

```bash
PROFILE_ID="<id from create response>"

curl -X POST http://localhost:8000/api/v1/context-engineering/profiles/$PROFILE_ID/assign \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{"assignment_level": "agent", "agent_fqn": "finance-ops:kyc-verifier"}'
```

### Trigger context assembly (in-process, from execution context)

```python
# In apps/control-plane/src/platform/execution/service.py
# Called when agent step begins

bundle = await context_engineering_service.assemble_context(
    execution_id=UUID("exec-abc123"),
    step_id=UUID("step-def456"),
    agent_fqn="finance-ops:kyc-verifier",
    workspace_id=UUID("ws-xyz"),
    goal_id=None,  # no active goal
    profile=None,  # auto-resolve from assignments
    budget=BudgetEnvelope(max_tokens_step=4096),
)

print(f"Quality: {bundle.quality_score:.2f}")
print(f"Tokens: {bundle.token_count}")
print(f"Elements: {len(bundle.elements)}")
print(f"Flags: {bundle.flags}")
```

### Create an A/B test

```bash
curl -X POST http://localhost:8000/api/v1/context-engineering/ab-tests \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "more-memory-sources",
    "control_profile_id": "'$PROFILE_ID'",
    "variant_profile_id": "'$VARIANT_PROFILE_ID'",
    "target_agent_fqn": "finance-ops:kyc-verifier"
  }'
```

### Query drift alerts

```bash
curl "http://localhost:8000/api/v1/context-engineering/drift-alerts?resolved=false" \
  -H "Authorization: Bearer $JWT" \
  -H "X-Workspace-ID: $WORKSPACE_ID"

# Check ClickHouse quality scores
curl 'http://localhost:8123/?query=SELECT+agent_fqn,+avg(quality_score)+as+mean,+stddevPop(quality_score)+as+std,+count()+as+n+FROM+context_quality_scores+WHERE+created_at+>+now()-7*86400+GROUP+BY+agent_fqn'
```

---

## Integration Test Scenarios

### Scenario 1: Deterministic assembly
1. Create profile with 3 sources enabled
2. Assign to agent "test-ns:test-agent"
3. Call `assemble_context()` with execution_id=A, step_id=B
4. Capture bundle hash (hash of element IDs + content)
5. Call again with same inputs
6. Verify bundle hash identical → determinism confirmed
7. Check `ContextAssemblyRecord` created with provenance chain
8. Verify each element has `provenance.origin`, `timestamp`, `authority_score`

### Scenario 2: Budget enforcement and compaction
1. Create profile with 4 sources, budget max_tokens_step=1000
2. Seed conversation history with 5000 tokens of content
3. Call `assemble_context()` — verify token_count_post ≤ 1000
4. Verify `compaction_applied=true` in assembly record
5. Verify system_instructions always present (minimum viable context)
6. Verify `quality_score_pre` and `quality_score_post` both present in record
7. Set budget to 100 tokens (below minimum viable) — verify budget_exceeded_minimum flag

### Scenario 3: Privacy filtering
1. Create a context source with data_classification=confidential
2. Configure agent without confidential access
3. Call `assemble_context()` — verify confidential elements excluded
4. Check assembly record `privacy_exclusions` list — verify exclusion logged with policy_id
5. Same setup, but grant agent confidential access — verify elements now included

### Scenario 4: Drift detection
1. Seed ClickHouse `context_quality_scores` with 7 days of scores: mean=0.82, stddev=0.04
2. Trigger 50 assemblies with mocked quality_score=0.55 (< 0.82 - 2*0.04 = 0.74)
3. Wait for drift monitor to run (or trigger manually)
4. Verify `ContextDriftAlert` created with correct historical_mean, recent_mean, degradation_delta
5. Verify `context_engineering.drift.detected` event emitted on Kafka

### Scenario 5: A/B test group assignment
1. Create A/B test (control vs variant profiles) for agent "test-ns:agent"
2. Trigger 100 assemblies for the agent
3. Query assembly records — verify ~50 control, ~50 variant (within 5% of 50/50)
4. Check `context_ab_tests` table metrics updated
5. End the test — verify status=completed, final metrics present

---

## Kafka Verification

```bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 \
  --topic context_engineering.events --from-beginning

# After assembly, expect:
# {"event_type": "context_engineering.assembly.completed",
#  "payload": {"assembly_id": "...", "agent_fqn": "...", "quality_score": 0.82, ...}}

# After drift detection:
# {"event_type": "context_engineering.drift.detected",
#  "payload": {"alert_id": "...", "agent_fqn": "...", "degradation_delta": 0.19}}
```

---

## Database Verification

```sql
-- Assembly records with compaction
SELECT execution_id, quality_score_pre, quality_score_post, token_count_post, compaction_applied, flags
FROM context_assembly_records
WHERE compaction_applied = true
ORDER BY created_at DESC
LIMIT 10;

-- Active drift alerts
SELECT agent_fqn, historical_mean, recent_mean, degradation_delta, created_at
FROM context_drift_alerts
WHERE resolved_at IS NULL
ORDER BY degradation_delta DESC;

-- A/B test progress
SELECT name, status, control_assembly_count, variant_assembly_count,
       control_quality_mean, variant_quality_mean
FROM context_ab_tests
WHERE status = 'active';
```
