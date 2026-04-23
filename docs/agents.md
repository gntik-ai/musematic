# Agents

An **agent** is the unit of work in musematic. It is identified by a
[Fully Qualified Name](#fqn-validation) (`namespace:local_name`), declared
via a signed manifest, and versioned with immutable revisions. Agents are
registered into a workspace, certified, and made discoverable through the
marketplace.

This page is for **end users** — people who author and register agents.
For admin-level configuration (approvals, quotas, visibility defaults),
see [Administration](administration/index.md).

## Registering an agent

Agents are uploaded as packaged archives (tar.gz / zip) containing a
`manifest.yaml` (or `manifest.json`). The API endpoint is:

```http
POST /api/v1/registry/namespaces/{namespace}/agents/upload
Content-Type: multipart/form-data
```

The manifest is extracted from the package and validated against the
canonical `AgentManifest` schema before the package is persisted to S3
and indexed for marketplace search.

## Manifest schema

Declared in
[`apps/control-plane/src/platform/registry/schemas.py`][schemas] as the
`AgentManifest` Pydantic model. Fields alphabetised:

| Field | Type | Required | Default | Purpose | Validation |
|---|---|---|---|---|---|
| `approach` | `str \| null` | — | `null` | How the agent implements its purpose. | Whitespace-trimmed. |
| `context_profile` | `object \| null` | — | `null` | Structured metadata (JSON) for domain-specific context config. | Free-form JSON object. |
| `custom_role_description` | `str \| null` | — * | `null` | Required if `role_types` contains `custom`. Describes the custom role. | Whitespace-trimmed. |
| `display_name` | `str \| null` | — | `null` | Human-readable name. | Whitespace-trimmed. |
| `local_name` | `str` | ✅ | — | Local identifier within its namespace. | `^[a-z][a-z0-9-]{1,62}$`. |
| `maturity_level` | `int` | — | `0` | Declared maturity. System may override after assessment. | `0`–`3`. |
| `purpose` | `str` | ✅ | — | What the agent does; affects marketplace ranking. | Minimum 50 characters. |
| `reasoning_modes` | `string[]` | — | `[]` | e.g. `["deterministic", "agentic"]`. | Whitespace-trimmed, empty items dropped. |
| `role_types` | `string[]` | ✅ | — | One or more agent roles. | At least one; see [Role types](#role-types). |
| `tags` | `string[]` | — | `[]` | Discovery tags. | Whitespace-trimmed, empty items dropped. |
| `version` | `str` | ✅ | — | Semantic version. | `^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$`. |

The schema uses Pydantic `ConfigDict(extra="forbid")` — **unknown fields
are rejected** at upload time.

### FQN validation

Every agent is addressed by its **fully qualified name**:

```
{namespace}:{local_name}
```

Both `namespace` and `local_name` must match:

```
^[a-z][a-z0-9-]{1,62}$
```

- Start with a lowercase letter
- 3–63 characters total (including the leading letter)
- Only lowercase alphanumerics and `-`
- Examples: `finance-ops`, `ai-services`, `kyc`

Full FQN examples:

- ✅ `finance-ops:kyc-verifier`
- ✅ `ai-services:sentiment-analyzer`
- ❌ `Finance:KYC` (uppercase)
- ❌ `ops:` (missing local_name)
- ❌ `ops:_priv` (must start with a letter)

The `:` separator and the slug pattern are enforced by the registry
router; the DB column `fqn` is `VARCHAR(127)` so a full FQN cannot exceed
127 characters.

### Role types

From [`apps/control-plane/src/platform/registry/models.py`][models], the
`AgentRoleType` enum:

| Role | Purpose |
|---|---|
| `executor` | Performs business actions; executes workflow steps. |
| `planner` | Produces an execution plan for a goal. |
| `orchestrator` | Coordinates other agents (fan-out, delegation). |
| `observer` | Watches system state without taking action; emits signals. |
| `judge` | Evaluates outputs against policy; part of the governance chain. |
| `enforcer` | Enforces rules; blocks or allows actions flagged by a judge. |
| `custom` | Domain-specific role. Requires `custom_role_description` set. |

An agent may declare **multiple** role types — e.g. a compliance agent
could carry both `judge` and `enforcer`.

### Maturity levels

Declared as `MaturityLevel` (IntEnum):

| Value | Name | Semantics |
|---|---|---|
| `0` | `unverified` | No assessment performed yet. |
| `1` | `basic_compliance` | Passes manifest + purpose compliance checks. |
| `2` | `tested` | Has an evaluation suite with passing results. |
| `3` | `certified` | Full certification (required for governance-chain roles). |

The system assesses maturity continuously — the value in the manifest is
a declaration that can be overridden upward by evidence (never downward
without explicit revocation).

### Lifecycle

Stored on `AgentProfile.status` (`LifecycleStatus`):

```
draft ─▶ validated ─▶ published ─▶ disabled
                                 └▶ deprecated ─▶ archived
```

`LifecycleTransitionRequest` (defined in the same schemas module)
is the payload for transitions.

## Visibility

Agents are **zero-trust by default** (constitutional principle IX and
[spec 053][s053]): a newly registered agent sees no other agents and no
tools until visibility is explicitly granted.

Visibility is configured via `PATCH /api/v1/registry/agents/{id}` with
`AgentPatch`:

```json
{
  "visibility_agents": ["finance:*", "shared:ocr-tool"],
  "visibility_tools": ["shared-tools:*"]
}
```

Patterns use the FQN format with optional wildcards:

- Exact: `"finance:kyc-verifier"`
- Namespace wildcard: `"finance:*"`
- Full wildcard: `"*"`
- Multiple patterns union: `["finance:*", "ai-services:analyzer-*"]`

Workspace-level grants can override per-agent defaults — see
[Administration › RBAC & Permissions](administration/rbac-and-permissions.md).

## Three worked examples

The following examples are taken from fixtures and integration tests in
this repo. Adapt them by replacing `local_name`, `purpose`, and
namespace references as needed.

### Example 1 — simple executor

The minimum viable manifest: required fields only, no visibility
overrides, a single role.

Source: [`apps/control-plane/tests/registry_support.py`][ex1]
(`build_manifest_payload()`).

```yaml
# manifest.yaml — finance:kyc-verifier v1.0.0
local_name: kyc-verifier
version: 1.0.0
purpose: >
  Verifies customer identity documents against government databases and
  returns KYC compliance status with confidence scores.
role_types:
  - executor
approach: >
  Reads the manifest, checks evidence, and emits a verdict.
maturity_level: 1
reasoning_modes:
  - deterministic
tags:
  - kyc
  - finance
display_name: KYC Verifier
```

Upload:

```bash
# Package the manifest + any agent code into a tarball
tar -czf kyc-verifier-1.0.0.tar.gz manifest.yaml agent.py

# Upload (multipart)
curl -X POST "http://localhost:8000/api/v1/registry/namespaces/finance/agents/upload" \
  -H "Authorization: Bearer $TOKEN" \
  -F "package=@kyc-verifier-1.0.0.tar.gz"
```

Expected response (201 Created):

```json
{
  "id": "a3f1...",
  "fqn": "finance:kyc-verifier",
  "status": "draft",
  "revision": {
    "version": "1.0.0",
    "sha256_digest": "d34db33f...",
    "storage_key": "agent-packages/..."
  }
}
```

---

### Example 2 — orchestrator with visibility patterns

An agent that delegates work to other agents. Registered with a basic
manifest, then patched with visibility patterns and a workspace grant.

Source: [`apps/control-plane/tests/integration/test_registry_discovery.py`][ex2]
(the `Requester Router` fixture).

```yaml
# manifest.yaml — ai-services:router v1.0.0
local_name: router
version: 1.0.0
purpose: >
  Routes delegated work to registry agents via availability and
  capability matching.
role_types:
  - orchestrator
approach: >
  Delegates and aggregates agent responses based on visibility grants.
maturity_level: 1
reasoning_modes:
  - deterministic
tags:
  - orchestration
  - routing
  - gateway
display_name: Requester Router
```

After registration, grant visibility:

```bash
curl -X PATCH "http://localhost:8000/api/v1/registry/agents/${AGENT_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "visibility_agents": ["finance:*", "ai-services:analyzer-*"],
    "visibility_tools": ["shared-tools:*"]
  }'
```

The router now sees every agent in `finance:*` and any agent whose local
name begins with `analyzer-` in `ai-services:*`. It can invoke any tool
in the `shared-tools:*` namespace.

---

### Example 3 — governance judge + enforcer

An agent carrying dual governance roles. Requires
`maturity_level: 3` (certified) after assessment to participate in an
Observer→Judge→Enforcer chain.

Pattern from
[`apps/control-plane/tests/integration/test_registry_visibility.py`][ex3]
(hidden Judge agent), extended with a `custom_role_description` and a
structured `context_profile`.

```yaml
# manifest.yaml — governance:decision-judge v1.0.0
local_name: decision-judge
version: 1.0.0
purpose: >
  Performs governance evaluation of agent outputs against organisational
  compliance rubrics and behavioural contracts. Scores decisions and
  gates risky operations.
role_types:
  - judge
  - enforcer
approach: |
  Applies deterministic scoring against policy rubrics.
  Blocks outputs failing compliance gates.
  Emits audit log entries for every judgment.
maturity_level: 2          # Declared; system assessment may raise to 3
reasoning_modes:
  - deterministic
  - policy-guided
context_profile:
  behavioral_contract_required: true
  min_confidence_threshold: 0.85
  audit_level: full
tags:
  - governance
  - compliance
  - judge
  - behavioral-contract
display_name: Compliance Judge
# custom_role_description is optional here because role_types does not
# include "custom". If it did, this field would be REQUIRED.
```

After certification, configure visibility to see every agent it must
judge and the policy + audit tool surface:

```bash
curl -X PATCH "http://localhost:8000/api/v1/registry/agents/${AGENT_ID}" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "visibility_agents": ["*"],
    "visibility_tools": ["policy:*", "audit:*"]
  }'
```

Wire it into a governance chain in a workspace (see
[spec 061][s061] for the binding API):

```bash
curl -X POST "http://localhost:8000/api/v1/trust/governance-chains" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "...",
    "observer_fqn": "governance:activity-observer",
    "judge_fqn":    "governance:decision-judge",
    "enforcer_fqn": "governance:decision-judge"
  }'
```

In this chain the same agent fills both `judge` and `enforcer` roles —
valid because its `role_types` includes both.

---

## Registering, testing, and debugging

1. **Register** — upload the manifest + package; status becomes `draft`.
2. **Validate** — the system runs compliance checks on manifest + purpose
   length; status advances to `validated`.
3. **Publish** — explicit call moves the agent to `published`. It appears
   in the marketplace.
4. **Test** — create an evaluation suite (see
   [spec 034][s034]) with trajectory scorers and LLM-as-Judge.
5. **Debug** — use the reasoning trace viewer in the web UI. Every
   execution emits a trace persisted per
   [spec 064][s064]; traces show the task plan, step-by-step tool
   selections, and parameter provenance.

## Common pitfalls

- **`purpose` must be at least 50 characters.** Short purposes are
  rejected with `ValidationError: purpose — ensure this value has at
  least 50 characters`.
- **`local_name` must start with a lowercase letter.** `2fa-agent` is
  rejected; `two-factor-agent` is fine.
- **`version` must be semver.** `1.0` and `v1.0.0` are rejected;
  `1.0.0` and `1.0.0-rc.1` are accepted.
- **`custom_role_description` is mandatory if and only if
  `role_types` contains `"custom"`.** Including it without `custom` is
  silently accepted; omitting it with `custom` is rejected.
- **Unknown fields are forbidden.** Typos like `purposee` or
  `role_type` (singular) are rejected with
  `ValidationError: Extra inputs are not permitted`.
- **Zero-trust bites on first invocation.** A newly registered agent
  sees nothing. Grant visibility via `PATCH` before wiring it into a
  workflow.

[schemas]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/registry/schemas.py
[models]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/registry/models.py
[ex1]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/tests/registry_support.py
[ex2]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/tests/integration/test_registry_discovery.py
[ex3]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/tests/integration/test_registry_visibility.py
[s034]: https://github.com/gntik-ai/musematic/tree/main/specs/034-evaluation-semantic-testing
[s053]: https://github.com/gntik-ai/musematic/tree/main/specs/053-zero-trust-visibility
[s061]: https://github.com/gntik-ai/musematic/tree/main/specs/061-judge-enforcer-governance
[s064]: https://github.com/gntik-ai/musematic/tree/main/specs/064-reasoning-modes-and-trace
