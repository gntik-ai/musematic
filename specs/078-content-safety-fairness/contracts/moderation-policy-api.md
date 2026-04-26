# Moderation Policy API Contract

**Feature**: 078-content-safety-fairness
**Modules**:
- `apps/control-plane/src/platform/trust/routers/moderation_policies_router.py` (NEW)
- `apps/control-plane/src/platform/trust/routers/moderation_events_router.py` (NEW)

## REST endpoints

### Workspace-admin policy CRUD

Under `/api/v1/trust/moderation/policies/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `POST /api/v1/trust/moderation/policies` | Create or replace the active policy for a workspace; bumps `version`, supersedes prior version. | `workspace_admin` for the target workspace |
| `GET /api/v1/trust/moderation/policies?workspace_id=` | Get the active policy plus version history. | `workspace_admin`, `auditor`, `superadmin` |
| `GET /api/v1/trust/moderation/policies/{id}` | Get a specific version (active or superseded). | same |
| `PATCH /api/v1/trust/moderation/policies/{id}` | Update the active policy in place; bumps `version`. | `workspace_admin` |
| `DELETE /api/v1/trust/moderation/policies/{id}` | Soft-delete (sets `active=false`, no replacement); workspace returns to baseline regex floor. | `workspace_admin` |
| `POST /api/v1/trust/moderation/policies/{id}/test` | Synthesise a sample output and run it through the policy without delivering downstream — useful for tuning thresholds. Response includes per-category scores, action that would be taken, and provider used. | `workspace_admin` |

Cross-workspace policy access (workspace_admin trying to read another workspace's policy) returns 403 (rule 47).

### Operator event log

Under `/api/v1/trust/moderation/events/*`:

| Method + path | Purpose | Role |
|---|---|---|
| `GET /api/v1/trust/moderation/events?workspace_id=&agent_id=&category=&action=&since=&until=&limit=&cursor=` | List events scoped to authorisation. | `workspace_admin` (own workspace only), `auditor`, `superadmin` |
| `GET /api/v1/trust/moderation/events/{id}` | Inspect a single event. Original content not returned in the body — only `audit_chain_ref` for cross-reference. | same |
| `GET /api/v1/trust/moderation/events/aggregate?workspace_id=&since=&until=&group_by=` | Aggregate counts per category, per agent, per action, per day. | same |

`group_by` supports `category`, `agent`, `action`, `day` (combinable as a comma-separated list).

## Request / response schemas (illustrative)

```python
class ModerationPolicyCreateRequest(BaseModel):
    workspace_id: UUID
    categories: list[Category]              # canonical taxonomy enum
    threshold_per_category: dict[Category, float]  # 0.0–1.0
    action_per_category: dict[Category, ModerationAction] = {}
    default_action: ModerationAction = "block"
    primary_provider: ModerationProviderName = "openai_moderation"
    fallback_provider: ModerationProviderName | None = None
    tie_break_rule: TieBreakRule = "max_score"
    provider_failure_action: ProviderFailureAction = "fail_closed"
    language_pins: dict[str, ModerationProviderName] | None = None
    agent_allowlist: list[AgentAllowlistEntry] | None = None
    monthly_cost_cap_eur: float = 50.0
    per_call_timeout_ms: int = 2000
    per_execution_budget_ms: int = 5000

class ModerationPolicyResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    version: int
    active: bool
    # ... echo of all input fields ...
    created_by: UUID
    created_at: datetime
    updated_at: datetime

class ModerationEventResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    execution_id: UUID
    agent_id: UUID
    policy_id: UUID
    provider: str
    triggered_categories: list[str]
    scores_per_category: dict[str, float]
    action_taken: str
    language_detected: str | None
    latency_ms: int | None
    audit_chain_ref: str | None
    created_at: datetime
```

## Authorization rules

- `workspace_admin` access to policies and events is restricted to their workspace via row-level filtering AND endpoint-level checks (defence-in-depth, rule 47).
- `auditor` and `superadmin` have read-only cross-workspace access.
- Cross-workspace `workspace_admin` request returns 403 with body `{"error":"forbidden"}` — no leakage of whether the other workspace exists.
- Self-service users have NO access to these endpoints (no `/api/v1/me/*` surface here — moderation policy is not user-self-service).

## Audit-chain emissions (rule 32, FR-037)

| Action | Audit event |
|---|---|
| Policy create / update / delete | `trust.content_moderation.policy.changed` with actor, before/after diff (with secret refs masked). |
| Policy test invocation | `trust.content_moderation.policy.tested` with actor, sample input hash (not the input itself), verdict. |
| Event row inspection by operator | `trust.content_moderation.event.viewed` (rule 9 — operator viewed PII-adjacent data). |

## Test-mode synthesis (`POST .../policies/{id}/test`)

Used by workspace admins tuning thresholds without affecting production agent outputs:

```python
class ModerationPolicyTestRequest(BaseModel):
    sample_output: str
    language: str | None = None
    agent_fqn: str | None = None  # for allowlist behaviour testing

class ModerationPolicyTestResponse(BaseModel):
    triggered_categories: list[str]
    scores_per_category: dict[str, float]
    action_that_would_be_taken: str
    provider_used: str
    latency_ms: int
    notes: list[str]                # e.g., "fallback_used", "cost_estimated_eur=0.0001"
```

The test invocation does NOT persist a moderation event row (no production consequence); it does emit an audit-chain entry (D-014 / rule 32).

## Unit-test contract

- **PA1** — POST without `workspace_admin` role returns 403.
- **PA2** — POST with valid policy creates row with `version=1, active=true`; subsequent POST creates `version=2`, marks `version=1` as `active=false`.
- **PA3** — GET list filtered by `workspace_id` returns only policies for that workspace; cross-workspace 403.
- **PA4** — DELETE sets `active=false` without removing the row; subsequent agent execution falls back to regex floor (no events generated).
- **PA5** — POST `/test` returns the action that WOULD be taken without producing a moderation event row.
- **PA6** — Event list filters by category, action, agent, time-range, all combinable.
- **PA7** — Event aggregate returns counts that reconcile with raw event-list counts.
- **PA8** — `workspace_admin` cannot list events for another workspace (403, no leakage).
- **PA9** — Audit-chain entries emitted on every CRUD; secret refs masked in diff payload (rule 32 + rule 23).
- **PA10** — Validation rejects out-of-range thresholds, unknown categories, unknown providers, unknown actions.
- **PA11** — Validation rejects `monthly_cost_cap_eur < 0`.
- **PA12** — Validation rejects `per_call_timeout_ms > per_execution_budget_ms` (logical constraint).
