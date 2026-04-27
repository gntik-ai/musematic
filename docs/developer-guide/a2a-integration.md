# A2A Integration

A2A integration lets Musematic coordinate with external agents through registered endpoints and task messages.

Implementation guidance:

- Register endpoints with explicit workspace ownership and auth metadata.
- Make task messages idempotent.
- Preserve external task IDs and Musematic GIDs in logs.
- Treat stream events as append-only.
- Validate against `docs/api-reference/openapi.json` for the target release.

The current surface is documented in the [A2A API](../api-reference/a2a-api.md).
