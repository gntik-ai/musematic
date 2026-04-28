# Research — UPD-045 (feature 095)

This file resolves the twelve research items called out by `plan.md`. Each entry follows Decision / Rationale / Alternatives. Citations are file:line into the current repo state on `main` as of 2026-04-28.

---

## R1 — Auth-exempt list extension vs separate router-tree

**Decision**: Extend `EXEMPT_PATHS` in `apps/control-plane/src/platform/common/auth_middleware.py:13-32` with the new public status paths. Mount the public endpoints under `/api/v1/public/...` for visual clarity but **NOT** under a separate router tree.

**Rationale**: The repo already establishes the exception-list pattern for public endpoints (e.g., `/api/v1/accounts/register`, `/api/v1/auth/login`, `/api/v1/security/audit-chain/public-key`, `/api/v1/maintenance/status-banner`). Adding a parallel `/api/public/*` router-tree would split the OpenAPI document and create two surfaces middleware authors must remember to extend (rate-limit, correlation IDs, etc.).

**Alternatives**:
- Separate `/api/public/*` router tree (planning-input wording) — rejected because of the maintenance burden.
- Move `/api/v1/maintenance/status-banner` into a public-only sub-app — rejected as scope creep; the status-page work composes with the existing endpoint, it does not relocate it.

**New EXEMPT_PATHS additions**:
```
"/api/v1/public/status",
"/api/v1/public/components",                           # per-component sub-resource (under same prefix → single rule covers it via prefix matching if middleware supports; see implementation note below)
"/api/v1/public/incidents",
"/api/v1/public/status/feed.rss",
"/api/v1/public/status/feed.atom",
"/api/v1/public/subscribe/email",                      # POST submit
"/api/v1/public/subscribe/email/confirm",              # GET token-link confirm
"/api/v1/public/subscribe/email/unsubscribe",          # GET token-link unsubscribe
"/api/v1/public/subscribe/webhook",                    # POST authenticated visitor — reuses confirm-token flow
```

**Implementation note**: `EXEMPT_PATHS` is a `frozenset[str]` of exact-match paths today. For per-component pages we use `/api/v1/public/components/{component_id}` — the middleware needs prefix-matching for `/api/v1/public/`. The cleanest extension is adding a `EXEMPT_PREFIXES: frozenset[str]` alongside `EXEMPT_PATHS`, with prefix matching guarded by a `startswith` check. This is a one-line additive change to the middleware and preserves the existing exact-match semantics for non-prefix entries. Verified safe: no current EXEMPT_PATHS entry uses a prefix that could clash with another route.

---

## R2 — RSS/Atom builder library choice

**Decision**: Add `feedgen` 1.0+ (PyPI: `feedgen`) as a new control-plane dependency. License MIT, ~50KB, pure-Python, no transitive deps beyond `lxml` (already present transitively via `opensearch-py`).

**Rationale**: RSS 2.0 + Atom 1.0 namespace handling is non-trivial; hand-rolled XML routinely fails third-party validators (W3C Feed Validator, FeedBurner) due to namespaced-element ordering and required `<atom:link rel="self">` self-references. `feedgen` is the de-facto Python feed builder, used in production by static-site generators (Pelican, Nikola).

**Alternatives**:
- Stdlib `xml.etree.ElementTree` — rejected: produces brittle output, requires careful namespace handling, fails Atom validators on edge cases.
- `feedformatter` — rejected: unmaintained since 2014.
- `python-feedgen` (different package) — same as `feedgen`; package name is `feedgen`.

---

## R3 — Locale list reconciliation

**Decision**: Plan deliverables target the FR-620 canonical 6-locale set: **en, es, de, fr, it, zh-CN**. The existing `apps/web/messages/ja.json` is treated as a stale artifact predating UPD-088 (feature 088) and is left in place by this feature; its removal is out of scope for UPD-045.

**Rationale**: `CLAUDE.md` (top of file, recent UPD-039 corrections paragraph) explicitly enumerates the canonical FR-620 locales as `en, es, de, fr, it, zh/zh-CN, not ja`. The repo currently ships `apps/web/messages/{de,en,es,fr,ja,zh-CN}.json` — `it.json` is missing AND `ja.json` is present, making the repo state out-of-spec versus FR-620. Spec FR-695-54 commits this feature to "all six locales (en, es, de, fr, it, zh)".

**Action items for this feature**:
1. CREATE `apps/web/messages/it.json` with the same key set as `en.json`. Italian translations may use English fallbacks initially per spec edge-case "Banner localisation gap"; copy review is owned by the localization team.
2. ADD UPD-045 keys to all 6 locales (en + es + de + fr + it + zh-CN). NEW keys ALSO appear in `ja.json` as English fallbacks to keep parity with the existing repo state.
3. Removal of `ja.json` is OUT OF SCOPE — flagged for the i18n team / a follow-up feature.

**Alternatives**:
- Skip `it.json` creation and ship in 5 locales — rejected: violates spec FR-695-54.
- Drop `ja.json` as part of this feature — rejected: scope creep; affects unrelated UI surfaces; needs i18n team approval.

---

## R4 — Public status snapshot generation strategy

**Decision**: Hybrid generation: (a) Kafka consumer subscribes to `multi_region_ops.events` and `incident_response.events` to react to lifecycle changes within seconds; (b) APScheduler 60-second cron polls in-cluster `/healthz`/`/readyz` for each service-of-record (control-plane runtime profiles, Go satellites, data stores) to update component health; (c) the composed `PlatformStatusSnapshot` is written to PostgreSQL (audit) AND `status:snapshot:current` Redis key (TTL 90s, hot read).

**Rationale**:
- Kafka events alone are not sufficient — they cover maintenance + incidents but not silent component degradation. Polling adds the safety net.
- 60s poll matches FR-695-03 ("regenerate at most every 60 seconds").
- Redis 90s TTL gives 30s of slack so a delayed regeneration still serves the current snapshot.
- Writing to PostgreSQL preserves the historical 30-day uptime view (FR-695-01 acceptance scenario 5) and provides the "last known good" fallback for Rule 49.

**Alternatives**:
- Pure pull every request → too slow (p95 ≤ 200ms unrealistic with N component fan-out).
- Pure event-driven → silent regressions in unmonitored components go unnoticed.

**Component health source**: Reuse the existing `/healthz` and `/readyz` endpoints already present per service. The poller does NOT introduce a new health protocol.

---

## R5 — Alembic migration slot allocation

**Decision**: Migration `095_status_page_and_scenarios.py`. Verified next available slot: feature 094 (UPD-044, neighbour) used `072_creator_context_contracts.py` per `specs/094-creator-context-contracts-ui/plan.md`. The `095_*` slot continues the per-feature numbering.

**Verification**: Listed `apps/control-plane/migrations/versions/` — current latest numeric prefix is below 095 (subject to ongoing `main` activity; tasks-phase will re-confirm and renumber if needed). The number is monotonic and assigned at task time; if a parallel feature races, this feature renames to next-free at PR-prep time.

---

## R6 — E2E directory bootstrap

**Decision**: This feature creates the top-level `tests/e2e/journeys/` and `tests/e2e/suites/` directories and the first batch of files inside them. If feature 071 (E2E kind testing) lands first and seeds these directories, this feature inherits them unchanged.

**Rationale**: The agent-research run on 2026-04-28 found `apps/control-plane/tests/integration/` populated but no top-level `tests/e2e/` tree. Per Rule 25 ("New BC suites live under `tests/e2e/suites/<bc_name>/`"), this feature is the first in the v1.4.0 wave to land a full journey test set if it sequences before UPD-035/071.

**Sequencing risk**: If feature 071 has not landed when this feature reaches tasks-phase, this feature owns harness bootstrap (pytest config, conftest fixtures for kind cluster, `db`/`kafka_consumer`/`http_client` fixtures). That is more work than the +1d already accounted for in the E2E line. Tasks-phase will surface this risk explicitly with a feature-flag/skip mechanism for tests that depend on the harness.

---

## R7 — Reuse `OutboundWebhook` for status webhook subscriptions

**Decision**: Reuse the existing `OutboundWebhook` table (`apps/control-plane/src/platform/notifications/models.py:229-348`) for webhook-channel status subscriptions. Add the new event types (`incident.created`, `incident.updated`, `incident.resolved`, `maintenance.scheduled`, `maintenance.started`, `maintenance.ended`) to the allowed-event-types validation. Email/RSS/Atom/Slack subscriptions live in the new `status_subscriptions` table.

**Rationale**:
- HMAC signing (Rule 17), DLQ, exponential-backoff retry, dead-letter inspection, and idempotency keys are already implemented in `notifications/deliverers/webhook_deliverer.py:43-89` and `notifications/webhooks_service.py:135-150`. Building a parallel webhook path would duplicate ~400 LOC and ~6 tables.
- Keeps the Operator Dashboard pattern consistent (one place to inspect failed webhook deliveries regardless of source).

**Alternatives**:
- Separate `status_webhook_subscriptions` table — rejected: duplication.
- Inline HMAC/retry in `status_page/` — rejected: violates Rule 4 (use existing patterns).

**Note on workspace scoping**: Anonymous-visitor webhook subscriptions have no `workspace_id`. Add a sentinel `IS_NULL` allowance to `OutboundWebhook.workspace_id` OR introduce a synthetic `system_status` workspace. Tasks-phase decides; the cleaner option is the synthetic system workspace because it preserves the NOT-NULL invariant. **Decision: synthetic `system_status` workspace, owned by the platform** (consistent with the existing pattern of platform-owned vs workspace-owned resources per Rule 47).

---

## R8 — Reuse `<RealLLMOptInDialog>` for scenario preview

**Decision**: Reuse `apps/web/app/(main)/agent-management/[fqn]/contract/_components/RealLLMOptInDialog.tsx` (introduced by UPD-044 / feature 094) for the scenario-preview real-LLM opt-in gate.

**Rationale**: Rule 50 mandates a "clear cost indicator" for real-LLM preview opt-in. UPD-044 implemented the canonical primitive: a Dialog that requires the user to type "USE_REAL_LLM" before enabling. Inventing a second variant for scenario-preview would split the pattern.

**Implementation**: Move the dialog out of the contract sub-folder into a shared location (`apps/web/components/features/shared/RealLLMOptInDialog.tsx`) as a tasks-phase refactor. Until that move, scenario editor imports from the current path.

**Alternatives**:
- Roll a new dialog — rejected: violates Rule 4 + Rule 50 spirit.
- Skip opt-in (default to mock LLM with no real-LLM option) — rejected: spec User Story 6 explicitly references real-LLM-opt-in.

---

## R9 — XYFlow + Dagre confirmation (no Cytoscape)

**Decision**: Reuse the existing `apps/web/components/features/discovery/HypothesisNetworkGraph.tsx` unchanged. The session-detail page renders the existing component as the "network" tab.

**Rationale**: Spec Brownfield Reconciliation #8 documents the planning-input's incorrect "Cytoscape" framing. Repo confirms `@xyflow/react ^12.10.2` + `@dagrejs/dagre ^3.0.0` are the canonical primitives.

**Alternatives**: None — adding Cytoscape is forbidden by the spec.

---

## R10 — `status_page/` BC structure conformance

**Decision**: Follow the standard bounded-context structure documented in the constitution (`.specify/memory/constitution.md:659-671`):

```
status_page/
├── __init__.py
├── models.py          # SQLAlchemy: PlatformStatusSnapshot, StatusSubscription, SubscriptionDispatch
├── schemas.py         # Pydantic
├── service.py         # snapshot composition, subscription confirm/unsubscribe, dispatch fan-out
├── repository.py      # async queries
├── router.py          # FastAPI router (public + admin)
├── me_router.py       # /api/v1/me/platform-status authenticated user surface (kept separate for clarity)
├── events.py          # internal event types (no new Kafka topic — events are in-process)
├── exceptions.py
├── dependencies.py
├── projections.py     # Kafka consumer + APScheduler poll + 30d uptime rollup
└── feed_builders.py   # RSS + Atom builders (uses feedgen)
```

**Rationale**: Constitution mandates this structure. The two unusual sub-modules (`me_router.py`, `feed_builders.py`) are additive and named per constitution patterns. `projections.py` is the constitutional name for read-model projection workers (`.specify/memory/constitution.md:670`).

**Alternatives**: None — structure is fixed by constitution.

---

## R11 — Static-site fallback strategy

**Decision**: Three-layer fallback for `apps/web-status/`:

1. **Primary** — client fetches `https://{public-host}/api/v1/public/status` from the visitor's browser. Fast cache via CDN.
2. **Secondary** — if the fetch fails, the page hydrates from a `last-known-good.json` file embedded in the static export. The CronJob (`status-snapshot-cronjob.yaml`) updates this file every 60s by writing to a shared volume mounted by the `web-status` Deployment.
3. **Tertiary** — if even the static asset is stale (the CronJob has been failing for >5 minutes), the page banners "Status data is stale (as of HH:MM UTC); platform team has been notified". Operators get a Prometheus alert via the existing observability rule pattern.

**Rationale**: Rule 49 demands operational independence. Layer 1 covers normal operations. Layer 2 covers main-platform outage (the API may be down; the static asset is independently served). Layer 3 covers degenerate cases where the snapshot generator itself is down.

**Implementation note for Layer 2**: The `web-status` pod has a volumeMount for a ConfigMap-or-emptyDir-shared-with-CronJob volume. The CronJob writes `last-known-good.json` after a successful snapshot generation. The static export reads from `/last-known-good.json` (relative URL) which the Nginx config serves from the volume.

**Alternatives**:
- Static-only (no live API hop) — rejected: 60s freshness ceiling means visitors see up to 60s-stale data even when the platform is healthy.
- Live-only (no fallback) — rejected: violates Rule 49.

---

## R12 — Shared component package vs duplication for `<StatusIndicator>`

**Decision**: Duplicate `<StatusIndicator>` between `apps/web/components/features/platform-status/StatusIndicator.tsx` and `apps/web-status/components/StatusIndicator.tsx`. Both copies are ~30 LOC, identical except for the `t()` import (the public site uses inline strings since it has its own minimal i18n setup — see implementation note).

**Rationale**:
- A shared package would force a build-time dependency between the two apps, which violates Rule 49 (independent deployments).
- The component is small (~30 LOC) and stable (severity dot + icon + text — the API surface is fixed by spec FR-695-12).
- Drift risk is low; tasks-phase will add a snapshot test in each app to catch divergence.

**Public-site i18n note**: `apps/web-status/` does NOT use `next-intl` — it uses a tiny static dictionary (`apps/web-status/lib/i18n.ts` ~40 LOC with the 6-locale strings) selected by `Accept-Language`. This avoids pulling in `next-intl` (~80KB) into a static export that the visitor's browser fetches before any auth.

**Alternatives**:
- Extract to `packages/ui/` workspace package — rejected: introduces pnpm workspace work that scope-creeps into a v1.4.0 workspace-restructuring task.
- Single source in `apps/web/` consumed by `apps/web-status/` via path alias — rejected: same outcome (static site depends on main app's build), still violates Rule 49.

---

## Open Questions Carried to `/speckit-clarify`

None. All twelve research items are resolved. Tasks-phase will own:
- Confirming the Alembic slot is still 095 at PR time (R5).
- Confirming UPD-035/071 sequencing for the E2E directory bootstrap (R6).
- Renaming the `<RealLLMOptInDialog>` import path during the contract→shared move (R8).

---

**End of Research.**
