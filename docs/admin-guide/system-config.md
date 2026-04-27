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

## Common Admin Workflows

### Rotate a Provider Credential

Create the replacement secret, verify that the rotatable provider resolves it, start the rotation window, and confirm traffic succeeds before retiring the old secret.

### Toggle a Feature Flag

Check the [Feature Flags](../configuration/feature-flags.md) reference, confirm scope, apply the change in the Admin Workbench, and watch audit and error-rate dashboards.

### Update OAuth Configuration

Change client ID, client secret reference, redirect URI, and org/domain allow-lists together. Use the provider test endpoint before enabling the provider for users.

### Enter Maintenance Mode

Schedule a maintenance window with reason and expected end time. Verify user-facing messaging and operator alerts before applying disruptive changes.
