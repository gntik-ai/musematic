# `/me` Endpoint Pattern

The `/api/v1/me/*` namespace is the self-service API surface for the authenticated principal. UPD-042 implements FR-649 through FR-657 with a `platform.me` aggregator plus the existing notifications router.

## Routing

- `apps/control-plane/src/platform/me/router.py` owns sessions, service accounts, consent, DSR, activity, and notification-preferences endpoints.
- `apps/control-plane/src/platform/notifications/router.py` continues to own `/me/alerts*`, including `POST /me/alerts/mark-all-read`.
- `apps/control-plane/src/platform/main.py` includes the `me` router under `/api/v1`.

## Rule 46 Requirements

Every `/api/v1/me/*` endpoint must:

- Depend on `get_current_user`.
- Derive `current_user_id` from the JWT claims.
- Avoid request body, path, or query parameters named `user_id`, `subject_user_id`, or equivalent user-scope overrides.
- Return 404 instead of 403 when disclosing resource existence would leak another user's data.

The static check is `python scripts/check-me-endpoint-scope.py`.

## Endpoint Inventory

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/me/sessions` | List current user's sessions. |
| `DELETE /api/v1/me/sessions/{session_id}` | Revoke a non-current session. |
| `POST /api/v1/me/sessions/revoke-others` | Revoke every session except the current one. |
| `GET /api/v1/me/service-accounts` | List personal API keys without raw key values. |
| `POST /api/v1/me/service-accounts` | Create a personal API key and return the raw key once. |
| `DELETE /api/v1/me/service-accounts/{sa_id}` | Revoke an owned personal API key. |
| `GET /api/v1/me/consent` | List current consent state. |
| `POST /api/v1/me/consent/revoke` | Revoke one consent type. |
| `GET /api/v1/me/consent/history` | List consent grant and revoke history. |
| `POST /api/v1/me/dsr` | Submit a self-service DSR. |
| `GET /api/v1/me/dsr` | List self-service DSRs. |
| `GET /api/v1/me/dsr/{dsr_id}` | Fetch an owned DSR. |
| `GET /api/v1/me/activity` | List audit entries where the user is actor or subject. |
| `GET /api/v1/me/notification-preferences` | Fetch extended notification preferences. |
| `PUT /api/v1/me/notification-preferences` | Update extended notification preferences. |
| `POST /api/v1/me/notification-preferences/test/{event_type}` | Send a synthetic notification. |
| `POST /api/v1/me/alerts/mark-all-read` | Mark the user's alerts read. |

## Audit And Secret Handling

State-changing endpoints emit audit events through the existing audit chain service. Raw API key values, MFA secrets, backup codes, and refresh JTIs must not be logged or returned from list endpoints. One-time material is returned only in the create or regenerate response that needs to show it to the user.
