# Quickstart: Tags, Labels, and Saved Views

This walkthrough assumes a reachable local control plane, a JWT in `TOKEN_A` for a
workspace member, a JWT in `TOKEN_B` for another member of the same workspace, and
these IDs. The `make dev-up` kind environment exposes the API on `8081`; direct
local `uvicorn` runs often use `8000`.

```bash
export API=${API:-http://localhost:8081}
export WORKSPACE_ID=<workspace-uuid>
export AGENT_ID=<agent-uuid>
export POLICY_ID=<policy-uuid>
```

## 1. Tag an Agent

```bash
curl -fsS -X POST "$API/api/v1/tags/agent/$AGENT_ID" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"tag":"production"}'

curl -fsS "$API/api/v1/tags/agent/$AGENT_ID" \
  -H "Authorization: Bearer $TOKEN_A"
```

Expected: the response contains exactly one `production` tag, even if the attach
call is repeated.

## 2. Label the Agent and Policy

```bash
curl -fsS -X POST "$API/api/v1/labels/agent/$AGENT_ID" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"key":"env","value":"production"}'

curl -fsS -X POST "$API/api/v1/labels/policy/$POLICY_ID" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"key":"tier","value":"critical"}'
```

Reserved keys such as `system.managed` and `platform.owner` should return `403`
for ordinary workspace members. Use `/api/v1/admin/labels/reserved/...` only with
a superadmin token.

## 3. Validate and Save a Label-Expression Policy

```bash
curl -fsS -X POST "$API/api/v1/labels/expression/validate" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"expression":"env=production AND tier=critical"}'
```

Expected: `{ "valid": true, "error": null }`.

Malformed input should fail with a line/column pointer:

```bash
curl -fsS -X POST "$API/api/v1/labels/expression/validate" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{"expression":"env=production AND"}'
```

Expected: `{ "valid": false, "error": { "line": 1, "col": ..., ... } }`.

Create a policy scoped by the expression:

```bash
curl -fsS -X POST "$API/api/v1/policies" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d "{
    \"name\":\"Production critical only\",
    \"description\":\"Applies only to production critical targets.\",
    \"scope_type\":\"workspace\",
    \"workspace_id\":\"$WORKSPACE_ID\",
    \"rules\":{\"label_expression\":\"env=production AND tier=critical\"},
    \"change_summary\":\"Initial label-expression policy\"
  }"
```

## 4. Save and Share a View

```bash
curl -fsS -X POST "$API/api/v1/saved-views" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d "{
    \"workspace_id\":\"$WORKSPACE_ID\",
    \"name\":\"Production agents\",
    \"entity_type\":\"agent\",
    \"filters\":{\"tags\":[\"production\"],\"labels\":{\"env\":\"production\"}},
    \"shared\":false
  }"
```

Capture the returned `id` as `VIEW_ID`, then share it:

```bash
export VIEW_ID=<saved-view-uuid>

curl -fsS -X POST "$API/api/v1/saved-views/$VIEW_ID/share" \
  -H "Authorization: Bearer $TOKEN_A" \
  -H "Content-Type: application/json" \
  -d '{}'
```

## 5. Apply the Shared View as Another User

```bash
curl -fsS "$API/api/v1/saved-views?entity_type=agent&workspace_id=$WORKSPACE_ID" \
  -H "Authorization: Bearer $TOKEN_B"

curl -fsS "$API/api/v1/agents?tags=production&label.env=production" \
  -H "Authorization: Bearer $TOKEN_B" \
  -H "X-Workspace-ID: $WORKSPACE_ID"
```

Expected: user B sees the shared view and the filtered agent list contains the
tagged/labeled agent only if user B has normal visibility to that agent.

## Smoke Notes

On 2026-04-29, the reachable local control plane at `http://localhost:8081` was
healthy and `/api/v1/_e2e/seed` succeeded, but the full curl walkthrough could
not complete end-to-end in that E2E-mode deployment. Observed deviations:

- `POST /api/v1/labels/expression/validate` returned `422` because the running
  deployment routed `/labels/expression/validate` through the dynamic
  `/{entity_type}/{entity_id}` label-attach path (`entity_type=expression`,
  `entity_id=validate`) instead of the validator route.
- The E2E contract router shadows `/api/v1/agents`, `/api/v1/workspaces`, and
  `/api/v1/policies`; seeded agents are returned with FQN IDs such as
  `default:seeded-executor`, while the tag/label REST routes require UUID
  entity IDs from the real registry tables.
- `POST /api/v1/tags/agent/default:seeded-executor` returned `422` UUID
  validation, and `POST /api/v1/tags/agent/00000000-0000-4000-8000-00000000a201`
  returned `404 ENTITY_NOT_FOUND_FOR_TAG`.
- Creating a workspace-scoped saved view against the E2E workspace ID returned
  `500`; a personal saved-view smoke remains the safer local probe when the
  E2E contract router is enabled.
- `GET /api/v1/agents?tags=production&label.env=production` returned `200` from
  the E2E contract listing, but it did not apply the tag/label filter.
- Chromium Playwright against the deployed UI at `http://localhost:8080` failed
  because the expected tagging controls were absent; the same spec passed
  against a local Next dev server from this source tree at `http://127.0.0.1:3000`.

Use a non-E2E-mode control plane, or seed DB-backed UUID entities through the
real bounded-context services, before treating the curl walkthrough as a full
acceptance smoke. The source-level smoke coverage still passed through:

- backend focused pytest for common tagging services and integration harness
- frontend Vitest coverage for the tagging components
- Chromium Playwright coverage for saved views and label-expression validation

The full curl walkthrough requires DB-backed workspace, agent, and policy rows
plus two workspace-member tokens.
