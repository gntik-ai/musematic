# Quickstart Test Scenarios: Workspace Goal Management and Agent Response Decision

**Phase 1 output for**: [plan.md](plan.md)
**Date**: 2026-04-18

Each scenario is independently verifiable. Scenarios 1–3 cover goal lifecycle. Scenarios 4–8 cover response decision strategies. Scenarios 9–10 cover best-match. Scenarios 11–12 cover auto-completion. Scenario 13 covers decision rationale. Scenarios 14–15 cover edge cases.

---

## Scenario 1 — READY → WORKING on First Message

**Setup**: Workspace exists. Goal created (state should be READY). Two agents subscribed with default `llm_relevance` strategy configs.

```bash
# 1. Create a goal
POST /api/v1/workspaces/{workspace_id}/goals
{"title": "Deploy v2.3 to production", "description": "..."}
# Expected: 201, body.state = "ready"

# 2. Verify goal state is READY
SELECT state FROM workspaces_goals WHERE id = '<goal_id>';
# Expected: ready

# 3. Post the first message
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Can someone review the deployment checklist?"}
# Expected: 201

# 4. Verify goal transitioned to WORKING
SELECT state FROM workspaces_goals WHERE id = '<goal_id>';
# Expected: working

# 5. Verify last_message_at was set
SELECT last_message_at FROM workspaces_goals WHERE id = '<goal_id>';
# Expected: non-null timestamp, within last 2 seconds

# 6. Post a second message
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Checklist LGTM, ready to deploy"}
# Expected: 201, goal state remains working (no re-transition)

SELECT state FROM workspaces_goals WHERE id = '<goal_id>';
# Expected: still 'working'
```

---

## Scenario 2 — COMPLETE State Blocks New Messages

**Setup**: Goal in WORKING state with existing messages.

```bash
# 1. Transition goal to COMPLETE
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition
{"target_state": "complete", "reason": "Deployment successful"}
# Expected: 200, body.new_state = "complete", body.automatic = false

# 2. Attempt to post a new message
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "One more thing..."}
# Expected: 409 Conflict
# Body: {"code": "goal_state_conflict", "message": "Goal is complete..."}

# 3. Verify existing messages are still readable
GET /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
# Expected: 200, existing messages all present

# 4. Verify no new message was stored
SELECT COUNT(*) FROM workspace_goal_messages WHERE goal_id = '<goal_id>';
# Expected: same count as before the rejected post
```

---

## Scenario 3 — COMPLETE is Terminal (No Re-transition)

```bash
# Attempt to re-open a completed goal
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition
{"target_state": "complete"}
# When already complete: Expected 409 Conflict
# {"code": "goal_state_conflict", "message": "...already in terminal state COMPLETE"}

# Attempt nonsensical target
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/transition
{"target_state": "ready"}
# Expected: 400 Bad Request (or 409 — "only COMPLETE is an allowed target")
```

---

## Scenario 4 — Keyword Decision Strategy (any_of)

**Setup**: Agent `hr-ops:deploy-bot` configured with keyword strategy.

```bash
# 1. Configure keyword strategy
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/hr-ops%3Adeploy-bot
{
  "response_decision_strategy": "keyword",
  "response_decision_config": {
    "keywords": ["deploy", "release", "rollback"],
    "mode": "any_of"
  }
}
# Expected: 200 or 201

# 2. Post a message containing a matching keyword
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Please rollback the last deploy"}
# Expected: 201

# 3. Verify decision rationale recorded with "respond"
SELECT decision, matched_terms, strategy_name
FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'hr-ops:deploy-bot';
# Expected: decision='respond', matched_terms CONTAINS 'rollback', strategy_name='keyword'

# 4. Post a message with no matching keywords
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Let's schedule a meeting to review the roadmap"}
# Expected: 201

SELECT decision, rationale FROM workspace_goal_decision_rationales
WHERE message_id = '<new_message_id>' AND agent_fqn = 'hr-ops:deploy-bot';
# Expected: decision='skip', rationale contains "no keyword match"
```

---

## Scenario 5 — Allow/Blocklist Decision Strategy

**Setup**: Agent `legal-ops:compliance-bot` configured with blocklist on "personal".

```bash
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/legal-ops%3Acompliance-bot
{
  "response_decision_strategy": "allow_blocklist",
  "response_decision_config": {
    "blocklist": ["personal", "confidential"],
    "allowlist": ["compliance", "audit"],
    "default": "skip"
  }
}

# Post message hitting blocklist
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Export personal data for this user"}

SELECT decision, matched_terms FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'legal-ops:compliance-bot';
# Expected: decision='skip', matched_terms CONTAINS 'personal'

# Post message hitting allowlist (no blocklist match)
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Run the quarterly audit report"}

SELECT decision FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'legal-ops:compliance-bot';
# Expected: decision='respond'
```

---

## Scenario 6 — LLM Relevance Strategy (threshold)

**Setup**: Agent configured with `llm_relevance`, threshold 0.7. LLM mock returns score 0.82 for relevant message.

```bash
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Arelevance-bot
{
  "response_decision_strategy": "llm_relevance",
  "response_decision_config": {"threshold": 0.7}
}

# Post relevant message (mock LLM returns 0.82)
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "The CI pipeline is failing on the deployment step"}

SELECT decision, score FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'ops:relevance-bot';
# Expected: decision='respond', score=0.82

# Post irrelevant message (mock LLM returns 0.34)
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Happy birthday to the team!"}

SELECT decision, score FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'ops:relevance-bot';
# Expected: decision='skip', score=0.34, rationale contains "below threshold 0.70"
```

---

## Scenario 7 — Strategy Config Error (Unknown Strategy Name)

```bash
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Abroken-bot
{
  "response_decision_strategy": "nonexistent_strategy",
  "response_decision_config": {}
}
# Expected: 422 Unprocessable Entity (validation at config time)

# If somehow a bad config reaches the engine at evaluation time:
SELECT decision, error FROM workspace_goal_decision_rationales
WHERE agent_fqn = 'ops:broken-bot' ORDER BY created_at DESC LIMIT 1;
# Expected: decision='skip', error IS NOT NULL (fail-safe)
```

---

## Scenario 8 — Strategy Evaluation Failure (Service Timeout)

**Setup**: Mock the LLM API to return HTTP 504 for one call.

```bash
# Post a message to trigger LLM strategy evaluation with mock timeout
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Deploy the service"}

# Verify fail-safe: decision is 'skip' with error recorded, not a crash
SELECT decision, error FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'ops:relevance-bot';
# Expected: decision='skip', error LIKE '%timeout%' or '%504%'
# Verify: the POST returned 201 (message was accepted), not 500
```

---

## Scenario 9 — Best-Match: Single Responder Selected

**Setup**: Three agents subscribed. Agent A scores 0.82, B scores 0.71, C scores 0.45.

```bash
# Configure all three agents with best_match strategy
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Aagent-a
{"response_decision_strategy": "best_match", "response_decision_config": {}}
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Aagent-b
{"response_decision_strategy": "best_match", "response_decision_config": {}}
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Aagent-c
{"response_decision_strategy": "best_match", "response_decision_config": {}}

# Post a message
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Deploy the service now"}

# Verify exactly one agent has decision='respond'
SELECT agent_fqn, decision, score FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' ORDER BY score DESC;
# Expected:
#   ops:agent-a | respond | 0.82
#   ops:agent-b | skip    | 0.71   (rationale: "not selected in best-match")
#   ops:agent-c | skip    | 0.45   (rationale: "not selected in best-match")
```

---

## Scenario 10 — Best-Match Tie-Breaking

**Setup**: Agents A and B both score 0.82. Agent A subscribed earlier.

```bash
# Verify subscribed_at ordering determines winner
SELECT agent_fqn, subscribed_at FROM workspaces_agent_decision_configs
WHERE workspace_id = '<workspace_id>' ORDER BY subscribed_at;
# Expected: ops:agent-a has earlier subscribed_at

POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Tied-score message"}

SELECT agent_fqn, decision, rationale FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>';
# Expected:
#   ops:agent-a | respond | (selected — earliest subscription, tie-break)
#   ops:agent-b | skip    | (tie-break: agent-a subscribed earlier)
```

---

## Scenario 11 — Auto-Completion Timeout

**Setup**: Goal created with `auto_complete_timeout_seconds = 60`. Feature flag `FEATURE_GOAL_AUTO_COMPLETE=true`.

```bash
# 1. Create goal with timeout
POST /api/v1/workspaces/{workspace_id}/goals
{"title": "Quick task", "auto_complete_timeout_seconds": 60}
# Expected: 201

# 2. Post one message (triggers READY → WORKING, sets last_message_at)
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Starting the task"}

# 3. Wait 65 seconds without posting
sleep 65

# 4. Verify goal auto-completed
SELECT state FROM workspaces_goals WHERE id = '<goal_id>';
# Expected: 'complete'

# 5. Verify auto-completion audit event emitted
# (check Kafka workspace.goal topic or audit log)
# Expected: event_type='workspace.goal.state_changed', payload.automatic=true

# 6. Verify timeout reset on new message
# Create a new WORKING goal with 60s timeout, post within 30s, wait 40s more (total 70s
# but only 40s since last message) — goal should still be WORKING
SELECT state FROM workspaces_goals WHERE id = '<second_goal_id>';
# Expected: 'working' (last_message_at + 60s > now)
```

---

## Scenario 12 — Auto-Completion: null/zero Timeout = Never

```bash
# Goal with null timeout
POST /api/v1/workspaces/{workspace_id}/goals
{"title": "Long-running task"}
# No auto_complete_timeout_seconds field (null)

POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "Starting"}

# Wait 120 seconds
sleep 120

# Scanner runs — should NOT auto-complete
SELECT state FROM workspaces_goals WHERE id = '<goal_id>';
# Expected: 'working' (null timeout means never auto-complete)
```

---

## Scenario 13 — Decision Rationale Query

```bash
# After posting several messages to a goal with multiple subscribed agents:

# Query rationale for a specific message
GET /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages/{message_id}/rationale
# Expected: 200, items contains one entry per subscribed agent
# Each entry has: strategy_name, decision, score (if applicable), matched_terms, rationale
# No entry should contain a credential, API key, or full raw message body

# Verify no secrets in rationale fields:
python3 -c "
import json, re, sys
data = json.loads(sys.stdin.read())
secret_pattern = re.compile(r'[A-Za-z0-9+/]{40,}')
for item in data['items']:
    text = json.dumps(item)
    if secret_pattern.search(text):
        print('WARNING: possible secret in rationale:', item['id'])
        sys.exit(1)
print('OK: no secrets detected')
" < response.json
```

---

## Scenario 14 — Concurrent Message Post vs. Transition (Race Condition)

**Automated stress scenario** (integration test):

```python
import asyncio

async def test_concurrent_complete_and_post():
    # Simulate concurrent: admin completes goal + user posts message
    # at exactly the same instant using asyncio.gather
    results = await asyncio.gather(
        transition_goal(goal_id, "complete"),
        post_message(goal_id, "last second message"),
        return_exceptions=True,
    )
    # One must succeed, one must fail — never both succeed
    statuses = [r.status_code if hasattr(r, 'status_code') else 200 for r in results]
    assert set(statuses) <= {200, 201, 409}, f"Unexpected statuses: {statuses}"
    assert not all(s in (200, 201) for s in statuses), \
        "Both operations succeeded — atomicity violated"

    # Verify goal state is consistent
    goal = await get_goal(goal_id)
    if goal['state'] == 'complete':
        # If goal completed, verify new message count matches only accepted messages
        messages = await list_messages(goal_id)
        # All messages in DB must have been posted before COMPLETE
```

---

## Scenario 15 — Config Change Takes Effect on Next Message

```bash
# Agent currently using llm_relevance
PUT /api/v1/workspaces/{workspace_id}/agent-decision-configs/ops%3Abot
{"response_decision_strategy": "keyword", "response_decision_config": {"keywords": ["urgent"]}}
# Expected: 200

# Immediately post a message
POST /api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages
{"content": "This is urgent — check the alerts"}

# Verify new keyword strategy was used (not the old llm_relevance)
SELECT strategy_name, decision, matched_terms FROM workspace_goal_decision_rationales
WHERE message_id = '<message_id>' AND agent_fqn = 'ops:bot';
# Expected: strategy_name='keyword', matched_terms CONTAINS 'urgent', decision='respond'
# New strategy is applied within 5 seconds of config update (SC-011)
```
