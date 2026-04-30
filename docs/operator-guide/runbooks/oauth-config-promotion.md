# OAuth Config Promotion

## Symptom

An operator needs to promote OAuth provider configuration from one environment to another without moving plaintext secrets.

## Diagnosis

Confirm the target environment already has the required Vault paths. The OAuth manifest stores provider configuration and Vault path references only. It stores a SHA-256 digest of the canonical manifest payload and never includes secret values.

## Remediation

Export from the source environment:

```bash
platform-cli admin oauth export --env staging --output staging-oauth.yaml
```

Validate in the target environment:

```bash
platform-cli admin oauth import --input staging-oauth.yaml --dry-run
```

Apply only after a dry-run has validated every `client_secret_vault_path`:

```bash
platform-cli admin oauth import --input staging-oauth.yaml --apply --dry-run-first
```

Imported providers are persisted with `source=imported` and emit `auth.oauth.config_imported`.

## Verification

Compare the dry-run diff with the applied provider state in `/admin/settings?tab=oauth`. Confirm the source badge is `imported`, the provider connectivity test runs, and audit history records the import.

## Rollback

Re-import the previous manifest or reseed from the target environment variables with `force_update=true`. Do not edit the manifest digest by hand; regenerate it with the export command.
