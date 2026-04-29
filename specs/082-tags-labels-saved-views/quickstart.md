# Quickstart: Tags, Labels, and Saved Views

This walkthrough assumes a local control plane at `http://localhost:8000`, a JWT in
`TOKEN_A` for a workspace member, a JWT in `TOKEN_B` for another member of the same
workspace, and these IDs:

```bash
export API=http://localhost:8000
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

On 2026-04-29, the local mocked smoke coverage passed through:

- backend focused pytest for common tagging services and integration harness
- frontend Vitest coverage for the tagging components
- Chromium Playwright coverage for saved views and label-expression validation

The full curl walkthrough requires a running local control plane with two
workspace-member tokens.
