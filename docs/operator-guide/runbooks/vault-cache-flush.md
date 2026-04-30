# Vault Cache Flush

## Symptom

Operators rotated a secret or suspect stale cached values are still being served by one or more pods.

## Diagnosis

Check cache metrics and status:

```bash
platform-cli vault status
```

High `vault_cache_hit_ratio` with failing downstream auth usually means a stale value is still cached.

## Remediation

Flush a single path on the current target:

```bash
platform-cli vault flush-cache --pod control-plane-api-0
```

Flush all known control-plane pods by iterating the CLI target selection:

```bash
platform-cli vault flush-cache --all-pods
```

The admin API scope is per pod; cluster-wide broadcast is intentionally out of scope.

## Verification

Confirm `vault.cache_flushed` exists in the audit chain and that subsequent reads use the expected credential version.
