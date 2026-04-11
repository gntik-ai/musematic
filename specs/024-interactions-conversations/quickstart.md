# Quickstart: Interactions and Conversations

**Feature**: 024-interactions-conversations  
**Date**: 2026-04-11

---

## Prerequisites

```bash
# Verify required infrastructure
docker ps | grep -E "postgres|kafka"
# Or via kubectl
kubectl get pods -n platform-data | grep postgres
kubectl get pods -n platform-kafka
```

Required services: PostgreSQL, Kafka.

---

## Run Migrations

```bash
cd apps/control-plane

# Apply migration 009 (interactions and conversations tables)
alembic upgrade head

# Verify
alembic current
# Expected: 009_interactions_conversations (head)
```

---

## Start the API

```bash
cd apps/control-plane

# API profile
uvicorn src.platform.entrypoints.api_main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Smoke Test

```bash
TOKEN="your-jwt-token"

# 1. Create a conversation
curl -X POST http://localhost:8000/api/v1/interactions/conversations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Q2 Report Discussion"}'
# Expected: 201, ConversationResponse with id

# 2. Create an interaction in the conversation
curl -X POST http://localhost:8000/api/v1/interactions/ \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"conversation_id": "<conversation-id>"}'
# Expected: 201, InteractionResponse with state "initializing"

# 3. Transition to running
curl -X POST http://localhost:8000/api/v1/interactions/<interaction-id>/transition \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"trigger": "ready"}'
# Then:
curl -X POST http://localhost:8000/api/v1/interactions/<interaction-id>/transition \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"trigger": "start"}'
# Expected: 200, state "running"

# 4. Send a message
curl -X POST http://localhost:8000/api/v1/interactions/<interaction-id>/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Analyze the Q2 sales data.", "message_type": "user"}'
# Expected: 201, MessageResponse

# 5. Inject a mid-process message
curl -X POST http://localhost:8000/api/v1/interactions/<interaction-id>/inject \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Also include the EU region data."}'
# Expected: 201, MessageResponse with message_type "injection"

# 6. Post a workspace goal message
curl -X POST http://localhost:8000/api/v1/workspaces/<workspace-id>/goals/<goal-id>/messages \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content": "Q2 report draft is ready for review."}'
# Expected: 201, GoalMessageResponse

# 7. Create an attention request
curl -X POST http://localhost:8000/api/v1/interactions/attention \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "target_identity": "user-123",
    "urgency": "high",
    "context_summary": "Found conflicting data in sales reports.",
    "related_interaction_id": "<interaction-id>"
  }'
# Expected: 201, AttentionRequestResponse

# 8. List my attention requests
curl http://localhost:8000/api/v1/interactions/attention?status=pending \
  -H "Authorization: Bearer $TOKEN"
# Expected: 200, list with the attention request above
```

---

## Run Tests

```bash
cd apps/control-plane

# Unit tests
pytest tests/unit/ -k "interactions" -v

# Integration tests (requires PostgreSQL, Kafka)
pytest tests/integration/ -k "interactions" -v

# Full suite with coverage
pytest tests/ -k "interactions" --cov=src/platform/interactions --cov-report=term-missing
# Expected: >= 95% coverage
```

---

## Linting and Type Checking

```bash
cd apps/control-plane

ruff check src/platform/interactions/ --fix
mypy src/platform/interactions/ --strict
# Expected: 0 errors
```
