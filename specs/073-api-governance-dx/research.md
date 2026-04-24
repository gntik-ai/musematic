# Phase 0 Research: API Governance and Developer Experience

**Feature**: 073-api-governance-dx
**Date**: 2026-04-23

## Scope

This feature extends the FastAPI app factory, installs two new middlewares
(rate-limit, API-versioning), ships one new Python module (debug logging),
adds one Alembic migration, and extends the existing `deploy.yml` CI
workflow with SDK generation + publication. Every decision below is
grounded in the current codebase as surveyed during Phase 0 discovery.

## Decisions

### D-001 — OpenAPI exposure path

**Decision**: Move FastAPI's OpenAPI doc from the default paths
(`/openapi.json`, `/docs`, `/redoc`) to `/api/openapi.json`, `/api/docs`,
`/api/redoc` by passing `openapi_url="/api/openapi.json"`,
`docs_url="/api/docs"`, `redoc_url="/api/redoc"` to the `FastAPI(...)`
constructor in `apps/control-plane/src/platform/main.py:712`
(`create_app`).

**Rationale**: The spec (FR-001, FR-002) explicitly requires the `/api/*`
namespace. The existing defaults are reachable but inconsistent with the
platform's `/api/v1/*` router prefix. Moving them is a one-line change;
the old paths can return 404 (no backwards-compatibility cost since no
external integrators depend on them yet).

**Alternatives considered**:
- Keep the defaults and proxy `/api/openapi.json` → `/openapi.json` at
  the ingress layer — rejected because it adds ingress config drift.
- Serve both old and new paths — rejected as unnecessary noise.

### D-002 — Admin endpoint segregation in OpenAPI

**Decision**: Tag admin endpoints under `/api/v1/admin/*` with the
`admin` OpenAPI tag (constitution rule 29). Ship **one** published
OpenAPI document; exclude the `admin` tag from SDK generation via the
tooling's tag-filter option (e.g. `openapi-python-client --include-tags`
inverted logic). v1 of this feature does NOT produce a second
admin-only document at a separate URL — that is a future iteration.

**Rationale**: A single document with a visible `admin` tag makes the
admin surface discoverable to humans while keeping SDK consumers clean.
A second OpenAPI URL would double the CI surface with no user-visible
benefit at v1.

**Alternatives considered**:
- Two OpenAPI documents, one at `/api/admin-openapi.json` — rejected
  for v1; reconsider when admin surface materially grows (UPD-036).
- Omit admin routes from the OpenAPI document entirely — rejected;
  violates constitution rule 36 ("every new FR with UX impact must be
  documented").

### D-003 — Rate-limit algorithm (multi-window Lua script)

**Decision**: Add a new Lua script
`apps/control-plane/src/platform/common/lua/rate_limit_multi_window.lua`
that atomically evaluates all three temporal buckets (minute / hour /
day) in a single Redis `EVALSHA` call and returns
`[allowed, remaining_min, remaining_hour, remaining_day, retry_after_ms]`.

**Rationale**: The existing `rate_limit_check.lua` (sliding-window, one
resource per call) would require three sequential Redis round-trips per
HTTP request — unacceptable on the hot path and prone to race conditions
when a principal saturates one bucket but not another. One atomic Lua
script is the idiomatic Redis-hosted-code answer and matches the pattern
already established for `budget_decrement.lua`.

**Alternatives considered**:
- Three sequential calls to existing script — rejected: triples
  latency, race-prone.
- Token bucket (client-computed) — rejected: harder to keep honest
  under concurrent requests from the same principal.
- Gap-based fixed-window — rejected: well-known thundering-herd problem
  at window boundaries.

### D-004 — Redis key naming

**Decision**: Extend the existing `ratelimit:{resource}:{key}` pattern
(`common/clients/redis.py:409`) with principal-scoped keys:

- `ratelimit:principal:{principal_type}:{principal_id}:{bucket}`
  where `bucket ∈ {min, hour, day}`.
- `ratelimit:anon:{source_ip}:{bucket}` for unauthenticated
  (anonymous-tier) requests.

TTLs align with the bucket: 60s, 3600s, 86400s respectively. Redis
cluster hashtags used only if Redis cluster is deployed (platform is
currently standalone; keep simple).

**Rationale**: Reuses the established `ratelimit:*` key prefix so it
sits inside the existing `rate_limit_check.lua` ownership model and
operators find keys where they expect. Separating `principal` vs `anon`
prefixes makes audit / eviction trivial.

### D-005 — Middleware installation order

**Decision**: In `create_app()`, add two middlewares. After this change
the registration order (bottom-to-top in source, which is reverse of
execution order) becomes:

```python
app.add_middleware(ApiVersioningMiddleware)   # outermost — sets response headers
app.add_middleware(RateLimitMiddleware)       # after auth; enforces before route
app.add_middleware(AuthMiddleware)            # existing
app.add_middleware(CorrelationMiddleware)     # existing — innermost
```

Execution order (incoming): Correlation → Auth → RateLimit →
ApiVersioning → route handler. Outgoing reverses. Rate-limit enforcement
runs immediately after auth so the principal is known but no expensive
handler code has run. API-versioning runs last so it can decorate
response headers regardless of whether the route fired or the
rate-limit middleware short-circuited with 429.

**Rationale**: Minimises wasted work per 429 response; preserves
constitutional correlation-context propagation at the outermost
boundary.

### D-006 — Anonymous-tier scope

**Decision**: The anonymous tier applies to requests whose path is in
`EXEMPT_PATHS` (per `auth_middleware.py:11-24`) AND to requests that
fail auth (i.e. no valid JWT / API key). The rate-limit key uses the
request's source IP (`X-Forwarded-For` first; peer address fallback)
rather than a synthetic principal ID. The default anonymous budget is
generous (e.g. 60 RPM, 1000 RPH, 10000 RPD) so public discovery
endpoints remain open.

**Rationale**: Health / OpenAPI / doc pages must remain reachable for
load balancers and integrator discovery. An anonymous tier avoids
unauthenticated requests bypassing rate limiting entirely.

### D-007 — Tier catalogue and default budgets

**Decision**: Seed four tiers via the Alembic migration:

| Tier | RPM | RPH | RPD |
|---|---|---|---|
| `anonymous` | 60 | 1,000 | 10,000 |
| `default` | 300 | 10,000 | 100,000 |
| `pro` | 1,000 | 50,000 | 500,000 |
| `enterprise` | 5,000 | 500,000 | 10,000,000 |

Administrators can change a principal's tier via an internal admin
endpoint (part of UPD-036's admin surface; this feature ships tier
assignment by seeder only). Tier rows are additive and editable, not
deletable.

**Rationale**: Four tiers match industry norms (Stripe, Twilio, Linear)
and align with the DDL's `subscription_tier VARCHAR(32)` field. Numbers
are informed guesses documented in Assumptions; easy to tune.

### D-008 — Debug-capture storage

**Decision**: Store captured debug records as Postgres rows
(`debug_logging_captures` table, new in migration 057). The table
holds: `session_id`, `captured_at`, `method`, `path`, redacted
`request_headers JSONB`, redacted `request_body TEXT` (capped at 8 KiB),
`response_status`, redacted `response_headers JSONB`, redacted
`response_body TEXT` (capped), `duration_ms`, `correlation_id`.

A daily APScheduler job purges captures whose parent session has
expired and whose `captured_at` is older than the platform's general
audit retention window.

**Rationale**: Keeps the feature self-contained — no new bounded
context or new data store. Postgres rows are cheap, queryable by
support engineers, and deletable under RTBF cascade (constitution
principle / rule 15). OpenSearch or ClickHouse would be overkill for
sessions bounded at ≤ 4 h each.

**Alternatives considered**:
- ClickHouse (extend `analytics`) — rejected: adds cross-BC DB coupling
  (principle IV), overkill for expected volume.
- Kafka-only ephemeral stream — rejected: requires a consumer to
  materialise captures; support engineers need SQL-queryable access.

### D-009 — PII redaction pattern set

**Decision**: Redaction runs **before** persistence, on headers and
body, matching a canonical set defined in
`common/debug_logging/redaction.py`:

- **Header allowlist**: only `user-agent`, `accept`, `content-type`,
  `content-length`, `x-correlation-id`, `x-goal-id`, `x-request-id`,
  `x-workspace-id` are captured verbatim. All other headers are
  replaced with `[REDACTED]`.
- **Body field denylist**: JSON keys matching any of `password`,
  `password_hash`, `token`, `access_token`, `refresh_token`, `secret`,
  `client_secret`, `api_key`, `mfa_secret`, `totp_secret`,
  `recovery_code`, `authorization`, `cookie`, `set-cookie`,
  `email`, `email_verified_token`, `session_id` have their values
  replaced with `[REDACTED:{type}]`.
- **Query string**: OAuth parameters (`code`, `state`, `access_token`,
  `id_token`) stripped from paths before capture.
- **Regex fallback**: patterns for JWT (`ey[A-Za-z0-9_-]+\.[...]`),
  Bearer tokens, API-key prefixes (`msk_`), and email-shaped strings
  run across the body text as a second pass.

The canonical set is the platform's floor; operators can extend via
configuration but not narrow (constitution rule — spec's FR-027 &
Assumption #7).

**Rationale**: Allowlist beats denylist for headers; denylist + regex
fallback for bodies. Mirrors the safety-sanitisation approach already
in `trust/` from feature 054.

### D-010 — SDK generator tool choice

**Decision**: Adopt the tools named in the user's input, which are the
current best-in-class OSS generators for each ecosystem:

| Language | Generator | Publish target |
|---|---|---|
| Python | `openapi-python-client` | PyPI |
| Go | `oapi-codegen` | GitHub release asset |
| TypeScript | `openapi-typescript` + `openapi-fetch` | npm |
| Rust | `openapi-generator` (OpenAPITools/openapi-generator-cli) | crates.io |

Each SDK is generated by a matrix job in a new `.github/workflows/
sdks.yml` triggered on `release: published` events. The job fetches
the latest release's `/api/openapi.json`, generates, and publishes.

**Rationale**: The four tools are battle-tested for each ecosystem;
they emit idiomatic code (dataclasses / structs / interfaces / Rust
structs + serde derives). Alternatives (Stoplight Studio,
swagger-codegen, Speakeasy) add cost or friction without clear benefit
at v1.

**Caveats**: Rust's `openapi-generator-cli` is Java-based; the CI job
pre-installs a JRE. TypeScript's `openapi-fetch` is a sibling runtime
the generated types pair with.

### D-011 — Release atomicity for SDK publication

**Decision**: Use a GitHub Actions "job-level success-or-nothing"
pattern: a single `sdks` workflow with four matrix jobs (one per
language) generates to a staging artefact bucket. A final `publish`
job with `needs: [generate]` runs only if all four generations
succeeded, and it performs all four publishes in parallel. If any
publish fails, the workflow fails loudly; the operator is expected to
re-run (generators are deterministic for a given OpenAPI SHA).

**Rationale**: Meets FR-009's atomicity (no partial publication). Pure
transactional publish across four public registries is impossible, but
"all published or none published in this run" is achievable and
auditable.

**Alternatives considered**:
- Sequential publish with rollback on failure — rejected: registries
  don't support yank-on-error uniformly (crates.io yank is soft).
- Use a single "umbrella" release artefact — rejected: defeats the
  per-language installability goal.

### D-012 — API-versioning middleware responsibilities

**Decision**: `ApiVersioningMiddleware` reads a per-route deprecation
marker (stored on the route definition via a decorator
`@deprecated_route(sunset="2026-10-01", successor="/api/v2/...")` that
sets a marker on the endpoint). On response egress the middleware:

1. Emits `Deprecation: true` when the route is marked.
2. Emits `Sunset: <RFC-9110 HTTP-date>` from the marker.
3. Emits `Link: <successor>; rel="successor-version"` if a successor
   URL is set.
4. If the sunset date has passed (as of request time), short-circuits
   the route and returns HTTP 410 Gone with a body identifying the
   successor.

Route markers are read from a small in-process registry populated at
import time (no DB round-trip per request).

**Rationale**: Decorator-based per-route marking keeps deprecation
metadata next to the route it concerns (discoverability), avoids a DB
table for a rarely-changing configuration, and surfaces the
`deprecated: true` flag to FastAPI's OpenAPI generator automatically.

### D-013 — Alembic migration numbering

**Decision**: Use migration **057** (next sequential; current head is
`056_proximity_graph_workspace.py`).

### D-014 — Event emission for debug sessions

**Decision**: Publish to a new Kafka topic `debug_logging.events` with
three event types:

- `debug_logging.session.created`
- `debug_logging.session.expired`
- `debug_logging.capture.written`

Use the existing `publish_*_event` pattern from `auth/events.py`. The
events carry `session_id`, `requester_id`, `target_type`, `target_id`,
`justification` (for created), `duration_ms` (for expired),
`capture_id` (for capture.written). No PII bodies in event payloads.

**Rationale**: Constitution rule 21 requires correlation-ID-propagated
events; using the canonical `EventProducer` inherits this. Matches
FR-028's audit-trail requirement.

### D-015 — Exempt-path list update

**Decision**: Extend `EXEMPT_PATHS` in
`common/auth_middleware.py` (current file has the list at lines 11–24)
with `/api/openapi.json`, `/api/docs`, `/api/redoc` and keep the
legacy `/openapi.json`, `/redoc` entries through one release cycle
before removing them.

**Rationale**: Doc endpoints must be anonymously reachable; the
rate-limit middleware applies the anonymous tier (D-006).

## Deferred / future

- Adding a **5th SDK language** (Java or Ruby) — out of scope; spec
  assumes future iteration.
- Publishing the **admin-only OpenAPI document** separately — deferred
  until UPD-036 ships the full admin surface.
- Introducing actual **`/api/v2/*` endpoints** — namespace reserved
  only; v2 is future work.
- Moving rate-limit storage to **Redis Cluster** with hashtags —
  deferred; platform currently standalone Redis.
