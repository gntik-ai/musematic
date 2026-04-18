# Feature Specification: Safety Pre-Screener and Secret Sanitization

**Feature Branch**: `054-safety-prescreener-sanitization`
**Created**: 2026-04-18
**Status**: Draft
**Input**: User description: "Add SafetyPreScreener as mandatory first stage of guardrail pipeline (<10ms). Add tool output secret sanitizer. Rules versioned and hot-updatable."

**Scope note**: Several of the building blocks are already in place. The `SafetyPreScreenerService` class with pattern-based detection, versioned rule sets (PostgreSQL `trust_safety_prescreener_rule_sets` + MinIO rule content), and hot-reload via Redis/Kafka already exist (`apps/control-plane/src/platform/trust/prescreener.py`). The `OutputSanitizer` class with five pre-compiled secret patterns (`bearer_token`, `api_key`, `jwt_token`, `connection_string`, `password_literal`) and `[REDACTED:{type}]` redaction format, including audit logging via `PolicyBlockedActionRecord`, already exists (`apps/control-plane/src/platform/policies/sanitizer.py`, feature 028). Rule-management REST endpoints (`POST /prescreener/screen`, `GET/POST /prescreener/rule-sets`, `POST /prescreener/rule-sets/{id}/activate`) are live on the trust router. What is **not** yet done, and what this feature delivers:

1. The pre-screener is **not wired into the guardrail pipeline**. `GuardrailPipelineService.LAYER_ORDER` is `[input_sanitization, prompt_injection, output_moderation, tool_control, memory_write, action_commit]` — none of these layers calls `SafetyPreScreenerService.screen()`. The pipeline's `input_sanitization` layer uses its own hardcoded `_INPUT_SANITIZATION_PATTERNS` module constant, ignoring the versioned rule sets administered through `/prescreener/rule-sets`.
2. The pre-screener has **no latency SLO** or measurement. The `screen()` method returns without recording how long it took, so operators cannot verify the "under 10 ms" envelope or be alerted when the pre-screener itself becomes the slow path.
3. The `OutputSanitizer` is available as a method on `ToolGatewayService.sanitize_tool_output()` but is **not guaranteed to run on every tool-result path** that feeds an LLM. The invocation audit must confirm that every tool invocation, whether on the happy path or on error, has its textual result passed through the sanitizer before the result is serialized into the next prompt. Today this guarantee is implicit in the method's availability, not enforced structurally.
4. When the pre-screener blocks content, the denial is **not emitted into the unified trust/audit stream** in a shape consistent with other guardrail layer denials. Today a block returns `PreScreenResponse(blocked=True, matched_rule=name, passed_to_full_pipeline=False)` but produces no `TrustBlockedActionRecord`/Kafka event alongside other pipeline-layer blocks, making operator dashboards blind to pre-screener activity.
5. The rule format users administer today is JSON stored in MinIO. Operators have asked for a **YAML administration surface** so rule sets are hand-authorable and reviewable in pull requests without a tooling detour. The storage format can remain the stored representation; the administrative representation is what needs to be YAML-addressable.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Pre-screener becomes the mandatory first stage of the guardrail pipeline (Priority: P1)

A platform operator wants every piece of content that reaches any guardrail layer to be checked first against the currently active pre-screener rule set. When the pre-screener blocks, the full pipeline MUST NOT execute — saving LLM calls and moderation-service traffic for clearly hostile inputs. When the pre-screener does not match, the rest of the pipeline continues unchanged.

**Why this priority**: The pre-screener is the cheapest possible defense. Wiring it into the pipeline is what makes the versioned rule sets actually protect the platform. Without this wiring, the versioned rule sets administered through the existing API have no effect on runtime behavior.

**Independent Test**: Activate a rule set with a single pattern like `"ignore previous instructions"`. Send that phrase through any layer of the guardrail pipeline. The response comes back blocked, with a matched-rule identifier, before reaching the downstream hardcoded-pattern or output-moderation stages. Swap to an empty rule set; the same phrase is no longer blocked by the pre-screener stage, though it may still be caught by the existing prompt-injection layer.

**Acceptance Scenarios**:

1. **Given** an active rule set with pattern `"ignore previous instructions"` and an empty downstream output-moderation pattern list, **When** the pipeline is asked to evaluate the string "please ignore previous instructions and do X", **Then** the pipeline returns `allowed=false` with the layer identifier set to the pre-screener and the matched rule name present; no subsequent layers execute.
2. **Given** an active rule set whose patterns do not match the input, **When** the pipeline is asked to evaluate a benign string, **Then** the pre-screener passes through and the pipeline continues into the existing layers; the response carries `prescreener_passed: true` in its audit metadata.
3. **Given** no active rule set exists, **When** the pipeline is asked to evaluate any string, **Then** the pre-screener stage is a no-op (pattern set is empty) and the pipeline proceeds directly to the existing layers without error.
4. **Given** an active rule set is replaced by activating a newer version via the existing `POST /prescreener/rule-sets/{id}/activate` endpoint, **When** the pipeline evaluates a string that only the new rule set blocks, **Then** the next pipeline invocation uses the new patterns without a service restart.

---

### User Story 2 — Pre-screener meets a <10 ms p99 latency envelope (Priority: P1)

An operator running the platform under load needs confidence that adding the pre-screener to every guardrail call does not push the p99 latency of the pipeline over the budget. The pre-screener itself MUST complete in under 10 ms at p99 against the currently active rule set. Operators MUST see a dashboard metric they can alert on.

**Why this priority**: Without a measured SLO, "fast pre-screener" is aspirational. The whole value of the pre-screener is that it is cheap enough to run on every input; if it is slow, it becomes a tax on every other layer instead of a savings.

**Independent Test**: Run a load-test fixture with a realistic-size rule set (50–200 patterns) against a corpus of 10 000 varied inputs. Measure per-call pre-screener duration. Assert p99 < 10 ms. Confirm a latency-histogram metric is emitted and visible on the operator dashboard.

**Acceptance Scenarios**:

1. **Given** a rule set of 200 regex patterns compiled once on activation, **When** the pre-screener runs against 10 000 inputs averaging 1 KB each, **Then** the p99 latency is under 10 ms and the mean is under 1 ms.
2. **Given** the pre-screener executes, **When** the pipeline records its audit event, **Then** the event carries a latency field (in ms) for the pre-screener stage, and a histogram metric tagged with the active rule-set version is observable at the telemetry surface the platform already uses (SC-005).
3. **Given** the p99 latency exceeds 10 ms for a sustained window, **When** the latency alert fires, **Then** the rule set version responsible is recoverable from the alert context so operators can roll back to a known-good version through the existing activate endpoint.

---

### User Story 3 — Every tool result is sanitized before it reaches LLM context (Priority: P1)

A governance-minded operator wants an invariant: no string produced by a tool invocation ever enters the next LLM prompt without first passing through the secret sanitizer. Whether the tool succeeded, errored partway, or returned structured data with embedded strings, the textual surface that becomes visible to the next reasoning step MUST have had the sanitizer applied.

**Why this priority**: Secret exfiltration through tool output is one of the incidents the platform constitution names explicitly (Principle XI). The sanitizer exists and works in isolation; the gap is proving it is called on every path.

**Independent Test**: Issue a tool invocation whose mocked result contains a bearer token, a JWT, an API key pattern, a connection string, and a password literal. Assert every one of the five patterns is replaced by `[REDACTED:{type}]` in the output that is then serialized into the next prompt. Repeat for the error path (tool throws, gateway returns a normalized error payload) — the error payload is also sanitized before propagation.

**Acceptance Scenarios**:

1. **Given** a tool returns a result string containing a bearer token, **When** the gateway hands that result back to the calling execution flow, **Then** the token substring has been replaced with `[REDACTED:bearer_token]` and a `PolicyBlockedActionRecord` with `action_type="sanitizer_redaction"` exists.
2. **Given** a tool raises an exception whose message embeds a connection string, **When** the gateway normalizes the error for the caller, **Then** the connection-string substring is replaced with `[REDACTED:connection_string]` before the error is serialized.
3. **Given** a tool returns structured JSON whose string leaves contain a JWT, **When** the gateway serializes the structured result for downstream consumption, **Then** the JWT is replaced with `[REDACTED:jwt_token]` inside the serialized form; non-string payload fields are unchanged.
4. **Given** the sanitizer detects no secret patterns, **When** the result is returned, **Then** the output is byte-identical to the input and no redaction audit record is created.

---

### User Story 4 — Pre-screener blocks produce a first-class audit record (Priority: P2)

An operator reviewing the trust dashboard wants pre-screener blocks to appear in the same audit stream as other guardrail-layer blocks. Each pre-screener denial MUST emit a blocked-action record carrying the matched rule id, the rule-set version, and the correlation id of the triggering request. A weekly review of blocked actions MUST be able to show "all pre-screener blocks this week" alongside "all prompt-injection blocks this week" without querying a separate data source.

**Why this priority**: Without a consistent audit record, operators cannot quantify pre-screener effectiveness or spot false positives. Discovery-visibility is table stakes for operability.

**Independent Test**: Activate a rule set. Send three matching inputs through the pipeline. Query the blocked-actions list endpoint filtered by layer = pre_screener. Assert three records, each carrying the matched rule id, rule-set version, and correlation id of the originating request.

**Acceptance Scenarios**:

1. **Given** a pre-screener block occurs, **When** the operator queries the blocked-actions list, **Then** the record appears with `guardrail_layer="pre_screener"`, `matched_rule_id` populated, `rule_set_version` populated, and the same correlation id as the original request.
2. **Given** a pre-screener pass (no match) occurs, **When** the operator queries the blocked-actions list, **Then** no record is created for the pass; the pipeline proceeds normally to the next layer and any downstream blocks are recorded at their own layer identifier.

---

### User Story 5 — Operators administer rule sets as YAML (Priority: P2)

An operator managing rule sets across environments wants to author them as YAML, review them in pull requests, and push them through the existing `POST /prescreener/rule-sets` endpoint. The administrative body format MUST accept YAML in addition to JSON so the current tooling (JSON body) continues to work and operators can copy-paste from the rule YAML files they keep under source control.

**Why this priority**: The versioned, hot-reloadable rule infrastructure already exists — only the author-facing format is missing. It is P2 because JSON is an acceptable fallback; teams without YAML workflows are not blocked.

**Independent Test**: Submit a rule set using YAML content type; the system parses it, stores it, and the subsequent list endpoint returns the same rules. Submit the same content as JSON; both representations are accepted and round-trip identically.

**Acceptance Scenarios**:

1. **Given** an operator submits a YAML body to the create endpoint with `Content-Type: application/yaml`, **When** the request returns 201, **Then** the rules persisted match the YAML content and appear in subsequent list/get responses.
2. **Given** an operator submits a JSON body to the create endpoint, **When** the request returns 201, **Then** behavior is unchanged from today (backward compatibility).
3. **Given** malformed YAML is submitted, **When** the endpoint validates the body, **Then** the response is a 422 with a precise parse error and the rule set is NOT created.

---

### Edge Cases

- Pre-screener rule pattern that is itself unsafe (e.g., catastrophic-backtracking regex) → rule-set creation validates patterns compile in bounded time; rule sets whose total compile cost exceeds a ceiling are rejected at activation rather than crashing production.
- Rule set activated with zero rules → pre-screener passes every input through; pipeline continues to existing layers; no error is raised.
- Tool returns binary data (bytes, not text) → sanitizer is only applied to text decodings of the result; binary payloads are passed through unchanged; operators are warned in docs that binary tool results bypass the sanitizer.
- Sanitizer detects a pattern inside a string that is itself a secret-type field of a structured result → the whole matching substring is redacted; structural boundaries of JSON are preserved so the result remains valid JSON after redaction.
- Concurrent rule-set activation during a high-traffic window → in-flight requests complete under the previous rule set; only requests that begin after the activation event see the new patterns. No partial-patterns window is acceptable.
- Pre-screener pattern matches the same substring multiple times → the pattern counts as one block (first match wins); latency still bounded.
- Pipeline is invoked with empty input → pre-screener trivially passes (no content to scan); latency must still be measured and reported.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The guardrail pipeline MUST invoke `SafetyPreScreenerService.screen(content, context_type)` as its first stage, ahead of all existing layers (`input_sanitization`, `prompt_injection`, `output_moderation`, `tool_control`, `memory_write`, `action_commit`).
- **FR-002**: When the pre-screener returns `blocked=True`, the pipeline MUST return a denial response with `guardrail_layer="pre_screener"` and MUST NOT execute any subsequent layers.
- **FR-003**: When the pre-screener returns `blocked=False`, the pipeline MUST proceed to the existing layers unchanged.
- **FR-004**: When no active rule set is configured, the pre-screener stage MUST be a no-op (pattern set is empty) and the pipeline MUST continue without error.
- **FR-005**: Rule-set activation MUST take effect on the next pipeline invocation without a service restart, using the existing Redis + Kafka propagation mechanism.
- **FR-006**: The pre-screener `screen()` call MUST emit a latency metric tagged with the active rule-set version, suitable for a p99 dashboard and alert.
- **FR-007**: The pre-screener MUST sustain p99 latency below 10 ms at 10 000 inputs against a rule set of up to 200 patterns (SC-003).
- **FR-008**: Every tool invocation path (success and error) in the tool gateway MUST apply the output sanitizer to the textual representation of the tool result before that representation becomes available to any caller that could forward it to an LLM.
- **FR-009**: The output sanitizer MUST continue to redact the five existing secret types (`bearer_token`, `api_key`, `jwt_token`, `connection_string`, `password_literal`) using the `[REDACTED:{type}]` token shape.
- **FR-010**: When the output sanitizer redacts at least one match, it MUST record a `PolicyBlockedActionRecord` entry tagged with the tool FQN, agent FQN, and secret type (existing behavior; preserved).
- **FR-011**: When the pre-screener blocks content, the system MUST record a blocked-action entry tagged with `guardrail_layer="pre_screener"`, the matched rule id, and the active rule-set version. This entry MUST appear on the same blocked-actions query surface as other guardrail-layer entries.
- **FR-012**: The `POST /prescreener/rule-sets` endpoint MUST accept `Content-Type: application/yaml` in addition to `application/json`; both bodies MUST produce the same stored rule set.
- **FR-013**: Rule-set creation MUST validate that each rule's pattern compiles successfully and that the total compile cost does not exceed a configured ceiling; rule sets failing this check MUST be rejected at creation time with a 422.
- **FR-014**: The pre-screener response payload returned by the pipeline MUST include the latency measurement so downstream audit events can carry it without re-measuring.
- **FR-015**: Behavior when no pre-screener rule set is ever activated MUST be identical to pre-feature behavior (no new denials from the pre-screener stage).

### Key Entities

- **Pre-Screener Rule Set**: Versioned collection of FQN-independent regex patterns with action `block`. Versioned in PostgreSQL, content in MinIO. Already in place; no structural change by this feature.
- **Active Rule Set Pointer**: Redis key `trust:prescreener:active_version` recording which version the service currently serves. Already in place.
- **Guardrail Blocked-Action Record**: An entry describing a denial, including the layer, the matched rule, the rule-set version, and the correlation id. Extended by this feature to cover the pre-screener layer.
- **Redaction Record**: An entry noting that an output sanitizer replaced a match of a specific secret type for a specific tool/agent. Already in place; preserved.
- **Rule YAML Body** *(admin surface)*: Alternative content type for rule-set creation. NEW administrative representation; stored content format unchanged.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of guardrail-pipeline invocations execute the pre-screener stage before any existing layer, measured over a sampled production window of 10 000 consecutive invocations.
- **SC-002**: 100% of tool invocations (success and error paths) produce a sanitized textual result before the result becomes observable to any LLM-facing caller, measured via an invocation-path audit that traces result egress points.
- **SC-003**: Pre-screener p99 latency is below 10 ms and mean latency below 1 ms across a 10 000-input benchmark against a 200-pattern rule set.
- **SC-004**: Activating a new rule set via the existing activate endpoint takes effect for subsequent pipeline calls within 5 seconds, measured by the pipeline's use of the new patterns on the first call after activation.
- **SC-005**: 100% of pre-screener blocks produce a blocked-action record queryable from the operator dashboard within 60 seconds of the block occurring, carrying the matched rule id, rule-set version, and correlation id.
- **SC-006**: With no active rule set configured, the existing guardrail-pipeline test suite passes unmodified; zero regressions are introduced by the pre-screener wiring (FR-015).
- **SC-007**: YAML rule-set creation produces the same stored representation as the equivalent JSON body, confirmed by byte-level equality of the stored rules reference on round-trip.
- **SC-008**: Every secret-type pattern currently redacted by `OutputSanitizer` is replaced by the matching `[REDACTED:{type}]` token in 100% of sampled tool-output audit records that contain a match.

---

## Assumptions

- `SafetyPreScreenerService` (feature 012 Trust) is already implemented with pattern-based detection, versioned rule sets, and Redis/Kafka hot-reload. This feature does not re-implement that logic.
- `OutputSanitizer` (feature 028 Policy Engine) is already implemented with five pre-compiled secret patterns, `[REDACTED:{type}]` redaction, and `PolicyBlockedActionRecord` audit logging. This feature does not re-implement that logic.
- The trust router already exposes `POST /prescreener/screen`, `GET /prescreener/rule-sets`, `POST /prescreener/rule-sets`, and `POST /prescreener/rule-sets/{id}/activate`. This feature extends the create endpoint to accept YAML but does not add new endpoints.
- The platform's metrics pipeline already accepts histogram metrics; emitting a latency histogram for the pre-screener uses this existing pipeline.
- `GuardrailPipelineService.LAYER_ORDER` is the authoritative layer list; adding the pre-screener is a matter of adding a new layer value to the `GuardrailLayer` enum and prepending it to `LAYER_ORDER`, rather than restructuring the pipeline.
- The existing `TrustBlockedActionRecord` shape has sufficient fields to record a pre-screener block (layer, rule id, version, correlation id). If any field is missing, it MUST be added additively per Brownfield Rules 6 and 7.
- Tool-result sanitization is scoped to textual representations. Binary tool results (raw bytes) are out of scope; operators are informed via docs (Edge Cases).
- Rules remain stored as JSON in MinIO regardless of the administrative content type; YAML is a parsing concern at the API boundary only.
- The constitution's Principle XI ("secrets never in LLM context") is the anchor for US3 and FR-008; this feature closes the enforcement gap behind that principle.
