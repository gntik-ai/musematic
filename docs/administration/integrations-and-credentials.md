# Integrations and Credentials

Model provider credentials are registered per workspace and provider as Vault references, not raw
secrets. Administrators create rows through `/api/v1/model-catalog/credentials` with:

- `workspace_id`: workspace that owns the provider key.
- `provider`: provider name such as `openai`, `anthropic`, `google`, or `mistral`.
- `vault_ref`: logical Vault reference resolved by the rotatable secret provider.

The control plane verifies that the Vault reference resolves before persisting the credential. At
runtime, `ModelRouter` resolves the current secret and sends it as `Authorization: Bearer <key>` to
the configured provider endpoint.

Rotation delegates to the UPD-024 secret rotation workflow. Normal rotation uses a 24-168 hour
overlap window. Emergency skip-overlap rotation requires a distinct second approver.

Operational rules:

- Do not store provider keys in agent manifests, workspace settings, or logs.
- Use one credential row per workspace/provider pair.
- Delete unused credential rows before decommissioning a workspace.
- Treat `rotation_schedule_id` as the source of truth for ongoing rotation state.
