# Contract — Abuse Events Kafka

**Phase 1 output.** Defines the new Kafka topic + 4 event types introduced by UPD-050. The topic is added to the canonical Kafka topic registry in the constitution (rule 22 / topic registry).

---

## Topic

`security.abuse_events`. **NEW**. Producer: `AbusePreventionService`, `SuspensionService`. Consumers: `audit` (writes audit-chain entry), `notifications` (suspension applied → user inbox; threshold-changed → super-admin Slack), `analytics` (refusal feed).

Key: `actor_ip_hash` for `signup.refused`; `user_id` for `suspension.applied` / `lifted`; `setting_key` for `threshold.changed`.

---

## Event types

### `abuse.signup.refused`

Emitted when any signup guard refuses an attempt.

```json
{
  "event_type": "abuse.signup.refused",
  "ts": "...",
  "correlation_id": "...",
  "tenant_id": null,                    // signup is pre-tenant in the public flow
  "payload": {
    "reason": "velocity_threshold_breached",  // see signup-guards-rest.md for full set
    "dimension": "ip",                  // null for non-velocity reasons
    "counter_key_hash": "sha256:...",   // hashed form of ip / asn / domain
    "actor_ip_hash": "sha256:...",
    "email_domain": "example.com",
    "country_code": null,               // populated when geo_blocked
    "provider": null,                   // populated when captcha_invalid / fraud_scoring_*
    "setting_value_at_refusal": 5       // threshold or relevant value at refusal time
  }
}
```

### `abuse.suspension.applied`

Emitted on every new `account_suspensions` row.

```json
{
  "event_type": "abuse.suspension.applied",
  "ts": "...",
  "correlation_id": "...",
  "tenant_id": "...",
  "payload": {
    "suspension_id": "...",
    "user_id": "...",
    "reason": "repeated_velocity",
    "evidence_summary_keys": ["rule", "events", "window_hours"],
    "suspended_by": "system"
  }
}
```

The full `evidence_json` is **not** serialised onto the bus (it can be large and contain sensitive data); consumers that need the evidence query `account_suspensions` directly with the `suspension_id`.

### `abuse.suspension.lifted`

Emitted on lift.

```json
{
  "event_type": "abuse.suspension.lifted",
  "ts": "...",
  "correlation_id": "...",
  "tenant_id": "...",
  "payload": {
    "suspension_id": "...",
    "user_id": "...",
    "lifted_by_user_id": "...",
    "lift_reason": "..."
  }
}
```

### `abuse.threshold.changed`

Emitted when an `abuse_prevention_settings` row is UPDATEd, when an entry is added/removed from `disposable_email_overrides` or `trusted_source_allowlist`, OR when a batch of disposable-email rows is added/removed by the upstream sync cron.

```json
{
  "event_type": "abuse.threshold.changed",
  "ts": "...",
  "correlation_id": "...",
  "tenant_id": null,
  "payload": {
    "scope": "settings",                // or "disposable_overrides" / "allowlist" / "disposable_blocklist_sync"
    "key": "velocity_per_ip_hour",
    "prior_value": 5,
    "new_value": 3,
    "updated_by_user_id": "..."
  }
}
```

For the cron-driven `disposable_blocklist_sync` events, `key` is the (single) batched delta with the format `"+example.com"` or `"-example.com"`; the cron emits one event per chunk of 100 deltas, not one per domain, to bound the bus traffic.

---

## Consumer expectations

### audit

- Writes an audit-chain entry per event using the existing `AuditChainService.write_chain_entry` interface. The entry kind matches the event_type.
- The audit-chain emission for `abuse.signup.refused` is rate-limited at the producer (per signup-guards contract); this consumer doesn't dedupe further.

### notifications

- Subscribes to `abuse.suspension.applied` → fans out to the user's UPD-042 inbox with subject "Account suspended" and the appeal contact.
- Subscribes to `abuse.threshold.changed` (filtered to `scope=settings`) → notifies the super-admin group when a critical knob (CAPTCHA, geo-block, fraud-scoring) changes state. The notification subject names the operator who made the change, for accountability.

### analytics

- Subscribes to `abuse.signup.refused` → feeds the refusal-rate Grafana panels and the `abuse_prevention_signup_refusals_total` counter.
- Subscribes to `abuse.suspension.applied` / `abuse.suspension.lifted` → suspension-rate panels.

---

## Backward compatibility

`security.abuse_events` is a brand-new topic — no existing consumers. Producers register the topic in the per-BC `events.py` module. A consumer that subscribes to a non-existent event type ignores it per the existing envelope contract — adding new event types in future is non-breaking.
