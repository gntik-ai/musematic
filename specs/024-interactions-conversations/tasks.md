# Tasks: Interactions and Conversations

**Input**: Design documents from `specs/024-interactions-conversations/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/interactions-api.md ✓, quickstart.md ✓

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the interactions bounded context package skeleton and Alembic migration

- [X] T001 Create `apps/control-plane/src/platform/interactions/` package with stub `__init__.py`, `models.py`, `schemas.py`, `service.py`, `repository.py`, `router.py`, `events.py`, `exceptions.py`, `dependencies.py`, `state_machine.py`
- [X] T002 Create Alembic migration `apps/control-plane/migrations/versions/009_interactions_conversations.py` with all 8 tables: `conversations` (soft-delete, message_count), `interactions` (state enum, goal_id nullable), `interaction_messages` (self-referencing parent_message_id FK, CASCADE on interaction), `interaction_participants` (unique constraint identity+interaction), `workspace_goal_messages`, `conversation_branches`, `branch_merge_records`, `attention_requests` — all indexes and constraints per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core models, state machine, schemas, exceptions, repository, and events infrastructure

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T003 Implement all 8 SQLAlchemy models and enums in `apps/control-plane/src/platform/interactions/models.py`: enums `InteractionState`, `MessageType`, `ParticipantRole`, `BranchStatus`, `AttentionUrgency`, `AttentionStatus`; models `Conversation` (UUIDMixin, TimestampMixin, SoftDeleteMixin), `Interaction`, `InteractionMessage` (self-referencing parent_message_id), `InteractionParticipant`, `WorkspaceGoalMessage`, `ConversationBranch`, `BranchMergeRecord`, `AttentionRequest` — all fields and constraints per data-model.md
- [X] T004 [P] Implement state machine in `apps/control-plane/src/platform/interactions/state_machine.py`: `INTERACTION_TRANSITIONS` dict mapping `(InteractionState, trigger_str) → InteractionState` for all valid transitions per data-model.md; `validate_transition(current: InteractionState, trigger: str) → InteractionState` raises `InvalidStateTransitionError` on invalid trigger or terminal state
- [X] T005 [P] Implement all Pydantic request schemas in `apps/control-plane/src/platform/interactions/schemas.py`: `ConversationCreate`, `ConversationUpdate`, `InteractionCreate`, `InteractionTransition`, `MessageCreate`, `MessageInject`, `ParticipantAdd`, `GoalMessageCreate`, `BranchCreate`, `BranchMerge`, `AttentionRequestCreate`, `AttentionResolve`
- [X] T006 [P] Implement all Pydantic response schemas in `apps/control-plane/src/platform/interactions/schemas.py`: `ConversationResponse`, `InteractionResponse`, `MessageResponse`, `ParticipantResponse`, `GoalMessageResponse`, `BranchResponse`, `MergeRecordResponse`, `AttentionRequestResponse`
- [X] T007 [P] Implement exception hierarchy in `apps/control-plane/src/platform/interactions/exceptions.py`: `InteractionError`, `InvalidStateTransitionError` (with `current_state` and `trigger` fields), `ConversationNotFoundError`, `InteractionNotFoundError`, `MessageNotInInteractionError`, `MessageLimitReachedError`, `InteractionNotAcceptingMessagesError`, `GoalNotAcceptingMessagesError`, `BranchNotFoundError`, `AttentionRequestNotFoundError`
- [X] T008 Implement `InteractionsRepository` in `apps/control-plane/src/platform/interactions/repository.py`: CRUD methods for all 8 models — `create_conversation()`, `get_conversation()`, `list_conversations()`, `soft_delete_conversation()`, `update_conversation()`; `create_interaction()`, `get_interaction()`, `list_interactions()`; `create_message()`, `get_message()`, `list_messages()`, `validate_parent_message()` (checks parent belongs to same interaction); `increment_message_count()` (atomic `UPDATE SET message_count = message_count + 1 WHERE message_count < $limit RETURNING message_count`); `add_participant()`, `remove_participant()`, `list_participants()`; `create_goal_message()`, `list_goal_messages()`, `get_goal_messages_for_context()`; `create_branch()`, `get_branch()`, `list_branches()`, `update_branch_status()`, `copy_messages_up_to()`, `merge_branch_messages()`, `check_prior_merges_from_same_point()`; `create_merge_record()`; `create_attention_request()`, `get_attention_request()`, `list_attention_requests()`, `update_attention_status()`
- [X] T009 [P] Implement Kafka event payload types and publish helpers in `apps/control-plane/src/platform/interactions/events.py`: payloads `InteractionStartedPayload`, `InteractionCompletedPayload`, `InteractionFailedPayload`, `InteractionCanceledPayload`, `MessageReceivedPayload`, `BranchMergedPayload` on topic `interaction.events`; `GoalMessagePostedPayload`, `GoalStatusChangedPayload` on topic `workspace.goal`; `AttentionRequestedPayload` on topic `interaction.attention`; corresponding `publish_*()` helpers using canonical `EventEnvelope`
- [X] T010 [P] Add `INTERACTIONS_*` settings fields to `apps/control-plane/src/platform/common/config.py`: `interactions_max_messages_per_conversation: int = 10000`, `interactions_default_page_size: int = 20`

**Checkpoint**: Foundation complete — all models, state machine, repository, events, settings in place.

---

## Phase 3: User Story 1 — Conversation and Interaction Lifecycle (Priority: P1) 🎯 MVP

**Goal**: Full conversation CRUD, interaction state machine, message sending with causal ordering, mid-process injection, and participant management.

**Independent Test**: Create conversation → start 2 interactions → send messages to each (verify isolation) → inject mid-process into one (verify injection type + parent_message_id) → complete one interaction → verify state change + event; delete conversation → verify cascade.

- [X] T011 [US1] Implement conversation and interaction service methods in `apps/control-plane/src/platform/interactions/service.py`: `create_conversation()`, `get_conversation()` (workspace-scoped), `list_conversations()` (paginated), `update_conversation()`, `delete_conversation()` (soft-delete cascades to interactions); `create_interaction()` (create + emit `interaction.started` on first `start` trigger), `get_interaction()`, `list_interactions()` (paginated, optional state filter); `transition_interaction()` (validate via `state_machine.validate_transition()`, update state + `state_changed_at`, emit lifecycle event for started/completed/failed/canceled transitions)
- [X] T012 [US1] Implement message and participant service methods in `apps/control-plane/src/platform/interactions/service.py`: `send_message()` (validate interaction state is running/waiting, validate parent_message_id belongs to same interaction, call `increment_message_count()` — raise `MessageLimitReachedError` if 0 rows returned, create message, emit `message.received`); `inject_message()` (validate state is "running", auto-set parent_message_id to most recent agent message in interaction, set message_type=injection, emit `message.received`); `list_messages()` (paginated, chronological); `add_participant()`, `remove_participant()` (set left_at), `list_participants()`
- [X] T013 [US1] Implement conversation and interaction REST endpoints in `apps/control-plane/src/platform/interactions/router.py`: Endpoints 1-15 — `POST /conversations` (201), `GET /conversations/{id}` (200), `GET /conversations` (200 paginated), `PATCH /conversations/{id}` (200), `DELETE /conversations/{id}` (204); `POST /` (201 interaction), `GET /{id}` (200), `GET /conversations/{id}/interactions` (200 paginated); `POST /{id}/transition` (200); `POST /{id}/messages` (201), `POST /{id}/inject` (201), `GET /{id}/messages` (200 paginated); `POST /{id}/participants` (201), `DELETE /{id}/participants/{identity}` (204), `GET /{id}/participants` (200)

**Checkpoint**: US1 complete — full conversation/interaction lifecycle, messages with causal ordering, injection, and participant management all functional.

---

## Phase 4: User Story 2 — Workspace Goals and Goal Messages (Priority: P1)

**Goal**: Goal message posting and listing on active goals, rejection on completed/abandoned goals, events on `workspace.goal` topic, and `get_goal_messages()` internal interface.

**Independent Test**: Post 3 goal messages from different participants → verify listing in chronological order → attempt to post to completed goal → verify 409 rejection; call `get_goal_messages()` directly → verify returns same list.

- [X] T014 [US2] Implement goal message service methods in `apps/control-plane/src/platform/interactions/service.py`: `post_goal_message()` (call `workspaces_service.get_goal()` to verify active status — raise `GoalNotAcceptingMessagesError` if completed/abandoned, create `WorkspaceGoalMessage`, emit `goal.message.posted` event on `workspace.goal` topic); `list_goal_messages()` (paginated, chronological); `get_goal_messages()` (internal interface — returns up to `limit` most recent messages for context assembly)
- [X] T015 [US2] Add goal message REST endpoints to `apps/control-plane/src/platform/interactions/router.py`: Endpoints 16-17 — `POST /workspaces/{workspace_id}/goals/{goal_id}/messages` (201), `GET /workspaces/{workspace_id}/goals/{goal_id}/messages` (200 paginated) — workspace-scoped access control via JWT

**Checkpoint**: US2 complete — goal messages persistable and queryable; `get_goal_messages()` internal interface available for context engineering.

---

## Phase 5: User Story 3 — Attention Requests (Priority: P1)

**Goal**: Attention request creation, listing (target-filtered), and resolution/dismissal; events on `interaction.attention` topic distinct from operational alerts.

**Independent Test**: Create attention request targeting "user-123" with urgency "critical" → verify persisted + event emitted on `interaction.attention` topic; query as user-123 (GET /attention?status=pending) → verify request returned; dismiss → verify status updated to "dismissed"; verify request NOT returned by monitor alerts endpoint.

- [X] T016 [US3] Implement attention request service methods in `apps/control-plane/src/platform/interactions/service.py`: `create_attention_request()` (persist, emit `attention.requested` on `interaction.attention` Kafka topic with `AttentionRequestedPayload`); `list_attention_requests()` (paginated, filter by `target_identity = current_user_id`, optional status filter); `resolve_attention_request()` (validate requester is target, transition: pending→acknowledged, pending/acknowledged→resolved/dismissed, set `acknowledged_at` / `resolved_at`)
- [X] T017 [US3] Add attention REST endpoints to `apps/control-plane/src/platform/interactions/router.py`: Endpoints 22-24 — `POST /attention` (201), `GET /attention` (200 paginated, filtered by JWT identity as target), `POST /attention/{request_id}/resolve` (200)

**Checkpoint**: US3 complete — attention requests are persisted, queryable by target, and resolvable; published on dedicated out-of-band topic.

---

## Phase 6: User Story 4 — Conversation Branching and Merging (Priority: P2)

**Goal**: Create branch (copy-on-branch from parent interaction at message M), send messages to branch independently, merge back with conflict detection, abandon.

**Independent Test**: Create interaction with 5 messages → branch at message 3 → verify new interaction with 3 copied messages; send 2 messages to branch → verify isolated from parent; merge → verify merge record created + branch messages appended to parent; branch again from same point, merge → verify `conflict_detected: true`; abandon a third branch → verify status "abandoned".

- [X] T018 [US4] Implement branching and merging service methods in `apps/control-plane/src/platform/interactions/service.py`: `create_branch()` (create new Interaction in same conversation, call `repository.copy_messages_up_to()` to deep-copy messages with new UUIDs and remapped parent references, create `ConversationBranch` record); `merge_branch()` (call `check_prior_merges_from_same_point()` to detect conflict flag, call `merge_branch_messages()` to append post-branch messages into parent, create `BranchMergeRecord`, update branch status to "merged", emit `branch.merged` event); `abandon_branch()` (update branch status to "abandoned"); `list_branches()` (by conversation_id)
- [X] T019 [US4] Add branch REST endpoints to `apps/control-plane/src/platform/interactions/router.py`: Endpoints 18-21 — `POST /branches` (201), `POST /branches/{id}/merge` (200), `POST /branches/{id}/abandon` (200), `GET /conversations/{id}/branches` (200)

**Checkpoint**: US4 complete — full branch → diverge → merge pipeline works; conflict detection flags overlapping merges.

---

## Phase 7: User Story 5 — Internal Interfaces and Subscription Access (Priority: P2)

**Goal**: Implement `get_conversation_history()` and `check_subscription_access()` internal interfaces consumed by context engineering (feature 022) and WebSocket gateway (feature 019).

**Independent Test**: Call `get_conversation_history(interaction_id, limit=10)` directly — verify returns last 10 messages in chronological order; call `check_subscription_access(user_id, "interaction", interaction_id, workspace_id)` — verify True for workspace member, False for non-member; call with "conversation" channel type — verify checks conversation belongs to workspace.

- [X] T020 [US5] Implement internal interfaces in `apps/control-plane/src/platform/interactions/service.py`: `get_conversation_history()` — fetch most recent `limit` messages from interaction ordered by `created_at ASC`, return `list[MessageResponse]`; `check_subscription_access()` — verify workspace membership via `workspaces_service.get_membership()`, verify conversation/interaction belongs to `workspace_id` via repository, return `bool`

**Checkpoint**: US5 complete — context engineering can pull conversation history and goal messages; WebSocket gateway can verify subscription access.

---

## Phase 8: User Story 6 — Concurrency Validation (Priority: P3)

**Goal**: Atomic message count enforcement and state machine guard under concurrent load.

**Independent Test**: 50 concurrent `send_message()` calls to same interaction → verify exactly `message_count` increments (no over-count, no under-count); concurrent `transition_interaction()` calls with same trigger from multiple coroutines → verify only one succeeds (others raise `InvalidStateTransitionError`); 100 interactions in workspace → verify no cross-interaction message leakage.

- [X] T021 [US6] Add optimistic locking guard to `transition_interaction()` in `apps/control-plane/src/platform/interactions/service.py`: use `UPDATE interactions SET state = $new_state, state_changed_at = now() WHERE id = $id AND state = $expected_current_state RETURNING id` — if 0 rows updated, re-fetch current state and raise `InvalidStateTransitionError` with actual current state (prevents concurrent double-transition)
- [X] T022 [US6] Verify atomic message count in `apps/control-plane/src/platform/interactions/repository.py`: confirm `increment_message_count()` uses single atomic UPDATE with WHERE+RETURNING pattern (no separate SELECT+UPDATE) — add inline comment explaining the race-free pattern

**Checkpoint**: US6 complete — concurrent interactions safe under load; state transitions and message count atomically enforced.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Wiring, DI factory, routing, linting, and test coverage

- [X] T023 Implement `get_interactions_service()` DI factory in `apps/control-plane/src/platform/interactions/dependencies.py` — inject `AsyncSession`, `AiokafkaProducer`, `InteractionsRepository`, and in-process `workspaces_service` + `registry_service` dependencies
- [X] T024 Mount interactions router in `apps/control-plane/src/platform/api/__init__.py`: `app.include_router(interactions_router, prefix="/api/v1/interactions", tags=["interactions"])` and `app.include_router(interactions_router, prefix="/api/v1/workspaces", tags=["goals"])` for goal message endpoints
- [X] T025 [P] Write unit tests `apps/control-plane/tests/unit/test_int_state_machine.py`: all valid transitions, invalid trigger raises `InvalidStateTransitionError`, terminal state (completed/failed/canceled) has no outbound transitions, concurrent double-transition guard
- [X] T026 [P] Write unit tests `apps/control-plane/tests/unit/test_int_causal_ordering.py`: parent_message_id None for first message, parent must belong to same interaction (raises `MessageNotInInteractionError` otherwise), multiple children from same parent (DAG branching), inject auto-selects latest agent message as parent
- [X] T027 [P] Write unit tests `apps/control-plane/tests/unit/test_int_branching.py`: copy_messages_up_to produces new UUIDs, parent references remapped correctly, branch messages isolated from parent after copy, conflict detection triggers on second merge from same branch point
- [X] T028 [P] Write integration tests `apps/control-plane/tests/integration/test_int_conversation_lifecycle.py`: end-to-end conversation → interaction → state transitions → messages → injection → completion → events emitted; cascade delete; message limit enforcement
- [X] T029 [P] Write integration tests `apps/control-plane/tests/integration/test_int_goal_messages.py`: post messages to active goal → list → get_goal_messages() internal interface; reject on completed/abandoned goal; `goal.message.posted` event emitted
- [X] T030 [P] Write integration tests `apps/control-plane/tests/integration/test_int_attention.py`: create request → list as target → acknowledge → resolve; create → dismiss; attention event on `interaction.attention` (not `interaction.events`)
- [X] T031 [P] Write integration tests `apps/control-plane/tests/integration/test_int_branching_merging.py`: full branch→send→merge pipeline; conflict flag on second merge from same point; abandon branch excluded from parent; merge record content
- [X] T032 [P] Write integration tests `apps/control-plane/tests/integration/test_int_concurrency.py`: 50 concurrent sends → correct message count; 50 concurrent same trigger → only one succeeds; 100 concurrent interactions → no cross-interaction leakage
- [X] T033 Run `ruff check src/platform/interactions/ --fix` and `mypy src/platform/interactions/ --strict` in `apps/control-plane/` — resolve all errors
- [X] T034 Run full test suite with coverage `pytest tests/ -k "interactions" --cov=src/platform/interactions --cov-report=term-missing` — achieve ≥ 95% coverage per SC-010

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — BLOCKS all user stories
- **US1 (Phase 3)**: Depends on Phase 2 — uses all foundational models, state machine, repository
- **US2 (Phase 4)**: Depends on Phase 2 + US1 (shares `service.py`; goal messages linked to interactions)
- **US3 (Phase 5)**: Depends on Phase 2 — attention requests independent from US1/US2 models
- **US4 (Phase 6)**: Depends on Phase 2 + US1 (branching operates on existing interactions/messages)
- **US5 (Phase 7)**: Depends on Phase 2 + US1 + US2 (internal interfaces read conversations and goal messages)
- **US6 (Phase 8)**: Depends on Phase 2 + US1 (concurrency guards are enhancements to existing service methods)
- **Polish (Phase 9)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2 — no story dependencies
- **US2 (P1)**: Can start in parallel with US1 if Phase 2 complete (separate service methods, different models)
- **US3 (P1)**: Can start in parallel with US1+US2 — attention requests use separate model and topic
- **US4 (P2)**: Requires US1 complete (branches are forks of interactions with messages)
- **US5 (P2)**: Requires US1 + US2 complete (reads conversations and goal messages)
- **US6 (P3)**: Requires US1 complete (concurrency guards enhance existing transitions and message count)

### Within Each User Story

- Service methods must precede router for each story
- T008 (repository) must precede all service implementations
- T003 (models) must precede T008 (repository)
- T004 (state machine) must precede T011 (transition service method)

### Parallel Opportunities

- T004+T005+T006+T007+T009+T010 in Phase 2 (different files, all independent)
- T011+T012 in US1 are sequential (T012 depends on service setup from T011)
- T014+T016 in US2+US3 can run in parallel (different service methods, different models)
- T025–T032 in Polish (all different test files, independent)

---

## Parallel Example: Phase 2 Foundational

```bash
# All independent foundational tasks — different files, run together:
Task: T004 "state_machine.py — INTERACTION_TRANSITIONS dict + validate_transition()"
Task: T005 "schemas.py — all request schemas"
Task: T006 "schemas.py — all response schemas"   # same file as T005 — sequential
Task: T007 "exceptions.py — exception hierarchy"
Task: T009 "events.py — event payloads + publish helpers"
Task: T010 "config.py — INTERACTIONS_* settings"
```

## Parallel Example: Polish Phase

```bash
# All test files are independent — run together:
Task: T025 "test_int_state_machine.py"
Task: T026 "test_int_causal_ordering.py"
Task: T027 "test_int_branching.py"
Task: T028 "test_int_conversation_lifecycle.py"
Task: T029 "test_int_goal_messages.py"
Task: T030 "test_int_attention.py"
Task: T031 "test_int_branching_merging.py"
Task: T032 "test_int_concurrency.py"
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US1 (conversation + interaction + messages)
4. **STOP and VALIDATE**: Create conversation, start interaction, send messages, inject — verify end-to-end

### Incremental Delivery

1. Setup + Foundational → skeleton
2. US1 → conversation/interaction lifecycle MVP
3. US2 → goal messages (unblocks context engineering integration)
4. US3 → attention requests (unblocks agent escalation path)
5. US4 → branching/merging (advanced workflow feature)
6. US5 → internal interfaces (completes cross-context integrations)
7. US6 → concurrency hardening
8. Polish → tests + linting + coverage

### Parallel Team Strategy

After Phase 2 complete:
- Developer A: US1 (most foundational, needed by US4/US5/US6)
- Developer B: US2 + US3 (independent models, parallel with US1)
- Developer A → US4 after US1
- Developer B → US5 after US1+US2 complete
- Both → Polish

---

## Notes

- [P] tasks = different files, no dependencies on each other
- [Story] label maps task to specific user story
- State machine is dict-based — no external library; terminal states have zero outbound transitions
- `increment_message_count()` uses atomic UPDATE+WHERE+RETURNING — never a separate SELECT+UPDATE
- Causal DAG: `parent_message_id` self-referencing FK; inject auto-selects latest agent message as parent
- Goal lifecycle (status transitions) is owned by workspaces bounded context (feature 018) — this BC only posts messages and reads status
- `interaction.attention` topic is DISTINCT from `interaction.events` — constitutional requirement §XIII
- 3 internal interfaces are in-process only — no HTTP (`get_goal_messages`, `get_conversation_history`, `check_subscription_access`)
- WebSocket real-time delivery (US5 subscriptions) is handled by feature 019 — this BC publishes events only
