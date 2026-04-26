# Research: Content Safety and Fairness

**Feature**: 078-content-safety-fairness
**Date**: 2026-04-26
**Phase**: 0 — Outline & Research

This document records the design decisions made before writing data-model.md and the contracts.

---

## D-001 — Extend `trust/` and `evaluation/` BCs vs. introduce a new BC

**Decision**: Extend the existing `trust/` and `evaluation/` bounded contexts. No new BC.

**Rationale**: Content moderation is a guardrail concern (trust BC owns guardrails). Fairness evaluation is a scoring concern (evaluation BC owns scorers). The constitution's "Critical Reminder #27" says "do not recreate existing functionality" — both trust and evaluation already have the right shape. Introducing a parallel BC (e.g., `responsible_ai/`) would split ownership of guardrails and scorers and confuse downstream consumers.

**Alternatives considered**:
- New `responsible_ai/` BC: rejected — duplicates existing BC ownership.
- Per-feature BCs (`content_moderation/`, `fairness/`): rejected — micro-BC granularity violates project conventions.

---

## D-002 — Insertion point in `guardrail_pipeline.py`

**Decision**: Use the existing `GuardrailLayer.output_moderation` slot in `LAYER_ORDER`. The existing regex `_OUTPUT_MODERATION_PATTERNS` becomes the **safety floor** that runs when no workspace policy is configured. When a policy IS configured, the `ContentModerator` runs first; the regex floor still runs after as a defence-in-depth fallback. The DLP layer (`dlp_scan`) continues to run immediately after, on whatever payload survives moderation.

**Rationale**: The layer already exists and is the documented insertion point in the constitution / existing pipeline; reusing it preserves the LAYER_ORDER contract. Keeping the regex floor active satisfies rule 7 (backwards compat) for workspaces that have not enabled the new feature.

**Alternatives considered**:
- New `GuardrailLayer.content_moderation` between `output_moderation` and `dlp_scan`: rejected — violates rule 6 spirit (additive enums) but more importantly creates a parallel concept that overlaps with `output_moderation`. Reuse is cleaner.
- Replacing the regex layer: rejected — loses the baseline for workspaces without policies.

---

## D-003 — Provider abstraction (Protocol + adapter registry)

**Decision**: Define `ModerationProvider` Protocol with a single `score(text, *, language, categories) -> ProviderVerdict` method. Adapters implement the Protocol; a registry (`ModerationProviderRegistry`) wires names to instances. The `ContentModerator` orchestrator picks providers per workspace policy at runtime.

**Rationale**: Mirrors the existing `Scorer` Protocol pattern in `evaluation/scorers/`. Allows operators to add new providers without touching orchestrator code. Self-hosted classifiers are a first-class citizen alongside cloud providers.

**Alternatives considered**:
- Inheritance hierarchy with abstract base class: rejected — Protocol is the existing pattern in this codebase.
- Plugin-style discovery (entry points): rejected — overkill for 4 known providers; can be lifted later if needed.

---

## D-004 — OpenAI Moderation adapter is NOT routed through the model router

**Decision**: `openai_moderation` calls OpenAI's dedicated moderation endpoint (`/v1/moderations`) directly via `httpx`. It is NOT considered an LLM call under rule 11.

**Rationale**: Rule 11 reads "every LLM call goes through the model router". The OpenAI moderation endpoint is not an LLM call — it's a classification API that does not produce generative text. The model router governs catalog and fallback for generative models; routing classification calls through it adds friction without value.

**Alternatives considered**:
- Routing moderation through model_router for uniformity: rejected — model_router is built for generative-model contracts (token usage, cost attribution, fallback). Pushing classification through it bends the abstraction.

---

## D-005 — Anthropic Safety adapter IS routed through the model router

**Decision**: `anthropic_safety` (the Anthropic safety classifier built on Claude) IS an LLM call (it produces generative output to score safety) and therefore goes through `common.clients.model_router`. The model router resolves the model binding, enforces catalog policy, and applies fallback.

**Rationale**: Rule 11 directly applies; Anthropic's safety model is a fine-tuned LLM. The router is already there; it would be a constitution violation to bypass it.

**Alternatives considered**:
- Direct Anthropic SDK: rejected — rule 11 violation.

---

## D-006 — Google Perspective adapter

**Decision**: `google_perspective` calls the Perspective API (https://perspectiveapi.com/) directly via `httpx`. Treated as a classification API like OpenAI Moderation. Returns category scores in the 0.0-1.0 range, normalised to the platform's category taxonomy.

**Rationale**: Standard public REST API; not an LLM call.

---

## D-007 — Self-hosted classifier adapter

**Decision**: `self_hosted_classifier` lazy-loads a HuggingFace Transformers model on first use. The model is NOT bundled in the platform image — it is downloaded on first call (cached locally) or pre-warmed via an init container at deployment time. The model name is configurable per workspace.

**Rationale**: Bundling a large classifier model in the platform image inflates image size for every operator regardless of whether they use self-hosted classification. Lazy-loading + per-workspace model selection lets operators choose models that match their language and content profile. The default model is `unitary/multilingual-toxic-xlm-roberta`.

**Alternatives considered**:
- Bundle the model in the image: rejected — image size; one-size-fits-all model is not appropriate for multilingual deployments.
- Run the model in a separate satellite service: deferred — the additional infrastructure isn't justified for v1; can be lifted later when GPU acceleration becomes a need.

---

## D-008 — Category taxonomy

**Decision**: Five canonical categories per FR-001: `toxicity`, `hate_speech`, `violence_self_harm`, `sexually_explicit`, `pii_leakage`. Each adapter maps its native category names to this canonical set; categories outside the canonical set are stored as `extra` metadata on the moderation event but do not drive policy actions.

**Rationale**: Operators configure policy per canonical category; mapping in the adapter (one place) is simpler than mapping in policy configuration (many places). The canonical set is the floor; per-deployment extension is allowed without breaking the policy contract.

**Alternatives considered**:
- Operator-defined categories with no canonical mapping: rejected — every operator would write their own mapping, error-prone.
- Provider-native categories surfaced directly: rejected — policy portability across providers becomes impossible.

---

## D-009 — Action selector — multi-category triggers

**Decision**: When multiple canonical categories trigger on a single output, the safer action wins: `block` > `redact` > `flag`. Implemented in `moderation_action_resolver.py`.

**Rationale**: Stated in spec FR-016 — explicit ordering avoids ambiguity. Block is safest because it prevents delivery entirely; redact is next because it modifies but delivers; flag is least restrictive.

---

## D-010 — Provider failure mode

**Decision**: Per-workspace `provider_failure_action` field with two values: `fail_closed` (default) and `fail_open`. On primary-provider unavailability the platform tries fallback (if configured), then self-hosted classifier (if configured), then applies the failure action. Operators receive an alert via the notifications subsystem on every failure.

**Rationale**: Default fail-closed is the responsible choice for a safety control. Operators who accept the availability tradeoff (e.g., high-throughput workloads where moderation outage is preferable to delivery outage) can explicitly switch. The fallback chain (primary → fallback → self-hosted floor → failure action) means most outages are absorbed without falling back to fail-open.

**Alternatives considered**:
- Default fail-open: rejected — defeats the purpose of moderation.
- No fallback chain: rejected — single-point-of-failure on provider availability.

---

## D-011 — Cost cap enforcement

**Decision**: Per-workspace monthly cost cap (USD or EUR; configurable per deployment). Counter is maintained in Redis (`trust:moderation_cost:{workspace_id}:{yyyy-mm}`); on `INCRBY` past the cap the provider failure action triggers and operators are alerted. The counter resets monthly via a sliding window.

**Rationale**: Same pattern as the SMS cost cap in feature 077. Redis INCRBY is atomic and cheap; the policy table records the cap; the worker doesn't need to be involved.

**Alternatives considered**:
- Cap enforcement per-call (read counter on every call): rejected — adds Redis read latency on every output; the INCRBY-on-bill approach is sufficient.
- Cost cap at the platform level: rejected — workspaces have wildly different volumes; per-workspace is the right granularity.

---

## D-012 — Latency budget

**Decision**: Per-call timeout 2 s (configurable). Cumulative per-execution budget 5 s (configurable). On per-call timeout, the failure action triggers for that call. On cumulative budget exhaustion the execution times out gracefully (existing execution-timeout machinery in `execution/`).

**Rationale**: Bounds tail latency. The cumulative budget catches the case where multiple short-but-not-timeout calls add up to user-noticeable latency.

---

## D-013 — Disclosure & consent reuse from feature 076

**Decision**: First-time AI disclosure is enforced via feature 076's `consent_service.require_or_prompt(user_id, workspace_id)` exactly as documented in `specs/076-privacy-compliance/contracts/consent-service.md`. The `ai_interaction` consent type from that contract is the disclosure consent. No new consent persistence, no new versioning. This feature only specifies (a) where to call `require_or_prompt` from in the agent invocation flow, and (b) the disclosure-text editing UI flow at the workspace-admin level.

**Rationale**: Feature 076 already shipped a complete consent service with HTTP 428 enforcement, propagation worker, and audit. Re-implementing would be a constitution violation (rule 27 — "do not recreate existing functionality"). Delegation keeps the consent surface single-sourced.

**Alternatives considered**:
- New `ai_disclosure` consent type: rejected — overlaps with `ai_interaction` from feature 076.
- New consent infrastructure: rejected — duplication.

---

## D-014 — Disclosure-text storage and material vs non-material change

**Decision**: Disclosure text is owned by the privacy compliance subsystem (feature 076) and versioned there. A "material" flag on each version triggers the re-prompt flow built into feature 076. This feature wires up an admin endpoint that updates the text and sets the material flag; feature 076 handles the rest.

**Rationale**: Same logic as D-013 — single source of truth.

---

## D-015 — Fairness scorer placement

**Decision**: Add `evaluation/scorers/fairness.py` (FairnessScorer class implementing the `Scorer` Protocol). Helper functions live in a sibling `evaluation/scorers/fairness_metrics.py` module to keep the scorer file small and to allow direct unit-testing of the metric math without going through Scorer.

**Rationale**: Existing scorers (e.g., `trajectory.py`, `llm_judge.py`) follow the same one-file-per-scorer pattern. Helper module is consistent with this codebase's standard refactoring (when one file grows past ~300 lines, helpers split out).

---

## D-016 — Fairness metric definitions

**Decision**: Three metrics per FR-023:
- **Demographic parity**: max-min difference of positive-prediction rate across groups. Pass when `max - min ≤ fairness_band` (default 0.10).
- **Equal opportunity**: max-min difference of true-positive-rate across groups (requires labelled correct answers). Pass when `max - min ≤ fairness_band`.
- **Calibration**: Brier-score difference across groups, computed only when probability outputs are available. Pass when `max - min ≤ fairness_band`.

**Rationale**: These three are the standard textbook fairness metrics covered in scikit-learn's `fairlearn` ecosystem and well-understood by the regulator audience. Higher-order metrics (e.g., counterfactual fairness, individual fairness) are deferred to a future iteration.

**Alternatives considered**:
- Disparate impact ratio: deferred — common in US legal contexts but adds confusion when demographic parity is already reported (they convey similar information).
- Counterfactual fairness: deferred — requires a causal model; not v1 scope.

---

## D-017 — Fairness band default

**Decision**: Default fairness band is 0.10 (10 percentage points spread across groups). Per-workspace + per-attribute override supported.

**Rationale**: 0.10 is the threshold used in many fairness toolkits (fairlearn, AIF360) as a starting point. Tighter bands are appropriate in high-stakes contexts (e.g., 0.05 for hiring); operators tune.

---

## D-018 — Determinism vs stochastic providers

**Decision**: Fairness scorer is deterministic for deterministic agents and stochastic providers. For stochastic providers (LLM-based scoring), the scorer uses temperature 0 and a fixed seed where provider supports it; otherwise it documents an epsilon tolerance (0.001 per spec SC-009).

**Rationale**: Spec FR-030 / SC-009 require determinism. Temperature 0 + fixed seed is the standard pattern.

---

## D-019 — Group attribute privacy

**Decision**: Group attributes are stored as part of the test suite metadata in the existing evaluation tables. They are NEVER emitted as observability labels (rule 22). They appear only in:
- The test suite definition (encrypted-at-rest by the platform's standard postgres encryption).
- The fairness evaluation row (per-attribute statistical aggregates only — never per-individual).
- The audit chain (rule 9 — when a group attribute is read, an audit entry is written).

**Rationale**: Group attributes are protected categories in many jurisdictions. Treating them as PII end-to-end avoids both regulatory and ethical exposure. The aggregate-only persistence on the evaluation row prevents per-user re-identification.

**Alternatives considered**:
- Logging group attributes for debugging: rejected — privacy violation.
- Storing per-individual scores by group: rejected — re-identification risk; aggregates are sufficient for the metric.

---

## D-020 — Certification gate scoping

**Decision**: Fairness gate fires only when the agent's manifest declares `high_impact_use=true`. The declaration field is the same one that drives the PIA gate in feature 076. Reuse keeps the high-impact concept single-sourced.

**Rationale**: Not every agent needs fairness evaluation. Marketing copy generators, code review assistants, and other low-stakes agents would be over-constrained by a blanket gate. Tying the gate to `high_impact_use=true` mirrors the PIA gate and produces a coherent regulatory story.

**Alternatives considered**:
- Blanket gate for every agent: rejected — over-constrains low-stakes agents and floods the certification queue.
- Per-deployment opt-in to the gate: rejected — would let operators skip fairness on high-impact agents (defeats the purpose).

---

## D-021 — Staleness window for fairness evaluations

**Decision**: Default 90 days. Per-workspace tunable. Material agent revisions (re-trained, re-prompted, manifest changes) invalidate prior evaluations regardless of age.

**Rationale**: 90 days balances the cost of re-evaluation against drift. Material revision invalidation captures cases where the agent's behaviour could have changed without time elapsing.

---

## D-022 — `flag` action and notifications

**Decision**: When `flag` action triggers, the platform emits a `monitor.alerts` event of type `trust.content_moderation.triggered` carrying the workspace_id, agent_id, execution_id, triggered categories, and scores. The notifications subsystem (feature 077) routes to the workspace's configured channels.

**Rationale**: Reuses the new multi-channel notifications infrastructure rather than re-implementing operator paging in trust BC. Single audit trail through `monitor.alerts`.

---

## D-023 — Migration numbering

**Decision**: Migration `059_content_safety_fairness.py`. Chained on top of `058_multi_channel_notifications.py` (feature 077). If feature 077 is not yet merged when this lands, the migration's `down_revision` is rebased to the actual current head — standard brownfield practice.

**Rationale**: Linear, predictable migration chain.

---

## Open questions resolved

All `[NEEDS CLARIFICATION]` markers from the spec have been resolved with industry-standard defaults documented in this research:

- Fail-closed default + fallback chain: D-010.
- Per-call timeout 2s, cumulative 5s: D-012.
- Default fairness band 0.10 with per-workspace tuning: D-017.
- Default staleness window 90 days: D-021.
- Three fairness metrics (parity, equal opportunity, calibration): D-016.
- Determinism via temperature 0 + fixed seed for stochastic providers: D-018.
- Group attributes are PII, never logged as labels: D-019.
- Fairness gate scoped to `high_impact_use=true` agents: D-020.
- Five canonical category taxonomy: D-008.
- Multi-category trigger: safer action wins (`block` > `redact` > `flag`): D-009.
- Disclosure & consent reuse feature 076 verbatim: D-013, D-014.
