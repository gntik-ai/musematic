# Contract — Onboarding Wizard REST API

**Prefix**: `/api/v1/onboarding/*`
**Owner**: `apps/control-plane/src/platform/accounts/onboarding_router.py`
**Authorization**: Authenticated user only.
**OpenAPI tag**: `onboarding`.
**Tenant scoping**: All endpoints run under the resolved tenant via UPD-046's hostname middleware. The `user_onboarding_states` table is tenant-scoped per UPD-046 conventions.

## `GET /api/v1/onboarding/state`

Returns the authenticated user's onboarding wizard state.

**Response 200**:

```jsonc
{
  "user_id": "uuid",
  "tenant_id": "uuid",
  "step_workspace_named": false,
  "step_invitations_sent_or_skipped": false,
  "step_first_agent_created_or_skipped": false,
  "step_tour_started_or_skipped": false,
  "last_step_attempted": "workspace_named",
  "dismissed_at": null,
  "first_agent_step_available": true,           // false when UPD-022 not deployed
  "default_workspace_id": "uuid",
  "default_workspace_name": "Alice's workspace"
}
```

If no row exists for the user yet (first call after signup), the endpoint creates the row with defaults and returns the freshly-created state.

## `POST /api/v1/onboarding/step/workspace-name`

Records step 1 completion (rename or accept default workspace name). Body:

```jsonc
{ "workspace_name": "Alice's research" }
```

Response 200: `{ "next_step": "invitations" }`. Sets `step_workspace_named=true`, advances `last_step_attempted`. Emits `accounts.onboarding.step_advanced` Kafka event.

## `POST /api/v1/onboarding/step/invitations`

Records step 2 completion (sent or skipped). Body:

```jsonc
{ "invitations": [{ "email": "bob@example.com", "role": "workspace_member" }] }
```

OR an empty array to skip. Response 200: `{ "next_step": "first_agent", "invitations_sent": 1 }`. The invitation send delegates to UPD-042's existing invitation infrastructure.

## `POST /api/v1/onboarding/step/first-agent`

Records step 3 completion. Body:

```jsonc
{ "skipped": true }
```

OR (when the user actually creates an agent via the embedded UPD-022 wizard):

```jsonc
{ "skipped": false, "agent_fqn": "namespace:hello-agent" }
```

Response 200: `{ "next_step": "tour" }`. Sets `step_first_agent_created_or_skipped=true`.

## `POST /api/v1/onboarding/step/tour`

Records step 4 completion. Body: `{ "started": true }` or `{ "started": false }` (skipped). Response 200: `{ "next_step": "done" }`. Sets `step_tour_started_or_skipped=true` and `last_step_attempted='done'`.

## `POST /api/v1/onboarding/dismiss`

Dismisses the wizard at the current step. Empty body. Response 200: `{ "dismissed_at": "2026-05-02T10:30:00Z" }`. Sets `dismissed_at = now()`. Emits `accounts.onboarding.dismissed` Kafka event.

## `POST /api/v1/onboarding/relaunch`

Re-launches the wizard from Settings (per FR-030). Empty body. Response 200 echoing the post-relaunch state. Sets `dismissed_at = NULL`. The wizard resumes at the first incomplete step. Emits `accounts.onboarding.relaunched` Kafka event.

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 404 | `default_workspace_not_yet_provisioned` (rare — only when the deferred-retry job hasn't run yet) |
| 409 | `wizard_already_dismissed_at_this_step` (idempotent dismiss attempts safely return 200, but the explicit re-dismiss attempt on the same state returns 409 to surface the race) |
| 422 | `invalid_step_payload` |

## Test contract

Integration test `tests/integration/accounts/test_onboarding_state.py`:

- Initial state created on first GET with sensible defaults.
- Each step advance is idempotent (re-calling step/workspace-name does not create duplicate state).
- Dismissed wizard's state is preserved (subsequent GET returns `dismissed_at != null`).
- Relaunch clears `dismissed_at` and resumes at the first incomplete step (SC-007).
- When UPD-022 is not deployed, `first_agent_step_available=false` and the wizard step is hidden cleanly.
