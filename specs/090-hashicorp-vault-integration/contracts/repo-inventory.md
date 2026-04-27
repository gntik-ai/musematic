# Repository Inventory — UPD-040

Date: 2026-04-27

## Confirmed Existing Surfaces

- `apps/control-plane/src/platform/connectors/security.py` exists and defines `VaultResolver`.
- `VaultResolver.resolve()` is currently mock-only: `settings.connectors.vault_mode == "mock"` delegates to `_resolve_mock()`, and all other modes raise `CredentialUnavailableError`.
- `_resolve_mock()` reads `.vault-secrets.json` by path, then falls back to `CONNECTOR_SECRET_*` environment variables, then raises `CredentialUnavailableError`.
- `apps/control-plane/src/platform/notifications/channel_router.py` defines the current `SecretProvider` Protocol with `read_secret(path)` and `write_secret(path, payload)`.
- `apps/control-plane/src/platform/security_compliance/providers/rotatable_secret_provider.py` exists and exposes the four public methods required by UPD-024: `get_current`, `get_previous`, `validate_either`, and `cache_rotation_state`.

## Per-BC Secret Reference Columns

| Bounded Context | File | Column |
| --- | --- | --- |
| auth OAuth | `apps/control-plane/src/platform/auth/models.py` | `OAuthProvider.client_secret_ref` |
| auth IBOR | `apps/control-plane/src/platform/auth/models.py` | `IBORConnector.credential_ref` |
| notifications channels | `apps/control-plane/src/platform/notifications/models.py` | `ChannelConfig.signing_secret_ref` |
| notifications webhooks | `apps/control-plane/src/platform/notifications/models.py` | `OutboundWebhook.signing_secret_ref` |
| model catalog | `apps/control-plane/src/platform/model_catalog/models.py` | `ModelProviderCredential.vault_ref` |

## Confirmed Absent Before UPD-040 Implementation

- `deploy/helm/vault/` does not exist.
- `services/shared/secrets/` does not exist.
- `apps/ops-cli/src/platform_cli/commands/vault.py` does not exist.

## Implementation Consequence

UPD-040 can proceed as a brownfield extension: keep `VaultResolver` as a compatibility wrapper for one release, promote the notifications Protocol into `platform.common.secret_provider`, preserve the `RotatableSecretProvider` public method names, and reuse the existing per-BC reference columns without migrations.
