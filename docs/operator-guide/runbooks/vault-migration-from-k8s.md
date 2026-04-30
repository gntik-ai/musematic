# Vault Migration From Kubernetes Secrets

## Symptom

An installation currently uses Kubernetes Secrets or mock secret files and needs to adopt HashiCorp Vault without exposing plaintext values.

## Diagnosis

Check the active mode:

```bash
kubectl -n platform get configmap amp-control-plane-config -o yaml | grep PLATFORM_VAULT_MODE
```

Use `mock` for local development, `kubernetes` for transitional cutover, and `vault` for production.

## Remediation

1. Install or configure Vault and confirm the `musematic-platform` auth role is present.
2. Run a dry run:

```bash
platform-cli vault migrate-from-k8s --namespace platform --env production --output-dir ./migration
```

3. Review the emitted manifest. It contains source, destination, SHA-256, and status, never plaintext values.
4. Apply the migration:

```bash
platform-cli vault migrate-from-k8s --namespace platform --env production --apply --output-dir ./migration
```

5. Roll the control plane with `PLATFORM_VAULT_MODE=vault`.

## Verification

```bash
platform-cli vault verify-migration --manifest ./migration/<manifest>.json
platform-cli vault status
```

Confirm `status` is `green` or `yellow`, read counters increase, and no pod logs contain secret values.

## Rollback

Flip `PLATFORM_VAULT_MODE` back to `kubernetes` and roll the control plane. Kubernetes Secrets are left in place until post-migration verification is accepted.
