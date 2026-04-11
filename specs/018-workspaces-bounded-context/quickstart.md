# Quickstart: Workspaces Bounded Context

**Feature**: 018-workspaces-bounded-context  
**Date**: 2026-04-11

## Prerequisites

- Feature 013 (FastAPI App Scaffold) complete — provides app factory, PlatformSettings, EventEnvelope, base models/mixins, Kafka producer/consumer, pagination, error handling
- Feature 014 (Auth Bounded Context) complete — provides JWT auth middleware, `get_current_user` dependency
- Feature 016 (Accounts Bounded Context) complete — provides `accounts.user.activated` event for default workspace provisioning
- PostgreSQL running on `localhost:5432`
- Kafka running on `localhost:9092`

## Run Migrations

```bash
cd apps/control-plane
alembic upgrade head
```

This runs migration `004_workspaces_tables.py` which creates:
- `workspaces_workspaces` (with indexes on owner_id, unique owner+name+status)
- `workspaces_memberships` (with unique workspace+user constraint)
- `workspaces_goals` (with unique GID constraint)
- `workspaces_settings` (one-to-one with workspace)
- `workspaces_visibility_grants` (one-to-one with workspace)

## Run the Dev Server

```bash
cd apps/control-plane
uvicorn src.platform.main:create_app --factory --reload --port 8000
```

## Verify: Create a Workspace

```bash
# Get a JWT token first (from auth endpoints)
TOKEN="your-jwt-token"

curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Workspace", "description": "My first workspace"}'
```

Expected: `201 Created` with workspace JSON including `id`, `name`, `status: "active"`, `owner_id`, `is_default: false`.

## Verify: List Workspaces

```bash
curl -X GET http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `200 OK` with `items` array containing the created workspace.

## Verify: Add a Member

```bash
WORKSPACE_ID="<workspace-id-from-create>"
USER_ID="<another-user-uuid>"

curl -X POST http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/members \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\": \"$USER_ID\", \"role\": \"member\"}"
```

Expected: `201 Created` with membership JSON.

## Verify: Data Isolation

```bash
# As user A, create workspace and add data
# As user B (not a member), attempt to access workspace A
curl -X GET http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID \
  -H "Authorization: Bearer $TOKEN_USER_B"
```

Expected: `404 Not Found` (workspace not visible to non-members).

## Verify: Workspace Goals

```bash
# Create a goal
curl -X POST http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/goals \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title": "Q4 Revenue Analysis", "description": "Analyze Q4 revenue trends"}'

# Update goal status
GOAL_ID="<goal-id-from-create>"
curl -X PATCH http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/goals/$GOAL_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "in_progress"}'
```

Expected: `201 Created` with GID, then `200 OK` with updated status.

## Verify: Visibility Grants

```bash
# Set visibility grant
curl -X PUT http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/visibility \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"visibility_agents": ["finance-ops:*", "data-tools:csv-*"], "visibility_tools": ["data-tools:csv-reader"]}'

# Get visibility grant
curl -X GET http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/visibility \
  -H "Authorization: Bearer $TOKEN"
```

Expected: `200 OK` with visibility patterns.

## Verify: Default Workspace Provisioning

Activate a new user via accounts API. Then:

```bash
# List workspaces for the newly activated user
curl -X GET http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $NEW_USER_TOKEN"
```

Expected: One workspace named `"{display_name}'s Workspace"` with `is_default: true`.

## Verify: Workspace Limits

```bash
# Set user's workspace limit to 1 (via accounts admin endpoint)
# Create one workspace — should succeed
# Create another workspace — should fail
curl -X POST http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Second Workspace"}'
```

Expected: `403 Forbidden` with "workspace limit reached" error.

## Verify: Archive and Restore

```bash
# Archive
curl -X POST http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/archive \
  -H "Authorization: Bearer $TOKEN"

# List — archived workspace should not appear
curl -X GET http://localhost:8000/api/v1/workspaces \
  -H "Authorization: Bearer $TOKEN"

# Restore
curl -X POST http://localhost:8000/api/v1/workspaces/$WORKSPACE_ID/restore \
  -H "Authorization: Bearer $TOKEN"
```

## Run Tests

```bash
cd apps/control-plane
pytest tests/unit/test_workspaces_*.py -v
pytest tests/integration/test_workspaces_*.py -v
```

## Key Test Files

```text
apps/control-plane/tests/
├── unit/
│   ├── test_workspaces_service.py         # Service logic (mocked repo)
│   ├── test_workspaces_state_machine.py   # Goal state transitions
│   ├── test_workspaces_schemas.py         # Pydantic validator tests
│   ├── test_workspaces_repository.py      # Repository (mocked session)
│   └── test_workspaces_router.py          # Router endpoints (TestClient)
└── integration/
    ├── test_workspace_crud_flow.py        # Create → update → archive → restore → delete
    ├── test_membership_flow.py            # Add → change role → remove
    ├── test_default_provisioning.py       # Kafka event → workspace created
    └── test_goal_flow.py                  # Create → update status → complete
```
