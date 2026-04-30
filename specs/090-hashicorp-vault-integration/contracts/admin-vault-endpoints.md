# Admin Vault Endpoint Contract

Date: 2026-04-30

Base path: `/api/v1/admin/vault`

All endpoints require `superadmin` via `Depends(require_superadmin)`. The aggregate admin router also applies the admin rate limit. Responses never include Vault token values, AppRole SecretIDs, KV values, or client secrets.

## GET `/status`

Returns the status payload used by the deferred `/admin/security/vault` UI page and by `platform-cli vault status`.

Response schema:

```json
{
  "status": "green|yellow|red",
  "mode": "mock|kubernetes|vault",
  "auth_method": "kubernetes|approle|token|null",
  "token_expiry_at": "2026-04-30T12:30:00Z",
  "lease_count": 4,
  "recent_failures": ["Forbidden: permission denied"],
  "cache_hit_rate": 0.91,
  "error": null,
  "read_counts_by_domain": {"oauth": 124},
  "auth_failure_counts_by_method": {"kubernetes": 1},
  "policy_denied_counts_by_path": {},
  "serving_stale_total": 0,
  "renewal_success_total": 12,
  "renewal_failure_total": 0,
  "cache_hit_total": 2500,
  "cache_miss_total": 250
}
```

Example:

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://api.example.com/api/v1/admin/vault/status
```

Errors:

- `401` when the request has no valid access token.
- `403` with `superadmin_required` when the principal is not a super admin.
- `503` with `vault_provider_unavailable` when the process has no configured secret provider.

## POST `/cache-flush`

Flushes the calling pod's in-process Vault cache. A `path` flushes only cached entries under that canonical Vault path; omit it to flush all cached entries on the current pod. The endpoint emits a `vault.cache_flushed` audit-chain entry with the principal, timestamp, result, path, scope, and flushed count.

Request schema:

```json
{
  "path": "secret/data/musematic/production/oauth/google",
  "pod": "control-plane-api-0",
  "all_pods": false
}
```

Only `path` changes server behavior today. `pod` and `all_pods` are accepted for CLI/UI intent echoing; cluster-wide broadcast is out of scope, so callers that need every pod flushed must repeat the request per target pod or use the CLI workflow.

Response schema:

```json
{
  "flushed_count": 3,
  "scope": "current-pod",
  "path": "secret/data/musematic/production/oauth/google",
  "pod": "control-plane-api-0",
  "all_pods_requested": false
}
```

Errors:

- `400` or `503` if the path is not canonical or the provider cannot flush.
- `401` for missing or invalid auth.
- `403` for non-super-admin callers.

## POST `/connectivity-test`

Performs a synthetic write and read at `secret/data/musematic/{env}/_internal/connectivity-test/{random}` through the configured `SecretProvider`. The endpoint does not return the synthetic value and attempts best-effort version cleanup after the read. It emits `vault.connectivity_test` to the audit chain with principal, timestamp, result, latency, and sanitized error text.

Request body: empty JSON object or omitted body.

Response schema:

```json
{
  "success": true,
  "latency_ms": 18.42,
  "error": null
}
```

Errors:

- `401` for missing or invalid auth.
- `403` for non-super-admin callers.
- Provider failures are represented as `200` with `"success": false` and a sanitized `"error"` string so the UI can render status without losing the audit event.

## POST `/rotate-token`

Utility endpoint consumed by `platform-cli vault rotate-token`. It forces the calling process to renew or reauthenticate its Vault session when the provider supports renewal.

Request schema:

```json
{
  "pod": "control-plane-api-0"
}
```

Response schema:

```json
{
  "success": true,
  "status": "green",
  "error": null,
  "pod": "control-plane-api-0"
}
```

Errors:

- `401` for missing or invalid auth.
- `403` for non-super-admin callers.
- Provider failures are returned in the response body with `success: false`.
