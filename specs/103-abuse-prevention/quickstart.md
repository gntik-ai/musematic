# Quickstart — UPD-050 Abuse Prevention

**Phase 1 output.** Operator and super-admin walkthroughs for the five user stories. Maps each spec scenario to a runnable demo on `make dev-up` (kind cluster).

---

## Prerequisites

- `make dev-up` running (PostgreSQL + Redis + Kafka + control-plane + admin UI)
- A super-admin account (the bootstrapped one from feature 086 works)
- A test mail catcher running (Mailhog at `localhost:8025` is the dev default)

---

## Walkthrough 1 — Bot signup velocity block (US1)

**Goal**: confirm that 6 signups from one IP within an hour produces 5 successes + 1 HTTP 429 with `Retry-After`.

### Steps

1. Sign in as superadmin. Navigate to `/admin/security/abuse-prevention`. Confirm `velocity_per_ip_hour=5` (default).
2. From a terminal, fire 6 requests from the same source IP:

   ```bash
   for i in $(seq 1 6); do
     curl -i -X POST -H "Content-Type: application/json" \
       -H "X-Forwarded-For: 198.51.100.42" \
       -d "{\"email\":\"bot${i}@example.com\",\"password\":\"...\",\"display_name\":\"bot${i}\"}" \
       http://localhost:8000/api/v1/accounts/register
   done
   ```

3. Expected: requests 1–5 return 202; request 6 returns 429 with `Retry-After: <seconds>` and body `{"code":"velocity_threshold_breached","dimension":"ip",...}`.

### Verify

- Redis: `redis-cli GET abuse:vel:ip:198.51.100.42` returns `6`.
- PostgreSQL durable mirror (after the 60-s cron tick): `SELECT * FROM signup_velocity_counters WHERE counter_key = 'ip:198.51.100.42'`.
- Audit chain: a single `abuse.signup.refused` entry recorded for the threshold-breach (the velocity guard rate-limits to one entry per breach per window).
- Kafka: `kafka-console-consumer --topic security.abuse_events --max-messages 1 | jq 'select(.payload.reason=="velocity_threshold_breached")'`.

### Tune it

Lower the threshold to 3 in the admin UI. Repeat: requests 1–3 succeed, 4 returns 429. Confirms FR-742.2 (no-redeploy tuning).

---

## Walkthrough 2 — Disposable-email rejection (US2)

**Goal**: confirm a `tempmail@10minutemail.com` signup is refused before any verification email is sent.

### Steps

1. Pre-load the disposable-email blocklist (the cron does this weekly; for the demo, run it manually):

   ```bash
   curl -X POST -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
     http://localhost:8000/api/v1/admin/security/email-overrides/refresh-blocklist
   ```

2. Submit a disposable-email signup:

   ```bash
   curl -i -X POST http://localhost:8000/api/v1/accounts/register \
     -H "Content-Type: application/json" \
     -d '{"email":"tempmail@10minutemail.com","password":"...","display_name":"..."}'
   ```

3. Expected: 400 with `{"code":"disposable_email_not_allowed","domain":"10minutemail.com"}`.

### Verify

- Mailhog at `localhost:8025` shows NO new mail (the verification email was never enqueued).
- Audit chain: `abuse.signup.refused` entry with `reason=disposable_email_not_allowed`.
- The 099-style audit redacts the local-part: the entry shows `**@10minutemail.com`, not the full address.

### Override

In the admin UI under `/admin/security/email-overrides`, add `10minutemail.com` with `mode='allow'` and a reason. Repeat the signup — it now proceeds (FR-743.2).

---

## Walkthrough 3 — Suspended user login refusal (US3)

**Goal**: confirm a suspended user sees the `account_suspended` refusal with the appeal contact, and existing sessions invalidate.

### Steps

1. As superadmin, manually suspend a test user:

   ```bash
   curl -X POST -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"user_id":"<uuid>","reason":"manual_super_admin","evidence":{"note":"demo"}}' \
     http://localhost:8000/api/v1/admin/security/suspensions
   ```

2. From an unauthenticated client, attempt login as the suspended user with valid credentials.

3. Expected: HTTP 403, body `{"code":"account_suspended","appeal_contact":"support@musematic.ai"}`.

4. The user's notification inbox (UPD-042) shows a "Your account has been suspended" alert with the appeal route.

### Mid-session test

1. Login as a non-suspended user, capture the session.
2. As superadmin, suspend that user.
3. The next authenticated request from the captured session returns the same `account_suspended` refusal — the session was invalidated mid-flight.

### Lift

```bash
curl -X POST -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"lift_reason":"False positive — confirmed by support"}' \
  http://localhost:8000/api/v1/admin/security/suspensions/<id>/lift
```

The user can log in again on their next attempt; the inbox shows a "Suspension lifted" alert.

---

## Walkthrough 4 — Suspension queue review (US4)

**Goal**: super admin reviews recent automatic suspensions, lifts a false positive.

### Steps

1. Trigger an auto-suspension by exceeding the cost-burn-rate threshold. In dev, the easiest path is a fixture:

   ```bash
   curl -X POST -H "Authorization: Bearer $SUPERADMIN_TOKEN" \
     -d '{"user_id":"<uuid>","amount_usd":50.00}' \
     http://localhost:8000/api/v1/_e2e/cost/inject  # dev-only seed endpoint
   ```

2. Wait for the auto-suspension scanner cron tick (≤5 minutes; in dev, run it inline with `make trigger-cron` if defined).

3. Sign in as superadmin, open `/admin/security/suspensions`. The queue shows the auto-applied suspension with reason `cost_burn_rate` and an evidence summary.

4. Click Lift, supply a reason ("Inspecting test data"), confirm.

5. The user is unsuspended; an audit-chain entry records the lift; the user's inbox gets the "Suspension lifted" alert.

### Distinguishing system vs. human suspensions

The queue UI styles `suspended_by='system'` rows differently from `super_admin` / `tenant_admin` rows so the operator can prioritise the human-applied (typically rarer, more urgent) cases (per US4 acceptance scenario 3).

---

## Walkthrough 5 — Free-tier cost-mining attempt (US5)

**Goal**: confirm the four cost-protection caps fire when a Free-tier user attempts abuse.

### Setup

- A Free-plan tenant exists (UPD-047 default Free plan).
- The Free plan defines `monthly_execution_cap=100`, `allowed_model_tier='cheap_only'`, `max_execution_time_seconds=300`, `max_reasoning_depth=5`.

### Test 1 — Monthly execution cap

1. As a Free user, run executions up to the 100th. The 101st returns 402 `quota_exceeded` (per UPD-047) and an audit-chain entry records the cap.

### Test 2 — Model tier

1. As a Free user, attempt to invoke a premium model (e.g., the most expensive in the catalog). The `model_router` refuses with 403 `model_tier_not_allowed`.

### Test 3 — Execution time

1. As a Free user, start an execution that runs longer than 300 s (use a long-running test agent).
2. At t≈300 s, the runtime auto-terminates the execution; the execution status surfaces `terminated_at_time_cap` as the reason.

### Test 4 — Reasoning depth

1. Construct an agent that recurses on itself.
2. The reasoning engine refuses to expand beyond depth 5; the caller receives a clear `reasoning_depth_exceeded` error.

### Verify

- Each cap-fired event emits a `abuse_prevention_cap_fired_total{cap=...}` increment (visible in Prometheus / Grafana).
- The admin's cost-protection dashboard panel shows the four cap counts in real time.

---

## Walkthrough 6 — Fraud-scoring graceful degradation

**Goal**: confirm that when fraud-scoring is enabled BUT the upstream is unreachable, signups still complete (with a structured-log warning).

### Steps

1. As superadmin, set `fraud_scoring_provider="minfraud"` and register a deliberately broken adapter (e.g., point it at `http://localhost:9999` which is unreachable in dev).
2. Submit a normal signup.
3. Expected: signup completes (202). The structured-log surface shows `WARN: fraud_scoring upstream unreachable; degrading to velocity+disposable+captcha`.
4. Signup latency MUST NOT exceed the no-fraud-scoring baseline by more than 1 second at p95 — verify on the abuse-prevention Grafana dashboard.

This validates SC-006 (graceful-degradation latency budget).

---

## Troubleshooting

### Velocity guard refuses every signup with HTTP 503

Redis is unreachable. The guard fails closed per R1. Check `redis-cli ping`. Until Redis recovers, signups are blocked — this is the intentional safe default.

### Disposable-email check returns false positives

A legitimate domain is on the upstream blocklist. Add an `allow` override at `/admin/security/email-overrides`. The override takes effect on the next signup (in-memory cache invalidates on write).

### CAPTCHA users complain about being shown the challenge despite `captcha_enabled=false`

Check the admin UI — someone may have flipped it on. The audit chain records the actor and timestamp.

### Geo-block reports `geoip_db_loaded=false`

The GeoLite2 .mmdb file is missing from the ConfigMap. Run `helm upgrade --reuse-values` to retrigger the pre-upgrade Job that downloads the DB. Until the DB lands, geo-block returns `country_code=null` for every signup and the policy never matches (graceful-degradation per FR-746.2).

### Auto-suspension fires against a privileged user

This is a bug — it shouldn't happen (FR-744.3). The suspension service refuses to write the row in the first place. If you see one, file an incident; manually delete the orphaned row from `account_suspensions` and grep for the rule that produced it.
