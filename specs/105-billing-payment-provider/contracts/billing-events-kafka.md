# Contract: `billing.events` Kafka topic

**Topic name**: `billing.events`
**Partitions**: 3 (prod), 1 (dev)
**Replication factor**: 3 (prod), 1 (dev)
**Retention**: 7 days
**Partition key**: `tenant_id` (str(UUID))

All envelopes use the canonical `EventEnvelope` (v1) defined in `apps/control-plane/src/platform/common/events/envelope.py`. The `event_type` discriminator carries the payload shape.

## Event types

### `billing.subscription.created`

Producer: `customer.subscription.created` webhook handler.
Consumers: `billing.quotas` (apply new caps), observability dashboards, `audit.chain`.

Payload (Pydantic v2):
```json
{
  "subscription_id": "uuid",
  "tenant_id": "uuid",
  "workspace_id": "uuid|null",
  "plan_slug": "pro",
  "stripe_customer_id": "cus_...",
  "stripe_subscription_id": "sub_...",
  "current_period_end": "2026-06-04T00:00:00Z",
  "trial_end": null,
  "correlation_context": { ... }
}
```

### `billing.subscription.updated`

Producer: `customer.subscription.updated` webhook handler + manual upgrade/downgrade API.

Payload:
```json
{
  "subscription_id": "uuid",
  "from_plan_slug": "pro",
  "to_plan_slug": "pro",
  "cancel_at_period_end": true,
  "current_period_end": "2026-06-04T00:00:00Z",
  "correlation_context": { ... }
}
```

### `billing.subscription.cancelled`

Producer: `customer.subscription.deleted` webhook + cancel API.

Payload:
```json
{
  "subscription_id": "uuid",
  "scheduled_at": "2026-05-04T10:00:00Z",
  "effective_at": "2026-06-04T00:00:00Z",
  "reason": "switched_to_competitor",
  "correlation_context": { ... }
}
```

### `billing.invoice.paid`

Producer: `invoice.payment_succeeded` webhook handler.

Payload:
```json
{
  "invoice_id": "uuid",
  "subscription_id": "uuid",
  "amount_total_eur": "24.20",
  "amount_tax_eur": "4.20",
  "currency": "EUR",
  "paid_at": "2026-06-01T00:05:30Z",
  "correlation_context": { ... }
}
```

### `billing.invoice.failed`

Producer: `invoice.payment_failed` webhook handler.

Payload:
```json
{
  "invoice_id": "uuid",
  "subscription_id": "uuid",
  "amount_total_eur": "24.20",
  "currency": "EUR",
  "attempt_count": 1,
  "next_retry_at": "2026-05-08T00:00:00Z",
  "correlation_context": { ... }
}
```

### `billing.payment_method.attached`

Producer: `payment_method.attached` webhook handler.

Payload:
```json
{
  "payment_method_id": "uuid",
  "tenant_id": "uuid",
  "workspace_id": "uuid|null",
  "stripe_payment_method_id": "pm_...",
  "brand": "visa",
  "last4": "4242",
  "is_default": true,
  "correlation_context": { ... }
}
```

### `billing.payment_failure_grace.opened`

Producer: `PaymentFailureGraceService.start_grace()`.

Payload:
```json
{
  "grace_id": "uuid",
  "subscription_id": "uuid",
  "started_at": "2026-05-04T10:00:00Z",
  "grace_ends_at": "2026-05-11T10:00:00Z",
  "correlation_context": { ... }
}
```

### `billing.payment_failure_grace.resolved`

Producer: `PaymentFailureGraceService.resolve_grace()`.

Payload:
```json
{
  "grace_id": "uuid",
  "subscription_id": "uuid",
  "resolved_at": "2026-05-11T10:05:00Z",
  "resolution": "downgraded_to_free",
  "correlation_context": { ... }
}
```

### `billing.dispute.opened`

Producer: `charge.dispute.created` webhook handler.

Payload:
```json
{
  "stripe_charge_id": "ch_...",
  "stripe_dispute_id": "dp_...",
  "tenant_id": "uuid",
  "subscription_id": "uuid",
  "amount_eur": "24.20",
  "reason": "credit_not_processed",
  "correlation_context": { ... }
}
```

## Consumer expectations

- **`billing.quotas` consumer** (existing UPD-047 quota engine): listens for `billing.subscription.created/updated/cancelled` and `billing.payment_failure_grace.resolved` (specifically for `downgraded_to_free`) to recompute caps.
- **`audit.chain` consumer**: appends a chain entry per event with non-sensitive metadata.
- **`notifications` consumer**: listens for `billing.invoice.failed`, `billing.payment_failure_grace.opened`, `billing.payment_failure_grace.resolved`, `billing.dispute.opened` and dispatches user/operator alerts via the existing UPD-077 channel router.
- Unknown consumers MUST tolerate event types they don't understand (forward-compatibility).
