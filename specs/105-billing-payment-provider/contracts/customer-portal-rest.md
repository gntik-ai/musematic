# Contract: Customer Portal session creation (Stripe-side details)

The platform creates Stripe Customer Portal sessions on behalf of workspace owners (default tenant) or tenant admins (Enterprise). The portal lets the user update card / view invoices / cancel — Stripe owns the UI; the platform receives state changes via webhooks.

## Trigger

`POST /api/v1/workspaces/{workspace_id}/billing/portal-session` (workspace scope) or `POST /api/v1/admin/tenants/{tenant_id}/billing/portal-session` (Enterprise tenant scope).

## Stripe API call

```python
session = stripe.billing_portal.Session.create(
    customer=stripe_customer_id,
    return_url=validated_return_url,
)
return session.url
```

## Return URL allowlist

Only relative paths are accepted, and they must match one of:

- `/workspaces/{id}/billing`
- `/workspaces/{id}/billing/invoices`
- `/admin/tenants/{id}/billing`

The platform prefixes the returned-from-stripe `return_url` with the platform's base URL (loaded from `PLATFORM_DOMAIN`). Absolute URLs in the request body are rejected with 400.

## Rate limit

10 sessions per `customer_id` per rolling hour. Counter at `billing:portal_session_ratelimit:{customer_id}` in Redis.

## Errors

- `404 customer_not_found` — the workspace/tenant has no Stripe customer record yet (the user must complete an upgrade first).
- `429 rate_limited` — the customer hit the portal-session rate limit.
- `503 stripe_unavailable` — Stripe API unreachable.

## Webhooks emitted by portal actions

When the user updates a card in the portal, Stripe emits `payment_method.attached`. When the user cancels in the portal, Stripe emits `customer.subscription.updated` (with `cancel_at_period_end=true`). The platform's existing handlers cover both.

## Audit chain

Creating a portal session is itself audit-logged via `AuditChainService.append()` with payload `{actor_id, workspace_id, customer_id, return_url}`. The session URL is NOT logged (it's short-lived and is a sensitive bearer token in the wrong hands).
