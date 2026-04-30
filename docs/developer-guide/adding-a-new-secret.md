# Adding a New Secret

Use this recipe when a bounded context needs a new credential.

## 1. Choose a Canonical Path

Use:

```text
secret/data/musematic/{env}/{domain}/{resource}
```

Allowed domains are `oauth`, `model-providers`, `notifications`, `ibor`, `audit-chain`, `connectors`, and `accounts`. `_internal` is reserved for platform connectivity probes.

## 2. Store Only References

Database models, events, API responses, and manifests store references or version metadata, never secret values.

## 3. Wire the Callsite

Inject `SecretProvider` from application state or the bounded-context dependency module:

```python
value = await secret_provider.get(secret_ref, "value", critical=True)
```

## 4. Add Vault Policy

Update the owning policy file under `deploy/vault/policies/platform-{bc}.hcl` and the Helm copy under `deploy/helm/vault/policies/`.

## 5. Add Tests and Docs

Add unit coverage for path validation, missing-secret behavior, and no-log leakage. Regenerate environment and Helm docs when configuration changes.
