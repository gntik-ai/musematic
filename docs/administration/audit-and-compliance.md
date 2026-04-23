# Audit & Compliance

The `audit` bounded context captures privileged operations and writes
them to an append-only record for later review. This page documents
what is captured, where it lands, and what compliance surfaces exist
today.

## What's captured today

The main branch ships audit events for:

- **Account lifecycle** — approvals, rejections, suspensions, blocks,
  MFA resets ([spec 016][s016]).
- **Registry lifecycle** — status transitions (`draft`, `validated`,
  `published`, `disabled`, `deprecated`, `archived`) with a per-event
  actor + timestamp ([spec 021][s021]).
- **Trust & certification** — verdicts issued, enforcement actions,
  certification approvals ([spec 032][s032], [spec 061][s061]).
- **Auth events** — login success/failure, MFA failures, lockouts
  ([spec 014][s014]).

Each is emitted as a Kafka event on the appropriate topic
(`auth.events`, `accounts.events`, `registry.events`, `trust.events`)
and projected into Postgres audit tables by the
`projection-indexer` runtime profile.

## Reading the audit trail

Read APIs exist per bounded context:

- `GET /api/v1/accounts/{user_id}/audit` — account lifecycle events.
- `GET /api/v1/registry/agents/{agent_id}/audit` — agent lifecycle.
- `GET /api/v1/trust/certifications/{cert_id}/events` — certification
  events.

Requires `auditor` role (or above). The `auditor` role is scoped to
`resource_type: [audit, analytics, trust, execution]` with `read`
actions only — it is read-only by design.

## What's NOT present yet

TODO(andrea): the constitution's audit-pass (v1.2.0) introduces a
**hash-chain audit integrity** decision (AD-18) and a
**security_compliance** bounded context providing a
`/api/v1/security/audit-chain/*` API for verification and export. As
of the main branch, these are planned (UPD-024) but not implemented.

Specifically missing:

- Tamper-evident hash chaining across audit entries.
- Signed exports of the audit trail for regulatory submission.
- A consolidated `/api/v1/audit/*` API (today each BC has its own).
- Automated retention policies for audit events.

## Retention

Audit records are persisted in Postgres indefinitely. No automatic
retention or purge job runs in the current codebase. Operators who
need bounded retention should schedule an external job that deletes
records older than the required window from:

- `accounts.lifecycle_audit`
- `registry_lifecycle_audit`
- `auth_audit_events`
- `trust_certification_events`

TODO(andrea): confirm exact table names from migration files; the
names above are the current conventions.

## GDPR / compliance

No GDPR-specific flows (data-subject requests, right-to-be-forgotten
cascade deletion, tombstone records) exist in the main branch. The
audit-pass adds these via the `privacy_compliance` bounded context
(UPD-023) — see [Roadmap](../roadmap.md).

Until then, compliance operators must:

- Handle data-subject access requests by querying the relevant BC APIs
  directly and assembling the export manually.
- Delete PII by issuing `DELETE` on each affected resource in each data
  store (Postgres, Qdrant, Neo4j, ClickHouse, OpenSearch, S3).

## SOC 2 / ISO 27001

No packaged evidence generation exists today. Typical controls
(MFA enforcement, session timeout, role-based access, audit logging of
privileged actions) are all present as platform features — admins
assemble evidence by querying the existing APIs.

[s014]: https://github.com/gntik-ai/musematic/tree/main/specs/014-auth-bounded-context
[s016]: https://github.com/gntik-ai/musematic/tree/main/specs/016-accounts-bounded-context
[s021]: https://github.com/gntik-ai/musematic/tree/main/specs/021-agent-registry-ingest
[s032]: https://github.com/gntik-ai/musematic/tree/main/specs/032-trust-certification-guardrails
[s061]: https://github.com/gntik-ai/musematic/tree/main/specs/061-judge-enforcer-governance
