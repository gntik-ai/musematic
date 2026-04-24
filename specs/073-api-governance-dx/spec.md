# Feature Specification: API Governance and Developer Experience

**Feature Branch**: `073-api-governance-dx`
**Created**: 2026-04-23
**Status**: Draft
**Input**: User description: "Publish OpenAPI 3.1 specification, generate SDKs for Python/Go/TypeScript/Rust, enforce URL-based API versioning policy, per-consumer rate limiting, time-bounded debug logging. Feature UPD-029 in the audit-pass constitution; implements FR-497 through FR-500."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — External developer discovers and navigates the API (Priority: P1) 🎯 MVP

A developer integrating a third-party system with the platform needs to understand what API surface exists, what each endpoint expects and returns, and which fields are optional vs required. Today they must read source code or ping engineering via Slack. After this feature they fetch a published machine-readable OpenAPI 3.1 specification and browse it in an interactive Swagger UI or Redoc renderer hosted by the platform. Every endpoint is tagged by bounded context, shows request/response schemas with examples, and documents authentication requirements.

**Why this priority**: Without machine-readable discovery, every downstream capability (SDKs, rate limiting, deprecation signalling) has no canonical source of truth. Discovery is the foundation the rest of the feature rests on, and the minimum delivery that still adds standalone value to external integrators.

**Independent Test**: With the platform running, fetch `/api/openapi.json` and verify it is a valid OpenAPI 3.1 document that lints clean with the `redocly` or `spectral` CLI; open `/api/docs` and `/api/redoc` in a browser and confirm every bounded-context router appears with schema-accurate request/response pairs. No other user story needs to be implemented for this to deliver value.

**Acceptance Scenarios**:

1. **Given** the platform is running, **When** a developer fetches `/api/openapi.json`, **Then** the response is a syntactically valid OpenAPI 3.1 document whose top-level `info` block identifies the platform, current version, and contact details.
2. **Given** the OpenAPI document is published, **When** a developer opens `/api/docs` in a browser, **Then** an interactive Swagger UI loads showing every public endpoint grouped by bounded-context tag with request and response schemas.
3. **Given** the OpenAPI document is published, **When** a developer opens `/api/redoc`, **Then** a Redoc-style three-panel reference loads with the same endpoint coverage.
4. **Given** a developer runs `spectral lint` or `redocly lint` against the published document, **Then** the lint passes with zero errors and no severity-high warnings.
5. **Given** a developer queries a specific endpoint's operation object in the OpenAPI document, **Then** the operation declares its authentication requirement (none / session / OAuth2 / service-account key) and any required permissions.

---

### User Story 2 — External developer integrates using a generated SDK (Priority: P1)

A developer building an integration wants to call the platform without hand-rolling HTTP clients, request/response models, or error types. After this feature lands, an official SDK is published for Python, Go, TypeScript, and Rust on each release; the developer adds the SDK package to their project, authenticates with a platform-issued token, and invokes endpoints as typed method calls. Each SDK release is version-locked to a specific platform release and pulls its shape from the canonical OpenAPI document.

**Why this priority**: SDKs are the tangible integrator experience; they turn the platform from "yet another REST API" into a first-class library in four ecosystems. P1 alongside US1 because the CI pipeline producing SDKs also validates that the OpenAPI document is stable and well-shaped; breaking either one breaks integration.

**Independent Test**: With a tagged platform release, run the SDK-generation pipeline; confirm four language-specific artefacts are produced and published to their respective package registries (PyPI, GitHub releases, npm, crates.io); install each SDK in a scratch project, make a round-trip authenticated call against a live platform instance, and confirm the response deserialises into the SDK's typed model.

**Acceptance Scenarios**:

1. **Given** a tagged platform release, **When** the SDK-generation pipeline runs, **Then** four SDK artefacts (Python, Go, TypeScript, Rust) are produced and each is version-tagged to match the platform release.
2. **Given** an SDK artefact is produced, **When** the pipeline publishes it, **Then** the artefact lands on its target registry (PyPI for Python, GitHub releases for Go, npm for TypeScript, crates.io for Rust) and is immediately installable by a public client.
3. **Given** a developer installs the Python SDK in a new project and authenticates with a valid API key, **When** they invoke a read endpoint (e.g. list workspaces), **Then** the SDK returns a typed model and the HTTP call fingerprint in server logs is identical to a hand-crafted curl.
4. **Given** a developer installs the TypeScript SDK and invokes a write endpoint, **When** the platform returns a standard validation error, **Then** the SDK surfaces the error as a structured typed exception or result, not as a raw string.
5. **Given** the OpenAPI document changes incompatibly between releases, **When** the SDK pipeline runs, **Then** the pipeline fails loudly rather than silently publishing an incompatible SDK.

---

### User Story 3 — Platform operator protects capacity with per-principal rate limits (Priority: P2)

A platform operator configures per-principal rate limits so that a single misbehaving user, service account, or external A2A peer cannot exhaust API capacity for everyone else. Each principal carries a subscription tier that maps to a per-minute, per-hour, and per-day request budget. When a principal exceeds their budget, the platform returns HTTP 429 with a `Retry-After` header; every response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` so well-behaved clients can back off before hitting the limit.

**Why this priority**: Rate limiting protects the platform as the API opens up. P2 because it only becomes critical once US1+US2 have surfaced the API to external integrators; before that, internal clients are the only consumers and they are already bounded by deployment topology.

**Independent Test**: Provision a user at the default subscription tier. Drive concurrent requests from that user until the per-minute budget is exhausted; verify the next request returns HTTP 429 with a `Retry-After` header and that every response carries `X-RateLimit-*` headers with accurate values. Wait the stated retry interval and confirm the user recovers automatically without operator intervention.

**Acceptance Scenarios**:

1. **Given** a principal at a configured subscription tier, **When** they make any API call, **Then** the response includes `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` reflecting that principal's current budget state.
2. **Given** a principal whose per-minute budget has been exhausted, **When** they make another request, **Then** the platform returns HTTP 429 with a `Retry-After` header indicating the wait time before the next retry is permitted.
3. **Given** a 429 has been returned, **When** the indicated `Retry-After` window elapses, **Then** the principal's next request succeeds without operator intervention.
4. **Given** two principals on the same subscription tier, **When** one exhausts their budget, **Then** the other principal's budget is unaffected (per-principal, not global, enforcement).
5. **Given** a platform administrator changes a principal's subscription tier, **When** the change is committed, **Then** the new tier's budget applies to that principal's next request without a service restart.

---

### User Story 4 — API lifecycle manager deprecates old endpoints gracefully (Priority: P2)

When the platform evolves an endpoint incompatibly, an API lifecycle manager marks the old version as deprecated and announces a sunset date. Responses from the deprecated endpoint automatically carry `Deprecation` and `Sunset` HTTP headers so any client (browser, SDK, raw HTTP) can learn of the upcoming removal without out-of-band notification. The platform supports this across a `/api/v1/` → `/api/v2/` namespace transition: v1 routes keep working during the deprecation window and only start returning 410 Gone after the sunset date. This closes the gap between "we told people to migrate" and "clients actually know they need to migrate".

**Why this priority**: Deprecation hygiene is important but only matters once the API has external consumers and moves past its first major version. P2 alongside rate limiting because both are API-lifecycle concerns that matter once integrators are on the platform.

**Independent Test**: Register a stub endpoint under `/api/v1/`, flag it as deprecated with a sunset date. Issue a request; confirm the response includes `Deprecation: true` and `Sunset: <RFC-9110 HTTP-date>`. Issue a second request after artificially advancing the sunset date; confirm the response is HTTP 410 Gone with a body pointing to the successor.

**Acceptance Scenarios**:

1. **Given** an endpoint has been flagged as deprecated, **When** a client makes a successful request to it, **Then** the response includes `Deprecation: true` and a `Sunset: <HTTP-date>` header per RFC 8594.
2. **Given** a deprecated endpoint has a documented successor, **When** a client makes a request before the sunset date, **Then** the response additionally includes a `Link: <successor>; rel="successor-version"` header.
3. **Given** a deprecated endpoint's sunset date has passed, **When** a client makes a request to it, **Then** the platform returns HTTP 410 Gone with a descriptive body pointing at the successor endpoint.
4. **Given** the platform exposes both `/api/v1/` and `/api/v2/`, **When** a client calls a v1 endpoint with no deprecation, **Then** no deprecation headers are emitted and the request succeeds normally.
5. **Given** the OpenAPI document is fetched, **When** an endpoint is deprecated, **Then** the operation's `deprecated: true` flag is present in the OpenAPI document and the sunset date is surfaced in the operation description.

---

### User Story 5 — Support engineer debugs a user's issue with time-bounded audited logging (Priority: P3)

A support engineer investigating a user-reported issue needs to see the exact sequence of API requests and responses that user (or workspace) is producing — without enabling verbose logging for the entire platform or extracting PII from general access logs. After this feature, the engineer requests a debug logging session scoped to a specific user or workspace, provides a written justification, and the platform captures that scope's request/response pairs (with PII redaction) for a strictly time-bounded window, then stops automatically. Every session is audit-logged for compliance and review.

**Why this priority**: Debug logging is a support-team lifeline but used infrequently. P3 because the platform operates fine without it; its value is only realised during active incident investigation. Required because today's alternatives (enabling full-trace logging globally, engineer queries on raw stores) are too blunt and compromise privacy.

**Independent Test**: A support engineer with the required permission opens a debug session for one specific user, provides a justification, and confirms the session expires automatically after the configured maximum window; during the window, an API call by that user produces a captured, PII-redacted request/response record retrievable by the support engineer; after expiry, no further capture occurs for that user even though a session re-request is required.

**Acceptance Scenarios**:

1. **Given** a support engineer has the `debug_logging_session:create` permission, **When** they open a session against a specific user with a justification, **Then** the session is recorded in an audit table with the engineer's identity, the scope, the justification, the start time, and an expiry time no more than the configured maximum.
2. **Given** a session is active, **When** the scoped user makes an API call, **Then** a request/response record is captured with PII fields redacted (email, token values, password hashes, MFA secrets) and associated with the session ID.
3. **Given** a session has passed its expiry time, **When** the scoped user makes another API call, **Then** no debug capture occurs; further capture requires a new session with a fresh justification.
4. **Given** a support engineer attempts to extend a session past the configured maximum window, **When** they submit the extension, **Then** the platform rejects it with an explanatory error; the engineer must open a new session.
5. **Given** any debug session has existed, **When** a compliance officer queries the audit trail, **Then** they can list every session that has ever existed with its requester, scope, justification, start, expiry, and count of captured records.

---

### Edge Cases

- **Rate limiting in a single-principal misconfiguration**: If a principal has no rate-limit row yet (e.g. a newly provisioned user before the background worker has populated their tier), the platform applies the "default" tier's limits rather than letting the request through unrestricted or failing outright.
- **SDK publishing from a failed release**: If the SDK-generation pipeline partially succeeds (e.g. Python publishes but Rust fails because crates.io is unreachable), the pipeline is atomic — either all four SDKs publish or none do, to avoid version-skew between language ecosystems.
- **OpenAPI document size**: The document is expected to exceed 1 MB. The platform serves it with `Content-Encoding: gzip` when the client accepts it.
- **Rate-limit header accuracy under load**: Under concurrent requests from the same principal, the `X-RateLimit-Remaining` value is a best-effort near-real-time snapshot, not a strict guarantee; the canonical enforcement still runs server-side on the very next call.
- **Deprecated v1 endpoint coexistence with non-deprecated v2**: A client may use both simultaneously during a migration; rate limits count against the same principal budget regardless of which version is called.
- **Debug-session target user deletion mid-session**: If the scoped user is deleted (GDPR RTBF) while a debug session is active, the session is terminated immediately and any captured records are purged as part of the deletion cascade.
- **Rate-limit configuration change during a burst**: A tier change applies on the next request; in-flight requests complete under the old tier. The platform does not retroactively reject already-accepted requests.
- **Rate limit for un-authenticated public endpoints** (health checks, OpenAPI): A separate "anonymous" tier with generous but bounded limits applies; anonymous callers from the same source IP share a bucket.
- **Clock skew between client and server on `Retry-After`**: The platform emits `Retry-After` as a `delta-seconds` value (not an HTTP-date) to avoid client-side time-zone confusion.
- **Debug capture collides with a sensitive route** (e.g. OAuth callback with secret in query): The PII redactor treats OAuth query parameters, Authorization headers, cookies, and common secret field names as always-redacted regardless of debug-session opt-in.
- **SDK consumer pinning to a specific platform release**: Each SDK's version string encodes the platform release it was generated against so consumers can pin compatibly.

## Requirements *(mandatory)*

### Functional Requirements

**OpenAPI publication and developer discovery**

- **FR-001**: The platform MUST publish an OpenAPI 3.1 specification at `/api/openapi.json` (JSON) covering every non-internal HTTP endpoint, including its path, method, authentication requirement, request schema, response schema, and standard error responses.
- **FR-002**: The platform MUST mount Swagger UI at `/api/docs` and Redoc at `/api/redoc`, both sourcing their content from the same OpenAPI document served at FR-001.
- **FR-003**: Each endpoint operation in the OpenAPI document MUST be tagged with the bounded-context name that owns it (e.g. `auth`, `registry`, `workflows`).
- **FR-004**: Admin-only endpoints MUST be tagged separately from user-facing endpoints in the OpenAPI document, either via distinct tags (e.g. `admin`) or via a separately-served OpenAPI document so that consumer SDKs can be generated without the admin surface.
- **FR-005**: The OpenAPI document MUST pass `spectral lint` or `redocly lint` with zero errors and no high-severity warnings, enforced as a CI gate.

**SDK generation and publication**

- **FR-006**: The platform's release pipeline MUST generate SDKs for Python, Go, TypeScript, and Rust from the published OpenAPI document.
- **FR-007**: Each generated SDK MUST be version-tagged to match the platform release that produced it.
- **FR-008**: The release pipeline MUST publish the Python SDK to PyPI, the Go SDK via GitHub releases, the TypeScript SDK to npm, and the Rust SDK to crates.io on every tagged release.
- **FR-009**: If any SDK fails to publish, the release pipeline MUST not publish any of the SDKs from that release (all-or-nothing), to prevent cross-ecosystem version skew.
- **FR-010**: Each SDK MUST surface platform errors as typed exceptions or result types rather than as raw strings, and MUST include convenience support for authenticating with a platform-issued API key or OAuth2 token.

**API versioning and deprecation**

- **FR-011**: The platform MUST prefix every public REST endpoint with a version segment (`/api/v1/…`) and MUST reserve `/api/v2/` as the namespace for the next major version.
- **FR-012**: When an endpoint is flagged as deprecated, every response from it MUST include a `Deprecation: true` header and a `Sunset` header carrying the sunset date per RFC 8594.
- **FR-013**: When a deprecated endpoint has a documented successor, responses MUST additionally include a `Link: <successor>; rel="successor-version"` header.
- **FR-014**: The deprecation state of an endpoint MUST be reflected in the OpenAPI document via the operation's `deprecated: true` flag and a human-readable sunset date in the operation description.
- **FR-015**: After the sunset date passes, requests to the deprecated endpoint MUST return HTTP 410 Gone with a body identifying the successor, rather than continuing to function or returning 404.

**Per-principal rate limiting**

- **FR-016**: The platform MUST enforce per-principal rate limits covering three temporal buckets per principal: requests-per-minute, requests-per-hour, and requests-per-day.
- **FR-017**: The platform MUST recognise three principal types for rate-limit purposes: authenticated users, service accounts, and external A2A peers; each principal has exactly one active rate-limit configuration.
- **FR-018**: Each principal's rate-limit configuration MUST be associated with a subscription tier; the tier determines the default per-minute, per-hour, and per-day budgets.
- **FR-019**: Every successful or rate-limited response MUST include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers reflecting the principal's current budget state for the most constrained bucket.
- **FR-020**: When a principal's budget is exhausted in any of the three temporal buckets, the platform MUST return HTTP 429 with a `Retry-After` header expressed as a delta in seconds.
- **FR-021**: A principal with no explicit rate-limit configuration MUST be assigned the `default` subscription tier automatically at request time; the platform MUST NOT accept requests from an unidentifiable principal unthrottled.
- **FR-022**: A subscription-tier change for a principal MUST take effect no later than the next API request from that principal, without requiring a platform restart.
- **FR-023**: Rate limits for anonymous public endpoints (health, OpenAPI document fetch) MUST apply to the source IP under a dedicated "anonymous" tier, separate from authenticated principal budgets.

**Time-bounded debug logging**

- **FR-024**: A support engineer with the `debug_logging_session:create` permission MUST be able to open a debug session scoped to a single target (user or workspace) with a written justification.
- **FR-025**: Each debug session MUST have a fixed expiry no longer than 4 hours from start; attempts to extend past this maximum MUST be rejected — a new session with a fresh justification is required.
- **FR-026**: While a debug session is active, the platform MUST capture request/response pairs whose scope matches the session (e.g. requests from the session's target user) into a dedicated debug-capture record, with PII fields redacted.
- **FR-027**: PII redaction in captured records MUST at minimum strip authorization headers, cookies, password hashes, MFA secrets, email addresses, and OAuth query parameters.
- **FR-028**: Every debug session MUST produce an audit-trail record at open time, at expiry, and on any capture activity, with the requester identity, scope, justification, timestamps, and count of captured records.
- **FR-029**: A debug session MUST automatically terminate when its target is deleted (e.g. via RTBF cascade), and any captured records MUST be purged as part of the same deletion.
- **FR-030**: After a session's expiry, the platform MUST NOT capture any further request/response pairs for that session's scope unless a new session is opened.

### Key Entities *(include if feature involves data)*

- **Rate Limit Configuration** — a per-principal record associating a principal (user, service account, external A2A peer) with a subscription tier and three numeric budgets (per-minute, per-hour, per-day). Each principal has at most one active configuration.
- **Subscription Tier** — a named bundle of rate-limit budgets plus any other tier-scoped platform policies (e.g. default tier, pro tier, enterprise tier, anonymous tier). Tiers are managed by platform administrators.
- **Debug Logging Session** — a time-bounded, audit-logged record scoping which target (user or workspace) the platform should capture request/response pairs for, why, and for how long. Each session has a creator, a justification, a strict expiry ≤ 4 hours, and produces zero or more captured debug records until expiry.
- **Debug Capture Record** — a PII-redacted snapshot of a single request/response exchange made during an active debug session, associated with its session.
- **Deprecation Marker** — a per-endpoint flag carrying at minimum a sunset date and optionally a successor URL; drives the emission of `Deprecation`, `Sunset`, and `Link` response headers and the `deprecated: true` flag in the OpenAPI document.
- **API Version Namespace** — a top-level path prefix (`/api/v1/`, `/api/v2/`) that scopes a group of endpoints as a release-coherent surface. The platform exposes exactly one "current" version at any time and zero or more deprecated-but-supported prior versions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The OpenAPI document published at `/api/openapi.json` passes `spectral lint` / `redocly lint` with zero errors on 100% of CI runs from the first release onward.
- **SC-002**: On a tagged platform release, all four SDKs (Python, Go, TypeScript, Rust) publish successfully to their respective registries on ≥ 99% of release-pipeline invocations; partial publication never occurs (FR-009).
- **SC-003**: An external developer unfamiliar with the platform can fetch the OpenAPI document, open Swagger UI, and make their first successful authenticated API call in under 15 minutes (measured by onboarding task timing in feature review).
- **SC-004**: 100% of responses from authenticated endpoints include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers; verified by a CI smoke test that walks the OpenAPI document and samples each route.
- **SC-005**: When a principal exhausts their per-minute budget, the platform returns HTTP 429 with a `Retry-After` value within 100 ms of the exhausting request; after the `Retry-After` delay elapses, the next request succeeds on ≥ 99% of attempts.
- **SC-006**: 100% of responses from endpoints marked `deprecated` include `Deprecation: true` and a `Sunset` header; 100% of requests to deprecated endpoints after the sunset date return HTTP 410 (not 404 or 200).
- **SC-007**: Every debug logging session terminates automatically within its configured expiry (≤ 4 hours); zero debug sessions run longer in any rolling 30-day window, verified by a periodic audit-trail sweep.
- **SC-008**: Every captured debug record contains zero matches for the redaction-pattern set (authorization headers, cookies, password hashes, MFA secrets, emails, OAuth query parameters), verified by a periodic audit-trail sampling job.
- **SC-009**: 100% of debug logging session creations, expirations, and captures produce a corresponding audit-trail record accessible by a user with `auditor` role.
- **SC-010**: The per-principal rate-limit enforcement at the default tier sustains ≥ 1,000 requests/second of enforcement decisions per platform instance under peak load without introducing more than 5 ms of median latency overhead, verified by a load-test smoke run.

## Assumptions

- The platform ships one OpenAPI document covering the user-facing `/api/v1/*` surface; admin-only endpoints under `/api/v1/admin/*` may be published in a separate OpenAPI document per constitution rule 29 (admin endpoint segregation). This spec describes the user-facing document; a second document for admin endpoints is an extension not in scope for v1 of this feature.
- The platform already authenticates every request before rate limiting runs, so principal identity is resolved by the existing auth middleware and this feature consumes that result rather than re-authenticating.
- Subscription tiers ship with a reasonable default set (e.g. `default`, `pro`, `enterprise`, `anonymous`); an administrator may reconfigure their budgets, but the named set itself is platform-managed and not dynamically extensible in v1.
- The Redis instance that backs hot state is available to the rate limiter; if Redis is unavailable, the rate limiter fails closed (rejects requests) rather than open (allowing unthrottled traffic), consistent with constitution principle that platform state defaults to safe-deny.
- SDK publishing credentials (PyPI token, GitHub release token, npm token, crates.io token) are provisioned in the CI environment by an operator as a one-time setup prior to the first release; this spec assumes that provisioning has happened.
- The `Retry-After` header is emitted as a delta-seconds value only (not an HTTP-date) to avoid client-side time-zone confusion. This matches RFC 7231 §7.1.3.
- Debug-session records share the platform's general audit-trail retention policy; this feature does not introduce a separate retention schedule.
- The platform ships a reasonable default PII-redaction pattern set; operators can extend it through configuration but cannot narrow it below the default floor described in FR-027 without a constitutional amendment.
- `/api/v2/` is reserved as a path namespace in this feature; no actual v2 endpoints are introduced. Their introduction is future work.
- SDK ecosystem choice (Python / Go / TypeScript / Rust) matches the platform's own language stack plus the two most-requested integration languages. Adding a fifth SDK (e.g. Java, Ruby) is future work.
