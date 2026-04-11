# Implementation Plan: Interactions and Conversations

**Branch**: `024-interactions-conversations` | **Date**: 2026-04-11 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/024-interactions-conversations/spec.md`

## Summary

Build the `interactions/` bounded context within `apps/control-plane/src/platform/`. This covers conversation CRUD (workspace-scoped, soft-delete), bounded interactions with an 8-state machine (initializing/ready/running/waiting/paused/completed/failed/canceled), causal message ordering via self-referencing parent_message_id DAG, mid-process message injection, workspace goal messages (super-context for context engineering), attention requests (out-of-band agent urgency signals on `interaction.attention` topic), conversation branching (copy-on-branch strategy) and merging (append with conflict flag), participant management, and 3 internal interfaces consumed by context engineering and WebSocket gateway. Storage: PostgreSQL (8 tables). Events on 3 Kafka topics: `interaction.events` (6 types), `workspace.goal` (2 types), `interaction.attention` (1 type).

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+ (event producer on 3 topics)  
**Storage**: PostgreSQL (8 tables: conversations, interactions, interaction_messages, interaction_participants, workspace_goal_messages, conversation_branches, branch_merge_records, attention_requests)  
**Testing**: pytest 8.x + pytest-asyncio  
**Target Platform**: Linux server, Kubernetes `platform-control` namespace (`api` profile for endpoints)  
**Performance Goals**: Conversation + interaction creation ≤ 300ms (SC-001); message injection ≤ 200ms (SC-002); real-time event ≤ 500ms (SC-003); 100 concurrent interactions/workspace zero corruption (SC-004); goal messages available ≤ 1s (SC-005)  
**Constraints**: Test coverage ≥ 95%; all async; ruff + mypy --strict; state machine transitions deterministic and validated; causal DAG enforced; message limit per conversation enforced atomically  
**Scale/Scope**: 6 user stories, 22 FRs, 10 SCs, 24 REST endpoints + 3 internal interfaces, 8 PostgreSQL tables, 3 Kafka topics, 9 event types

## Constitution Check

| Gate | Status | Notes |
|------|--------|-------|
| Python 3.12+ | PASS | §2.1 mandated |
| FastAPI 0.115+ | PASS | §2.1 mandated |
| Pydantic v2 for all schemas | PASS | §2.1 mandated |
| SQLAlchemy 2.x async only | PASS | §2.1 mandated — 8 PostgreSQL tables |
| All code async | PASS | Coding conventions: "All code is async" |
| Bounded context structure | PASS | models, schemas, service, repository, router, events, exceptions, dependencies, state_machine |
| No cross-boundary DB access | PASS | §IV — goal lifecycle via in-process workspaces_service; agent identity via registry_service |
| Canonical EventEnvelope | PASS | All events on 3 topics use EventEnvelope from feature 013 |
| CorrelationContext everywhere | PASS | Events carry workspace_id + interaction_id + goal_id in CorrelationContext |
| Repository pattern | PASS | `InteractionsRepository` (SQLAlchemy) in repository.py |
| Kafka for async events (not DB polling) | PASS | §III — 3 topics, 9 event types |
| Alembic for PostgreSQL schema changes | PASS | migration 009_interactions_conversations for all 8 tables |
| ClickHouse for OLAP/time-series | N/A | No OLAP analytics in this bounded context |
| No PostgreSQL for rollups | N/A | No rollups |
| Qdrant for vector search | N/A | No vector operations |
| Redis for caching | N/A | No caching needed; all state is authoritative in PostgreSQL |
| OpenSearch | N/A | No full-text search |
| No PostgreSQL FTS | N/A | No FTS use case |
| Neo4j for graph traversal | N/A | Causal message DAG is simple parent_message_id FK, not a graph traversal use case |
| ruff 0.7+ | PASS | §2.1 mandated |
| mypy 1.11+ strict | PASS | §2.1 mandated |
| pytest + pytest-asyncio 8.x | PASS | §2.1 mandated |
| Secrets not in LLM context | PASS | §XI — no LLM calls in this bounded context |
| Zero-trust visibility | PASS | §IX — workspace-scoped access control on all operations (FR-019) |
| Goal ID as first-class correlation | PASS | §X — goal_id is a first-class field on Interaction model and in CorrelationContext |
| Modular monolith (no HTTP between contexts) | PASS | §I — 3 internal interfaces are in-process function calls |
| Attention pattern (out-of-band) | PASS | §XIII — `interaction.attention` Kafka topic, distinct from operational alerts |
| APScheduler for background tasks | N/A | No background tasks in this bounded context |

**All 24 applicable constitution gates PASS.**

## Project Structure

### Documentation (this feature)

```text
specs/024-interactions-conversations/
├── plan.md                          # This file
├── spec.md                          # Feature specification
├── research.md                      # Phase 0 decisions (12 decisions)
├── data-model.md                    # Phase 1 — SQLAlchemy models, Pydantic schemas, service signatures
├── quickstart.md                    # Phase 1 — run/test guide
├── contracts/
│   └── interactions-api.md          # REST API contracts (24 endpoints + 3 internal interfaces)
└── tasks.md                         # Phase 2 — generated by /speckit.tasks
```

### Source Code

```text
apps/control-plane/
├── src/platform/
│   └── interactions/
│       ├── __init__.py
│       ├── models.py                          # SQLAlchemy: 8 models + enums + state machine transitions
│       ├── schemas.py                         # Pydantic: all request/response schemas
│       ├── service.py                         # InteractionsService — conversation/interaction/message/goal/branch/attention
│       ├── repository.py                      # InteractionsRepository — SQLAlchemy CRUD for all 8 tables
│       ├── router.py                          # FastAPI router: /api/v1/interactions/* (24 endpoints)
│       ├── events.py                          # Event payload types + publish_* helpers for 3 topics
│       ├── exceptions.py                      # InteractionError, InvalidStateTransitionError, MessageLimitError, etc.
│       ├── dependencies.py                    # get_interactions_service DI factory
│       └── state_machine.py                   # INTERACTION_TRANSITIONS dict + validate_transition()
├── migrations/
│   └── versions/
│       └── 009_interactions_conversations.py  # Alembic: 8 tables + indexes
└── tests/
    ├── unit/
    │   ├── test_int_state_machine.py          # State transition validation: valid/invalid/terminal
    │   ├── test_int_causal_ordering.py        # Parent message ID validation, DAG correctness
    │   ├── test_int_schemas.py                # Pydantic validation tests
    │   └── test_int_branching.py              # Branch copy logic, merge conflict detection
    └── integration/
        ├── test_int_conversation_lifecycle.py # Conversation CRUD + interaction lifecycle + messages
        ├── test_int_goal_messages.py          # Goal message posting, listing, rejection on completed goals
        ├── test_int_attention.py              # Attention request create, list, resolve, dismiss
        ├── test_int_branching_merging.py      # Full branch→send→merge pipeline, conflict flag
        └── test_int_concurrency.py            # Concurrent interaction message isolation, state transitions
```

## Implementation Phases

### Phase 1 — Setup & Package Structure
- Create `src/platform/interactions/` package with all module stubs
- Alembic migration `009_interactions_conversations.py`: all 8 tables + indexes + self-referencing FK on `interaction_messages.parent_message_id` + cascade deletes on conversations

### Phase 2 — US1: Conversation and Interaction Lifecycle (P1)
- `models.py`: all 8 SQLAlchemy models + enums (`InteractionState`, `MessageType`, `ParticipantRole`, `BranchStatus`, `AttentionUrgency`, `AttentionStatus`)
- `state_machine.py`: `INTERACTION_TRANSITIONS` dict + `validate_transition(current_state, trigger) → InteractionState` (raises `InvalidStateTransitionError`)
- `schemas.py`: `ConversationCreate/Update/Response`, `InteractionCreate/Response`, `InteractionTransition`, `MessageCreate/Inject/Response`, `ParticipantAdd/Response`
- `exceptions.py`: `InteractionError`, `InvalidStateTransitionError`, `ConversationNotFoundError`, `InteractionNotFoundError`, `MessageNotInInteractionError`, `MessageLimitReachedError`, `InteractionNotAcceptingMessagesError`
- `repository.py`: `InteractionsRepository` — CRUD for conversations, interactions, messages, participants + `increment_message_count()` (atomic with limit check) + `get_messages_by_interaction()` + `validate_parent_message()`
- `service.py`: `create_conversation()`, `get_conversation()`, `list_conversations()`, `update_conversation()`, `delete_conversation()`; `create_interaction()`, `get_interaction()`, `list_interactions()`, `transition_interaction()` (validate via state_machine, emit lifecycle events); `send_message()` (validate interaction state, validate parent_message_id, increment count atomically), `inject_message()` (auto-set parent to latest agent message, set type=injection), `list_messages()`; `add_participant()`, `remove_participant()`, `list_participants()`
- `events.py`: `InteractionStartedPayload`, `InteractionCompletedPayload`, `InteractionFailedPayload`, `InteractionCanceledPayload`, `MessageReceivedPayload` + publish helpers on `interaction.events` topic
- `router.py`: Endpoints 1-15 (conversations CRUD, interactions CRUD, messages, participants)

### Phase 3 — US2: Workspace Goals and Goal Messages (P1)
- `schemas.py`: `GoalMessageCreate/Response`
- `repository.py`: `create_goal_message()`, `list_goal_messages()`, `get_goal_messages_for_context()`
- `service.py`: `post_goal_message()` (verify goal is active via in-process `workspaces_service.get_goal()`, reject if completed/abandoned, emit `goal.message.posted` event), `list_goal_messages()`, `get_goal_messages()` (internal interface)
- `events.py`: `GoalMessagePostedPayload`, `GoalStatusChangedPayload` + publish helpers on `workspace.goal` topic
- `router.py`: Endpoints 16-17 (POST/GET goal messages)

### Phase 4 — US3: Attention Requests (P1)
- `schemas.py`: `AttentionRequestCreate/Response`, `AttentionResolve`
- `repository.py`: `create_attention_request()`, `list_attention_requests()`, `update_attention_status()`
- `service.py`: `create_attention_request()` (persist + emit `attention.requested` event on `interaction.attention` topic), `list_attention_requests()`, `resolve_attention_request()` (transition status: pending → acknowledged/resolved/dismissed)
- `router.py`: Endpoints 22-24 (POST/GET/resolve attention)

### Phase 5 — US4: Branching and Merging (P2)
- `schemas.py`: `BranchCreate`, `BranchMerge`, `BranchResponse`, `MergeRecordResponse`
- `repository.py`: `create_branch()`, `copy_messages_up_to()` (deep copy with remapped UUIDs and parent references), `merge_branch_messages()` (append post-branch messages into parent), `create_merge_record()`, `update_branch_status()`, `check_prior_merges_from_same_point()`
- `service.py`: `create_branch()` (create new interaction + copy messages + create ConversationBranch), `merge_branch()` (copy post-branch messages, detect conflict if >1 merge from same point, create BranchMergeRecord, emit `branch.merged` event), `abandon_branch()` (mark abandoned), `list_branches()`
- `events.py`: `BranchMergedPayload` + publish helper
- `router.py`: Endpoints 18-21 (branch CRUD, merge, abandon)

### Phase 6 — US5+US6: Subscriptions, Concurrency, Internal Interfaces (P2/P3)
- `service.py`: `get_conversation_history()` (internal interface), `check_subscription_access()` (internal interface — verify workspace membership + conversation/interaction ownership)
- `dependencies.py`: `get_interactions_service()` DI factory

### Phase 7 — Polish & Cross-Cutting Concerns
- Mount interactions router in `src/platform/api/__init__.py`
- Full test coverage audit (≥ 95%)
- ruff + mypy --strict clean run

## Key Decisions (from research.md)

1. **8 PostgreSQL tables**: One table per entity — no JSONB message embedding; self-referencing parent_message_id FK for causal DAG
2. **State machine**: Dict-based `(current_state, trigger) → next_state` — consistent with feature 021 lifecycle pattern; terminal states have no outbound transitions
3. **Causal ordering**: Parent message ID DAG (nullable FK), supports branching within conversations; validated on write (parent must belong to same interaction)
4. **Goal messages owned by interactions BC**: Goal lifecycle (create, status) is workspaces BC; goal messages (conversational content) are interactions BC; split avoids cross-boundary ownership confusion
5. **Attention requests persisted**: Stored in `attention_requests` table (not just published); supports query "my pending requests" for offline targets
6. **Copy-on-branch**: Deep copy messages up to branch point; branch is fully self-contained; simpler than shared-history
7. **Merge conflict detection**: Flag when >1 branch merged from same point; user resolves (no automatic semantic merge)
8. **3 Kafka topics**: `interaction.events` (keyed by interaction_id), `workspace.goal` (keyed by workspace_id), `interaction.attention` (keyed by target_identity) — matches constitution event topology
9. **No WebSocket handling**: Publishes events only; WebSocket gateway (feature 019) handles distribution and subscriptions
10. **Message count enforcement**: Atomic `UPDATE ... SET message_count = message_count + 1 WHERE message_count < limit RETURNING message_count` — race-free
11. **3 internal interfaces**: `get_goal_messages()`, `get_conversation_history()`, `check_subscription_access()` — in-process, no HTTP
12. **Migration 009**: Sequential after 008_memory_knowledge; depends on workspaces FK from feature 018
