# Contract — Geo-Policy REST

**Phase 1 output.** Defines the geo-block configuration endpoints at `/api/v1/admin/security/geo-policy/*`. All routes gated by `require_superadmin`.

The geo-block feature is **off by default** (`geo_block_mode='disabled'`). When enabled, it operates in one of two mutually-exclusive modes:

- `deny_list` — block listed countries; allow all others.
- `allow_list` — allow only listed countries; block all others.

The two modes are intentionally exclusive — operators do not maintain both at the same time. Switching mode resets the country list to empty and asks for explicit re-confirmation.

---

## `GET /api/v1/admin/security/geo-policy`

Returns the current geo-policy.

**Response 200**:

```json
{
  "mode": "disabled",       // or "deny_list" / "allow_list"
  "country_codes": [],
  "geoip_db_loaded": true,
  "geoip_db_version": "20260501",
  "updated_at": "...",
  "updated_by_user_id": "..."
}
```

`geoip_db_loaded` is true when the GeoLite2 .mmdb file is present and the reader initialised successfully. `false` means geo-resolution is degraded (R5's graceful-degradation path).

---

## `PATCH /api/v1/admin/security/geo-policy`

Updates the policy mode + country list together.

**Request body**:

```json
{
  "mode": "deny_list",
  "country_codes": ["RU", "KP"],
  "confirm_mode_switch": true
}
```

**Behaviour**:
- Switching `mode` to a different value REQUIRES `confirm_mode_switch=true` and resets `country_codes` if the caller didn't explicitly supply a new list. This prevents an operator from accidentally inheriting a deny-list when switching to allow-list or vice versa.
- `country_codes` is validated against ISO-3166-1 alpha-2 (2-letter, uppercase). Unknown codes are refused (422 `country_code_invalid`).
- Audits the change. Emits `abuse.threshold.changed` with prior + new (mode, country_codes) tuple.

**Errors**:

| Status | Code |
|---|---|
| 422 | `mode_invalid` |
| 422 | `country_code_invalid` |
| 409 | `mode_switch_requires_confirmation` |

---

## `GET /api/v1/admin/security/geo-policy/recent-blocks`

Returns the most recent N geo-blocked signup attempts, paginated.

**Query params**: `limit` (1–200, default 50), `cursor`, `country_code` (optional filter).

**Response 200**:

```json
{
  "items": [
    { "ts": "...", "country_code": "RU", "actor_ip_hash": "sha256:...", "email_domain": "..." },
    ...
  ],
  "next_cursor": "..."
}
```

This is a separate endpoint from the generic refusal feed (under `admin-abuse-prevention-rest.md`) so an operator running a country-deny-list can see at a glance which countries the policy is hitting.

---

## Operational notes

- The GeoLite2 .mmdb refresh runs at chart-upgrade time (R5). Operators wanting to refresh between upgrades can run `helm upgrade` with `--reuse-values` to retrigger the pre-upgrade Job.
- When `geoip_db_loaded=false`, the geo-block guard returns `country_code=null` for every signup and the policy never matches. This is graceful degradation per FR-746.2 — no signup is blocked when the DB is missing.
- Country codes in `country_codes` are stored as JSON array (`["RU", "KP"]`) inside the `geo_block_country_codes` setting row. The mode is stored separately as `geo_block_mode`.
