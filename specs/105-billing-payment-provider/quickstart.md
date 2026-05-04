# Quickstart: UPD-052 — Billing and Overage operator runbook

This is the operator-facing checklist for bringing UPD-052 up in dev/staging/prod. Engineers running `make dev-up` should read § Dev cluster Stripe test mode first; on-call should read § Stripe Dashboard configuration and § Webhook signing-secret rotation.

## Stripe Dashboard configuration (one-time)

In the Stripe Dashboard for the platform's Stripe account:

1. **Default API version** — set to `2024-06-20` (or whichever version the platform pins via `Stripe-Version` header). Webhooks use the dashboard default.
2. **Tax** — enable Stripe Tax. Configure VATIN and IVA OSS registration. The platform reads `automatic_tax: { enabled: true }` on subscription creation.
3. **Customer Portal** — enable it. Configure allowed actions: update card, view invoices, cancel subscription. The platform creates sessions on demand.
4. **Webhook endpoint** — add `https://<platform-domain>/api/webhooks/stripe`. Subscribe to: `customer.subscription.created`, `customer.subscription.updated`, `customer.subscription.deleted`, `customer.subscription.trial_will_end`, `invoice.payment_succeeded`, `invoice.payment_failed`, `payment_method.attached`, `charge.dispute.created`. Copy the **signing secret**.
5. **Prices** — create prices for each plan slug:
   - `Free`: no Stripe price (the workspace runs against the local Free plan version without a Stripe subscription).
   - `Pro`: monthly fixed-price (`price_1...`); record the price id.
   - `Pro overage`: metered price priced per minute (`price_1...`); record the price id.
   - `Enterprise`: custom price per tenant — created on demand by the super-admin tenant-provisioning flow.
   Save the price ids in the platform's `plan_versions.stripe_price_id` and `stripe_overage_price_id` columns (already exist from UPD-047).
6. **Test cards** — confirm 4242-4242-4242-4242 succeeds and 4000-0000-0000-0002 declines for the test mode key.

## Vault secret layout

Two paths must exist before the control-plane comes up:

```
secret/data/musematic/{env}/billing/stripe/api-key:
  { "key": "sk_test_..." }   # test mode in dev; sk_live_... in prod

secret/data/musematic/{env}/billing/stripe/webhook-secret:
  { "active":   "whsec_...",
    "previous": null }       # populate previous during rotation; null otherwise
```

Both paths are KV v2. Operators with the `billing-stripe` Vault policy can read; nothing else can. Rotation is documented below.

## Helm values

The `control-plane` sub-chart picks up the following new values:

```yaml
billing:
  provider: stripe              # or "stub" in unit tests
  stripe:
    mode: test                  # "test" in dev/staging; "live" in prod
    apiVersion: "2024-06-20"
    publishableKey: pk_test_xxx # public; safe to ship in values
    pricesMapping:
      free: null
      pro: price_xxx
      pro_overage: price_yyy
    portalReturnUrlAllowlist:
      - "/workspaces/{id}/billing"
      - "/workspaces/{id}/billing/invoices"
      - "/admin/tenants/{id}/billing"
```

A startup health-check refuses to boot the control-plane in `BILLING_STRIPE_MODE=live` if the Vault api-key starts with `sk_test_` (and vice versa). This prevents the classic "test charge against live customer" disaster.

## Dev cluster Stripe test mode

```bash
# 1. Make sure Vault is up and seeded with stripe.api-key + webhook-secret
make dev-up

# 2. Run the Stripe CLI listener so test events flow back to your local kind cluster
stripe listen --forward-to "http://localhost:8000/api/webhooks/stripe" \
              --skip-verify  # only if you run without TLS in dev

# Stripe CLI will print a session-specific webhook signing secret. In dev,
# write it to Vault overriding the production secret:
vault kv put secret/musematic/dev/billing/stripe/webhook-secret \
   active="$(stripe listen --print-secret)" previous=null

# 3. Trigger any webhook by hand
stripe trigger customer.subscription.created
stripe trigger invoice.payment_failed
```

The dev cluster is configured for Stripe test mode by default; the Helm values shipped under `deploy/helm/platform/values.dev.yaml` set `billing.stripe.mode: test`. Stripe test cards work against this stack as in production.

## Webhook signing-secret rotation playbook

Stripe documents this; we mirror it verbatim:

1. In the Stripe Dashboard, add a **second** webhook endpoint (same URL). Copy its signing secret — call this `new_secret`.
2. In Vault, write the rotated secrets:
   ```
   vault kv put secret/musematic/{env}/billing/stripe/webhook-secret \
       active="<new_secret>" previous="<old_secret>"
   ```
3. The control-plane re-reads the secrets on the next webhook (Vault reads are not cached longer than 60s). For the rotation window, both secrets are accepted.
4. After 24 hours of clean traffic on `new_secret`, delete the old endpoint in Stripe and update Vault:
   ```
   vault kv put secret/musematic/{env}/billing/stripe/webhook-secret \
       active="<new_secret>" previous=null
   ```
5. Confirm by inspecting the `billing_webhook_signature_failed_total` Prometheus metric — it should be 0 over the previous hour.

## Smoke test after deployment

```bash
# Replace BASE_URL and CUSTOMER_ID as appropriate.
BASE_URL=https://control-plane.dev.musematic.ai
CUSTOMER_ID=cus_xxx

# Webhook endpoint reachable + correctly rejects unsigned bodies
curl -i "$BASE_URL/api/webhooks/stripe" -d '{}'                                   # → 401
curl -i "$BASE_URL/api/webhooks/stripe"                                           # → 401

# Customer Portal session creation reaches Stripe and returns a redirect URL
curl -X POST -H "Authorization: Bearer $JWT" \
  -d '{"return_url": "/workspaces/'"$WS_ID"'/billing"}' \
  "$BASE_URL/api/v1/workspaces/$WS_ID/billing/portal-session"                     # → 200 with {portal_url}

# Trigger a real test webhook via stripe-cli and confirm the local subscription
stripe trigger customer.subscription.created
sleep 2
psql -c "SELECT status, stripe_subscription_id FROM subscriptions \
         WHERE workspace_id='$WS_ID' ORDER BY created_at DESC LIMIT 1"            # → status=active
```

## Failure modes

| Symptom | Likely cause | First step |
|---|---|---|
| Webhook 503 in logs, no events processed | Vault is down | `vault status`; check `vault-agent-injector` pod logs |
| Webhook 401 spike (≥10 in 15 min) | Rotation window expired or Stripe Dashboard secret changed | Verify both `active` and `previous` in Vault; check Dashboard for endpoint config drift |
| Subscription stuck in `pending` | Webhook from Stripe never arrived | Inspect `processed_webhooks` for the event id; replay via `stripe events resend <event_id>` |
| Day-7 downgrade didn't fire | `grace_monitor` cron is paused | Check the APScheduler logs in the worker profile; restart with `kubectl rollout restart deployment control-plane-worker` |
| Invoice has `pdf_url=null` | Stripe hasn't finalized the invoice | Wait until `status='open'` or `status='paid'`; the URL is only valid for finalized invoices |
| Customer Portal returns "no portal" | Customer Portal not enabled in Stripe Dashboard | Go to Dashboard → Settings → Billing → Customer Portal → enable |
| 503 on `POST /billing/upgrade` | Stripe Tax disabled or VATIN missing | Stripe Tax must be enabled and configured before any subscription can be created |
| `mode=live` boot refused | Vault `api-key` starts with `sk_test_` while Helm values set live | Write the live api-key into Vault, then restart |

## Audit chain integrity

After any payment flow run (manual or journey test), verify the chain integrity:

```bash
python tools/verify_audit_chain.py --tenant <tenant-uuid>
```

The tool exits 0 when the chain verifies, non-zero on hash mismatch. The Day-7 downgrade test in particular emits ~6 chain entries (grace opened, day-1/3/5 reminders, downgrade, grace resolved); the verifier walks all of them.
