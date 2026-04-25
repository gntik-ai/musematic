# DSR Handling Contract

**Feature**: 076-privacy-compliance
**Module**: `apps/control-plane/src/platform/privacy_compliance/services/dsr_service.py`
**Router**: `apps/control-plane/src/platform/privacy_compliance/router.py`

## Lifecycle state machine

```
received ──[optional hold]──▶ scheduled ──[hold expires]──▶ in_progress
received ──[immediate]─────────────────────────────────────▶ in_progress
in_progress ──[cascade completes]──▶ completed (terminal)
in_progress ──[cascade fails]──────▶ failed (retry-friendly)
scheduled ──[superadmin cancel]────▶ cancelled (terminal)
```

## Six request types

| Type | Handler | Primary action |
|---|---|---|
| `access` | `_handle_access(dsr)` | Gather subject's data from PostgreSQL + Qdrant + OpenSearch; redact third-party PII via DLP; return a structured export. |
| `rectification` | `_handle_rectification(dsr)` | Apply a user-supplied field update across the subject's records (admin-reviewed). |
| `erasure` | `_handle_erasure(dsr)` | Invoke `CascadeOrchestrator.run(dsr_id, subject_user_id)`; produce tombstone. |
| `portability` | `_handle_portability(dsr)` | Same as `access` but output in a machine-readable format (JSON + CSV bundle). |
| `restriction` | `_handle_restriction(dsr)` | Mark the subject's `users.processing_restricted = true`; downstream services honour via an auth-middleware check (new flag column). |
| `objection` | `_handle_objection(dsr)` | Revoke consent_types per subject preference; stop auto-decision-making (no-op in v1 — no auto-decision feature exists). |

## Admin REST endpoints

All under `/api/v1/privacy/dsr/*`. Every method depends on
`privacy_officer` / `platform_admin` / `superadmin` (new role +
existing). Tagged `['admin', 'privacy', 'dsr']`.

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/privacy/dsr` | Open a new DSR | `privacy_officer`, `platform_admin`, `superadmin` |
| `GET /api/v1/privacy/dsr` | List DSRs (filter by subject, status, type) | `privacy_officer`, `auditor`, `compliance_officer`, `superadmin` |
| `GET /api/v1/privacy/dsr/{id}` | Get single DSR | same |
| `POST /api/v1/privacy/dsr/{id}/cancel` | Cancel a `scheduled` DSR (hold window only) | `superadmin` (2PA) |
| `POST /api/v1/privacy/dsr/{id}/retry` | Retry a `failed` cascade | `privacy_officer`, `platform_admin`, `superadmin` |
| `GET /api/v1/privacy/dsr/{id}/tombstone` | Fetch tombstone for an erasure DSR (unsigned JSON) | `privacy_officer`, `auditor`, `compliance_officer`, `superadmin` |
| `POST /api/v1/privacy/dsr/{id}/tombstone/signed` | Export signed tombstone | `privacy_officer`, `auditor`, `compliance_officer`, `superadmin` |
| `GET /api/v1/privacy/dsr/{id}/export` | Download access/portability export | same |

## Self-service endpoints (per rule 46)

Under `/api/v1/me/dsr/*`. Scoped to `current_user`:

| Method + path | Purpose |
|---|---|
| `POST /api/v1/me/dsr` | Submit a DSR on behalf of oneself (e.g. user requests their own data export) |
| `GET /api/v1/me/dsr` | List own DSRs |
| `GET /api/v1/me/dsr/{id}` | Get own DSR |

Self-service DSRs are gated by the `FEATURE_PRIVACY_DSR_ENABLED` flag
(per constitution §10).

## Request body shape

### `POST /dsr`

```json
{
  "subject_user_id": "<UUID>",
  "request_type": "erasure",
  "legal_basis": "consent withdrawn per GDPR Art. 17(1)(b)",
  "hold_hours": 24
}
```

`hold_hours`: optional (0–72). If `> 0`, DSR starts at `status=scheduled`
with `scheduled_release_at = now() + hold_hours * 3600s`; a background
worker (`hold_window_releaser`) transitions to `in_progress` when the
hold elapses. A superadmin can cancel during the hold via the cancel
endpoint (2PA enforced).

## Audit chain integration

Every state transition emits an `AuditChainEntry` via
`UPD-024.AuditChainService.append()`:

- `privacy.dsr.received` (on POST)
- `privacy.dsr.scheduled_with_hold` (if hold > 0)
- `privacy.dsr.in_progress` (on cascade start)
- `privacy.deletion.cascaded` (on cascade adapter run, one per store)
- `privacy.dsr.completed` (terminal success)
- `privacy.dsr.failed` (terminal failure)

## Unit-test contract

- **DSR1** — open erasure DSR → `status='received'`, audit chain
  entry, Kafka event.
- **DSR2** — open erasure with `hold_hours=24` → `status='scheduled'`,
  `scheduled_release_at` populated.
- **DSR3** — hold window releaser transitions scheduled → in_progress
  at the right moment.
- **DSR4** — access DSR returns subject's data with third-party PII
  redacted.
- **DSR5** — restriction DSR sets `processing_restricted=true`;
  downstream service calls respect the flag.
- **DSR6** — cancel endpoint rejects when not in `scheduled`.
- **DSR7** — cancel requires 2PA (two approvers in the cancel request
  body; single-approver rejected).
- **DSR8** — retry after failure is idempotent (already-deleted
  records skipped).
- **DSR9** — `completion_proof_hash` matches SHA-256 of canonical
  completion payload.
