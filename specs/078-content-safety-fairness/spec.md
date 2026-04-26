# Feature Specification: Content Safety and Fairness

**Feature Branch**: `078-content-safety-fairness`
**Created**: 2026-04-26
**Status**: Draft
**Input**: User description: "Integrate content moderation for agent outputs (toxicity, hate speech, violence/self-harm, sexually explicit, PII leakage), add bias and fairness evaluation metrics, and enforce consent/disclosure on first-time agent interactions. Provider-agnostic moderation (OpenAI Moderation, Anthropic safety, Google Perspective, self-hosted classifier). Per-workspace moderation policies. Fairness scorer for demographic parity, equal opportunity, calibration. FRs: FR-508, FR-509, FR-510."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Workspace admin configures content moderation and unsafe agent output is blocked, redacted, or flagged (Priority: P1)

A workspace administrator turns on content moderation for their workspace. They pick which categories to enforce (toxicity, hate speech, violence/self-harm, sexually explicit, PII leakage), set a threshold per category, and pick the action when a category triggers (block — refuse to deliver and surface a generic safe message; redact — replace the offending fragment with a safe placeholder before delivery; flag — deliver but log the event for review). When any agent in that workspace produces output that crosses one of those thresholds, the platform enforces the configured action before the output reaches the user, the calling agent, or any external integration. Every triggered event is recorded with category, score, action, and full provenance for after-the-fact audit.

**Why this priority**: Content moderation is the single biggest gap that prevents the platform from being deployed in customer-facing or regulated contexts. Without it, every output is a liability — the platform cannot ship to enterprise customers regardless of how good its agents are. P1 because it is the necessary safety floor for everything else.

**Independent Test**: Configure a workspace policy with `block` action on `toxicity` at threshold 0.8; force an agent in that workspace to produce a clearly toxic output via a deterministic test fixture; verify (1) the user receives a safe replacement message rather than the toxic content, (2) a moderation event is recorded with the triggered category, score, and action, (3) the original toxic content is preserved in the audit chain but not delivered, (4) downstream consumers (other agents, webhooks, alerts) also do not receive the toxic content. Repeat with `redact` and `flag` actions to verify per-action behaviour.

**Acceptance Scenarios**:

1. **Given** a workspace policy blocks toxicity at threshold 0.8, **When** an agent produces output that scores 0.9 for toxicity, **Then** the output is replaced with a safe message before reaching any consumer and a moderation event is recorded with `action_taken="block"` and the original score.
2. **Given** a workspace policy redacts PII at threshold 0.5, **When** an agent produces output containing an email address that scores 0.7, **Then** the email is replaced with a safe placeholder (e.g., `[REDACTED:email]`) before delivery and the event is recorded.
3. **Given** a workspace policy flags violence at threshold 0.6 with action `flag`, **When** an agent produces output that scores 0.7 for violence, **Then** the output is delivered unmodified, the event is recorded with `action_taken="flag"`, and the workspace operator is notified through their configured notification channel.
4. **Given** the configured moderation provider is unavailable, **When** an agent produces output, **Then** the platform applies a fail-safe behavior (configurable per workspace: `fail_closed` blocks all output until provider returns; `fail_open` delivers output and records a "provider unavailable" event) and surfaces an operator alert.
5. **Given** a workspace has not enabled content moderation, **When** an agent produces any output, **Then** behavior is unchanged (existing guardrail pipeline runs without the moderation stage) — backwards-compat for existing deployments.
6. **Given** a workspace admin updates the policy thresholds, **When** the next agent execution runs, **Then** the new thresholds are applied within 60 seconds without restarting the workspace.

---

### User Story 2 — User sees AI disclosure on first-time agent interaction (Priority: P1)

When a user (human end-user, not another agent) interacts with an agent for the first time on the platform, they see a non-dismissible disclosure stating that they are interacting with an AI system, what data may be processed, and a link to the workspace's AI use policy. The user must explicitly acknowledge the disclosure to proceed. The acknowledgement is recorded as a consent record so it persists across sessions; the user is not re-prompted on subsequent interactions unless the disclosure text changes materially. Machine consumers (other agents, A2A integrations) receive the same disclosure as response metadata so they can reason about it without a UI.

**Why this priority**: Required by EU AI Act Article 50 (transparency obligations) and similar regulations in California, Colorado, and other jurisdictions. Without it, the platform exposes customers to immediate compliance risk on every user interaction. P1 alongside US1 because moderation and disclosure together form the minimum responsible-AI posture; one without the other is insufficient.

**Independent Test**: Sign in as a user who has never interacted with any agent; start a conversation with any agent; verify (1) the disclosure appears non-dismissible until acknowledged, (2) a consent record is created in the privacy compliance subsystem, (3) subsequent interactions do not re-prompt, (4) when the disclosure text is materially updated by an admin, the next interaction re-prompts the user. Run the same flow via the API for a machine consumer and verify the disclosure appears in response metadata as a structured field.

**Acceptance Scenarios**:

1. **Given** a user has no prior consent record for AI interactions, **When** they start their first conversation with any agent, **Then** an AI disclosure appears, the user must explicitly acknowledge to proceed, and a consent record is created.
2. **Given** a user has previously acknowledged the AI disclosure (consent record exists and is current), **When** they start a new conversation with any agent, **Then** no disclosure is shown.
3. **Given** a workspace admin updates the disclosure text materially (not a typo fix), **When** any user with a stale consent record interacts next, **Then** the new disclosure appears and the user must re-acknowledge.
4. **Given** a machine consumer calls the agent via the API, **When** the user behind the call has no prior consent record, **Then** the response includes a structured disclosure field and the call is gated behind acknowledgement (per the consent service contract from feature 076).
5. **Given** a user explicitly revokes their AI-interaction consent via the privacy self-service endpoints, **When** they next attempt to start a conversation, **Then** the disclosure re-appears for re-acknowledgement before any agent can be reached.

---

### User Story 3 — Evaluator runs fairness evaluation across demographic groups (Priority: P2)

A data scientist (evaluator) selects an agent and a labelled test suite where each test case carries optional group-attribute metadata (e.g., gender, ethnicity, age bracket, country). They run the platform's fairness scorer, which computes per-group metrics — demographic parity, equal opportunity, and calibration — and produces a structured report showing which groups are within an acceptable fairness band and which are not. Test cases without group metadata are excluded from group-aware metrics but still contribute to overall accuracy. The report links each metric to the test cases driving the result so the evaluator can drill in.

**Why this priority**: Required by the same body of regulation as US2 (EU AI Act, US sector-specific rules) and increasingly demanded by enterprise procurement. Without fairness metrics, the platform cannot evidence non-discrimination claims. P2 because it does not block first deployment in the way US1/US2 do — fairness metrics are a quality-gate input rather than a real-time runtime guard.

**Independent Test**: Take a published agent, build a 100-case test suite with two group attributes (e.g., language=en|es, gender=m|f|nb); run the fairness scorer; verify the report includes per-group accuracy, demographic parity score, equal-opportunity score, calibration drift, and a top-line pass/fail vs. the configured fairness band. Run the same suite with all group metadata omitted and verify metrics computed only on aggregate accuracy.

**Acceptance Scenarios**:

1. **Given** a test suite where group metadata is present on every case, **When** the evaluator runs the fairness scorer, **Then** per-group metrics (demographic parity, equal opportunity, calibration) are computed and a structured report is produced.
2. **Given** a test suite where group metadata is missing on some cases, **When** the fairness scorer runs, **Then** group-aware metrics use only the cases with metadata; cases without metadata are still counted toward aggregate accuracy and the report flags coverage explicitly.
3. **Given** the configured fairness band is 0.10 (10 percentage points spread across groups for demographic parity), **When** scoring shows a 0.18 spread for one attribute, **Then** the report flags `passed=false` for that metric and identifies the failing groups.
4. **Given** an evaluator runs the fairness scorer twice on the same suite + agent, **When** the underlying agent revision is unchanged, **Then** the scores are deterministic (within an epsilon tolerance for stochastic scoring providers).

---

### User Story 4 — Trust officer gates certification on fairness pass (Priority: P2)

A trust reviewer is processing a certification request for an agent intended for high-impact uses (defined by the agent's declared categories). The certification workflow now requires a recent passing fairness evaluation in addition to the existing checks (model card, pre-screener, PIA when required). If a passing fairness evaluation does not exist for the agent revision under review, the certification is blocked with a clear, actionable reason — the evaluator can run the fairness scorer, the trust reviewer re-runs the certification flow, and the gate clears.

**Why this priority**: Closes the loop on US3 — fairness evaluation only delivers compliance value when it actually gates production deployment. P2 because the gate is conditional on use-case declarations, not blanket; agents with no fairness-relevant declared use can still ship without it.

**Independent Test**: Submit a certification request for an agent declared as `high_impact_use=true`; verify it is blocked with reason `fairness_evaluation_required`. Run a fairness evaluation that passes the configured band; resubmit certification; verify it proceeds. Submit a certification for an agent declared as `high_impact_use=false`; verify the fairness gate does not block.

**Acceptance Scenarios**:

1. **Given** an agent with `high_impact_use=true` and no recent passing fairness evaluation, **When** a trust reviewer requests certification, **Then** the request is blocked with reason `fairness_evaluation_required` and a hint pointing to the fairness scorer.
2. **Given** an agent with a passing fairness evaluation older than the configured staleness window (default 90 days), **When** certification is requested, **Then** the gate fires with reason `fairness_evaluation_stale`.
3. **Given** an agent revision changes materially (re-trained or re-prompted), **When** certification is re-requested, **Then** the prior fairness evaluation does not satisfy the gate and a fresh evaluation against the new revision is required.
4. **Given** an agent with `high_impact_use=false`, **When** certification is requested, **Then** the fairness gate does not block (existing certification gates apply normally).

---

### User Story 5 — Operator views moderation event log and aggregates (Priority: P3)

A platform operator (or workspace admin scoped to their workspace) views a chronological log of every content-moderation event produced by their agents: which execution triggered it, which categories triggered, what scores were observed, and what action was taken. They can filter by category, action, agent, time range. They can also view per-workspace aggregates (events per category per day, top offending agents, action breakdown) so they can decide whether to tune thresholds, retire an agent, or escalate to compliance.

**Why this priority**: Operational visibility for ongoing tuning and incident response. Without it, the moderation pipeline runs as a black box and operators cannot tell whether thresholds are right or whether an agent is regressing. P3 because the underlying audit trail (US1) is already there as a database-of-record; the visibility layer is incremental on top.

**Independent Test**: Trigger 20 moderation events across 4 categories and 3 actions over 1 hour; open the moderation event log filtered by workspace; verify all 20 appear with correct fields; apply category and action filters and verify counts; view the aggregated dashboard and verify per-day per-category counts match.

**Acceptance Scenarios**:

1. **Given** a workspace has logged 20 moderation events in the last hour, **When** the workspace admin opens the moderation event log, **Then** all 20 events appear with execution id, agent, categories triggered, scores, and action taken.
2. **Given** a platform operator filters the log by `category=toxicity` and `action=block`, **When** the filter is applied, **Then** only events matching both criteria are returned.
3. **Given** a workspace admin attempts to view events from a different workspace, **When** the request is made, **Then** the request is denied with a 403 (workspace-scope enforcement, no information leakage).
4. **Given** an operator opens the per-workspace aggregate view, **When** the time range is set to last 7 days, **Then** counts per category, per agent, and per action are returned, and the totals reconcile with the raw event log.

---

### Edge Cases

- **Provider failure mode**: When the configured moderation provider is unreachable, the workspace's `provider_failure_action` (default `fail_closed` for safety; alternative `fail_open` for permissive availability) determines whether outputs are blocked or delivered with an event marker. Operators are alerted on every failure.
- **Provider disagreement**: When two providers are configured (primary + fallback), and they return materially different verdicts, the workspace's tie-break rule (`max_score`, `min_score`, `primary_only`) decides; the discrepancy is recorded.
- **Latency budget**: Moderation calls are bounded by a per-call timeout (default 2s). On timeout the provider failure mode applies. Cumulative moderation latency MUST NOT exceed a per-execution budget (configurable, default 5s) — beyond which the execution times out gracefully rather than hanging.
- **Cost cap**: Each provider call has an associated cost. Per-workspace monthly cost caps prevent runaway moderation spend; when the cap is reached the provider failure mode applies and operators are alerted.
- **Self-hosted classifier fallback**: When all external providers are configured for `fail_open` but a self-hosted classifier is also configured, the platform always falls back to the self-hosted classifier before applying `fail_open`, so the safety floor is preserved even during external-provider outages.
- **Multilingual content**: Moderation must handle multilingual agent outputs. Providers without sufficient language coverage are flagged at workspace setup; operators can pin specific providers per language.
- **False positives on technical content**: Technical content (security writeups, medical literature, code that mentions sensitive operations) can trip generic providers. Per-workspace allow-listing of categories per agent (or per agent capability) is supported so that, for example, a security-research agent is exempt from `violence` blocking but not from `pii` blocking.
- **Disclosure text changes**: A non-material change (typo, wording polish) does not invalidate existing consent records. A material change (new data category, new processing purpose, new third-party provider) does — versioned disclosure text and a change-flag mechanism on the privacy compliance subsystem govern when re-acknowledgement is required.
- **Test suite without group metadata**: Fairness scorer falls back to aggregate metrics only and the report flags coverage as `null` for group-aware metrics; the run is not blocked.
- **Group attribute with one group only**: Demographic parity and equal opportunity require at least two non-empty groups; the scorer reports `insufficient_groups` for that attribute and continues with the remaining attributes.
- **Imbalanced groups**: Very small groups (configurable minimum, default 5 cases) are excluded from group-aware metrics with a coverage warning rather than producing unreliable estimates.
- **Calibration metric availability**: Calibration requires probability outputs. Agents that output classifications without probabilities have calibration reported as `unsupported`; the run still produces parity and equal-opportunity metrics where applicable.
- **Privacy of group attributes**: Group attributes are sensitive (often protected categories). The fairness subsystem treats them as PII, never logs them as labels, and stores them only as part of the test suite metadata governed by the privacy compliance subsystem.
- **Conflicting actions**: When multiple categories trigger on a single output and policies disagree (one redact, one block), the safer action wins (block > redact > flag).
- **Re-evaluation post-revocation**: When a user revokes consent (US2 acceptance scenario 5), in-flight conversations complete, but no new agent calls succeed for that user until re-acknowledgement.

## Requirements *(mandatory)*

### Functional Requirements

#### Content moderation

- **FR-001**: The platform MUST evaluate every agent output against a configured set of moderation categories — at minimum: toxicity, hate speech, violence/self-harm, sexually explicit content, and PII leakage — before the output reaches a user, another agent, or any external integration.
- **FR-002**: Moderation MUST run as a stage in the existing guardrail pipeline, after the agent has produced its output and before delivery; existing pre-output guardrails MUST continue to run unchanged.
- **FR-003**: Moderation MUST support multiple provider implementations with a provider-agnostic interface so workspace operators can choose between a hosted moderation service and a self-hosted classifier.
- **FR-004**: Each workspace MUST be able to define its own moderation policy: which categories to enforce, the score threshold per category, the action to take when a threshold is crossed (`block`, `redact`, `flag`), the primary provider, and an optional fallback provider.
- **FR-005**: When the configured action is `block`, the original content MUST NOT be delivered to any consumer; a safe replacement message MUST be delivered instead, while the original content is retained in the audit chain.
- **FR-006**: When the configured action is `redact`, the offending fragment MUST be replaced with a safe placeholder identifying the redacted category before delivery; the original content MUST be retained in the audit chain.
- **FR-007**: When the configured action is `flag`, the original content MUST be delivered unchanged but a moderation event MUST be recorded and the workspace's notification channels MUST be notified.
- **FR-008**: Every moderation evaluation MUST persist a moderation event with timestamp, execution reference, policy reference, triggered categories, per-category scores, and action taken — including non-triggering evaluations when configured for full audit (default: only triggering events).
- **FR-009**: Moderation policy changes MUST take effect within 60 seconds of being saved, without requiring an agent restart, deployment, or redeployment.
- **FR-010**: Moderation MUST honor a per-call timeout (default 2 seconds) and a cumulative per-execution latency budget (default 5 seconds); on timeout the workspace's `provider_failure_action` is applied (`fail_closed` blocks, `fail_open` delivers with an event marker).
- **FR-011**: Per-workspace monthly cost caps MUST be supported for paid moderation providers; when the cap is reached the provider failure mode applies and operators are alerted.
- **FR-012**: When two providers are configured (primary + fallback) and disagree materially on a category, the workspace's tie-break rule (`max_score`, `min_score`, `primary_only`) MUST decide and the discrepancy MUST be recorded.
- **FR-013**: Self-hosted classifier MUST be available as a fallback option that runs locally without an external API call, so the safety floor can be preserved during external-provider outages.
- **FR-014**: Moderation MUST handle multilingual agent outputs; per-workspace operators MUST be able to pin specific providers per language when default coverage is insufficient.
- **FR-015**: Per-workspace allow-listing MUST be supported so that designated agents (e.g., security-research) can be exempted from specific categories without disabling moderation entirely.
- **FR-016**: When multiple categories trigger on the same output and policies prescribe different actions, the safer action MUST win (`block` > `redact` > `flag`).

#### Disclosure and consent

- **FR-017**: First-time interactions between a user and ANY agent on the platform MUST present a non-dismissible AI disclosure stating that the user is interacting with an AI, what categories of data may be processed, and where the workspace's AI-use policy is documented.
- **FR-018**: The disclosure MUST be acknowledged explicitly by the user before any agent invocation can proceed; acknowledgement creates or updates a consent record in the platform's consent subsystem.
- **FR-019**: After the consent record is current, subsequent interactions MUST NOT re-prompt unless the disclosure text has changed materially since the last acknowledgement.
- **FR-020**: Workspace admins MUST be able to update the disclosure text and mark the change as material (re-prompt) or non-material (do not re-prompt); the platform MUST version the disclosure text and reference the version on each consent record.
- **FR-021**: Machine consumers (other agents, A2A integrations) MUST receive the disclosure as a structured field in response metadata so they can reason about consent obligations without a UI.
- **FR-022**: Consent revocation by the user MUST take effect on the next agent invocation: in-flight conversations complete, but no new agent calls succeed for that user until re-acknowledgement.

#### Fairness evaluation

- **FR-023**: The platform MUST provide a fairness scorer registered alongside existing evaluation scorers that computes per-group metrics — at minimum demographic parity, equal opportunity, and calibration — when group-attribute metadata is available on test cases.
- **FR-024**: Group-attribute metadata on test cases MUST be optional; runs without group metadata MUST still produce aggregate accuracy metrics and MUST flag group-aware metric coverage as `null` rather than failing the run.
- **FR-025**: Test cases lacking group metadata MUST be excluded from group-aware metrics for that attribute but MUST still contribute to the aggregate metrics; coverage statistics MUST be reported.
- **FR-026**: Groups with fewer than the configured minimum sample size (default 5 cases) MUST be excluded from group-aware metrics with a coverage warning, rather than producing unreliable estimates.
- **FR-027**: When an attribute has only one non-empty group, the scorer MUST report `insufficient_groups` for that attribute and continue scoring the remaining attributes.
- **FR-028**: Calibration MUST be reported as `unsupported` when the agent does not produce probability outputs; demographic parity and equal opportunity MUST still be computed where data permits.
- **FR-029**: The fairness scorer MUST produce a structured report identifying per-attribute, per-group results, the configured fairness band, and a top-line `passed`/`failed` per metric so reviewers can decide quickly.
- **FR-030**: The fairness scorer MUST be deterministic for deterministic agents — re-running on the same suite and same revision MUST produce identical scores within an epsilon tolerance.
- **FR-031**: Group-attribute values MUST be treated as sensitive PII, never logged as labels, and accessible only to the evaluator and the trust reviewer; storage and access MUST follow the privacy compliance subsystem's rules.

#### Certification gating

- **FR-032**: The agent certification workflow MUST consult fairness-evaluation history before approving certification for agents whose declared use is high-impact (declaration field on the agent's manifest).
- **FR-033**: Certification MUST be blocked with reason `fairness_evaluation_required` when no passing fairness evaluation exists for the agent revision under review.
- **FR-034**: Certification MUST be blocked with reason `fairness_evaluation_stale` when the most recent passing evaluation is older than the configurable staleness window (default 90 days).
- **FR-035**: A material agent revision MUST invalidate prior fairness evaluations; certification MUST require a fresh evaluation against the new revision.
- **FR-036**: Agents not declared as high-impact MUST NOT be blocked by the fairness gate; the existing certification path applies unchanged.

#### Audit, observability, and authorization

- **FR-037**: Moderation events, fairness evaluations, disclosure acknowledgements, and consent revocations MUST emit audit-chain entries via the platform's audit subsystem.
- **FR-038**: A moderation event log MUST be queryable by workspace, agent, category, action, and time range, scoped to the requesting user's authorization (workspace admins see only their workspace; platform operators see all).
- **FR-039**: Per-workspace aggregates of moderation events (events per category per day, top offending agents, action breakdown) MUST be available for ongoing tuning and incident response.
- **FR-040**: Cross-workspace access to moderation events or fairness evaluations MUST be denied for non-platform-admins, returning 403 without information leakage about the existence of other workspaces.
- **FR-041**: All moderation-provider API credentials MUST be stored via the platform's secrets-management mechanism, never in plaintext; credentials MUST never appear in logs.

### Key Entities *(include if feature involves data)*

- **Content moderation policy**: A workspace-scoped record binding categories to thresholds and actions, with a primary provider, optional fallback, tie-break rule, failure mode, allow-list of agents-per-category, and per-language provider pins.
- **Content moderation event**: A per-evaluation record carrying execution reference, policy reference, triggered categories, per-category scores, action taken, and timestamps. The original (pre-moderation) content is referenced via the audit chain rather than duplicated on the event.
- **Disclosure text version**: A workspace-versioned text + change flag (material vs. non-material) governing re-prompt behavior. Stored in the privacy compliance subsystem.
- **Consent record**: An entry in the privacy compliance subsystem (existing) that records a user's acknowledgement of the disclosure version. Already provided by feature 076; this feature consumes it rather than redefining.
- **Fairness evaluation**: A per-(agent, suite) record carrying per-attribute, per-group, per-metric scores, the configured fairness band, the pass/fail per metric, and evaluator identity. Linked to the agent revision so material revisions invalidate prior evaluations.
- **Group attribute**: A piece of test-case metadata identifying group membership (e.g., gender, language, age bracket). Treated as sensitive PII and governed by the privacy compliance subsystem.
- **Moderation provider**: A pluggable adapter exposing a uniform scoring interface across hosted services and self-hosted classifiers. Per-provider credentials and cost rates are stored separately.
- **Provider failure event**: A record of provider unavailability, timeout, or cost-cap exhaustion, used to drive operator alerts and retroactive policy review.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For workspaces with content moderation enabled, 100% of agent outputs pass through the moderation stage before delivery (no bypass paths).
- **SC-002**: When a category triggers `block`, 100% of attempts to deliver the original content to any consumer (user UI, downstream agent, webhook, alert) fail; consumers see only the safe replacement.
- **SC-003**: Moderation latency adds at most 500 ms p95 per output to a healthy provider, and at most 2 s p99 (the per-call timeout) including provider call.
- **SC-004**: Moderation policy changes are visible to running agents within 60 s of save in 100% of measurement intervals.
- **SC-005**: Provider unavailability is detected and the configured failure mode applied within 5 s; operators receive an alert within 1 minute.
- **SC-006**: First-time AI disclosure is presented to 100% of users at their first agent interaction; no agent invocation succeeds before acknowledgement is recorded.
- **SC-007**: After a material disclosure update, 100% of users with stale consent are re-prompted at their next interaction.
- **SC-008**: Fairness evaluations on a 100-case suite complete in under 5 minutes wall-clock for a typical agent (excluding the time to actually run the agent on each case).
- **SC-009**: Re-running a fairness evaluation on the same (suite, revision) pair produces identical scores within ±0.001 in 100% of measurement intervals.
- **SC-010**: Certification requests for agents declared as high-impact without a passing fairness evaluation are blocked with the correct reason 100% of the time.
- **SC-011**: Cross-workspace access attempts to moderation events or fairness evaluations are denied with 403 in 100% of measurement intervals; no logs leak the existence of other workspaces.
- **SC-012**: Self-hosted classifier fallback successfully scores 100% of outputs during a forced primary-provider outage in fault-injection tests, preserving the safety floor.
- **SC-013**: Group-attribute values never appear in observability labels (logs, metrics, traces) — verified by automated label-scan against the platform's PII inventory.

## Assumptions

- **Existing trust BC + guardrail pipeline**: The `trust/` bounded context already exists with a guardrail pipeline that processes agent outputs. This feature adds a moderation stage to that pipeline rather than rebuilding it.
- **Existing evaluation BC + scorer registry**: The `evaluation/` bounded context already exposes a scorer registry. This feature registers a new fairness scorer alongside existing ones (exact match, semantic, regex, JSON schema, trajectory, LLM judge).
- **Existing privacy compliance / consent subsystem (feature 076)**: The consent records, disclosure text versioning, and consent-required HTTP gating are already provided by feature 076. This feature consumes them; it does not redefine them.
- **Existing certification workflow**: The trust certification workflow already exists with multiple gates (model card, pre-screener, PIA when required). This feature adds a new fairness gate that fires only for high-impact agents.
- **Provider credentials**: Operators bring their own moderation-provider API keys (OpenAI, Anthropic, Google Perspective, etc.) and configure them at the deployment level; the platform itself does not provision them.
- **Fail-closed default**: The default `provider_failure_action` is `fail_closed` (block on provider failure). Operators who accept the availability tradeoff can explicitly switch to `fail_open` per workspace.
- **Default thresholds**: Initial default thresholds per category are conservative (favoring more events over fewer); workspaces tune them based on the moderation event log over time.
- **High-impact use declaration**: Agents declare high-impact use as part of their existing manifest; the certification workflow already reads this field for the PIA gate (feature 076), and the fairness gate reuses it.
- **Group-attribute taxonomy**: The platform does not prescribe a taxonomy of group attributes; evaluators choose their own attribute names and values per test suite. Privacy and i18n considerations apply.
- **Fairness band default**: Default fairness band is 0.10 (10 percentage points spread across groups for parity metrics); operators can tighten per workspace.
- **Calibration applicability**: Calibration is reported only when the agent produces probability outputs. Classification-only agents will see calibration as `unsupported`.
- **Disclosure text storage and i18n**: Disclosure text is stored versioned in the privacy compliance subsystem and supports i18n in the same way other user-facing strings do (feature 030 / UPD-030).
- **Audit chain availability**: The platform's audit chain (UPD-024) is available for compliance traceability; this feature emits to it but does not redefine it.
- **Backwards compatibility**: Workspaces that have not enabled content moderation see no behavior change; existing guardrail pipeline and evaluation scorers continue to work unchanged.
- **Notification integration**: When `flag` action triggers, the existing notifications subsystem (extended by feature 077) is responsible for delivery to operator channels; this feature emits the event and lets notifications dispatch.

## Dependencies

- **Existing trust bounded context**: This feature extends the guardrail pipeline; it must not regress existing pre-screener, certification, or contract surveillance behaviour.
- **Existing evaluation bounded context**: This feature registers a new scorer; it must not regress existing scorers or break the existing scorer registry contract.
- **Privacy compliance subsystem (feature 076)**: Required for consent records, disclosure text versioning, and the consent-required HTTP gating reused by this feature for first-time interaction enforcement.
- **Audit chain (UPD-024)**: Required for FR-037 audit emissions on every moderation event, fairness evaluation, disclosure acknowledgement, and consent revocation.
- **Secrets management (UPD-040 vault)**: Required for FR-041 storage of moderation-provider API credentials.
- **Notifications subsystem (feature 077 / UPD-009 baseline)**: Required for `flag`-action notifications to operator channels.
- **Model router (UPD-026 / feature 075)**: When a moderation provider is itself an LLM (e.g., the Anthropic safety model option), the call MUST go through the platform's model router rather than directly through a provider SDK; the model router enforces catalog and fallback policies.
- **Existing certification workflow**: Required for FR-032 to FR-036 fairness-gate integration; this feature adds a gate, it does not own the workflow.
