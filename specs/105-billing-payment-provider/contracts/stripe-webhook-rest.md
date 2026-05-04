# Contract: Stripe webhook ingress

**Endpoint**: `POST /api/webhooks/stripe`

Public ingress (no platform auth header — security is by HMAC signature). Operated under `apps/control-plane/src/platform/billing/webhooks/router.py`.

## Request

| Header | Required | Notes |
|---|---|---|
| `Stripe-Signature` | yes | Stripe-supplied HMAC-SHA256 signature line; format `t=<unix>,v1=<sig>[,v0=<sig>]` |
| `Content-Type` | yes | `application/json; charset=utf-8` |

Body: raw Stripe event JSON (do not trust pre-parsed fields — verify HMAC against the *raw* body bytes).

## Responses

| Status | Meaning | Body shape |
|---|---|---|
| `200 OK` | Event processed (or already processed). | `{"status": "processed"}` or `{"status": "already_processed"}` or `{"status": "already_processing"}` or `{"status": "ignored"}` (unknown event_type) |
| `401 Unauthorized` | HMAC signature mismatch against both active and previous secrets. | Generic `{"detail": "invalid_signature"}` — no information about which variant failed. |
| `503 Service Unavailable` | Vault unreachable, signing secrets cannot be loaded. | `{"detail": "secrets_unavailable"}` |

## Idempotency

The endpoint dedupes by `(provider="stripe", event_id)` in two layers (research R3): a Redis 60-s lock and a PostgreSQL unique row. Re-delivery is safe and produces no extra side effects.

## Handled event types (FR-768)

| Stripe event type | Handler | Effect |
|---|---|---|
| `customer.subscription.created` | `handlers/subscription.py:on_created` | Upsert local `subscriptions` row to `active`; emit `billing.subscription.created` Kafka event; audit-chain entry. |
| `customer.subscription.updated` | `handlers/subscription.py:on_updated` | Update local subscription's plan, period, cancel-at-period-end flag; emit `billing.subscription.updated`. |
| `customer.subscription.deleted` | `handlers/subscription.py:on_deleted` | Transition local status to `canceled`; downgrade workspace to Free; emit `billing.subscription.cancelled`. |
| `customer.subscription.trial_will_end` | `handlers/subscription.py:on_trial_ending` | Trial-ending notification dispatched via UPD-077. |
| `invoice.payment_succeeded` | `handlers/invoice.py:on_paid` | Upsert local invoice row; if open `payment_failure_grace` exists for the subscription, resolve it as `payment_recovered` and transition subscription back to `active`; emit `billing.invoice.paid`. |
| `invoice.payment_failed` | `handlers/invoice.py:on_failed` | Upsert local invoice row; transition subscription to `past_due`; open a `payment_failure_grace` row with `grace_ends_at = now + 7d` (or extend existing one's reminder counter); emit `billing.invoice.failed` and `billing.payment_failure_grace.opened`. |
| `payment_method.attached` | `handlers/payment_method.py:on_attached` | Upsert local `payment_methods` row; emit `billing.payment_method.attached`. |
| `charge.dispute.created` | `handlers/dispute.py:on_dispute` | Auto-suspend the affected subscription; emit `billing.dispute.opened`; super-admin notification (urgency=high). |

Unknown event types are acknowledged with `{"status": "ignored"}` and recorded in `processed_webhooks` so re-delivery doesn't trigger handler search again.

## Rate limits

100 req/s per source IP at the ingress controller; a Redis token-bucket fallback at the FastAPI layer protects against ingress misconfiguration.

## Errors during handler execution

A handler-side exception causes:
1. The transaction is rolled back (no partial state).
2. The `processed_webhooks` row is NOT inserted (so Stripe retries succeed).
3. The endpoint returns 200 but with body `{"status": "processed"}`. (We *acknowledge* but the durable record will reflect "not actually processed" — the next retry re-runs.) **EXCEPTION**: handler-side exceptions are caught at the router layer; uncaught exceptions return 500 to force Stripe to retry.

The 200-vs-500 nuance is encoded in `webhooks/router.py:_dispatch_or_500`: any handler that raises returns 500, which Stripe interprets as "retry."
