# Contract — Admin Abuse-Prevention REST

**Phase 1 output.** Defines the threshold-tuning admin endpoints under `/api/v1/admin/security/abuse-prevention/*`. All routes gated by `require_superadmin` per rule 30.

---

## `GET /api/v1/admin/security/abuse-prevention/settings`

Returns all rows from `abuse_prevention_settings`.

**Response 200**:

```json
{
  "settings": [
    { "key": "velocity_per_ip_hour", "value": 5, "updated_at": "...", "updated_by_user_id": "..." },
    { "key": "captcha_enabled", "value": false, "updated_at": "...", "updated_by_user_id": "..." },
    ...
  ]
}
```

---

## `PATCH /api/v1/admin/security/abuse-prevention/settings/{setting_key}`

Update a single setting. The service layer audits the change and emits `abuse.threshold.changed` on `security.abuse_events` with prior + new value.

**Request body**:

```json
{ "value": <jsonb-compatible value> }
```

**Validation**: each `setting_key` has a typed value at the service layer. Invalid types return 422 `setting_value_invalid` with an error detail.

**Response 200**: the updated row.

**Errors**:

| Status | Code |
|---|---|
| 404 | `setting_not_found` (unknown `setting_key`) |
| 422 | `setting_value_invalid` (type mismatch) |
| 403 | `not_authorized` (caller is not superadmin) |

---

## `GET /api/v1/admin/security/abuse-prevention/allowlist`

Returns rows from `trusted_source_allowlist`.

**Query params** (optional): `entry_kind` to filter by `ip_cidr` or `email_domain`.

---

## `POST /api/v1/admin/security/abuse-prevention/allowlist`

Add an entry. Body: `{ "entry_kind": "ip_cidr", "entry_value": "10.0.0.0/8", "note": "..." }`. Audits the add. Returns the row.

---

## `DELETE /api/v1/admin/security/abuse-prevention/allowlist/{entry_kind}/{entry_value}`

Remove an entry. Audits the remove. 204 on success, 404 if not present (idempotent).

---

## `GET /api/v1/admin/security/abuse-prevention/refusals/recent`

Returns the most recent N refusals (paginated cursor) for operator monitoring. Powers the dashboard's refusal feed.

**Query params**: `limit` (1–200, default 50), `cursor` (opaque ISO timestamp), `reason` (optional filter).

**Response 200**:

```json
{
  "items": [
    {
      "ts": "...",
      "reason": "velocity_threshold_breached",
      "dimension": "ip",
      "counter_key_hash": "sha256:...",
      "email_domain": "example.com",
      "country_code": null,
      "provider": null
    },
    ...
  ],
  "next_cursor": "..."
}
```

The IP is **never** returned in cleartext on this endpoint — only the SHA-256 hash. Operators investigating a specific IP must hash the IP themselves and grep, by design (privacy note in spec).

---

## Rate limiting

The admin surface has its own rate-limit group per rule 29: 60 req/min per superadmin user. The settings PATCH endpoint additionally cools down 1 second after each write to discourage rapid threshold churn (a UX nudge — no hard block).
