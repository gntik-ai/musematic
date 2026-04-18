# Quickstart: FQN Namespace System and Agent Identity

**Feature**: 051-fqn-namespace-agent-identity
**Phase**: 1 — Design
**Date**: 2026-04-18

---

## What This Feature Changes

```text
apps/control-plane/
├── src/platform/
│   ├── common/events/
│   │   └── envelope.py           MODIFIED — add agent_fqn to CorrelationContext
│   └── registry/
│       └── schemas.py            MODIFIED — purpose min_length 10 → 50
│
└── migrations/versions/
    └── 041_fqn_backfill.py       NEW — backfill default namespace + FQNs for existing agents
```

**Everything else (models.py, service.py, router.py, repository.py) is unchanged** — the FQN system was shipped in feature 021.

---

## Test Setup

All tests use pytest + pytest-asyncio. Integration tests require a live PostgreSQL connection (no SQLite for this feature — FQN constraints require PostgreSQL UUID + JSONB).

```bash
cd apps/control-plane
make test-integration  # runs pytest tests/integration/registry/
```

---

## Testing Per User Story

### US1 — Namespace Management and Agent FQN Registration

**Focus**: Existing endpoints (verify they work correctly, not that they're new).

**Setup**: Empty workspace with no namespaces.

**Test cases**:
1. `POST /api/v1/namespaces` with `{"name": "test-ns"}` → 201, namespace in response
2. `POST /api/v1/namespaces` with same name → 409 conflict
3. `POST /api/v1/agents/upload` with valid manifest (namespace=test-ns, local_name=agent-a, purpose=50+ chars) → 201, `fqn = "test-ns:agent-a"` in response
4. Upload second agent with same local_name in same namespace → 409 conflict
5. Upload same local_name in different namespace → 201 (separate FQN)
6. `DELETE /api/v1/namespaces/{id}` with active agents → 409
7. `DELETE /api/v1/namespaces/{id}` after removing agents → 204

---

### US2 — Agent Resolution and Discovery by FQN

**Setup**: Three agents in workspace: `finance-ops:kyc-verifier`, `finance-ops:aml-checker`, `hr-ops:onboarding-agent`.

**Test cases**:
1. `GET /api/v1/agents/resolve/finance-ops:kyc-verifier` → 200, correct agent returned
2. `GET /api/v1/agents/resolve/finance-ops:nonexistent` → 404
3. `GET /api/v1/agents?fqn_pattern=finance-ops:*` → 200, items has exactly 2 agents (both finance-ops)
4. `GET /api/v1/agents?fqn_pattern=*:kyc-*` → 200, returns `finance-ops:kyc-verifier`
5. `GET /api/v1/agents?fqn_pattern=hr-ops:*` → 200, returns `hr-ops:onboarding-agent`
6. `GET /api/v1/agents?fqn_pattern=nonexistent:*` → 200, `items: []`, `total: 0`

---

### US3 — Agent Manifest Enrichment (Purpose Validation Change)

**Focus**: Purpose `min_length` updated from 10 to 50.

**Setup**: Namespace "test-ns" exists.

**Test cases**:
1. Upload agent with `purpose = "Short"` (5 chars) → 422, validation error mentioning minimum 50 characters
2. Upload agent with `purpose = "A" * 49` (49 chars) → 422
3. Upload agent with `purpose = "A" * 50` (50 chars) → 201
4. Upload agent without `role_types` → 422 (pre-existing validation)
5. Upload agent with `role_types: [executor]` → 201, `role_types: ["executor"]` in response
6. `PATCH /api/v1/agents/{id}` with `role_types: [observer, judge]` → 200, updated role_types

---

### US4 — Agent Visibility Configuration

**Setup**: Two agents registered: `main-agent`, `helper-agent`. Workspace-level visibility is empty.

**Test cases**:
1. Create agent with no visibility config → `visibility_agents: []`, `visibility_tools: []`
2. `PATCH /api/v1/agents/{main-agent-id}` with `{"visibility_agents": ["test-ns:helper-agent"]}` → 200, updated
3. `PATCH /api/v1/agents/{main-agent-id}` with `{"visibility_agents": []}` → 200, back to empty (removal works)
4. `PATCH /api/v1/agents/{main-agent-id}` with `{"visibility_tools": ["tools:search:*"]}` → 200
5. `GET /api/v1/agents/{main-agent-id}` → confirm all visibility fields persisted

---

### US5 — Backward-Compatible Agent Migration (Backfill)

**Focus**: The new migration `041_fqn_backfill.py`.

**Setup**: Manually insert a raw agent row with `namespace_id = NULL`, `fqn = NULL`, `display_name = "old-agent"`, `purpose = "Short"` into `registry_agent_profiles`.

**Test cases**:
1. Run `alembic upgrade 041_fqn_backfill`
2. Query agent → `fqn = "default:old-agent"`, `namespace_id` set, `local_name = "old-agent"`
3. Verify "default" namespace was created for the workspace
4. Run migration again (idempotency test) → no error, no duplicate namespace
5. Verify `needs_reindex = true` for agents where purpose length < 50 after backfill
6. Verify existing agents with FQNs already set are not modified

---

### US1 + US5 Combined: CorrelationContext Event Change

**Focus**: `agent_fqn` field added to `CorrelationContext`.

**Test cases**:
1. Deserialize existing event JSON without `agent_fqn` → no error, `agent_fqn = None`
2. Serialize `CorrelationContext(correlation_id=uuid, agent_fqn="finance-ops:kyc-verifier")` → JSON includes `agent_fqn`
3. Serialize with `agent_fqn=None` → JSON includes `"agent_fqn": null`
4. Existing event producers: build `EventEnvelope` without specifying `agent_fqn` → `agent_fqn: None` in serialized output (backward compatible)
5. Agent lifecycle event published after agent creation includes correct `agent_fqn` in `CorrelationContext`

---

## Edge Cases

| Scenario | Expected Behavior |
|----------|------------------|
| Namespace name with uppercase | Rejected with 422: must be lowercase slug |
| Namespace name starting with digit | Rejected with 422 |
| FQN collision (same namespace:local_name) | 409 Conflict on upload |
| `fqn_pattern=*` query | Returns all visible agents, paginated |
| Backfill with display_name containing spaces | Spaces converted to hyphens in local_name |
| Backfill: two agents in same workspace with same display_name | Second gets suffix `-2` to avoid collision |
| `agent_fqn` in event from non-agent context (e.g., human action) | Set to `None` |
| Purpose exactly 50 chars | Accepted |
| Purpose 49 chars | Rejected |

---

## Running the Migration

```bash
cd apps/control-plane
# Apply all pending migrations including 041
alembic upgrade head

# Verify backfill
psql $DATABASE_URL -c "
  SELECT fqn, local_name, namespace_id IS NOT NULL as has_ns
  FROM registry_agent_profiles
  WHERE deleted_at IS NULL
  LIMIT 10;
"

# Check flagged agents (need purpose review)
psql $DATABASE_URL -c "
  SELECT fqn, length(purpose) as purpose_len
  FROM registry_agent_profiles
  WHERE needs_reindex = true
  ORDER BY purpose_len;
"
```
