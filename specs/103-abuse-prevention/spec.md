# Feature Specification: UPD-050 — Abuse Prevention and Trust & Safety

**Feature Branch**: `103-abuse-prevention`
**Spec Directory**: `specs/103-abuse-prevention/`
**Created**: 2026-05-03
**Status**: Draft
**Input**: User description: "UPD-050 — Abuse Prevention and Trust & Safety"

---

## Brownfield Context

**Prior work (unmerged)**: branch `100-upd-050-abuse` carries an earlier pass at this feature dated 2026-05-02 — `specs/100-abuse-prevention/` (spec, plan, tasks, data-model, quickstart, contracts), a new `security_abuse/` bounded context (16 modules: `velocity.py`, `service.py` for disposable-emails and suspension, `geo_block.py`, `fraud_scoring.py`, `captcha.py`, `consumer.py`, `cron.py`, etc.), Alembic migration `109_abuse_prevention.py`, and frontend admin surfaces under `(admin)/admin/security/`. **It has not been merged.** Five `chore(UPD-050): speckit implement ...` commits on the branch indicate the prior pass progressed through `/speckit-implement` rounds without closing.

**Two known conflicts with what is already on `main` after the UPD-049 refresh (PR #135):**

1. **Migration number collision.** Prior work claims revision `109_abuse_prevention`. After PR #135, `main` carries `109_marketplace_reviewer_assign` as the head. UPD-050 must take **migration 110** (or higher) when this refresh re-targets the work onto `main`.
2. **Bounded-context module path.** The user input for this refresh names the directory `security/abuse_prevention/`. The prior pass on `100-upd-050-abuse` used `security_abuse/` instead (no nested `abuse_prevention/` subpackage). The refresh adopts the user input's path; if the prior branch is later cherry-picked, the tree must be re-rooted accordingly.

**Scope boundary.** This feature covers velocity rules + disposable-email detection + account-suspension automation + optional CAPTCHA / geo-block / fraud-scoring integrations + Free-tier runtime cost protection + a `/admin/security/*` admin surface. It does NOT modify the existing UPD-037 signup rate-limiter (5/IP/hour, 3/email/24h) — those rate-limit rules continue to apply at the request gate; this feature stacks deeper protections on top.

**FR coverage**: FR-742 through FR-750 (functional-requirements section 123).

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Bot signup velocity block (Priority: P1)

A bot creates many signup attempts from a single IP within an hour. The system refuses the attempts after a configurable threshold and the legitimate users on the same network are not collaterally blocked beyond a brief, recoverable window.

**Why this priority**: This is the most common abuse vector for a public signup surface. Without per-IP velocity, a single bot can fill the user table with garbage accounts, drain the email-sending budget, and exhaust the signup-funnel telemetry. P1 is non-negotiable for the public default tenant.

**Independent Test**: Issue 10 signup requests from one IP within 60 seconds. The first 5 succeed (or follow the normal pending_verification → activated flow). Requests 6–10 return HTTP 429 with a `Retry-After` header indicating the rolling window's remaining seconds. After the rolling window elapses, the same IP can sign up again. A second IP in parallel is unaffected.

**Acceptance Scenarios**:

1. **Given** a default-tenant signup endpoint and the per-IP-hour threshold set to 5, **When** an actor issues 6 signup attempts from one IP inside the hour, **Then** attempt 6 returns HTTP 429 with a `Retry-After` header and an audit-chain entry recording the IP, the threshold breached, and the actor identity (anonymous before signup completes).
2. **Given** the same threshold, **When** an actor at one IP exhausts the limit and a different actor at a different IP attempts a signup, **Then** the second IP succeeds and is unaffected by the first IP's counter.
3. **Given** a successful signup completes, **When** counted, **Then** it counts toward the per-IP velocity counter the same as a failed attempt — the counter measures attempts, not outcomes.
4. **Given** a super admin lowers the threshold from 5 to 3, **When** the change is saved, **Then** subsequent attempts honour the new threshold without a redeploy. An audit-chain entry records the change with the admin's identity and the prior + new value.

---

### User Story 2 — Disposable-email signup rejected (Priority: P1)

A user attempts a signup with an email address whose domain appears on the disposable-email blocklist. The system refuses before sending any verification email.

**Why this priority**: Disposable emails are the primary churn vector for free-tier abuse. Sending verification mail to a `10minutemail.com` address wastes outbound bandwidth and pollutes deliverability reputation. P1 with story 1.

**Independent Test**: Submit signup with `tempmail@10minutemail.com`. Backend matches the domain against the disposable-email blocklist. The endpoint returns HTTP 400 with body identifying disposable-email as the refusal reason. No verification email is sent (verifiable by inspecting the outbound mail audit log). The UI surfaces a clear message naming the cause and pointing the user to use a permanent email address.

**Acceptance Scenarios**:

1. **Given** the disposable-email list contains `10minutemail.com`, **When** a user submits a signup with that email domain, **Then** the API returns HTTP 400 with a body identifying the rejection reason and no verification email is enqueued.
2. **Given** a super admin adds `legitimate-but-flagged.example` to the per-domain override list, **When** a user signs up with that domain, **Then** the signup proceeds normally even though the domain appears on the upstream blocklist.
3. **Given** the disposable-email list is refreshed weekly from an upstream source, **When** the refresh job completes, **Then** the new list version is used by subsequent signups without a redeploy and an audit-chain entry records the upstream source, the version, and the count of domains added/removed.
4. **Given** every disposable-email refusal, **When** counted, **Then** it emits an audit-chain entry with the (hashed or redacted) email, the matched domain, and the disposable-email list version at refusal time.

---

### User Story 3 — Suspended user login blocked (Priority: P1)

A user account that was suspended (manually by a super admin or automatically by an abuse rule) cannot log in. The login surface returns a clear, actionable error rather than a generic 401.

**Why this priority**: Suspension is the primary remediation tool for confirmed abuse. If suspended users can still authenticate, the suspension achieves nothing. P1 with stories 1–2.

**Independent Test**: Apply a suspension to a user (manually via the admin endpoint OR by triggering an abuse rule). The user attempts login with their correct credentials. The login endpoint returns an HTTP response that names "account suspended" as the reason and surfaces a contact route ("appeal at support@…"). The user is NOT given a JWT and existing sessions for that user are revoked at next request.

**Acceptance Scenarios**:

1. **Given** a user has an active suspension record, **When** they POST valid credentials to the login endpoint, **Then** the endpoint returns a refusal with code `account_suspended` and body containing the appeal contact; no JWT is issued.
2. **Given** a user has an existing valid session and is then suspended mid-session, **When** they make the next authenticated request, **Then** the request is refused with the same `account_suspended` code and the session is invalidated.
3. **Given** a super admin lifts the suspension, **When** the lift is recorded, **Then** the user can log in again on their next attempt and an audit-chain entry records the lift, the lifter's identity, and the lift reason.
4. **Given** the system applies an automatic suspension, **When** the suspension is recorded, **Then** the user is notified through the user-notification channel (UPD-042) — they are not left guessing why login fails.

---

### User Story 4 — Super admin reviews suspension queue (Priority: P2)

A super admin opens the abuse-prevention admin surface and reviews recent automatic suspensions for false positives.

**Why this priority**: Auto-suspension is high-precision but not perfect; legitimate users will occasionally trip a rule (e.g., a tester exercising the system, a NAT'd office issuing many simultaneous signups). The queue gives operations a fast path to lift mistaken suspensions and to tune thresholds. P2 because the system functions without it (manual lift via API works); the queue is an ergonomics layer.

**Independent Test**: A super admin opens `/admin/security/suspensions`. Sees the list of pending suspensions with reason, evidence summary, suspended_at, and a Lift button. The admin clicks Lift on one item, supplies a reason, and confirms. The user is unsuspended and notified. Audit chain entry recorded.

**Acceptance Scenarios**:

1. **Given** a super admin opens the suspension queue, **When** the queue renders, **Then** it lists active suspensions with the reason code, an evidence summary, `suspended_at`, and `suspended_by` (system / super_admin / tenant_admin).
2. **Given** a super admin clicks Lift on a row, supplies a reason, and confirms, **When** the lift is recorded, **Then** the suspension's `lifted_at` / `lifted_by_user_id` / `lift_reason` columns are populated, the user receives a notification, and an audit-chain entry records the lift.
3. **Given** the queue contains both system-applied and super-admin-applied suspensions, **When** the queue renders, **Then** the two sources are visually distinguished so the admin can prioritise human-applied vs. automated cases.

---

### User Story 5 — Cost-mining attempt blocked by Free hard cap (Priority: P1)

A bot creates a Free workspace and attempts to use it as a free LLM proxy by running many small executions or by selecting a premium model for a long-running operation. The platform's plan-defined caps refuse the abuse before it spends platform money.

**Why this priority**: Free-tier cost mining is the highest-cost abuse vector for the SaaS public tenant — every minute of an unbounded Free workspace is platform expense. P1 because without these caps the public tenant is economically unviable.

**Independent Test**: A Free user creates a workspace and runs N executions. The 100th execution in the calendar month is refused with a clear quota-exceeded error. Separately, the Free user attempts to invoke a premium model: the request is refused with a model-tier-not-allowed error. Separately, an execution that runs longer than the Free plan's max execution time is auto-terminated with a clear termination reason logged.

**Acceptance Scenarios**:

1. **Given** the Free plan defines `monthly_execution_cap=100`, **When** a Free workspace user runs the 101st execution in a calendar month, **Then** the runtime refuses with a quota-exceeded surface (per UPD-047) and an audit-chain entry records the cap.
2. **Given** the Free plan defines `allowed_model_tier='cheap_only'`, **When** a Free workspace agent attempts to invoke a non-cheap model, **Then** the model-router refuses with a clear error and the tool gateway records the refusal.
3. **Given** the Free plan defines `max_execution_time_seconds=300`, **When** an execution exceeds 300 seconds of wall time, **Then** the runtime auto-terminates the execution and records the termination reason as the time cap.
4. **Given** the Free plan defines `max_reasoning_depth=5` (or equivalent), **When** the reasoning engine would exceed the depth, **Then** the engine refuses to recurse and surfaces the limit to the caller.
5. **Given** any of the above caps fires, **When** observed, **Then** the cap-applied event is queryable by the admin so cost-protection effectiveness is auditable.

---

### Edge Cases

- **Velocity threshold tuned too tight**: a legitimate enterprise office NAT issues 6 signup requests in an hour and gets blocked. Mitigation: thresholds are tunable; an IP allowlist for trusted NATs is supported; threshold breach for a previously-allowlisted IP raises an admin notification rather than blocking.
- **Disposable-email list false positive**: a legitimate organisation's domain (e.g., a small SaaS using a catch-all) appears on the upstream blocklist by mistake. Mitigation: super-admin per-domain override list takes precedence over the upstream list.
- **Transient suspension on benign pattern**: a tester legitimately creates 10 accounts to exercise the signup flow. Mitigation: short-duration auto-suspension (e.g., 1 hour) with auto-lift, escalating to a longer or human-review-required suspension only on repeats.
- **Geo-block too aggressive**: enabling geo-block accidentally rejects legitimate global users. Mitigation: geo-block is opt-in (default off); per-country lists are explicit allow OR explicit deny and never both at the same time; admin is warned when enabling.
- **Fraud-scoring API unavailable**: the external scoring service is down or rate-limiting. Mitigation: fraud-scoring failures (timeout, 5xx) MUST NOT block legitimate users; the system degrades to velocity rules + CAPTCHA + disposable-email checks.
- **CAPTCHA bypass attempt via replayed token**: an attacker replays a prior CAPTCHA solve. Mitigation: CAPTCHA verification refuses replayed tokens via single-use validation against the provider.
- **Model-tier check evaded by direct API call**: a Free user attempts to bypass the UI and call the runtime directly with a premium model. Mitigation: the model-router enforces the tier at the API layer; UI-only enforcement is a security violation per the existing model-router contract.
- **Suspension applied to a user mid-execution**: the user has an in-flight execution when a suspension lands. Mitigation: in-flight executions are allowed to complete (consistent with the maintenance-mode rule from UPD-025); new executions are refused.
- **Disposable-email signup that was successfully completed before the domain was added to the blocklist**: a previously-good domain is later flagged. Mitigation: existing accounts are NOT retroactively suspended on the basis of a domain blocklist update; the blocklist applies only to new signups. (Manual super-admin suspension can apply to existing accounts when warranted.)
- **An auto-suspension fires against a super admin or a tenant-admin role**: privileged users cannot be locked out by automated rules. Mitigation: auto-suspension rules MUST exempt the platform-staff and tenant-admin roles; only super-admin manual action can suspend a privileged user.

---

## Requirements *(mandatory)*

### Functional Requirements

**Velocity rules**

- **FR-742**: The system MUST track signup-attempt counters keyed on at least three dimensions: source IP, source ASN (Autonomous System Number), and email domain. Counters MUST be additive across attempts within their rolling window.
- **FR-742.1**: When a counter reaches its configured threshold, the next attempt within the rolling window MUST be refused with HTTP 429 and a `Retry-After` header indicating the seconds remaining in the window.
- **FR-742.2**: All thresholds (per-IP-hour, per-ASN-hour, per-email-domain-day) MUST be tunable by a super admin without a redeploy; threshold changes MUST take effect within 30 seconds of save.
- **FR-742.3**: Failed signup attempts MUST count against the same counter as successful attempts — the counter measures attempt rate, not outcomes.
- **FR-742.4**: Every threshold breach MUST emit an audit-chain entry with the breached counter key, the threshold value, the rolling-window start, and the actor identity (anonymous IP/ASN before signup completes).
- **FR-742.5**: A super-admin-managed allowlist MUST exempt specific IPs (or CIDR ranges) and specific email domains from velocity counting; allowlist entries MUST be auditable.

**Disposable-email detection**

- **FR-743**: The system MUST refuse signup attempts whose email-address domain appears on a curated disposable-email blocklist before any verification email is sent.
- **FR-743.1**: The disposable-email list MUST be refreshable by a scheduled job from an upstream source (the public `disposable-email-domains` GitHub project is the canonical seed; alternatives are acceptable so long as the list is curated and updateable).
- **FR-743.2**: A super admin MUST be able to add per-domain overrides that take precedence over the upstream list (both adding to and subtracting from the effective blocklist).
- **FR-743.3**: Every disposable-email refusal MUST emit an audit-chain entry with the matched domain and the list version at refusal time. The refused email itself MAY be hashed or redacted in the audit entry consistent with privacy rules.
- **FR-743.4**: The disposable-email check MUST execute before any outbound mail is enqueued — the verification email is never sent to a refused address.

**Account suspension**

- **FR-744**: The system MUST persist account-suspension records with at least: target user, target tenant, suspension reason code, evidence summary, applied-at timestamp, applied-by identity (system / super_admin / tenant_admin), lifted-at timestamp (nullable), lifted-by identity (nullable), and lift reason (nullable).
- **FR-744.1**: A user with an active (non-lifted) suspension MUST NOT be issued a new authentication token, regardless of credential validity. Existing tokens / sessions MUST be invalidated on the user's next request.
- **FR-744.2**: Auto-suspension MUST trigger on at least these abuse patterns: (a) a configurable cost burn-rate threshold breach despite hard caps, (b) repeated velocity-rule hits within a configurable window, (c) a fraud-scoring callback returning a "suspend" verdict (when fraud-scoring is enabled).
- **FR-744.3**: Auto-suspension MUST NOT apply to users in privileged roles (platform-staff, tenant-admin); only manual super-admin action can suspend a privileged user.
- **FR-744.4**: A super admin MUST be able to lift a suspension via an admin endpoint, supplying a reason. Lift records the lifter identity and reason and notifies the user via the UPD-042 user-notification channel.
- **FR-744.5**: A user with an active suspension attempting login MUST receive a refusal whose code identifies suspension as the reason and whose body includes an appeal contact route. The refusal MUST NOT be indistinguishable from a generic credential failure.

**CAPTCHA**

- **FR-745**: The signup endpoint MUST support an optional CAPTCHA verification step; the provider implementation is pluggable (Cloudflare Turnstile and hCaptcha both acceptable). CAPTCHA MUST be off by default.
- **FR-745.1**: A super admin MUST be able to flip CAPTCHA on without a redeploy. The CAPTCHA toggle MUST take effect within 30 seconds of save.
- **FR-745.2**: CAPTCHA verification MUST refuse replayed tokens — each token validates exactly once.
- **FR-745.3**: When CAPTCHA is enabled, the signup UI MUST surface the challenge before the user can submit; a missing or failed CAPTCHA MUST be refused with a clear, accessible error message.

**Geo-blocking**

- **FR-746**: The system MUST support optional per-country geo-blocking for signup attempts, off by default. A super admin MUST be able to switch the mode to either "deny-list" (block listed countries) or "allow-list" (allow only listed countries) — the two modes are mutually exclusive.
- **FR-746.1**: When geo-blocking is enabled, blocked-country signup attempts MUST be refused with a clear error and an audit-chain entry recording the resolved country code, the source IP, and the geo-block rule that fired.
- **FR-746.2**: Geo resolution MUST degrade gracefully when the geo-IP source is unavailable — failure to resolve MUST NOT block legitimate signups; the failure MUST be logged.

**Fraud scoring**

- **FR-747**: The system MUST support optional pluggable fraud-scoring at signup. The integration is off by default and the implementation accepts at least two upstream providers (e.g., MaxMind minFraud, Sift) interchangeably via a common adapter.
- **FR-747.1**: Fraud-scoring failures (timeouts, 5xx, network errors) MUST NOT block signups — the system degrades to velocity + disposable-email + CAPTCHA only.
- **FR-747.2**: A "suspend" verdict from the fraud-scoring callback MUST trigger an auto-suspension as documented under FR-744.2; a "review" verdict MUST emit an admin notification but not auto-suspend.

**Free-tier runtime cost protection**

- **FR-748**: The runtime MUST refuse model invocations that exceed the executing workspace's plan-defined `allowed_model_tier`. Refusal happens at the model-router level; UI-only enforcement is insufficient.
- **FR-748.1**: The runtime MUST auto-terminate executions that exceed the executing workspace's plan-defined `max_execution_time_seconds`. The terminated execution's status surfaces the time cap as the termination reason.
- **FR-748.2**: The reasoning engine MUST refuse to expand reasoning beyond the plan-defined `max_reasoning_depth`; the refusal surfaces a clear limit error to the caller.
- **FR-748.3**: New executions MUST be refused when the workspace has reached its plan-defined hard execution cap (per UPD-047). The refusal surfaces the cap value, the current count, and the reset-at timestamp.
- **FR-748.4**: Every cap-fired event (model-tier, time, depth, hard cap) MUST be queryable by the workspace owner and the super admin so cost-protection effectiveness is auditable.

**Admin surface**

- **FR-749**: A super admin MUST have access to a `/admin/security/*` UI surface that exposes (a) current threshold settings with edit affordances, (b) the suspension queue with lift action, (c) the disposable-email override list with add/remove affordances, and (d) the geo-block configuration.
- **FR-749.1**: Every admin-side change to threshold settings, override lists, geo-block configuration, or suspension state MUST emit an audit-chain entry with the prior + new value, the actor identity, and a timestamp.
- **FR-749.2**: The admin surface MUST surface telemetry charts at least once-per-tunable-knob: refusals per minute by reason (velocity / disposable / geo / fraud / cap), suspension counts by source (system / human), and cap-fired counts by cap type.

**Cross-cutting**

- **FR-750**: All abuse-prevention actions (counter increments, refusals, suspensions, lifts, list refreshes, threshold changes) MUST be observable through the existing audit-chain machinery and through the structured-logging surface; no abuse-prevention decision MUST be silent.

### Key Entities *(include if feature involves data)*

- **Velocity counter**: an additive counter keyed on a (dimension, key, rolling-window-start) triple where dimension is one of `ip` / `asn` / `email_domain` and key is the concrete value (`1.2.3.4`, `AS12345`, `example.com`). Carries the current value and decrements / rolls forward as the window advances.
- **Disposable-email blocklist entry**: a domain plus the source it was learned from plus the timestamp it was last refreshed. Per-domain super-admin overrides ride alongside as a separate list.
- **Account suspension**: a record naming the target user and tenant, the reason code, an evidence summary (free-form JSON for the auto-suspension path; reviewer notes for the manual path), applied-at + applied-by, and lifted-at + lifted-by + lift-reason (nullable).
- **Abuse-prevention setting**: a key-value pair representing a tunable knob (`velocity_per_ip_hour`, `captcha_enabled`, `geo_block_mode`, `fraud_scoring_provider`, `disposable_email_blocking`, etc.). Each change is audited.
- **Plan caps (extended attributes on the existing Plan from UPD-047)**: `allowed_model_tier`, `max_execution_time_seconds`, `max_reasoning_depth`, `monthly_execution_cap`. These are not introduced by this feature — they are referenced by it; the runtime enforcement is what this feature wires.
- **Audit-chain entry**: tamper-evident log entry recording each abuse-prevention decision (refusal, suspension, lift, threshold change, list refresh, cap-fired) with actor + timestamp + before/after state.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of signup attempts above the per-IP-hour threshold are refused with HTTP 429, measured over the rolling window.
- **SC-002**: 0 disposable-email-domain signup attempts complete the verification path (no verification email sent to an address whose domain is on the effective blocklist), measured by mail-audit + signup-audit cross-reference.
- **SC-003**: 100% of authentication attempts from suspended users are refused with the `account_suspended` code; 0% leak through as generic 401.
- **SC-004**: Suspended-user notification reaches the user's UPD-042 inbox within 60 seconds at the 95th percentile of the suspension being applied.
- **SC-005**: Free-tier cost protection caps fire within ≤1 execution of the configured limit (the 101st execution is refused, not the 110th); the time cap terminates an execution within ≤10 seconds of the configured `max_execution_time_seconds`.
- **SC-006**: When the fraud-scoring upstream is unavailable, signup latency MUST NOT exceed the no-fraud-scoring baseline by more than 1 second at the 95th percentile (graceful degradation, no synchronous failure cascade).
- **SC-007**: 100% of admin-surface threshold changes / override-list edits / geo-policy edits / suspension lifts emit a corresponding audit-chain entry; the count of admin actions equals the count of audit entries on the same key set, verified by a daily reconciliation report.
- **SC-008**: When an IP-allowlisted enterprise NAT issues 6 signups in an hour, 0 of those 6 are refused — the allowlist is honoured.
- **SC-009**: J26 — the Abuse Prevention end-to-end journey covering all five user stories — passes on every CI run.

---

## Assumptions

- **UPD-046 / UPD-047 / UPD-048 are merged.** Tenant kind, plan caps, and the public default-tenant signup flow are present on `main`. This feature consumes them; it does not redefine them.
- **UPD-024 audit chain is in place.** Tamper-evident audit logging is the canonical mechanism for recording abuse-prevention decisions; this feature emits new entry kinds but does not redefine the chain.
- **UPD-042 user notifications are in place.** Suspension notifications are delivered via the existing user-inbox channel; this feature does not redesign it.
- **UPD-040 Vault is in place.** CAPTCHA provider secrets and fraud-scoring API keys are resolved via the existing `SecretProvider` per constitutional rule 39 — never read from environment variables in business logic.
- **The existing UPD-037 signup rate limiter (5/IP/hour, 3/email/24h) remains active.** The new velocity rules from this feature stack on top — they are NOT a replacement. The existing cap is the outer gate; the new cap is the configurable, finer-grained inner gate that an admin can tune.
- **Migration number 109 is taken by `109_marketplace_reviewer_assign` (PR #135).** This refresh's migration is `110_abuse_prevention` (or higher if other work lands first).
- **Bounded-context module path is `apps/control-plane/src/platform/security/abuse_prevention/`** per the user input. The prior-pass branch `100-upd-050-abuse` used `security_abuse/` (no nested subpackage) — that path is rejected here in favour of the user input's nested layout. If prior-pass code is later cherry-picked, files must be moved.
- **GeoIP data source.** MaxMind GeoLite2 (free tier, license-key registered) is the assumed geo-IP source, mirroring how existing services in this repo resolve country codes. Operators may swap to ip-api.com or a self-hosted MaxMind copy; the adapter pattern keeps this swappable.
- **Fraud-scoring providers.** MaxMind minFraud and Sift are the two named providers in scope for the pluggable adapter. Both are commercial; the integration is off by default and operators activate one (or none) by setting the `fraud_scoring_provider` setting and registering the credential in Vault.
- **Privileged-role exemption.** Auto-suspension never applies to platform-staff or tenant-admin roles. Manual super-admin action remains the only path to suspend a privileged user. This is encoded as a hard rule in the auto-suspension service.
- **Per-tenant scope.** Velocity, disposable-email, and geo-block all apply specifically to the public default tenant's signup surface (UPD-048). Enterprise tenants do not use this signup surface; this feature does not change their flow.
- **Allowlist tooling is shared with UPD-037's existing allowlist (if present)** rather than introducing a parallel mechanism. If UPD-037 does not have an IP allowlist, this feature creates one; either way, there is a single platform-wide allowlist surface, not two.
