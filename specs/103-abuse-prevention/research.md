# Research — UPD-050 Abuse Prevention (Refresh on 100-upd-050-abuse)

**Phase 0 output.** Resolves the architecture decisions for the refresh pass. The prior `100-upd-050-abuse` branch's research file is the baseline; the items below either restate (R1–R8) or replace (R9–R12) those decisions for the refresh.

---

## R1 — Velocity counter substrate (Redis vs. PostgreSQL)

**Decision**: Redis is the primary substrate for the rolling-window velocity counters. PostgreSQL is the durable mirror that the cron persists daily for forensics and for cross-pod consistency (so a pod restart does not lose recent state).

**Rationale**:
- The hot path of every signup attempt issues an `INCR` + `EXPIRE` against `abuse:vel:ip:{ip}` (and `:asn`, `:domain`). Redis adds <2 ms p99; PostgreSQL would add 10–50× that.
- Counters are short-lived (1 hour or 1 day); durability beyond that window is not required for enforcement, only for audit.
- The PostgreSQL mirror table `signup_velocity_counters` is written by the cron every 60 seconds with the current Redis values for the open windows, so an analyst can run forensic queries against the database without consulting Redis directly.

**Failure mode (fail-closed)**: when Redis is unreachable the velocity guard refuses the signup with HTTP 503 (`abuse_prevention_unavailable`) rather than admitting it. Refusing is safer than admitting an unbounded burst — this is encoded in the spec's Constraints section.

**Alternatives considered**:
- PostgreSQL-only with a partial index on `(counter_key, counter_window_start)`: rejected — the hot path latency hit is unacceptable on a public signup surface.
- In-process counters per pod: rejected — cross-pod state means a 5/IP/hour limit becomes 5×N/IP/hour with N pods, defeating the purpose.
- Memcached: rejected — no AOF/RDB-equivalent durability; Redis already in stack.

---

## R2 — Disposable-email list source

**Decision**: weekly cron sync from the `disposable-email-domains/disposable-email-domains` GitHub project (`master/disposable_email_blocklist.conf`). Stored in `disposable_email_domains` table with the source name and last-update timestamp. Super-admin per-domain overrides ride alongside in `disposable_email_overrides` (separate table, takes precedence).

**Rationale**:
- The upstream project is the de-facto industry standard, MIT-licensed, ~2,000 domains, updated weekly.
- A weekly refresh balances freshness vs. churn; daily would be needlessly aggressive given the upstream cadence.
- Override list as a separate table (rather than a `is_blocked` boolean on `disposable_email_domains`) keeps the upstream sync idempotent — the cron truncates + reinserts the upstream list without disturbing manual overrides.

**Privacy**: refused-email entries in the audit chain hash the local-part (left of @) but keep the domain in cleartext; this lets analysts spot abuse domains without exposing PII.

**Alternatives considered**:
- Maintain the list in-house: rejected — high maintenance cost, no upstream community signal.
- Multiple upstream sources merged: rejected for the initial pass — adds operational complexity (deduplication, conflict resolution); the user input names a single source as the canonical seed.
- Bloom filter for memory efficiency: rejected — the list is small enough (~2,000 domains × ~30 bytes = 60 KB) that an in-memory `set[str]` is fine.

---

## R3 — Auto-suspension rule scope

**Decision**: three rule families ship in the initial pass — (a) cost burn-rate breach despite hard caps (Kafka consumer reading `cost.budget.exceeded`), (b) repeated velocity hits within a configurable window (3+ velocity-block events on the same user within 24 h), (c) fraud-scoring "suspend" verdict (only when fraud-scoring is enabled).

**Rationale**:
- The three rules cover the most common abuse patterns at the lowest false-positive rate; spec FR-744.2 names exactly these.
- Each rule emits an audit-chain entry naming the rule that fired so a super admin reviewing the suspension queue can see "why" without reading code.
- Privileged-role exemption is a hard rule (FR-744.3): the auto-suspension service refuses to suspend any user whose roles include `platform_admin` or `tenant_admin`. The check happens before the suspension UPDATE.

**Cron cadence**: the auto-suspension scanner runs every 5 minutes (APScheduler). Faster cadence is overkill (the underlying signals — cost-burn, repeated velocity hits — accumulate over minutes, not seconds). Slower than 15 minutes would let an abuser run unchecked for too long.

**Alternatives considered**:
- Real-time evaluation in the Kafka consumer only (no cron): rejected — some rules (repeated-velocity-hits) require windowed aggregation which is awkward in a single-message handler.
- ML-based scoring instead of rule-based: deferred — needs training data the platform doesn't have yet.

---

## R4 — CAPTCHA provider abstraction

**Decision**: a `CaptchaProvider` Protocol with two implementations shipping (`TurnstileProvider`, `HCaptchaProvider`). The provider is selected by the `captcha_provider` setting (`"turnstile"` | `"hcaptcha"` | `"disabled"` default). Verification happens server-side; the frontend obtains the token via the provider's widget and posts it on the signup body.

**Rationale**:
- Both providers expose nearly identical verify endpoints (`POST` with `secret` + `response`). The Protocol abstracts the common shape; provider-specific quirks (Turnstile's `idempotency_key`, hCaptcha's `sitekey` echo) live in each implementation.
- Token replay is prevented by a Redis 10-minute cache (`abuse:captcha_seen:{sha256(token)}`); the provider's own replay protection is the primary defence; the cache is belt-and-braces.
- Provider secrets resolve through the existing `SecretProvider` per constitutional rule 39 — never `os.getenv` from business logic.

**Alternatives considered**:
- Single provider hardcoded (Turnstile only): rejected — operators in some regions prefer hCaptcha; the abstraction is cheap.
- Self-hosted CAPTCHA: rejected — operational burden; the two cloud providers are free for low traffic.

---

## R5 — Geo-IP source and update cadence

**Decision**: MaxMind GeoLite2-Country (free tier, license-key registered). The `.mmdb` binary file ships as a chart-mounted `ConfigMap` under 100 KB (the country DB only — not the larger city DB). Refreshed by an existing Helm Job that downloads on chart upgrade; no live refresh.

**Rationale**:
- GeoLite2-Country is the smallest accurate country-resolution DB; the city DB (~80 MB) would be overkill for "block country X".
- ConfigMap delivery means no network call from the running pod — `geoip2.Reader` reads the file on init and serves lookups in <1 ms.
- Chart-time refresh is acceptable because country mappings rarely change; a stale month-old DB is fine. Operators upgrading the chart get a fresh DB automatically.

**Failure mode**: if the DB file is missing (e.g., chart misconfiguration), `geo_block.py` returns `None` for the country lookup and the geo-block guard skips with a structured-log warning. Spec FR-746.2 mandates this graceful degradation.

**Alternatives considered**:
- ip-api.com (HTTP API): rejected — adds 50–200 ms per signup; rate-limited; another dependency.
- MaxMind GeoLite2-City: rejected — 80 MB is too much for a ConfigMap (limit 1 MB, would need a PVC); city granularity not needed.
- IPgeolocation.io: rejected for the same reason as ip-api.com.

---

## R6 — Fraud-scoring adapter shape

**Decision**: Protocol-based `FraudScoringProvider` with NO concrete implementations shipping in this branch. The Protocol has one method `score_signup(payload) -> FraudScoreResult` with `verdict ∈ {"allow", "review", "suspend"}`. The setting `fraud_scoring_provider` defaults to `"disabled"`. When set to a value (e.g., `"minfraud"`), the system raises a runtime error at startup until a concrete adapter is registered — i.e., shipping the Protocol without a provider is intentional, so operators must explicitly opt in by registering an adapter at app startup.

**Rationale**:
- MaxMind minFraud and Sift have very different request/response shapes — abstracting them via Protocol is the right separation.
- Shipping no concrete provider keeps the dependency graph clean; operators add `minfraud` (or whatever they choose) to their own deployment if they need it.
- The "review" verdict path emits a notification to the super admin but does NOT auto-suspend (FR-747.2) — that distinction belongs to the operator's playbook, not the platform default.

**Failure mode** (FR-747.1): timeouts and 5xx from the upstream provider MUST NOT block signup. The adapter wraps the call in a 3-second timeout with retries disabled; failure short-circuits to "allow" with a structured-log warning.

**Alternatives considered**:
- Ship a minFraud adapter: rejected for now — adds a commercial dependency that most operators don't need; the Protocol surface is the value.
- Synchronous block on fraud-scoring failure: rejected per the spec's graceful-degradation requirement.

---

## R7 — Free-tier cost protection enforcement points

**Decision**: enforcement happens at three call sites:

1. **Model-router** (`apps/control-plane/src/platform/common/clients/model_router.py`): refuses `model_id` whose `tier` is not in the workspace's plan-defined `allowed_model_tier`. UI-only enforcement is insufficient per AD-19 / constitutional rule 11.
2. **Execution service** (`apps/control-plane/src/platform/execution/service.py`): refuses new execution start when the workspace's `monthly_execution_cap` is reached; auto-terminates running executions when their wall time exceeds `max_execution_time_seconds`.
3. **Reasoning engine client** (`apps/control-plane/src/platform/reasoning/client.py`): passes `max_reasoning_depth` to the gRPC `ReasoningEngineService.RequestReasoning` call; the Go reasoning engine refuses to recurse beyond the depth.

**Rationale**:
- Defence in depth: each enforcement point is independent and authoritative within its layer.
- Enforcement at the model-router level catches direct API calls (per the spec's "Model-tier check evaded by direct API call" edge case).
- Auto-termination at the execution service runs against an existing per-execution timer (already implemented for the workflow engine); this just lowers the timeout per the workspace's plan.

**Alternatives considered**:
- Single enforcement point at the API gateway: rejected — too far from the data; the API gateway doesn't know the workspace's plan.
- Enforcement only at the runtime controller (Go): rejected — Python-side checks add an earlier rejection point, reducing wasted work; the runtime controller still enforces as a final gate.

---

## R8 — Admin surface routing and shared abstractions

**Decision**: all admin endpoints under `/api/v1/admin/security/*` (consistent with the existing `/api/v1/admin/*` segregation per rule 29). The frontend admin pages live under `app/(admin)/admin/security/*` (consistent with the existing `(admin)` route group). Settings reads/writes go through a single `AbusePreventionService.get_setting / set_setting(key, value, actor)` interface; the service emits the audit-chain entry on each write so per-endpoint code doesn't have to remember.

**Rationale**:
- The existing admin surface convention (queue + tuning + override list) is well-understood by reviewers; replicating it minimises cognitive load.
- A single setting service guarantees every write is audited — rule 9 enforcement at the service layer catches mistakes at the route layer.

**Alternatives considered**:
- Per-knob endpoints with bespoke logic: rejected — duplicates audit boilerplate.
- Settings as env vars: rejected — operators want to tune in real time without a redeploy (rule 8).

---

## R9 — Migration number conflict (refresh-pass specific)

**Decision**: this refresh's Alembic revision is `110_abuse_prevention` (≤32 chars per the `alembic_version.version_num varchar(32)` constraint we observed in PR #135). The prior branch's `109_abuse_prevention` is no longer available — `109` is occupied by `109_marketplace_reviewer_assign` (UPD-049 refresh, merged via PR #135).

**Why we observed this constraint**: in PR #135 the original revision id `109_marketplace_reviewer_assignment` (35 chars) failed `make migrate` with `StringDataRightTruncationError: value too long for type character varying(32)`. The fix was to shorten the id; the same constraint applies here. `110_abuse_prevention` is 22 chars — well under the limit.

**Operational consequence**: if the prior `100-upd-050-abuse` branch is later cherry-picked, its migration must be renumbered AND its revision id shortened (the prior file `109_abuse_prevention` is 22 chars so the length was not the original problem there — only the number).

**Alternatives considered**:
- Fork off the prior branch and rebase its migration: rejected — the divergence in module path (R10 below) means a clean restart is cheaper than a rebase.
- Skip the migration and use only Redis: rejected — the durable mirror is necessary for forensics and for the auto-suspension scanner's lookback queries.

---

## R10 — Bounded-context module path (refresh-pass specific)

**Decision**: bounded context at `apps/control-plane/src/platform/security/abuse_prevention/`. The prior branch used a flat `security_abuse/` (no nested subpackage). The user input for this refresh names the nested layout, and we adopt it.

**Rationale**:
- A `security/` package leaves room for future security-domain BCs (e.g., a hypothetical `security/incident_intake/` or `security/credential_review/`) without another rename.
- The existing `security_compliance/` BC is unrelated to abuse prevention — it owns SBOM, vuln scanning, JIT credentials, audit-chain machinery. Co-locating it under `security/security_compliance/` would be cleaner long-term but is OUT OF SCOPE for this feature (would touch dozens of imports across other BCs).
- The nested split reflects the spec's separation-of-concerns: `abuse_prevention/` handles the public-tenant defensive layer; `security_compliance/` handles internal compliance machinery.

**Operational consequence**: as noted in R9, prior-branch cherry-picks must move files into the nested path.

**Alternatives considered**:
- Flat `security_abuse/` (matching prior branch): rejected per user input.
- Add to `security_compliance/`: rejected — different concern, different cadence, would couple feature surfaces.

---

## R11 — Module split for disposable-emails and suspension (refresh-pass specific)

**Decision**: split into `disposable_emails.py` and `suspension.py` per the user input. The prior branch used a single `service.py` containing both. The split improves locality of concern: each domain owns its service, repository hits, exceptions, and audit emission paths.

**Rationale**:
- Two domains, two services — matches the existing per-domain service pattern in `auth/`, `accounts/`, `marketplace/`.
- `disposable_emails.py` owns the registry, the in-memory cache, the lookup API, and the cron sync. `suspension.py` owns the suspension lifecycle, the auto-rule engine, and the lift API.
- The split makes unit testing easier — each service has a clear seam.

**Alternatives considered**:
- Keep them in one `service.py` (matching prior branch): rejected per user input.
- Three-way split (`disposable_emails.py`, `suspension.py`, `auto_rules.py`): rejected — the auto-rule engine is small (~3 rules) and cleanly nested under suspension.

---

## R12 — Telemetry naming convention

**Decision**: Prometheus counters / histograms follow the `abuse_prevention_*` prefix with explicit dimension labels:
- `abuse_prevention_signup_refusals_total{reason="velocity"|"disposable_email"|"captcha"|"geo_block"|"fraud_scoring"}`
- `abuse_prevention_suspensions_total{source="system"|"super_admin"|"tenant_admin", reason="..."}`
- `abuse_prevention_cap_fired_total{cap="model_tier"|"execution_time"|"reasoning_depth"|"monthly_execution_cap"}`
- `abuse_prevention_velocity_check_seconds` histogram (verifies the ≤5 ms p99 perf goal)
- `abuse_prevention_disposable_email_lookup_seconds` histogram (verifies the ≤2 ms p99 perf goal)

**Rationale**:
- The `abuse_prevention_` prefix mirrors the bounded-context name; existing code uses `marketplace_*`, `accounts_*`, etc. Consistency aids dashboard discovery.
- Dimension labels are LOW cardinality (≤8 distinct values per label, no per-user/per-IP labels) per constitutional rule 22 / rule 40. High-cardinality fields (IP, user_id) go in JSON log payloads, not Prometheus labels.

**Alternatives considered**:
- Single `abuse_events_total{kind=...}` counter with high-cardinality `kind`: rejected — operators want to alert on `velocity_refusals_per_minute > X` independently of `disposable_email_refusals`.

---

## Summary of Phase 0 decisions

| ID | Topic | Decision |
|---|---|---|
| R1 | Velocity substrate | Redis primary + PostgreSQL durable mirror; fail-closed on Redis outage |
| R2 | Disposable-email source | Weekly cron from `disposable-email-domains` GitHub repo; separate override table |
| R3 | Auto-suspension rules | 3 families: cost-burn / repeated-velocity / fraud-scoring-verdict; 5-min scanner; privileged exemption |
| R4 | CAPTCHA abstraction | Protocol + Turnstile + hCaptcha; replay cache 10 min; Vault for secrets |
| R5 | Geo-IP source | GeoLite2-Country .mmdb in ConfigMap; chart-time refresh; graceful degrade on missing DB |
| R6 | Fraud-scoring adapter | Protocol only — no concrete provider in this branch; "review" verdict notifies, "suspend" auto-suspends |
| R7 | Free-tier enforcement | 3 call sites: model-router, execution service, reasoning engine; defence in depth |
| R8 | Admin surface routing | `/api/v1/admin/security/*` + `(admin)/admin/security/*`; single settings service for audit emission |
| R9 | Migration number | `110_abuse_prevention` (109 taken by UPD-049 refresh) — revision id ≤32 chars |
| R10 | Bounded-context path | `security/abuse_prevention/` (nested) — replaces prior branch's flat `security_abuse/` |
| R11 | Module split | `disposable_emails.py` + `suspension.py` (separate) — replaces prior branch's combined `service.py` |
| R12 | Telemetry naming | `abuse_prevention_*` prefix; low-cardinality labels only |

All NEEDS CLARIFICATION markers from the spec resolved (none introduced).
