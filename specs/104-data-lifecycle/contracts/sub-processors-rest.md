# Contract — Sub-Processors REST

**Phase 1 output.** Public read endpoint plus admin write endpoints. The admin routes are gated by `require_superadmin`. The public route requires no auth and is served by the operationally-independent `public-pages` Helm release (rule 49).

---

## `GET /api/v1/public/sub-processors`

Public, unauthenticated. Cached aggressively at the edge.

**Headers**: `Cache-Control: public, max-age=300, stale-while-revalidate=900`. Server emits `ETag` from `MAX(updated_at)`.

**Response 200**:

```json
{
  "last_updated_at": "2026-04-15T00:00:00Z",
  "items": [
    {
      "name": "Anthropic, PBC",
      "category": "LLM provider",
      "location": "USA",
      "data_categories": ["prompts", "outputs"],
      "privacy_policy_url": "https://www.anthropic.com/legal/privacy",
      "dpa_url": null,
      "started_using_at": "2024-09-01"
    },
    ...
  ]
}
```

`is_active=false` rows are EXCLUDED. `notes` is NEVER returned by the public endpoint.

---

## `GET /api/v1/public/sub-processors.rss`

RSS 2.0 feed of changes (US4 acceptance #5).

**Headers**: `Content-Type: application/rss+xml; charset=utf-8`

```xml
<rss version="2.0">
  <channel>
    <title>Musematic Sub-Processors Changes</title>
    <link>https://musematic.ai/legal/sub-processors</link>
    <description>Changes to the list of third-party data processors.</description>
    <item>
      <title>Added: MaxMind (Fraud)</title>
      <pubDate>Wed, 15 Apr 2026 00:00:00 GMT</pubDate>
      <description>MaxMind, Inc. — Fraud detection — USA — IP addresses</description>
      <guid>sub_processor_added:uuid</guid>
    </item>
    ...
  </channel>
</rss>
```

The feed re-renders from the `data_lifecycle.sub_processor.{added,modified,removed}` Kafka events as projected into a feed table maintained by the `sub_processors_regenerator` cron.

---

## `POST /api/v1/public/sub-processors/subscribe`

Email subscription for sub-processor changes.

**Request body**:

```json
{ "email": "trust@example.com" }
```

**Response 202**: identical for any email (anti-enumeration). Confirmation email sent via UPD-077 with verification token; subscription only effective after click-through.

---

## Admin endpoints

### `GET /api/v1/admin/sub-processors`

Admin queue. Returns ALL rows including `is_active=false` and `notes`. Auditing not required for read.

### `POST /api/v1/admin/sub-processors`

Add a new sub-processor.

**Request body**:

```json
{
  "name": "MaxMind, Inc.",
  "category": "Fraud",
  "location": "USA",
  "data_categories": ["ip_addresses"],
  "privacy_policy_url": "https://www.maxmind.com/en/privacy-policy",
  "dpa_url": "https://www.maxmind.com/en/dpa",
  "started_using_at": "2026-04-15",
  "notes": "Activated when feature 050 fraud-scoring enabled"
}
```

**Response 201**: full row.

**Behaviour**:
- Audits `data_lifecycle.sub_processor_change` (subtype `added`).
- Emits `data_lifecycle.sub_processor.added` Kafka event.
- Triggers public-page re-render via the regenerator cron's tickless wake (it watches the topic).
- Sends HMAC-signed outbound webhooks to subscribed endpoints (UPD-077 producer call).

### `PATCH /api/v1/admin/sub-processors/{id}`

Modify an existing entry. Same fields as POST, all optional.

Behaviour: same as POST but `data_lifecycle.sub_processor.modified`. The modified row preserves `started_using_at`.

### `DELETE /api/v1/admin/sub-processors/{id}`

Soft delete (set `is_active=false`). Hard delete is not exposed — historical rows must remain queryable for the audit history.

Behaviour: `data_lifecycle.sub_processor.removed` event + audit.

---

## Authorization

The public `/api/v1/public/sub-processors*` routes are served by the `public-pages` Deployment, which has no JWT validation middleware mounted — these are the only platform endpoints reachable without authentication. The admin routes are mounted on the main `apps/control-plane` Deployment.

The `public-pages` release uses a cached PostgreSQL replica for read-only access (`POSTGRES_REPLICA_DSN` env var). When the replica is unreachable, it serves the snapshot baked into the regenerator's ConfigMap (R5 fallback).
