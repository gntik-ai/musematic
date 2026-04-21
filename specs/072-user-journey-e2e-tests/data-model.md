# Phase 1 Data Model: User Journey E2E Tests

**Feature**: 072-user-journey-e2e-tests
**Date**: 2026-04-21

## Overview

No database schema changes. This document captures: (1) the **journey-scoped entities** created by pre-baked fixtures at runtime, (2) the **persona fixtures** and the user/role shapes they assume, (3) the **mock OAuth server** seed state, (4) the **narrative report** row structure, and (5) the **per-journey isolation scope** naming convention.

All persistence is in the platform's existing data stores via feature 071's fixtures. This feature owns no tables.

---

## 1. Journey Test File Shape

Every `tests/e2e/journeys/test_j{NN}_{persona}.py` file MUST open with a mandatory header block followed by a single async test function (or fixture + function pair).

```python
"""
Journey J{NN} — {Persona}: {One-line summary}

Priority: P{1|2|3}
Steps: {count}
"""
# Cross-context inventory:
# - auth
# - workspaces
# - registry
# - policies
# - trust
# - governance

import pytest
from tests.e2e.journeys.helpers.narrative import journey_step
from tests.e2e.journeys.helpers.oauth import oauth_login
# ... other helpers

JOURNEY_ID = "j01"                      # matches test file suffix; used as resource-name prefix
TIMEOUT_SECONDS = 180                   # per-journey timeout (D-008)


@pytest.mark.journey
@pytest.mark.j01_admin
@pytest.mark.timeout(TIMEOUT_SECONDS)
async def test_admin_bootstrap_to_production(admin_client, ws_client, mock_google_oidc, mock_github_oauth):
    with journey_step("Admin logs in with temporary password"):
        # ... code + assert
    with journey_step("Admin changes temporary password"):
        # ... code + assert
    # ... 13+ more steps
```

**Required structural elements** (enforced by meta-test in contracts/journey-structure.md):
- Top-level `"""`-delimited docstring naming journey + priority + step count
- `# Cross-context inventory:` header comment listing ≥ 4 bounded contexts (FR-003)
- `JOURNEY_ID = "j{NN}"` module constant
- `TIMEOUT_SECONDS = N` module constant
- `@pytest.mark.journey` + `@pytest.mark.j{NN}_{persona}` + `@pytest.mark.timeout(...)` decorators
- ≥ 15 `journey_step` context-manager invocations (FR-004) OR equivalent assertion-point count

---

## 2. Persona Fixture Specifications

Seven persona-scoped fixtures live in `tests/e2e/journeys/conftest.py`. Each yields an authenticated `AuthenticatedAsyncClient` (from feature 071's `http_client.py`) pre-configured with the correct role and workspace scope.

| Fixture Name | Persona | Authentication Method | Roles | Primary Use |
|---|---|---|---|---|
| `admin_client` | Platform Admin | Bootstrap credential + forced password change + MFA | `platform_admin` | J01, J05, J06 |
| `creator_client` | Agent Creator | GitHub OAuth (mock) | `workspace_admin` scoped to creator workspace | J02, J07 |
| `consumer_client` | End-user Consumer | Google OAuth (mock) | `workspace_member` default role | J03, J04 |
| `operator_client` | Platform Operator | Email+password (admin-provisioned) | `platform_operator` | J06 |
| `trust_reviewer_client` | Trust Reviewer | Email+password (admin-provisioned) | `trust_reviewer` | J05 |
| `evaluator_client` | Data Scientist / Evaluator | Email+password (admin-provisioned) | `evaluator` | J07 |
| `researcher_client` | Research Scientist | Email+password (admin-provisioned) | `researcher` | J09 |

**Fixture scope**: `function` (per-test). A fresh persona client is created per journey invocation to avoid cross-journey authentication state leakage. Cost is amortized because the persona user account itself is seeded at session scope (shared across journeys) — only the JWT+session is per-test.

**Persona user seeding** (session-scoped autouse fixture `ensure_journey_personas`): creates one user per persona with emails `j-admin@e2e.test`, `j-creator@e2e.test`, `j-consumer@e2e.test`, `j-operator@e2e.test`, `j-trust-reviewer@e2e.test`, `j-evaluator@e2e.test`, `j-researcher@e2e.test` and assigns the corresponding role. Idempotent — skips if email already exists.

---

## 3. Pre-baked State Fixture Specifications

Four pre-baked fixtures seed multi-step state so journeys can start mid-flow.

### `workspace_with_agents(journey_id, admin_client) → dict`

**Yields**:
```python
{
    "workspace": {"id": "...", "name": "j{NN}-test-{hash}-ws-primary"},
    "namespace": {"id": "...", "name": "j{NN}-test-{hash}-ns-ops"},
    "agents": {
        "executor": {"fqn": "j{NN}-test-{hash}-ns-ops:executor", "id": "..."},
        "observer": {"fqn": "...", "id": "..."},
        "judge": {"fqn": "...", "id": "..."},
        "enforcer": {"fqn": "...", "id": "..."},
    },
    "policies": {"default-allow": {...}, "finance-strict": {...}},
    "governance_chain": {"observer_fqn": "...", "judge_fqn": "...", "enforcer_fqn": "..."},
}
```

**Creation sequence**:
1. `admin_client.post("/api/v1/workspaces", name=f"j{NN}-test-{hash}-ws-primary")`
2. Create namespace
3. `register_full_agent(...)` for executor/observer/judge/enforcer
4. Attach `default-allow` policy to executor
5. `create_governance_chain(...)` binding observer → judge → enforcer

**Teardown**: Registered via `request.addfinalizer` at creation time. Deletes by `workspace_id` cascade.

### `published_agent(journey_id, admin_client, workspace_with_agents) → dict`

**Yields**:
```python
{
    "fqn": "j{NN}-test-{hash}-ns-ops:published-executor",
    "id": "...",
    "revision_id": "...",
    "certification_id": "...",
    "marketplace_listing_id": "...",
}
```

**Creation sequence**:
1. `register_full_agent(...)` with complete manifest (FQN, purpose ≥ 50 chars, approach, role type, visibility patterns)
2. Upload package (canned tarball fixture stored in `tests/e2e/journeys/fixtures/agent_package.tar.gz`)
3. Attach policy
4. `certify_agent(...)` — admin self-approves as reviewer
5. Publish to marketplace

### `workspace_with_goal_ready(journey_id, admin_client, workspace_with_agents) → dict`

**Yields**:
```python
{
    "workspace": {...},
    "goal": {
        "id": "...",
        "gid": "...",
        "state": "READY",
        "title": "Test goal for j{NN}",
    },
    "subscribed_agents": ["...:market-data-agent", "...:risk-analysis-agent", "...:client-advisory-agent", "...:notification-agent"],
}
```

**Creation sequence**: Start from `workspace_with_agents`, register 4 additional agents with distinct response-decision configs (3 relevant, 1 irrelevant), create a goal in READY state.

### `running_workload(journey_id, admin_client, workspace_with_agents) → dict`

**Yields**:
```python
{
    "workspace": {...},
    "fleet": {"id": "...", "name": "j{NN}-test-{hash}-fleet"},
    "active_executions": [{"id": "...", "status": "running", "checkpoint_count": 1}, ...],
    "warm_pool": {"size": 2, "available": 2, "hit_rate": 0.95},
    "queued_executions": [{"id": "...", "priority": 0}, ...],
}
```

**Creation sequence**: Seed a 3-agent fleet, start 2 long-running executions (mock LLM returns slow responses), let warm pool fill, queue 3 additional executions.

---

## 4. Narrative Report Row

The `narrative_report.py` pytest plugin emits one row per `@journey_step` / `with journey_step(...)` invocation:

```python
@dataclass
class JourneyStepRecord:
    journey_id: str                # "j01"
    test_nodeid: str               # "tests/e2e/journeys/test_j01_admin_bootstrap.py::test_admin_bootstrap_to_production"
    step_index: int                # 1, 2, 3, ...
    description: str               # "Admin logs in with temporary password"
    started_at: str                # ISO 8601
    duration_ms: int
    status: str                    # "passed" | "failed" | "skipped"
    error: str | None              # populated on failure (short message only; full traceback in pytest output)
```

Records are aggregated per-test into the `journeys-report.html` HTML report as an ordered narrative list per journey. On failure, the narrative stops at (and highlights) the failing step.

JUnit XML integration: each `JourneyStepRecord` becomes a nested `<testcase>` under the parent test so CI systems show step-level pass/fail.

---

## 5. Isolation Scope Naming Convention

**Prefix**: `j{NN}-test-{hash}-`

- `NN`: two-digit journey number (01–09)
- `hash`: 8-hex-char UUID4 slice, generated once per `JOURNEY_ID` at module import time (or per-test in parallel runs via fixture)

**Examples**:
- Workspace: `j02-test-a3f1b9c2-ws-primary`
- Namespace: `j02-test-a3f1b9c2-ns-finance`
- Agent FQN: `j02-test-a3f1b9c2-ns-finance:kyc-verifier`
- User email: `j02-test-a3f1b9c2-user-alice@e2e.test`
- Goal title: `j02-test-a3f1b9c2: Optimize KYC review flow`

**Scope filter** for reset endpoint: `name LIKE 'j%-test-%'` — inherits feature 071's `test-%` filter because `j01-test-%` matches `%test-%`.

**Parallel safety**: Two parallel workers running J02 get distinct `hash` values via `uuid4()` → distinct resource names → no collision.

---

## 6. Mock OAuth Server Seed State

Both mock servers (Google OIDC + GitHub OAuth) run in the `platform` namespace with services `mock-google-oidc:8080` and `mock-github-oauth:8080`. Each has an in-memory seed of test users that journey tests can reference by email:

**Google OIDC mock users** (see contracts/oauth-mock.md for endpoint details):
```
j-admin@company.com         → sub: "google-admin-001"
j-creator@company.com       → sub: "google-creator-001"
j-consumer@company.com      → sub: "google-consumer-001"
```

**GitHub OAuth mock users**:
```
j-admin-gh                  → id: 1001, email: j-admin@company.com
j-creator-gh                → id: 1002, email: j-creator@company.com
```

Mock servers retain no persistent state. Restarting a mock pod clears state; seed users are recreated on pod startup from a ConfigMap.

---

## 7. No Schema Changes

This feature introduces **zero** Alembic migrations, **zero** new tables, **zero** new columns, **zero** new enum values, **zero** new Kafka topics. All assertions are against existing schemas and topics from prior features.
