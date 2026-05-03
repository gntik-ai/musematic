# Contract — Workspace Export REST

**Phase 1 output.** Routes mounted under `/api/v1/workspaces/{workspace_id}/data-export/*`. All routes gated by `require_workspace_member`. RBAC: only workspace owners or admins may request.

---

## `POST /api/v1/workspaces/{workspace_id}/data-export`

Request a new workspace export. Idempotent against an in-flight job — concurrent requests return the existing pending/processing job.

**Request body**: empty (the workspace_id path param is the scope).

**Response 202**:

```json
{
  "id": "uuid",
  "scope_type": "workspace",
  "scope_id": "uuid",
  "status": "pending",
  "requested_at": "2026-05-03T10:00:00Z",
  "estimated_completion": "2026-05-03T10:08:00Z"
}
```

**Behaviour**:
- Audits `data_lifecycle.export_requested`.
- Emits `data_lifecycle.export.requested` Kafka event.
- Returns the in-flight job if `status IN ('pending','processing')` already exists for this workspace (idempotency guard).

**Errors**:

| Status | Code |
|---|---|
| 403 | `not_workspace_owner_or_admin` |
| 404 | `workspace_not_found` |
| 422 | `cross_region_export_blocked` (when residency policy denies) |
| 429 | `export_rate_limit_exceeded` (max 5 exports per workspace per 24 h) |

---

## `GET /api/v1/workspaces/{workspace_id}/data-export/jobs`

List the workspace's recent export jobs (most recent 50, paginated).

**Query params**: `limit` (1–50, default 20), `cursor` (opaque), `status` (optional filter).

**Response 200**:

```json
{
  "items": [
    {
      "id": "uuid",
      "status": "completed",
      "started_at": "...",
      "completed_at": "...",
      "output_size_bytes": 12345678,
      "output_expires_at": "..."
    }
  ],
  "next_cursor": null
}
```

`output_url` is **not** returned by list — it requires a separate fetch (audited).

---

## `GET /api/v1/workspaces/{workspace_id}/data-export/jobs/{job_id}`

Returns full job details including the signed URL when `status='completed'` and now < `output_expires_at`.

**Response 200** (completed):

```json
{
  "id": "uuid",
  "status": "completed",
  "started_at": "...",
  "completed_at": "...",
  "output_url": "https://...presigned...",
  "output_size_bytes": 12345678,
  "output_expires_at": "..."
}
```

**Behaviour**:
- Returns a fresh signed URL with TTL = remaining time until `output_expires_at` (max 7 days).
- Audits `data_lifecycle.export_url_issued` on every fetch.
- For non-completed jobs, `output_url` is omitted; for failed jobs, `error_message` (redacted) is included.

**Errors**:

| Status | Code |
|---|---|
| 404 | `export_job_not_found` |
| 410 | `export_url_expired` |

---

## ZIP layout

```
metadata.json                         # workspace_id, exported_at, format_version, schema URLs
agents/
  {agent_fqn}.json                    # registry profile + revisions
executions/
  {execution_id}.json                 # journal + cost summary
audit/
  audit_chain.jsonl                   # chronological audit entries
costs/
  cost_summary.json                   # daily rollups
members/
  members.json                        # display names + workspace roles only (no global emails)
README.md                             # how to read the export
```

`members/members.json` honours the rule-46 / rule-47 scope: a workspace owner sees ONLY their workspace's member list; cross-workspace email addresses are NEVER included. This is the privacy guard from US1 acceptance #4.
