# Contract — Non-Leakage Parity Probe (Dev-Only)

**Phase 1 output.** Defines the dev-mode-only endpoint that backs the SC-004 information-non-leakage CI test (FR-741.10). The probe is gated by `FEATURE_E2E_MODE` and returns 404 in production per rule 26 (E2E dev-only seeding endpoints under `/api/v1/_e2e/*` or behind explicit dev-mode flag).

---

## Why this endpoint exists

SC-004 says: when the `consume_public_marketplace` flag is unset, no information about public-hub agents leaks into a tenant. The verification harness needs a black-box equality check across two real request flows, not an introspection tool — see R10 for the rationale.

The endpoint runs the same search query through the standard search path twice:

1. **Counter-factual run** — as if no public agent matching the query existed.
2. **Live run** — with the public agent matching the query published.

It returns both response payloads (counts, suggestions, analytics events) and a computed `parity_violation` boolean. CI fails the build when `parity_violation = true`.

---

## `GET /api/v1/admin/marketplace-review/parity-probe`

### Authorization

- `require_superadmin`
- Additionally: returns 404 if `FEATURE_E2E_MODE != true`. This is the constitutional pattern (rule 26) — dev-only endpoints MUST 404 in production, not 403, so they are completely invisible to non-dev clients.

### Query parameters

| Param | Type | Required | Notes |
|---|---|---|---|
| `query` | string | yes | The search term to probe. Length 1–256. |
| `subject_tenant_id` | UUID | yes | The tenant under whose context to run both probe paths. Must be a non-default tenant (the probe is meaningful only for non-default tenants — for default tenants public visibility is always on). |

### Behaviour

The probe internally:

1. Runs the standard marketplace search as `subject_tenant_id` with `consume_public_marketplace=false` (the counter-factual; this is the production setting for tenants without the flag). Captures the response: result list, `total_count`, `suggestions`, and the analytics-event payload that would have been emitted.
2. Publishes a synthetic public-default-tenant agent matching `query` (via the existing test-fixture path; written and immediately rolled back in a savepoint so production data is never affected).
3. Re-runs the same search with the same tenant context.
4. Captures the same response surfaces.
5. Compares: `result.ids`, `result.total_count`, `result.suggestions`, `result.analytics_event_payload` MUST be byte-identical between (1) and (3). Any field that differs is recorded in `parity_violations`.
6. Rolls back the savepoint so the synthetic agent is not persisted.

### Response 200

```json
{
  "query": "kyc-verifier",
  "subject_tenant_id": "...",
  "counterfactual": {
    "total_count": 3,
    "result_ids": ["...", "...", "..."],
    "suggestions": ["kyc-aml", "kyc-onboarding"],
    "analytics_event_payload": { "...": "..." }
  },
  "live": {
    "total_count": 3,
    "result_ids": ["...", "...", "..."],
    "suggestions": ["kyc-aml", "kyc-onboarding"],
    "analytics_event_payload": { "...": "..." }
  },
  "parity_violation": false,
  "parity_violations": []
}
```

`parity_violations` enumerates each diff:

```json
{
  "field": "total_count",
  "counterfactual_value": 3,
  "live_value": 4
}
```

A non-empty `parity_violations` array means the visibility filter let the synthetic public agent affect what the no-consume-flag tenant sees — a leak.

### Errors

| Status | Code | When |
|---|---|---|
| 404 | (no body) | `FEATURE_E2E_MODE != true`. Endpoint is invisible. |
| 403 | `not_authorized` | Caller is not a superadmin (only emitted when `FEATURE_E2E_MODE = true`). |
| 422 | `tenant_not_eligible` | `subject_tenant_id` resolves to the default tenant. Probe is meaningful only for non-default tenants. |
| 422 | `query_invalid` | `query` length out of range. |
| 500 | `parity_probe_setup_failed` | Synthetic-agent fixture failed to publish/roll back. The probe MUST roll back before returning. |

### Audit + Kafka

- **No** Kafka event. The probe is a read-only diagnostic.
- Audit-chain entry kind: `marketplace.parity_probe.run`. Fields: `actor_user_id`, `subject_tenant_id`, `query`, `parity_violation`. Required because the probe is dev-only and reads cross-tenant data.

### Production safety

- The probe is wrapped in a database savepoint. The synthetic agent is rolled back before the response returns. A deferred coverage test in CI asserts the rollback happens even on exception paths.
- The probe only runs against `subject_tenant_id`'s real search index — but with synthetic data that is rolled back. The tenant's actual data is never modified.
- `FEATURE_E2E_MODE` is `false` in every production Helm values overlay (`values.prod.yaml`). The probe's 404-in-production behaviour means an accidentally-deployed call from a production frontend is invisible.

---

## CI integration

The CI parity test calls this endpoint with each of the canonical query terms (drawn from a fixed test corpus that includes terms guaranteed to match a known synthetic public agent). Build fails if any call returns `parity_violation = true` or if the endpoint returns 200 with non-empty `parity_violations`.

The test corpus and the assertion live at `tests/e2e/suites/marketplace/test_non_leakage_parity.py`.

---

## Why a probe and not just an in-test diff

We considered authoring the parity check inline in the test and bypassing the endpoint. Rejected because:

- The probe forces the visibility filter to be applied via the same code path the production frontend uses. An in-test diff that bypasses the search service would be testing different code — defeating the point.
- The probe returns analytics-event payloads that the in-test diff would have to reconstruct. Those payloads are the most leak-prone surface (a stray emission before the visibility filter is the canonical leak).
- The probe being a real endpoint forces the dev-mode gate to be exercised in CI, catching regressions where someone removes `FEATURE_E2E_MODE` enforcement.
