# Data Model: Content Safety and Fairness

**Feature**: 078-content-safety-fairness
**Phase**: 1 — Design
**Migration**: `059_content_safety_fairness.py` (rebase to current Alembic head at merge)

---

## PostgreSQL — schema additions

### 1. `content_moderation_policies` (NEW)

Per-workspace moderation configuration. Up to one active policy row per workspace at a time; previous versions retained for audit.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Default `gen_random_uuid()`. |
| `workspace_id` | UUID FK → `workspaces.id` ON DELETE CASCADE | One workspace, one active policy. |
| `version` | INTEGER NOT NULL DEFAULT 1 | Bumped on every change; older versions retained. |
| `active` | BOOLEAN NOT NULL DEFAULT TRUE | False on superseded versions. |
| `categories` | JSONB NOT NULL | Subset of canonical taxonomy: `["toxicity","hate_speech","violence_self_harm","sexually_explicit","pii_leakage"]`. |
| `threshold_per_category` | JSONB NOT NULL | `{"toxicity":0.8,"hate_speech":0.7,...}` — score floor that triggers the action. |
| `action_per_category` | JSONB NOT NULL DEFAULT `{}` | Optional per-category action override; falls back to `default_action`. Values: `block`, `redact`, `flag`. |
| `default_action` | VARCHAR(16) NOT NULL DEFAULT 'block' | Action when category-specific override is absent. |
| `primary_provider` | VARCHAR(64) NOT NULL DEFAULT 'openai_moderation' | One of: `openai_moderation`, `anthropic_safety`, `google_perspective`, `self_hosted`. |
| `fallback_provider` | VARCHAR(64) NULL | Optional secondary; same value space as primary. |
| `tie_break_rule` | VARCHAR(16) NOT NULL DEFAULT 'max_score' | One of: `max_score`, `min_score`, `primary_only`. |
| `provider_failure_action` | VARCHAR(16) NOT NULL DEFAULT 'fail_closed' | `fail_closed` blocks; `fail_open` delivers with event marker. |
| `language_pins` | JSONB NULL | `{"es":"google_perspective","ja":"self_hosted"}` — per-language provider override. |
| `agent_allowlist` | JSONB NULL | `[{"agent_fqn":"sec-research:scanner","allowed_categories":["violence_self_harm"]}]` — exempt specified agents from specified categories (still subject to other categories). |
| `monthly_cost_cap_eur` | NUMERIC(10,2) NOT NULL DEFAULT 50.00 | Per-workspace monthly spend cap on paid providers. |
| `per_call_timeout_ms` | INTEGER NOT NULL DEFAULT 2000 | Per-call deadline. |
| `per_execution_budget_ms` | INTEGER NOT NULL DEFAULT 5000 | Cumulative deadline per execution. |
| `created_by` | UUID FK → `users.id` | For audit. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Constraints**:
- Partial unique index on `(workspace_id) WHERE active = TRUE` — one active policy per workspace.
- Index on `(workspace_id, version)` for version listing.
- Check: `default_action IN ('block','redact','flag')`.
- Check: `provider_failure_action IN ('fail_closed','fail_open')`.
- Check: `tie_break_rule IN ('max_score','min_score','primary_only')`.

---

### 2. `content_moderation_events` (NEW)

Append-only audit stream — one row per moderation evaluation that triggered an action (or, when `audit_all_evaluations=true`, every evaluation).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Default `gen_random_uuid()`. |
| `workspace_id` | UUID NOT NULL | Denormalised for query performance and authorisation scoping. |
| `execution_id` | UUID NOT NULL | The execution that produced the moderated output. |
| `agent_id` | UUID NOT NULL | The agent that produced the output. |
| `policy_id` | UUID NOT NULL FK → `content_moderation_policies.id` | The policy version that evaluated. |
| `provider` | VARCHAR(64) NOT NULL | The provider that produced the verdict. |
| `triggered_categories` | JSONB NOT NULL | `["toxicity","pii_leakage"]`. Empty when `action_taken='none'` (used in audit-all mode). |
| `scores_per_category` | JSONB NOT NULL | Full score map: `{"toxicity":0.92,"hate_speech":0.10,...}`. |
| `action_taken` | VARCHAR(16) NOT NULL | One of: `block`, `redact`, `flag`, `none` (audit-all), `fail_closed_blocked`, `fail_open_delivered`. |
| `language_detected` | VARCHAR(8) NULL | ISO 639-1; NULL when adapter does not detect. |
| `latency_ms` | INTEGER NULL | Provider call latency. |
| `audit_chain_ref` | VARCHAR(128) NULL | Reference to the audit-chain entry for the original (pre-moderation) content. |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Constraints**:
- Index on `(workspace_id, created_at DESC)` for the operator log.
- Index on `(workspace_id, agent_id, created_at DESC)` for per-agent drill-in.
- Partial index on `(workspace_id, action_taken)` WHERE `action_taken IN ('block','redact','flag')` for filter views.
- Partition by month on `created_at` may be added in a future migration if event volume warrants — out of scope for v1.

**Note on storage of original content**: The full pre-moderation content is NOT stored on this row. It lives in the audit chain (rule 18 / UPD-024); `audit_chain_ref` points to the chain entry. This keeps the event row compact and ensures the original content is governed by the same retention rules as the rest of the audit chain.

---

### 3. `fairness_evaluations` (NEW)

One row per (agent_revision, suite, attribute, metric) result. Multiple rows make up a single "evaluation run" identified by `evaluation_run_id`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | Default `gen_random_uuid()`. |
| `evaluation_run_id` | UUID NOT NULL | Groups all rows from a single run. |
| `agent_id` | UUID NOT NULL | The agent under evaluation. |
| `agent_revision_id` | UUID NOT NULL | Specific revision evaluated; revision change invalidates prior runs. |
| `suite_id` | UUID NOT NULL | Test suite used. |
| `metric_name` | VARCHAR(64) NOT NULL | One of: `demographic_parity`, `equal_opportunity`, `calibration`. |
| `group_attribute` | VARCHAR(64) NOT NULL | Attribute name (e.g., `gender`, `language`). |
| `per_group_scores` | JSONB NOT NULL | `{"f":0.78,"m":0.81,"nb":0.76}` — aggregated metric value per group. |
| `spread` | NUMERIC(8,4) NULL | `max - min` across groups; NULL when fewer than 2 groups. |
| `fairness_band` | NUMERIC(8,4) NOT NULL | The band used for this run (default 0.10). |
| `passed` | BOOLEAN NOT NULL | `spread <= fairness_band`. |
| `coverage` | JSONB NULL | `{"f":42,"m":40,"nb":18,"insufficient":["x"]}` — per-group sample counts and any groups dropped. |
| `notes` | VARCHAR(256) NULL | Free-text marker, e.g. `unsupported` for calibration-on-classification. |
| `evaluated_by` | UUID FK → `users.id` | The evaluator. |
| `computed_at` | TIMESTAMPTZ NOT NULL DEFAULT now() | |

**Constraints**:
- Unique on `(evaluation_run_id, metric_name, group_attribute)` — one row per metric × attribute per run.
- Index on `(agent_id, agent_revision_id, computed_at DESC)` for the certification gate's "latest passing" lookup.
- Index on `(evaluation_run_id)` for run roll-up.

**Note on group-level data**: Per-group scores are aggregates only. No per-individual data lives in this row. Per-individual scores (used to compute the aggregates) are in the existing per-test-case evaluation tables, which already follow the privacy compliance subsystem's rules.

---

### 4. Tables NOT modified

- `agent_profiles` / `agent_revisions` (in `registry/`) — existing `high_impact_use` declaration field is read by the certification gate; no schema change required.
- `certifications` (in `trust/`) — existing certification flow is extended with a new gate but no new columns; the gate is enforced in service code by querying `fairness_evaluations`.
- `privacy_consent_records` (in `privacy_compliance/`) — owned by feature 076; this feature consumes the existing `ai_interaction` consent type via `consent_service.require_or_prompt`.

---

## Redis — key patterns

| Key | Type | TTL | Purpose |
|---|---|---|---|
| `trust:moderation_cost:{workspace_id}:{yyyy-mm}` | counter | 35d | Per-workspace per-month moderation provider spend (in eur cents). Atomic INCRBY on each provider call. |
| `trust:moderation_failure:{workspace_id}` | string (last failure ts) | 1h | Cooldown for operator alert flooding when a provider is repeatedly failing. |
| `trust:moderation_lang_cache:{text_hash}` | string (lang code) | 5m | Optional language-detection cache to amortise repeated detection on similar outputs. |

---

## Vault — secret paths

| Path | Contains | Rotation |
|---|---|---|
| `secret/data/trust/moderation-providers/openai/{deployment}` | `{"api_key":"sk-..."}` | Manual via existing rotation pattern (rule 44 — rotation does not echo secret). |
| `secret/data/trust/moderation-providers/anthropic/{deployment}` | `{"api_key":"sk-ant-..."}` | Manual; reused by the model_router's existing Anthropic credential resolution. |
| `secret/data/trust/moderation-providers/google_perspective/{deployment}` | `{"api_key":"..."}` | Manual. |
| `secret/data/trust/moderation-providers/self_hosted/{deployment}` | (Empty or model-cache token) | N/A (no external auth). |

All paths resolve via `common.secrets.secret_provider` (rule 39).

---

## Kafka — events emitted

No new topics. Reuses existing topics:

| Topic | Event type | Producer | Consumers |
|---|---|---|---|
| `trust.events` (existing) | `trust.content_moderation.policy.changed` | `trust/services/content_moderator.py` orchestrator | audit, analytics |
| `trust.events` (existing) | `trust.content_moderation.triggered` | content moderator | audit, analytics |
| `trust.events` (existing) | `trust.content_moderation.provider_failed` | content moderator | operator (notifications), analytics |
| `monitor.alerts` (existing) | `trust.content_moderation.triggered` | content moderator (on `flag` action) | notifications fan-out (feature 077) |
| `evaluation.events` (existing) | `evaluation.fairness.completed` | `evaluation/scorers/fairness.py` | analytics, agentops, audit |
| `trust.events` (existing) | `trust.certification.blocked.fairness` | `trust/certification_service.py` (extended) | audit, agentops |

---

## Configuration — `PlatformSettings` extensions

New fields under a new `ContentModerationSettings` (in `common/config.py`), referenced from `PlatformSettings.content_moderation`:

| Field | Type | Default | Purpose |
|---|---|---|---|
| `enabled` | bool | False | Master flag (`FEATURE_CONTENT_MODERATION`). |
| `default_per_call_timeout_ms` | int | 2000 | Per-call provider timeout. |
| `default_per_execution_budget_ms` | int | 5000 | Cumulative per-execution moderation latency budget. |
| `default_monthly_cost_cap_eur` | float | 50.0 | Default workspace cap. |
| `default_fairness_band` | float | 0.10 | Spread allowed for parity / equal-opportunity / calibration. |
| `default_min_group_size` | int | 5 | Minimum cases per group for inclusion in group-aware metrics. |
| `default_fairness_staleness_days` | int | 90 | Window after which a passing fairness evaluation no longer satisfies the gate. |
| `audit_all_evaluations` | bool | False | When True, every moderation evaluation produces an event row (with `action_taken='none'` for non-triggers); when False (default), only triggers are persisted. |
| `self_hosted_model_name` | str | `unitary/multilingual-toxic-xlm-roberta` | HuggingFace model id for the self-hosted classifier. |

---

## Validation rules (enforced at service layer)

- `categories` ⇒ subset of canonical taxonomy `{toxicity, hate_speech, violence_self_harm, sexually_explicit, pii_leakage}`.
- `threshold_per_category` ⇒ keys ⊆ `categories`; values in `[0.0, 1.0]`.
- `action_per_category` values ⇒ `{block, redact, flag}`.
- `primary_provider`, `fallback_provider` ⇒ resolvable provider names.
- `language_pins` keys ⇒ ISO 639-1; values ⇒ resolvable provider names.
- `agent_allowlist[].agent_fqn` ⇒ resolvable to a registry agent FQN.
- Active policies per workspace ≤ 1 (partial unique index enforces).
- Fairness band ∈ `(0.0, 1.0)`.
- `metric_name` ∈ `{demographic_parity, equal_opportunity, calibration}`.

---

## Backwards compatibility checklist

- Workspaces with no `content_moderation_policies` row see no change in `guardrail_pipeline.py` behaviour: the existing regex `_OUTPUT_MODERATION_PATTERNS` still runs as before, the DLP layer still runs immediately after.
- Existing scorers (`exact_match`, `regex`, `json_schema`, `semantic`, `llm_judge`, `trajectory`) are unaffected; the registry just gains one additional registration for `fairness`.
- Agents not declared as `high_impact_use=true` see no change to the certification flow.
- Existing tests for guardrail pipeline, scorer registry, and certification gate stay green.

---

## Audit chain integration (rules 9, 32, 37)

Every operation below appends an entry via `security_compliance/services/audit_chain_service.py`:

1. Moderation policy create / update / delete (rule 32).
2. Every triggered moderation event (rule 37).
3. Every fairness evaluation run (rule 37; group attribute access is rule 9).
4. Every certification request that hits the fairness gate, regardless of pass/fail (rule 37).

Audit calls are fire-and-forget at the call-site but use the existing durable audit-chain infrastructure (Kafka-backed; critical reminder #30).

---

## Entity relationships

```
workspaces 1───∞ content_moderation_policies (only one active per workspace)
                                       1
                                       │
                                       ▼
content_moderation_events ∞───1 content_moderation_policies
content_moderation_events ∞───1 executions (existing, registry/)
content_moderation_events ∞───1 agent_profiles (existing, registry/)
content_moderation_events 1───1 audit_chain entries (via audit_chain_ref)

agent_profiles 1───∞ agent_revisions (existing)
                              1
                              │
                              ▼
fairness_evaluations ∞───1 agent_revisions
fairness_evaluations ∞───1 evaluation_test_suites (existing)
fairness_evaluations ∞───1 users (evaluated_by)

certifications (existing) ──[gate consults]──▶ fairness_evaluations (latest passing)
agent_invocation flow ──[require]──▶ privacy_consent_records (feature 076)
```

---

## ClickHouse — analytics rollups

No new ClickHouse tables. Reuses the existing `trust_metrics` analytics rollup pattern (feature 020). The Kafka events emitted on `trust.events` and `evaluation.events` flow into the existing analytics pipeline, which materializes per-day per-workspace per-category rollups via existing materialized views — the only change is that those views now include `content_moderation.triggered` and `evaluation.fairness.completed` event types.
