# Contract — Signup Guards REST

**Phase 1 output.** Defines how the existing `POST /api/v1/accounts/register` endpoint at `apps/control-plane/src/platform/accounts/router.py:72` is extended with five abuse-prevention guards. The endpoint's request shape stays backward-compatible: `captcha_token` is optional and only required when the super-admin setting `captcha_enabled=true`.

Guards execute in order (each refusal short-circuits the rest):

1. Velocity (per-IP / per-ASN / per-email-domain)
2. Disposable-email
3. CAPTCHA (when enabled)
4. Geo-block (when enabled)
5. Fraud-scoring (when enabled)

---

## Request additions

```json
POST /api/v1/accounts/register
{
  "email": "user@example.com",
  "password": "...",
  "display_name": "...",
  "captcha_token": "...optional, required if captcha_enabled..."
}
```

Headers consumed by the guards:

- `X-Forwarded-For` / `X-Real-IP` (behind ingress) — source IP for velocity + geo-block + fraud-scoring.
- `X-Forwarded-ASN` (set by the ingress's GeoIP lookup, if available) — ASN for velocity.

---

## Refusal codes

Each guard returns a stable error code so the UI can render a clean message.

| Status | Code | Triggered by | Body fields |
|---|---|---|---|
| 429 | `velocity_threshold_breached` | Per-IP/ASN/domain rolling counter exceeded its threshold | `dimension`, `retry_after_seconds`, `Retry-After` header |
| 400 | `disposable_email_not_allowed` | Domain on effective blocklist | `domain` |
| 400 | `captcha_required` | `captcha_enabled=true` but no token submitted | — |
| 400 | `captcha_invalid` | Token verification failed (provider rejected or replayed) | `provider` |
| 403 | `geo_blocked` | Resolved country denied by `geo_block_mode` | `country_code` |
| 403 | `fraud_scoring_suspend` | Provider returned "suspend" verdict | `verdict` |
| 503 | `abuse_prevention_unavailable` | Velocity Redis check failed (fail-closed per R1) | — |

The successful path is unchanged — 202 with the same body the current endpoint returns.

---

## Audit / Kafka emission

Every refusal emits `abuse.signup.refused` on `security.abuse_events` AND a corresponding audit-chain entry. The payload identifies the reason, the (hashed) actor IP, the email domain, the resolved country (when geo-block fires), and the provider (when CAPTCHA / fraud-scoring fires).

To bound chain-write traffic during a sustained attack, **the velocity guard's audit-chain entries are rate-limited at the source**: one entry per (counter_key, threshold-breach) tuple per rolling window. Every refusal still emits the Kafka event (cheap, async), only the audit-chain emission is throttled.

---

## Idempotency

The signup endpoint is not idempotent (it is a state-creating operation per the existing 099 / 097 contracts). The guards do not change idempotency semantics — they reject before state is created.

---

## Out-of-scope for this contract

- Login-side suspension check is documented in `suspension-rest.md`.
- The existing UPD-037 outer rate-limiter (5/IP/hour) sits in front of this endpoint and is unchanged. The new velocity guards are stacked on top — both fire independently.
