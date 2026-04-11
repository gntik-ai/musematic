# Research: Interactions and Conversations

**Feature**: 024-interactions-conversations  
**Date**: 2026-04-11  
**Status**: Complete — all decisions resolved

---

## Decision 1: PostgreSQL Tables — Schema Design

**Decision**: 8 tables in migration `009_interactions_conversations.py`:
1. `conversations` — workspace-scoped container with soft delete
2. `interactions` — bounded unit within a conversation, with state machine and optional goal_id FK
3. `interaction_messages` — causal DAG via self-referencing `parent_message_id` FK
4. `interaction_participants` — agent/user linkage with role and timestamps
5. `workspace_goal_messages` — goal super-context entries (FK to workspaces.goals from feature 018)
6. `conversation_branches` — fork metadata linking parent/branch interactions and branch-point message
7. `branch_merge_records` — merge documentation with conflict flag
8. `attention_requests` — out-of-band agent urgency signals with status machine

**Rationale**: Each entity maps cleanly to a table. The causal DAG (parent_message_id) is a self-referencing FK on `interaction_messages` — no recursive CTE needed for reads (we reconstruct the DAG client-side or use a simple depth-limited query). Workspace goals are already modeled in the workspaces bounded context (feature 018) — `workspace_goal_messages` is this bounded context's table that references the workspace goal (goal_id), not a duplicate of the goal itself.

**Alternatives considered**:
- Embedding messages as JSONB array in interactions: loses query flexibility, pagination, and individual message addressing.
- Separate table per message type (user, agent, system, injection): premature split — `message_type` enum column is simpler and sufficient.

---

## Decision 2: Interaction State Machine — Dict-Based Transitions

**Decision**: State machine uses a Python dict mapping `(current_state, trigger) → next_state`. States: `initializing`, `ready`, `running`, `waiting`, `paused`, `completed`, `failed`, `canceled`. Transitions are validated in-process before any DB update — invalid transitions raise `InvalidStateTransitionError`.

**Rationale**: Consistent with feature 021's lifecycle state machine pattern (dict-based). No external library needed for 8 states with well-defined transitions. Terminal states (`completed`, `failed`, `canceled`) have no outbound transitions.

Valid transitions:
```
initializing → ready
ready → running, canceled
running → waiting, paused, completed, failed, canceled
waiting → running, paused, canceled
paused → running, canceled
```

**Alternatives considered**:
- State machine library (transitions, python-statemachine): overkill for a simple transition table; adds dependency for no benefit.
- PostgreSQL CHECK constraint on state transitions: cannot express transition rules in CHECK; would need triggers, which are harder to test and debug.

---

## Decision 3: Causal Ordering — Parent Message ID (DAG)

**Decision**: Each `InteractionMessage` has a nullable `parent_message_id` FK referencing another message in the same interaction. The first message in an interaction has `parent_message_id = NULL`. Subsequent messages reference the message they are responding to. This forms a directed acyclic graph (DAG). Mid-process injections reference the most recent agent message as their parent.

**Rationale**: DAG-based causal ordering is the standard pattern for threaded conversations (used by Slack, Discord, etc.). It's simpler than vector clocks or Lamport timestamps, supports branching within a conversation naturally, and is easy to reconstruct on the client side. The DAG is validated on write — `parent_message_id` must belong to the same interaction.

**Alternatives considered**:
- Sequential integer ordering (`sequence_number`): loses causal structure; can't represent reply-to relationships or injection points.
- Vector clocks: overkill for a single-process system; adds complexity without distributed consistency benefits.
- Lamport timestamps: same — unnecessary for a centralized database.

---

## Decision 4: Workspace Goals — Relationship to Feature 018

**Decision**: Workspace goals (goal_id, lifecycle) are **already modeled** in the workspaces bounded context (feature 018 — `workspace_goals` table). This bounded context adds:
1. `workspace_goal_messages` table — stores goal conversation messages (this bounded context owns this table)
2. An internal interface `get_goal_messages()` consumed by context engineering service for super-context assembly
3. Events on `workspace.goal` Kafka topic when goal messages are posted

The interactions bounded context does NOT own the goal entity itself — it calls `workspaces_service.get_goal()` and `workspaces_service.update_goal_status()` via in-process interface.

**Rationale**: Goal lifecycle (create, status transitions) is a workspace concern. Goal messages (the conversational content) are an interaction concern — they represent agent/user contributions to the shared objective. This split avoids cross-boundary ownership confusion.

**Alternatives considered**:
- Duplicating goal lifecycle in interactions: violates §IV (no cross-boundary DB access, no duplicate ownership).
- Putting goal messages in the workspaces bounded context: would make workspaces responsible for message ordering, pagination, and causal semantics — not its domain.

---

## Decision 5: Attention Requests — Dedicated Table, Not Notifications

**Decision**: `attention_requests` is a table in the interactions bounded context. Status: `pending` → `acknowledged` → `resolved` | `dismissed`. Events emitted on `interaction.attention` Kafka topic (distinct from `monitor.alerts`). The WebSocket gateway (feature 019) already supports the `attention` channel type — this bounded context just publishes the events.

**Rationale**: Attention requests are agent-initiated, context-specific, and tied to interactions/executions. They are fundamentally different from system alerts (which are monitoring-driven). Storing them in the interactions bounded context keeps the data close to its source and consumers.

**Alternatives considered**:
- Storing in a generic notifications system: loses the strong typing and interaction linkage.
- Publishing only (no persistence): loses the ability to query "my pending attention requests" — the user needs to see requests even if they weren't connected when the request was created.

---

## Decision 6: Branching — Copy-on-Branch Strategy

**Decision**: When a branch is created from interaction A at message M:
1. Create a new interaction B (the branch) in the same conversation
2. Copy messages 1..M from interaction A into interaction B (deep copy, new UUIDs, parent references remapped)
3. Create a `ConversationBranch` record linking (parent_interaction=A, branch_interaction=B, branch_point_message=M)
4. Branch interaction B operates independently from this point

**Rationale**: Copy-on-branch is simpler than shared-history (where branch reads the parent's messages up to the fork point). Shared-history creates complex query logic ("read my messages + parent's messages up to branch point") and makes message deletion/modification in the parent affect branches. Copy-on-branch duplicates some data but keeps each interaction fully self-contained.

**Alternatives considered**:
- Shared history with materialized view: complex query semantics; parent message modifications affect all branches unpredictably.
- Lazy copy (copy on first write to branch): saves storage but adds latency and complexity to the first branch write.

---

## Decision 7: Branch Merging — Append Strategy with Conflict Detection

**Decision**: Merging branch B into parent interaction A:
1. Append all messages from B that are post-branch-point into A (new UUIDs, parent references adjusted to link to A's last message before merge)
2. Create a `BranchMergeRecord` with `conflict_detected: bool`
3. Conflict detection: if multiple branches are merged from the same branch point, compare final messages of each branch for contradictory content (simple: always flag when >1 branch merged from same point; let user resolve)
4. Merged branch status → `merged`

**Rationale**: Simple append-and-flag is predictable. Automatic conflict resolution (choosing one branch over another) would require semantic understanding of message content — beyond scope. Flagging lets the user decide.

**Alternatives considered**:
- Three-way merge (like git): requires semantic understanding of message content, not just structural comparison.
- No conflict detection: users could unknowingly merge contradictory branches.

---

## Decision 8: Kafka Topics and Event Types

**Decision**: 3 Kafka topics:
1. `interaction.events` (keyed by `interaction_id`) — 6 event types: `interaction.started`, `interaction.completed`, `interaction.failed`, `interaction.canceled`, `message.received`, `branch.merged`
2. `workspace.goal` (keyed by `workspace_id`) — 2 event types: `goal.message.posted`, `goal.status.changed`
3. `interaction.attention` (keyed by `target_id`) — 1 event type: `attention.requested`

All events use canonical `EventEnvelope` from feature 013.

**Rationale**: Three topics match the constitution's event topology. Keying by interaction_id enables per-interaction consumer ordering. `workspace.goal` is keyed by workspace_id so all goal activity for a workspace is ordered. `interaction.attention` is keyed by target_id so a specific user/agent's attention requests are ordered.

**Alternatives considered**:
- Single topic for all events: loses the separation that the constitution requires (attention is a dedicated out-of-band channel).
- Keying interaction.events by conversation_id: loses per-interaction ordering guarantees.

---

## Decision 9: Real-Time Subscriptions — Kafka-to-WebSocket Bridge

**Decision**: This bounded context does NOT implement WebSocket handling. It publishes events to the 3 Kafka topics. The WebSocket gateway (feature 019) already consumes these topics and distributes events to connected clients based on channel subscriptions (`conversation:{id}`, `interaction:{id}`, `attention:{user_id}`). The interactions bounded context provides an internal interface `get_subscription_filter()` that the WS hub uses to verify workspace access before accepting a subscription.

**Rationale**: The WebSocket gateway (feature 019) already handles dynamic topic subscription, per-client queues, backpressure, and workspace visibility filtering. Duplicating this in the interactions bounded context would violate the single-responsibility principle and the modular monolith pattern.

**Alternatives considered**:
- Direct WebSocket handling in interactions: duplicates feature 019's infrastructure.
- Server-Sent Events (SSE): doesn't support bidirectional communication needed for mid-process injection.

---

## Decision 10: Message Count Enforcement

**Decision**: `conversations.message_count` is an integer column incremented atomically on each message insert (via `UPDATE conversations SET message_count = message_count + 1 WHERE id = $id AND message_count < $limit RETURNING message_count`). If the update returns 0 rows, the limit has been reached and the insert is rejected. Default limit: 10,000, configurable per workspace.

**Rationale**: Atomic increment-and-check prevents race conditions under concurrent message sends. No separate count query needed. The limit is stored in workspace settings (via workspaces_service), not in the conversations table.

**Alternatives considered**:
- Count query before insert: race condition under concurrent writes.
- PostgreSQL trigger: harder to test and debug; same result achievable in application code.

---

## Decision 11: Alembic Migration Number

**Decision**: Migration `009_interactions_conversations.py` — 8 tables. Depends on feature 018 (workspaces) for workspace FK and workspace_goals FK.

**Rationale**: Sequential after 008_memory_knowledge (feature 023).

---

## Decision 12: Internal Interfaces for Cross-Context Consumers

**Decision**: 3 internal interfaces (in-process, no HTTP):
1. `get_goal_messages(workspace_id, goal_id, limit) → list[WorkspaceGoalMessageResponse]` — consumed by context engineering service (feature 022) for super-context assembly
2. `get_conversation_history(interaction_id, limit) → list[InteractionMessageResponse]` — consumed by context engineering service for conversation history source
3. `get_subscription_filter(user_id, channel_type, channel_id) → bool` — consumed by WebSocket gateway (feature 019) for access verification

**Rationale**: In-process calls consistent with §I (no HTTP between bounded contexts). Each interface is minimal — returns only what the consumer needs.

**Alternatives considered**:
- Exposing full service methods: leaks internal implementation to consumers.
- Kafka-based query: wrong pattern for synchronous reads.
