# Quickstart: Multi-Channel Notifications

**Feature**: 077-multi-channel-notifications

This document is a hands-on walkthrough of every primary path. Each Q-block is a complete scenario producing a single observable outcome.

## Prerequisites

- Control plane running with `FEATURE_MULTI_CHANNEL_NOTIFICATIONS=true`.
- Audit chain (UPD-024) and DLP/residency (feature 076) enabled.
- Vault accessible and `SecretProvider` healthy.
- Migration `058_multi_channel_notifications.py` applied.

---

## Q1 — Per-user email channel with quiet hours (US1)

```bash
# 1. As the user, register an email channel.
curl -X POST $API/api/v1/me/notifications/channels \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{
    "channel_type": "email",
    "target": "alice@example.com",
    "display_name": "Personal email",
    "quiet_hours": {"start": "22:00", "end": "08:00", "timezone": "Europe/Madrid"},
    "alert_type_filter": ["execution.failed", "governance.verdict.issued"]
  }'
# 201 {id, target, verified_at: null, ...}

# 2. Click the verification link (or POST the token).
curl -X POST $API/api/v1/me/notifications/channels/$CHANNEL_ID/verify \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{"token": "<token-from-email>"}'
# 200 {verified_at: "..."}

# 3. Trigger an alert outside quiet hours → email arrives.
# 4. Trigger an alert inside quiet hours → email NOT sent;
#    in-app channel still receives it.
# 5. Trigger a critical-severity alert inside quiet hours → email IS sent
#    (critical bypasses quiet hours).
```

**Verify**: `notification_channel_configs` row has `verified_at` set; `alert_delivery_outcomes` rows for the test alerts show `outcome=success` (outside QH) and `outcome=success` for in-app + no email row (inside QH).

---

## Q2 — Workspace outbound webhook (US2)

```bash
# 1. As workspace admin, register a webhook for execution failures.
curl -X POST $API/api/v1/notifications/webhooks \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -d '{
    "workspace_id": "'$WS_ID'",
    "name": "Incident bridge",
    "url": "https://incidents.acme.com/musematic-webhook",
    "event_types": ["execution.failed", "governance.verdict.issued"]
  }'
# 201 returns {id, signing_secret: "<one-time>", ...}

# 2. Save the secret (the response will not include it again).
SECRET="<one-time-secret>"

# 3. Trigger an execution.failed event for the workspace.
# 4. Verify the receiver got a POST with:
#    X-Musematic-Signature: sha256=<hex>
#    X-Musematic-Timestamp: <unix>
#    X-Musematic-Idempotency-Key: <uuid_v5>
# 5. Verify HMAC by recomputing locally:
python3 -c '
import hmac, hashlib, sys
secret = b"<SECRET>"
ts = "<timestamp>"
body = open("/tmp/captured.json","rb").read()
expected = hmac.new(secret, f"{ts}.".encode()+body, hashlib.sha256).hexdigest()
print(expected == sys.argv[1])
' <signature_hex>
# True
```

**Verify**: `webhook_deliveries` row has `status='delivered'`, `attempts=1`, `last_response_status=200`.

---

## Q3 — At-least-once with retries (US2)

```bash
# 1. Receiver returns 503 for the next 2 deliveries, then 200.
# 2. Trigger an event; observe in webhook_deliveries:
#    attempt 1 -> 503 -> next_attempt_at = now+60s
#    attempt 2 -> 503 -> next_attempt_at = now+300s
#    attempt 3 -> 200 -> status='delivered'
# 3. All 3 attempts share the same idempotency_key.
SELECT idempotency_key, attempts, last_response_status, status
FROM webhook_deliveries WHERE webhook_id = '$WEBHOOK_ID'
ORDER BY created_at DESC LIMIT 1;
```

**Verify**: One row, idempotency_key stable across retries, final `status='delivered'`.

---

## Q4 — Permanent 4xx skips retries (US2)

```bash
# 1. Receiver returns 410 Gone.
# 2. Trigger an event.
# 3. Inspect webhook_deliveries: attempts=1, status='dead_letter',
#    failure_reason='4xx_permanent'.
```

**Verify**: No retries scheduled; row is in dead-letter immediately.

---

## Q5 — Dead-letter inspection and replay (US5)

```bash
# 1. Receiver is hard-down (returns 503 for all attempts).
# 2. Trigger 5 events; wait for retry budget exhaustion.
# 3. List dead-letter:
curl $API/api/v1/notifications/dead-letter?workspace_id=$WS_ID \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN"
# 200 [{...}, ...] - 5 entries.

# 4. Restore receiver.
# 5. Batch replay:
curl -X POST $API/api/v1/notifications/dead-letter/replay-batch \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -d '{"workspace_id": "'$WS_ID'", "since": "..."}'
# 202 {job_id: "..."}

# 6. Wait one retry tick (~30s); list dead-letter again.
# 7. Verify all 5 are now delivered (status='delivered' on the
#    new replay rows; original dead-letter rows still present
#    as audit trail).
```

**Verify**: `webhook_deliveries` shows 5 dead-letter rows + 5 new replay rows linking back via `replayed_from`; replay rows have `status='delivered'` and reuse the original `idempotency_key`.

---

## Q6 — Slack channel (US3)

```bash
# 1. Add a Slack channel (incoming webhook URL).
curl -X POST $API/api/v1/me/notifications/channels \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{
    "channel_type": "slack",
    "target": "https://hooks.slack.com/services/T0/B0/SECRET",
    "display_name": "Personal Slack DM",
    "alert_type_filter": ["attention.requested"]
  }'
# 2. Confirm receipt of the test card in Slack and verify with
#    the displayed code.
# 3. Trigger an attention.requested alert; observe Block Kit message
#    in Slack with title, severity, deep link.
```

**Verify**: Slack channel rendering matches the spec; `alert_delivery_outcomes` row shows `outcome=success`.

---

## Q7 — Microsoft Teams channel (US4)

```bash
# Same shape as Q6 with channel_type="teams" and a Teams connector URL.
# Verify the Adaptive Card appears in the target Teams channel.
```

---

## Q8 — SMS for critical only (US6)

```bash
# 1. Register a phone number; submit verification code.
curl -X POST $API/api/v1/me/notifications/channels \
  -H "Authorization: Bearer $USER_TOKEN" \
  -d '{
    "channel_type": "sms",
    "target": "+34666123456",
    "display_name": "Oncall mobile",
    "severity_floor": "critical"
  }'
# 2. Submit 6-digit verify code.
# 3. Trigger a high-severity alert -> NO SMS sent (below floor).
# 4. Trigger a critical-severity alert -> SMS sent.
# 5. Inspect Twilio (or whichever provider) for the message body.
```

**Verify**: One SMS sent for the critical alert; per-workspace cost counter incremented; below-floor alert leaves no SMS trace.

---

## Q9 — Quiet-hours bypass for critical (Edge case)

```bash
# 1. User has an email channel with quiet hours 22:00-08:00.
# 2. At 23:30 local time, trigger:
#    a) execution.failed (severity=high) -> NO email.
#    b) governance.violation.detected (severity=critical) -> email IS sent.
```

**Verify**: Quiet hours suppress non-critical, critical bypasses cleanly.

---

## Q10 — DLP redact on outbound (rule 34)

```bash
# 1. Configure workspace DLP to redact email addresses in outbound
#    payloads.
# 2. Trigger an event whose payload contains "user@example.com".
# 3. Inspect webhook_deliveries.payload — email is replaced by
#    "[REDACTED:email]".
# 4. Confirm the receiver got the redacted payload (verify HMAC over
#    the redacted body, not the original).
```

**Verify**: HMAC computed over redacted bytes; signature verifies with the secret; sensitive content not transmitted.

---

## Q11 — Residency block at registration (rule 18)

```bash
# 1. Workspace residency restricts egress to eu-* regions.
# 2. As workspace admin, attempt to register a webhook URL whose
#    DNS resolves to us-east-1.
curl -X POST $API/api/v1/notifications/webhooks \
  -H "Authorization: Bearer $WS_ADMIN_TOKEN" \
  -d '{"workspace_id": "'$WS_ID'", "url": "https://us-east-1-receiver.example/incoming"}'
# 422 {"error":"residency_violation","detail":"webhook URL region 'us-east-1' is not in allowed_egress_regions"}
```

---

## Q12 — Backwards compatibility

```bash
# 1. Disable the feature flag (FEATURE_MULTI_CHANNEL_NOTIFICATIONS=false).
# 2. Trigger an alert for a user who has NO notification_channel_configs
#    rows but DOES have user_alert_settings.delivery_method=email.
# 3. Verify email is sent via the legacy path.
# 4. Re-enable the flag.
# 5. Add one notification_channel_configs row for the same user
#    (channel_type=in_app).
# 6. Trigger another alert.
# 7. Verify routing now uses the per-channel rows; legacy
#    user_alert_settings.delivery_method is ignored.
```

---

## Smoke checklist

After deployment, run all 12 Q-scripts in a fresh workspace and verify:

- [ ] All `webhook_deliveries` rows that should be `delivered` end at `status='delivered'`.
- [ ] All HMAC signatures verify against the secret resolved from Vault.
- [ ] Idempotency keys are deterministic (`uuid_v5(webhook.id, event.id)`).
- [ ] Dead-letter list filters by workspace correctly; cross-workspace 403.
- [ ] Audit chain entries exist for every channel/webhook CRUD and every replay.
- [ ] No log line in any module contains a HMAC secret, SMS API token, or OAuth-style credential.
- [ ] DLQ depth threshold alert lands on `monitor.alerts` exactly once per cooldown window.
- [ ] Quiet-hours evaluation correct across DST transitions (parameterised in CI).
