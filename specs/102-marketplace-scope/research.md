# Research — UPD-049 Refresh Pass on 099 Baseline

**Phase 0 output.** Resolves the open questions specific to the refresh-pass deltas. The original eight research items (R1–R8) are documented in `specs/099-marketplace-scope/research.md` and are not re-litigated here. The refresh adds four new items (R9–R12) corresponding to the new behavioural requirements (FR-741.9 self-review prevention, FR-741.10 / SC-004 non-leakage parity, FR-738 / SC-007 assignment-distinct-from-claim, FR-741.7 fork-update notification path) and one operational item (R13 live-DB integration fixture).

---

## R9 — Self-review prevention enforcement layer

**Decision**: enforce self-review prevention at TWO layers — service layer (`MarketplaceReviewService.approve` / `.reject`) and API layer (FastAPI dependency on the assign/approve/reject routes). UI hides self-review actions but is not authoritative.

**Why two layers (not one):**
- Service-layer guard catches every code path that calls `approve`/`reject`, including future internal automation. A pure API guard would miss programmatic callers.
- API-layer guard returns a stable error code (`self_review_not_allowed`) that the UI can surface as a toast without round-tripping through the service-layer exception. This matters for sub-100 ms latency on the queue page.

**Rationale:**
- 099's `MarketplaceReviewService.approve` (`apps/control-plane/src/platform/marketplace/review_service.py:190`) accepts `reviewer_id` and trusts the caller. The same module reads `created_by` (the submitter) into the queue projection at line 96 but does not compare it against `reviewer_id` on action.
- The new `SelfReviewNotAllowedError(PlatformError)` maps to HTTP 403 with code `self_review_not_allowed` and details `{ "submitter_user_id": ..., "reviewer_user_id": ... }` (the audit chain captures both IDs already; surfacing them in the error body lets the UI render an unambiguous toast).
- Assignment is also in scope: a platform-staff lead MUST NOT assign a submission to its creator. The same guard applies to `MarketplaceReviewService.assign`.

**Audit:**
- Refused approve/reject/assign attempts emit a `marketplace.review.self_review_attempted` audit-chain entry (NOT a Kafka event — refusals are diagnostics, not state changes). The audit entry includes both user IDs and the action attempted.

**Alternatives considered:**
- DB CHECK constraint (`reviewed_by_user_id <> created_by`) — rejected. The constraint would need to fire on the UPDATE that records the reviewer, but the column is also used as the **claim marker** (set on claim before any approve/reject decision). A CHECK that refuses self-claim would prevent the submitter from claiming their own draft for re-review, which is a legitimate workflow when a submitter claims back to release. Better solved at service layer where the action verb is known.
- Single layer (API only) — rejected as documented above.

---

## R10 — Information non-leakage parity (SC-004)

**Decision**: parity is enforced via a **single visibility-filter pre-query layer** that applies to both PostgreSQL (RLS), OpenSearch (in-document filter), and ClickHouse (WHERE clause) reads. The same `MarketplaceVisibilityFilter` Pydantic model is constructed once per request from the user's tenant context and passed into all three query paths. Result counts, suggestion arrays, and analytics events are emitted **after** the filter is applied — never before.

**Why this approach (not RLS-only):**
- 099's RLS-only model relies on the `agents_visibility` PostgreSQL policy. RLS does not extend to OpenSearch or ClickHouse — those stores get raw queries from the application. If a Globex (no-consume-flag) tenant runs a search against OpenSearch and the application emits a result count BEFORE filtering, the count itself reveals public-hub population.
- The visibility-filter layer is a **single source of truth** for "what scopes is this user allowed to see right now." Each store's reader translates the filter into its native query language (RLS GUCs for PG, `term`/`terms` filters for OpenSearch, `WHERE` clauses for ClickHouse). The application code never emits a count or a suggestion before the filter has been applied.

**SC-004 verification harness — parity probe:**
- A new dev-only endpoint `GET /api/v1/admin/marketplace-review/parity-probe?query={q}` is added under the existing `FEATURE_E2E_MODE` gate (active in the kind cluster, returns 404 in production). It runs the search query as a fresh-Enterprise-tenant user (no consume flag, no public agents to find) and as the same tenant after a public agent matching `q` has been published. It returns both response payloads (counts, suggestions, analytics events) and a `parity_violation` boolean. The CI parity test fails the build if `parity_violation=true`.
- The probe deliberately does NOT bypass any layer — it is a black-box equality check across two real request flows, not an introspection tool.

**Rationale:**
- Putting parity at one layer (the visibility filter) means correctness is locally verifiable and one well-tested module covers all three data stores. The alternative — replicating the visibility logic in each store's reader — multiplies the surface area and the bug count.
- The probe being dev-only is mandatory: surfacing a "is this public agent in the public hub?" oracle in production would itself be a leakage channel.

**Alternatives considered:**
- Dual-write the public-published agent into a per-tenant projection — rejected. Storage cost scales O(public-agents × consuming-tenants); also defeats the point of a single visibility-filter abstraction.
- Apply the filter at OpenSearch only — rejected. ClickHouse-driven analytics views (e.g., trending-agent panels in the marketplace UI) need the same filter; otherwise trending data leaks public-hub population to non-consuming tenants.

---

## R11 — Queue assignment distinct from claim

**Decision**: introduce a new column `assigned_reviewer_user_id UUID NULL` on `registry_agent_profiles` (Alembic migration 109). The existing `reviewed_by_user_id` column is preserved with its current semantics (claim marker → final reviewer). Assignment and claim are now independent dimensions:

| State | `assigned_reviewer_user_id` | `reviewed_by_user_id` |
|---|---|---|
| Unassigned, unclaimed | NULL | NULL |
| Assigned (queue lead picked an owner) | UUID(reviewer) | NULL |
| Assigned + claimed | UUID(reviewer) | UUID(reviewer) — usually same |
| Approved/Rejected | UUID(reviewer) (preserved) | UUID(reviewer) — final |

**Why a separate column:**
- 099 conflates claim and final-review in one column. That makes "assigned but not yet acted" indistinguishable from "in-progress claim." The queue-load workflow needs to distinguish them so a lead can re-assign idle items.
- The new column is independently nullable so today's "no assignment, anyone can claim" workflow still works for tenants with one reviewer.
- A single partial index `WHERE review_status = 'pending_review'` over the new column keeps "submissions assigned to me" queries cheap.

**Assignment semantics:**
- `assign(agent_id, reviewer_user_id, assigner_user_id)` — only platform-staff with `assign_marketplace_review` permission can call. Sets `assigned_reviewer_user_id`. Idempotent if same reviewer; rejects with 409 if different reviewer already assigned (lead must explicitly `unassign` first).
- `unassign(agent_id, assigner_user_id)` — clears `assigned_reviewer_user_id`. Idempotent.
- `claim` — unchanged from 099 except: if `assigned_reviewer_user_id` is set and is NOT the claimant, raises `ReviewerAssignmentConflictError` (HTTP 409). This prevents claim-jumping.

**Audit:**
- `marketplace.review.assigned` and `marketplace.review.unassigned` Kafka events on `marketplace.events`, additive to the 099 set. Audit-chain entries include both assigner and assignee user IDs.

**Self-review forbidden on assignment:**
- A lead MUST NOT assign a submission to its creator. Same `SelfReviewNotAllowedError` (R9) applies.

**Alternatives considered:**
- Reuse `reviewed_by_user_id` for both — rejected per the 099 conflation problem above.
- Many-to-many `agent_review_assignments` table — rejected. Each submission has at most one assigned reviewer at a time; many-to-many is a future feature (panel-of-reviewers) not in scope here.

---

## R12 — Fork-update notification path (FR-741.7)

**Decision**: notify fork owners via the UPD-044 template-update notification channel (`notifications.template_updated.fork`), reusing the existing `MarketplaceFanoutConsumer` (`apps/control-plane/src/platform/marketplace/consumer.py:37`) once it is registered in the worker lifespan. The consumer subscribes to `marketplace.source_updated` (already produced by `review_service.approve` per the 099 implementation) and fans out to the fork-owner inbox.

**Why reuse the existing consumer (not write a new one):**
- 099 already implements `MarketplaceFanoutConsumer` and the upstream emit. Only registration is missing — a one-line addition in `apps/control-plane/entrypoints/worker_main.py` after the existing consumer registrations.
- UPD-044's template-update channel is the canonical path for "the source of a thing you forked has updated" notifications. Reusing it gives fork-update users the same UI affordances (the alert renderer, the inbox grouping) as template forks.

**Frontend renderer:**
- `SourceUpdatedAlertRenderer` (T076 from 099 NOTES) maps `marketplace.source_updated` to a notification card with deep-link to the source agent detail page. The card body explicitly states "this fork has NOT been auto-updated" so the user is not misled.

**Alternatives considered:**
- Per-fork polling from the frontend — rejected. Doesn't scale, generates needless query load, and creates inconsistent state across browser tabs.
- Inline alerting from `review_service.approve` synchronously — rejected. Sync notifications inside the approve transaction would block reviewers if the inbox is slow; the Kafka-backed fan-out is fire-and-forget and matches existing patterns.

---

## R13 — Live-DB integration test fixture rollout

**Decision**: introduce the live-DB+Kafka integration fixture by **registering the existing `tests/e2e/` fixture from feature 071 inside the `apps/control-plane/conftest.py`** under a new pytest mark `integration_live`. The 18 scaffolded integration tests committed by 099 (with `pytest.mark.skipif(True, ...)` markers) are migrated to the new mark, and the skip markers are removed.

**Why reuse the feature-071 fixture (not author a new one):**
- Feature 071 (`specs/071-e2e-kind-testing/`) already provides a `db`, `kafka_consumer`, and `http_client` fixture set that boots a kind cluster with the same Helm chart used in production. Reusing it avoids duplicating the bootstrap logic and ensures the integration suite always tests against the same data-store images as production.
- The skipif markers in 099's scaffolds name the fixture they need (each docstring is a self-contained test specification per 099 NOTES.md item 5). Wiring them up is mechanical.

**Tests un-skipped:**
- T020 — RLS cross-product visibility test (default-tenant ↔ enterprise-with-flag ↔ enterprise-without-flag × workspace/tenant/public scopes × draft/pending/published statuses).
- T023–T030 — REST contract tests for publish-with-scope, claim, release, approve, reject.
- T048–T049 — feature-flag toggle audit + cache invalidation contract tests.
- T054–T056 — consumer-side fork tests (refused-without-flag, name-collision, mcp-dependency-mismatch).
- T060 — admin assignment/unassignment contract test.
- T064–T069 — fork lifecycle end-to-end (resolve consumer plan version, quota check, tool registry cross-check).

**CI integration:**
- The `integration_live` mark is included in the existing `make integration-test` target. CI gates merge on PR.

**Alternatives considered:**
- Author a fresh in-tree fixture — rejected. Duplicates feature 071 work and risks divergence.
- Run the integration suite only in nightly — rejected. Catching regressions on PR is the whole point of the un-skip.

---

## R14 — Cost attribution verification (SC-005)

**Decision**: SC-005 is verified by an integration test that runs a public agent as an Acme user (consume-flag enabled), then asserts the resulting cost event in ClickHouse has `tenant_id = acme_tenant_uuid` (the consumer), not `tenant_id = default_tenant_uuid` (the publisher). The 099 implementation already records `tenant_id` from the running execution context, which is the consumer's; the test makes this property load-bearing.

**Why we test it explicitly when the path is "automatic":**
- "Automatic via tenant_id-on-execution" is true in the current code path, but a future refactor of cost attribution that moves cost-event-emit upstream of execution-context binding could regress it silently. SC-005 says "production billing reports MUST be zero defects on this surface" — so the test must lock the property.
- The test runs against ClickHouse via the existing `clickhouse-connect` fixture. It does not introduce a new test-only data store.

**Alternatives considered:**
- Skip the test, trust the code path — rejected. SC-005 names production billing reports; a silent-regression risk on billing is constitutional rule 31 territory ("cost data is cumulative, never modify past attributions" — adjacent enough to warrant a regression lock).

---

## Summary of Phase 0 decisions

| ID | Topic | Decision |
|---|---|---|
| R9 | Self-review prevention | Two-layer guard: service + API. New `SelfReviewNotAllowedError` (HTTP 403). Audit-chain on refusal. |
| R10 | Non-leakage parity | Single visibility-filter pre-query layer across PG/OpenSearch/ClickHouse. Dev-only `parity-probe` endpoint backs the SC-004 CI test. |
| R11 | Assignment vs. claim | New column `assigned_reviewer_user_id`. Separate audit/Kafka events. Claim refuses on assignment mismatch. |
| R12 | Fork-update notification | Reuse `MarketplaceFanoutConsumer`; one-line worker registration. UPD-044 template-update channel. New `SourceUpdatedAlertRenderer`. |
| R13 | Integration-test fixture | Reuse feature-071 live-DB+Kafka fixture under new `integration_live` pytest mark. Un-skip 18 scaffolded tests. |
| R14 | Cost attribution lock | Integration test against ClickHouse asserts `tenant_id = consumer_tenant_uuid` on public-agent invocations. |

All NEEDS CLARIFICATION markers from the spec resolved (none introduced — the spec was complete enough for direct planning).
