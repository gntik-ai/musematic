# Catalogue Admin Contract

**Feature**: 075-model-catalog-fallback
**Module**: `apps/control-plane/src/platform/model_catalog/services/catalog_service.py`
**Router**: `apps/control-plane/src/platform/model_catalog/router.py`

## REST endpoints

All under `/api/v1/model-catalog/*`. Every mutating method requires
`platform_admin` or `superadmin` (rule 30). Tagged `['admin',
'model-catalog']`.

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/model-catalog/entries` | Create catalogue entry | `platform_admin`, `superadmin` |
| `GET /api/v1/model-catalog/entries` | List (filter by provider, status) | authenticated |
| `GET /api/v1/model-catalog/entries/{id}` | Get entry | authenticated |
| `PATCH /api/v1/model-catalog/entries/{id}` | Update metadata | `platform_admin`, `superadmin` |
| `POST /api/v1/model-catalog/entries/{id}/deprecate` | Explicit deprecation | `platform_admin`, `superadmin` |
| `POST /api/v1/model-catalog/entries/{id}/block` | Block entry | `platform_admin`, `superadmin` |
| `POST /api/v1/model-catalog/entries/{id}/reapprove` | Re-approve after deprecation/block | `superadmin` (stricter; re-approval is significant) |
| `POST /api/v1/model-catalog/fallback-policies` | Create policy | `platform_admin`, `superadmin` |
| `GET /api/v1/model-catalog/fallback-policies` | List policies | authenticated |
| `PATCH /api/v1/model-catalog/fallback-policies/{id}` | Update policy | `platform_admin`, `superadmin` |
| `DELETE /api/v1/model-catalog/fallback-policies/{id}` | Delete policy | `platform_admin`, `superadmin` |

## Status transitions

```
approved ──[explicit or auto-deprecation]──▶ deprecated
approved ──[explicit block]──▶ blocked
deprecated ──[explicit reapprove]──▶ approved (new approval_expires_at required)
blocked ──[explicit reapprove]──▶ approved (audit-logged justification)
```

Every transition:
- Writes an `AuditChainEntry` via `AuditChainService.append()`
  (UPD-024, rule 9).
- Emits `model.catalog.updated` Kafka event.
- Invalidates router's in-process LRU cache within 60 seconds.

## Auto-deprecation job

APScheduler job `model_catalog_auto_deprecation` runs on the `scheduler`
runtime profile. Default interval 1 hour (configurable via
`MODEL_CATALOG_AUTO_DEPRECATION_INTERVAL_SECONDS`).

```sql
UPDATE model_catalog_entries
SET status = 'deprecated', updated_at = now()
WHERE status = 'approved'
  AND approval_expires_at < now()
RETURNING id, provider, model_id;
```

For each row returned, the job:
1. Emits `AuditChainEntry` (source=`model_catalog`, event_type=
   `approval_expired`).
2. Emits `model.deprecated` Kafka event.
3. Sends notification to `model_steward` role (or `platform_admin`
   fallback).

## Fallback-policy validation rules

On `POST /fallback-policies` + `PATCH /fallback-policies/{id}`:

1. Every UUID in `fallback_chain` must reference an existing catalogue
   entry with status IN (`approved`, `deprecated`). Blocked entries are
   rejected.
2. No duplicate entries in chain (no cycles even at chain-length 1).
3. No entry appears more than once in the chain.
4. `primary_model_id` NOT in `fallback_chain`.
5. Each chain entry's `context_window >= primary.context_window`.
6. Each chain entry's `quality_tier` does not exceed
   `acceptable_quality_degradation` below primary:
   - `tier_equal`: all same tier.
   - `tier_plus_one`: each entry's numeric tier ≤ primary + 1.
   - `tier_plus_two`: each entry's numeric tier ≤ primary + 2.

## Unit-test contract

- **CA1** — create entry: row inserted, event emitted, chain entry
  written.
- **CA2** — duplicate entry rejected: `(provider, model_id)` unique.
- **CA3** — explicit block: in-flight sticky cache invalidated; next
  call fails.
- **CA4** — auto-deprecation: expired entry transitions within 1 hour.
- **CA5** — fallback cycle rejected at create time with offending
  index.
- **CA6** — tier degradation: `tier1 → tier3` with `tier_plus_one`
  rejected.
- **CA7** — reapprove: deprecated → approved requires fresh
  `approval_expires_at`.
