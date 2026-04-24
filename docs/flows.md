# Flows

A **flow** (or **workflow**) in musematic is a directed acyclic graph of
steps that agents execute to reach a goal. Flows are declared in YAML,
compiled to an intermediate representation, and executed by the workflow
engine ([spec 029][s029]) with an append-only execution journal,
durable dispatch leases, and checkpoint-based resume.

This page is for **end users** — people who author and run flows. For
admin-level configuration of triggers, quotas, and approval gates, see
[Administration](administration/index.md).

## Anatomy of a workflow

A workflow definition has two nesting levels:

```yaml
schema_version: 1          # required, const 1
workflow_id: string        # optional, internal identifier
steps:                     # required, minItems 1
  - id: step_identifier
    step_type: agent_task | tool_call | approval_gate | parallel_fork | parallel_join | conditional
    # …step-specific fields…
```

The full JSON Schema is at
[`apps/control-plane/src/platform/workflows/schemas/v1.json`][jsonschema].
The compiler is
[`apps/control-plane/src/platform/workflows/compiler.py`][compiler] — it
parses YAML, validates against the schema, checks that `depends_on`
references exist, rejects cycles, and emits a typed `WorkflowIR`.

## Creating a workflow

```http
POST /api/v1/workflows
Content-Type: application/json
```

Body per `WorkflowCreate` (from
[`apps/control-plane/src/platform/workflows/schemas.py`][pyschemas]):

| Field | Type | Required | Purpose |
|---|---|---|---|
| `name` | `str` (1–200) | ✅ | Display name. |
| `description` | `str \| null` | — | Free-text description. |
| `yaml_source` | `str` | ✅ | The raw YAML of the workflow definition. |
| `change_summary` | `str \| null` | — | Commit-message-style summary. |
| `tags` | `string[]` | — | Discovery tags. |
| `workspace_id` | `UUID` | ✅ | Owning workspace. |

## Step shape

Every `steps[]` entry supports the following fields. The required set
depends on `step_type` — see [Step types](#step-types).

| Field | Type | Required | Default | Purpose |
|---|---|---|---|---|
| `agent_fqn` | `string` | conditional | — | FQN of the agent to invoke (required for `agent_task`). |
| `approval_config` | `object \| null` | conditional | `null` | Required for `approval_gate`. See below. |
| `compensation_handler` | `string \| null` | — | `null` | Handler name to invoke on undo. |
| `condition_expression` | `string \| null` | — | `null` | JSONPath / expression evaluated for `conditional` steps. |
| `context_budget_tokens` | `integer \| null` | — | `null` | Per-step context budget in tokens (≥ 1). |
| `depends_on` | `string[]` | — | `[]` | Step IDs that must complete before this step runs. |
| `id` | `string` | ✅ | — | Step identifier, unique in this workflow. |
| `input_bindings` | `object` | — | `{}` | Map of `{input_name: path_expression}` (e.g. `"invoice_id": "$.payload.invoice_id"`). |
| `output_schema` | `object \| null` | — | `null` | JSON Schema that the step output must satisfy. |
| `parallel_group` | `string \| null` | — | `null` | Group label for parallel execution. |
| `reasoning_mode` | `string \| null` | — | `null` | e.g. `"deep"`, `"fast"` — routes to the reasoning engine. |
| `retry_config` | `object \| null` | — | `null` | Retry policy; see below. |
| `step_type` | `string` | ✅ | — | One of the allowed step types. |
| `timeout_seconds` | `integer \| null` | — | `null` | Per-step hard timeout (≥ 1). |
| `tool_fqn` | `string` | conditional | — | FQN of the tool to invoke (required for `tool_call`). |

### `retry_config`

```yaml
retry_config:
  max_retries: 3                          # default 3, minimum 0
  backoff_strategy: exponential           # fixed | exponential | linear, default fixed
  base_delay_seconds: 5.0                 # default 5.0
  max_delay_seconds: 300.0                # default 300.0
  retry_on_event_types: [failed]          # event types that trigger retry
```

### `approval_config`

```yaml
approval_config:
  required_approvers: [ops]               # required, non-empty list
  timeout_seconds: 86400                  # default 86400 (24h)
  timeout_action: fail                    # fail | skip | escalate, default fail
```

## Step types

Declared in the v1 JSON Schema (`steps[].step_type` enum):

| Type | Requires | Purpose |
|---|---|---|
| `agent_task` | `agent_fqn` | Invoke a registered agent by FQN. |
| `tool_call` | `tool_fqn` | Invoke a tool through the tool gateway. |
| `approval_gate` | `approval_config` | Pause until human approval. |
| `parallel_fork` | — | Begin a parallel-execution group. |
| `parallel_join` | — | Synchronise a parallel group. |
| `conditional` | `condition_expression` | Branch based on expression result. |

Parallel execution is also expressible implicitly through the
dependency graph — two steps with the same `depends_on` and no
dependency between them run in parallel automatically.

## Trigger types

Declared in
[`apps/control-plane/src/platform/workflows/models.py`][wfmodels] as the
`TriggerType` enum. Seven triggers:

| Trigger | Purpose |
|---|---|
| `api` | Direct programmatic invocation via `POST /api/v1/executions`. |
| `cron` | Timezone-aware recurring schedule. |
| `event_bus` | Matching event on a subscribed Kafka topic. |
| `manual` | UI-initiated run. |
| `orchestrator` | Parent workflow / fleet invokes a child workflow. |
| `webhook` | External HTTP POST to a workflow-specific webhook endpoint. |
| `workspace_goal` | New or updated goal in a workspace. |

## Execution state machine

Declared as `ExecutionStatus` in
[`apps/control-plane/src/platform/execution/models.py`][execmodels]:

```
queued ──▶ running ──▶ waiting_for_approval ──▶ queued (after approval)
                                              └▶ failed (timeout)
   │           │                               
   │           ├──▶ completed (terminal)
   │           ├──▶ failed (terminal)
   │           └──▶ compensating ──▶ (terminal)
   └──▶ canceled (terminal)
```

Checkpoint-based resume ([spec 063][s063]) creates a new execution
whose `parent_execution_id` points at the original.

### Event journal

Every transition emits an event. Declared as `ExecutionEventType`:

- Lifecycle: `created`, `queued`, `dispatched`, `runtime_started`,
  `sandbox_requested`, `completed`, `failed`, `canceled`
- Approval: `waiting_for_approval`, `approved`, `rejected`, `approval_timed_out`
- Resumption: `resumed`, `retried`, `reprioritized`, `hot_changed`
- Compensation: `compensated`, `compensation_failed`
- Reasoning: `reasoning_trace_emitted`, `self_correction_started`, `self_correction_converged`
- Context: `context_assembled`

The journal is **append-only** (constitutional principle V) — state is
projected from events, never mutated in place.

## Running a workflow

```http
POST /api/v1/executions
Content-Type: application/json
```

Body per `ExecutionCreate` (from
[`apps/control-plane/src/platform/execution/schemas.py`][execschemas]):

```json
{
  "workflow_definition_id": "UUID",
  "workflow_version_id": "UUID | null",
  "trigger_type": "manual",
  "input_parameters": { "invoice_id": "INV-42" },
  "workspace_id": "UUID",
  "correlation_conversation_id": null,
  "correlation_interaction_id": null,
  "correlation_fleet_id": null,
  "correlation_goal_id": null,
  "trigger_id": null,
  "sla_deadline": null
}
```

Correlation fields propagate through every downstream event (principle X;
see [GID correlation envelope][s052]).

## Three worked examples

### Example 1 — simple linear flow

A single-step workflow that invokes an agent. Minimum viable.

Source: [`apps/control-plane/tests/integration/workflows/test_workflow_crud.py`][ex1]
(lines 23–29).

```yaml
# simple-fetch.yaml
schema_version: 1
steps:
  - id: fetch_invoice
    step_type: agent_task
    agent_fqn: finance:fetcher
```

Register and run:

```bash
curl -X POST http://localhost:8000/api/v1/workflows \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "simple-fetch",
    "yaml_source": "'"$(cat simple-fetch.yaml | sed 's/\"/\\\"/g')"'",
    "workspace_id": "'$WS_ID'"
  }'
```

---

### Example 2 — branching flow with an approval gate

Data flows through a fetch agent, then a human approval, then publishes.

Source: [`apps/control-plane/tests/integration/workflows/test_workflow_crud.py`][ex1]
(lines 43–56).

```yaml
# approved-publish.yaml
schema_version: 1
steps:
  - id: fetch_invoice
    step_type: agent_task
    agent_fqn: finance:fetcher

  - id: approve_invoice
    step_type: approval_gate
    depends_on: [fetch_invoice]
    approval_config:
      required_approvers: [ops]
      timeout_seconds: 3600        # 1h
      timeout_action: fail         # fail the whole execution on timeout
```

Semantics:

- `fetch_invoice` runs first; its output becomes available for downstream
  steps via `input_bindings` (see next example).
- `approve_invoice` pauses the execution. The engine emits
  `waiting_for_approval` and the configured approvers receive a
  notification.
- Approvers act through the UI or the approval API. Approval advances
  the execution; rejection or timeout ends it.

---

### Example 3 — multi-step orchestration with compensation

Three steps in sequence with a compensation handler on the first step.
Demonstrates the saga pattern: if any downstream step fails, the engine
triggers `compensation_handler` for every completed step in reverse
order.

Source: [`apps/control-plane/tests/integration/execution/test_hot_change_compensation.py`][ex3]
(lines 24–39).

```yaml
# compensation-pipeline.yaml
schema_version: 1
steps:
  - id: step_a
    step_type: agent_task
    agent_fqn: ops:fetch
    compensation_handler: undo_step_a

  - id: step_b
    step_type: tool_call
    tool_fqn: ops:transform
    depends_on: [step_a]

  - id: step_c
    step_type: tool_call
    tool_fqn: ops:publish
    depends_on: [step_b]
```

Behavior:

- If `step_c` fails and retries are exhausted, execution transitions to
  `compensating`.
- The engine calls `undo_step_a` to roll back `step_a`'s side effects.
- `step_b` has no `compensation_handler` — tool calls through the
  gateway are expected to be idempotent, so undo is implicit.
- Final state: `failed` (with compensation recorded in the journal).

### Bonus — parallel review pattern

Two independent reviewers run in parallel after a fetch, gated on an
approval before publishing. No explicit `parallel_fork`/`parallel_join`
needed — the DAG makes parallelism explicit.

```yaml
schema_version: 1
steps:
  - id: fetch_data
    step_type: agent_task
    agent_fqn: data:fetcher

  - id: review_compliance
    step_type: agent_task
    agent_fqn: reviewers:compliance
    depends_on: [fetch_data]

  - id: review_security
    step_type: agent_task
    agent_fqn: reviewers:security
    depends_on: [fetch_data]

  - id: final_approval
    step_type: approval_gate
    depends_on: [review_compliance, review_security]
    approval_config:
      required_approvers: [admin]
      timeout_seconds: 3600
      timeout_action: fail

  - id: publish
    step_type: tool_call
    tool_fqn: storage:publish
    depends_on: [final_approval]
```

The engine runs `review_compliance` and `review_security` concurrently
because they share their only dependency (`fetch_data`) and do not
depend on each other.

---

## Observability

Every step emits OpenTelemetry spans with shared attributes: `workspace_id`,
`conversation_id`, `interaction_id`, `execution_id`, `goal_id` (the GID
correlation envelope — [spec 052][s052]). Reasoning traces are recorded
through the reasoning engine and surfaced via
`reasoning_trace_emitted` events (see [spec 064][s064]).

Real-time progress streams over the WebSocket hub — subscribe to the
`execution.*` channel for the execution ID.

## Error handling & retries

- `retry_config.max_retries` bounds retries per step.
- `retry_config.backoff_strategy` controls the delay curve.
- Steps with `compensation_handler` are rolled back in reverse order on
  terminal failure.
- Approval timeouts follow `approval_config.timeout_action`:
  - `fail` — end the execution with `failed`.
  - `skip` — continue past the approval gate.
  - `escalate` — raise a new approval to the next tier
    (TODO(andrea): confirm escalation wiring location in `workflows/models.py`).

[jsonschema]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/workflows/schemas/v1.json
[pyschemas]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/workflows/schemas.py
[wfmodels]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/workflows/models.py
[execmodels]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/execution/models.py
[execschemas]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/execution/schemas.py
[compiler]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/src/platform/workflows/compiler.py
[ex1]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/tests/integration/workflows/test_workflow_crud.py
[ex3]: https://github.com/gntik-ai/musematic/blob/main/apps/control-plane/tests/integration/execution/test_hot_change_compensation.py
[s029]: https://github.com/gntik-ai/musematic/tree/main/specs/029-workflow-execution-engine
[s052]: https://github.com/gntik-ai/musematic/tree/main/specs/052-gid-correlation-envelope
[s063]: https://github.com/gntik-ai/musematic/tree/main/specs/063-reprioritization-and-checkpoints
[s064]: https://github.com/gntik-ai/musematic/tree/main/specs/064-reasoning-modes-and-trace
