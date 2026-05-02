# Contract — Publish + Submit-for-Review REST API

**Affected endpoints**: extends the existing publish flow at `apps/control-plane/src/platform/registry/router.py` (the registry BC owns agent lifecycle).
**OpenAPI tag**: `registry.agents`.

## `POST /api/v1/registry/agents/{id}/publish` (extended)

The existing publish endpoint gains a `scope` field in the request body.

```jsonc
{
  "scope": "workspace",                  // or "tenant" | "public_default_tenant"
  "marketing_metadata": {                // REQUIRED only when scope == "public_default_tenant"
    "category": "data-extraction",
    "marketing_description": "...",
    "tags": ["pdf", "extraction"]
  }
}
```

Behaviour by scope:

- `workspace` or `tenant`: existing flow — `review_status` transitions to `published` immediately. Audit-chain entry recorded. `marketplace.published` event published.
- `public_default_tenant`: refused with HTTP 403 `code=public_scope_not_allowed_for_enterprise` if the request's tenant is not the default tenant. Otherwise the request body MUST include the `marketing_metadata` block. `review_status` transitions to `pending_review`; audit-chain entry recorded; `marketplace.submitted` event published; the submission appears in `/admin/marketplace-review/queue`.

## `POST /api/v1/registry/agents/{id}/marketplace-scope` (new)

Allows the agent owner to change `marketplace_scope` without publishing. Used to demote a published agent back to private without deprecating it.

```jsonc
{ "scope": "workspace" }
```

Response: updated `AgentProfileView`. Records `marketplace.scope_changed`.

## `POST /api/v1/registry/agents/{id}/deprecate-listing` (new)

Owner of a published public agent marks it `deprecated`. The agent disappears from public marketplace search; existing forks remain visible.

```jsonc
{ "reason": "Superseded by v2; see https://..." }
```

Records `marketplace.deprecated`. The published version remains queryable for `MARKETPLACE_DEPRECATION_RETENTION_DAYS` (default 30) so existing forks can still resolve a known-good source pointer.

## Error model

| HTTP | `code` |
|---|---|
| 401 | `unauthenticated` |
| 403 | `public_scope_not_allowed_for_enterprise`, `not_agent_owner` |
| 404 | `agent_not_found` |
| 422 | `marketing_metadata_required`, `category_invalid`, `tags_required` |
| 429 | `submission_rate_limit_exceeded` (5/day per submitter) — `Retry-After` header included |

## Test contract

Integration tests in `tests/integration/marketplace/test_publish_*.py`:

- `test_publish_workspace_scope.py` — happy path, no review.
- `test_publish_tenant_scope.py` — happy path, no review.
- `test_publish_public_scope_flow.py` — submission → review → approval → published listing visible.
- `test_publish_public_refused_for_enterprise.py` — 403 from API; DB constraint refuses direct INSERT; UI hides the option (verified in Playwright suite).
- `test_review_queue_rate_limit.py` — 6th submission in 24 hours returns 429.
