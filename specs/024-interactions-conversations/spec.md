# Feature Specification: Interactions and Conversations

**Feature Branch**: `024-interactions-conversations`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Implement conversation CRUD, bounded interactions within conversations, mid-process message injection, workspace-goal posting, conversation branching/merging, multi-interaction concurrency, causal ordering, and WebSocket subscriptions."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Conversation and Interaction Lifecycle (Priority: P1)

A user or agent initiates a conversation within a workspace — a container for one or more interactions. The conversation is created with a title and optional metadata. Within the conversation, the user starts an interaction: a bounded unit of work with a specific purpose (e.g., "analyze this document" or "draft a response"). The interaction transitions through a state machine: initializing → ready → running → waiting → paused → completed/failed/canceled. Multiple interactions can coexist within the same conversation without interfering with each other — each interaction has its own participant list, message stream, and state. Messages within an interaction maintain causal ordering (each message references the message it replies to, forming a directed acyclic graph). The user can inject a message into a running interaction mid-process — the injected message is delivered to the active agent with its causal position preserved.

**Why this priority**: Conversations and interactions are the fundamental communication abstraction. Without them, agents have no structured way to receive instructions, report results, or maintain threaded dialogue. Every other feature in this bounded context builds on the conversation/interaction lifecycle.

**Independent Test**: Create a conversation in a workspace. Start two interactions within it. Send messages to each interaction — verify messages are isolated to their respective interaction. Inject a mid-process message into a running interaction — verify it arrives with correct causal ordering (parent_message_id set). Transition one interaction to "completed" — verify the other remains "running." Delete the conversation — verify all interactions and messages are cascade-deleted.

**Acceptance Scenarios**:

1. **Given** a workspace, **When** a user creates a conversation, **Then** a conversation record is created with a UUID, title, workspace ID, creator, and timestamp
2. **Given** a conversation, **When** an interaction is started, **Then** the interaction transitions from "initializing" to "ready" and then to "running" when execution begins
3. **Given** two running interactions in the same conversation, **When** a message is sent to interaction A, **Then** interaction B's message stream is not affected
4. **Given** a running interaction, **When** a mid-process message is injected by the user, **Then** the message appears in the interaction's stream with a valid parent_message_id preserving causal order
5. **Given** an interaction in "running" state, **When** the interaction completes, **Then** it transitions to "completed" and an event is emitted
6. **Given** an interaction, **When** it fails, **Then** it transitions to "failed" with error metadata and an event is emitted
7. **Given** an interaction, **When** the user cancels it, **Then** it transitions to "canceled" and any running agent receives a cancellation signal

---

### User Story 2 — Workspace Goals and Goal-Oriented Execution (Priority: P1)

A platform operator or orchestrator agent creates a goal within a workspace — a shared objective that multiple agents can contribute to. The goal has a lifecycle (active → paused → completed/abandoned) and is identified by a Goal ID (GID) that becomes a first-class correlation dimension in all related activity. Participants (agents or users) post goal messages — timestamped contributions visible to all agents subscribed to the goal. Goal messages form the "super-context" that the context engineering service pulls when assembling context for any agent working on that goal. When a goal message is posted, a notification is published so that subscribed agents can self-select whether to act on it based on their capabilities and visibility configuration. An interaction can optionally be linked to a goal (via goal_id), making all interaction messages part of the goal's context.

**Why this priority**: Goal-oriented collaboration is a core architectural pattern (constitution §X — GID as first-class correlation). Without workspace goals, agents cannot coordinate on shared objectives, and the context engineering service cannot assemble goal-scoped super-context.

**Independent Test**: Create a workspace goal with title "Prepare Q2 report." Post 3 goal messages from different participants. Query goal messages — verify all 3 returned in order. Create an interaction linked to the goal — verify the interaction's messages appear in the goal's context. Transition the goal to "completed" — verify status updated and event emitted. Attempt to post a message to a completed goal — verify rejection.

**Acceptance Scenarios**:

1. **Given** a workspace, **When** a goal is created, **Then** it is assigned a GID, starts in "active" status, and an event is emitted
2. **Given** an active goal, **When** a participant posts a goal message, **Then** the message is stored with workspace_id, goal_id, participant identity, content, and timestamp
3. **Given** a goal with messages, **When** the context engineering service queries for goal super-context, **Then** all goal messages and linked interaction messages are available
4. **Given** an active goal, **When** it is transitioned to "completed," **Then** the status updates and no further messages can be posted
5. **Given** a goal, **When** an interaction is created with that goal_id, **Then** the interaction's correlation context includes the GID for all downstream tracing
6. **Given** a goal event published to the event stream, **When** subscribed agents receive it, **Then** they can evaluate whether to self-select based on their capabilities

---

### User Story 3 — Attention Requests (Priority: P1)

An agent encounters a situation during execution where it urgently needs human input or peer assistance — for example, it found conflicting data and cannot proceed, or it requires approval for a sensitive action. The agent creates an attention request specifying: the target (a specific user or agent FQN), urgency level (low/medium/high/critical), a context summary explaining the need, and references to the related execution, interaction, and goal. The attention request is published as an out-of-band signal — it does not interrupt the agent's current execution flow or block other interactions. The target user receives the attention signal via a dedicated real-time channel (distinct from operational monitoring alerts). The target can view pending attention requests and dismiss or act on them.

**Why this priority**: The attention pattern is a constitutional requirement (§XIII) and enables safe human-in-the-loop interaction without blocking agent execution. Without it, agents have no structured way to escalate or request help.

**Independent Test**: As agent "ns:agent-A" in a running interaction, create an attention request targeting user "user-123" with urgency "high." Verify the attention request is persisted and an event is emitted. Verify a real-time notification is delivered to user-123's attention channel (distinct from alerts). Query "my" attention requests as user-123 — verify the request appears. Dismiss the request — verify status updated.

**Acceptance Scenarios**:

1. **Given** a running interaction, **When** an agent creates an attention request, **Then** the request is stored with source agent FQN, target, urgency, context summary, and related IDs
2. **Given** an attention request, **When** it is published, **Then** a notification event is emitted on a dedicated topic distinct from operational alerts
3. **Given** a target user connected via real-time channels, **When** an attention request targets them, **Then** the signal is delivered in real time
4. **Given** a user with pending attention requests, **When** they query their requests, **Then** all unresolved requests targeting them are returned
5. **Given** a pending attention request, **When** the target user dismisses it, **Then** the request is marked as resolved

---

### User Story 4 — Conversation Branching and Merging (Priority: P2)

A user wants to explore multiple approaches simultaneously within a conversation. They create a branch from an existing interaction — this forks the conversation into a parallel thread that shares history up to the branch point but diverges from there. Each branch operates as an independent interaction with its own message stream and state. When the user is satisfied with one branch's results, they can merge it back into the main conversation thread. Merging combines the branch's messages and outcomes into the parent interaction, with a merge record documenting what was combined. If merging would create conflicts (e.g., contradictory conclusions from two branches), the system flags the conflict for the user to resolve.

**Why this priority**: Branching enables exploratory workflows and parallel reasoning paths. It's valuable for complex decision-making but not strictly required for basic conversation/interaction functionality — agents can operate without branching.

**Independent Test**: Start an interaction in a conversation. Branch the interaction at message 5 — verify a new branch interaction is created with messages 1-5 copied. Send 3 new messages to the branch. Merge the branch back — verify a merge record is created and the branch messages appear in the parent interaction's timeline. Create two branches from the same point, send conflicting results, merge both — verify a conflict flag is raised.

**Acceptance Scenarios**:

1. **Given** an interaction with messages, **When** a branch is created at a specific message, **Then** a new interaction is created inheriting history up to (and including) that message
2. **Given** a branch interaction, **When** messages are added, **Then** they are isolated to the branch and do not appear in the parent interaction
3. **Given** a completed branch, **When** it is merged into the parent, **Then** a merge record is created and branch messages are integrated into the parent's timeline
4. **Given** two branches with contradictory conclusions, **When** both are merged, **Then** the system flags a merge conflict for user resolution
5. **Given** a branch, **When** the user decides to discard it, **Then** the branch is marked as "abandoned" and its messages remain for audit but are excluded from the parent

---

### User Story 5 — Real-Time Subscriptions (Priority: P2)

A user or platform component wants to receive real-time updates about a conversation or interaction as they happen. They subscribe to a channel (e.g., "conversation:{id}" or "interaction:{id}") and receive live events: new messages, state transitions, participant joins/leaves, and branch/merge operations. Subscriptions are scoped to the workspace — a user can only subscribe to conversations they have access to. When an interaction transitions state (e.g., running → completed), all subscribers to that interaction and its parent conversation receive the transition event.

**Why this priority**: Real-time subscriptions enable responsive UIs and agent-to-agent awareness. Without them, clients must poll for updates, which is inefficient and introduces latency. However, the core conversation/interaction lifecycle (US1) functions without real-time delivery — events can be consumed asynchronously.

**Independent Test**: Subscribe to "interaction:{id}" via real-time channel. Send a message to the interaction — verify the subscriber receives the message event. Transition the interaction to "completed" — verify the subscriber receives the state transition event. Subscribe to "conversation:{id}" — verify receiving events from all interactions within the conversation. Attempt to subscribe to a conversation in a different workspace — verify access denied.

**Acceptance Scenarios**:

1. **Given** a subscription to an interaction, **When** a new message is sent, **Then** the subscriber receives a message event in real time
2. **Given** a subscription to an interaction, **When** the interaction transitions state, **Then** the subscriber receives a state transition event
3. **Given** a subscription to a conversation, **When** any interaction within it emits an event, **Then** the conversation subscriber receives it
4. **Given** a user without workspace membership, **When** they attempt to subscribe, **Then** the subscription is rejected with an access error
5. **Given** an active subscription, **When** the conversation is deleted, **Then** the subscriber receives a deletion event and the subscription is closed

---

### User Story 6 — Multi-Interaction Concurrency (Priority: P3)

A workspace runs multiple simultaneous interactions across several conversations — for example, 10 agents each running their own interaction within the same workspace. The system ensures that concurrent interactions do not cause state corruption, message interleaving, or resource contention. Each interaction maintains its own state machine independently. Causal ordering within each interaction is preserved even under concurrent load. The system can sustain a defined level of concurrent interactions per workspace without degradation.

**Why this priority**: Concurrency correctness is essential for production use but is an optimization/hardening concern. Basic single-interaction usage (US1) works without explicit concurrency testing. This story validates that the system is production-ready under concurrent load.

**Independent Test**: Create 50 concurrent interactions in the same workspace. Send messages to all of them simultaneously. Verify no cross-interaction message leakage. Verify all state transitions are valid (no illegal transitions). Verify causal ordering is maintained within each interaction. Measure throughput — verify it meets the defined target.

**Acceptance Scenarios**:

1. **Given** 50 concurrent interactions in a workspace, **When** messages are sent simultaneously, **Then** no messages leak across interaction boundaries
2. **Given** concurrent state transitions, **When** multiple interactions transition at the same time, **Then** all transitions are valid and no state corruption occurs
3. **Given** concurrent message sends within a single interaction, **When** messages arrive out of order, **Then** causal ordering reconstructs the correct message DAG
4. **Given** the system under concurrent load, **When** 100 interactions per workspace are active, **Then** message delivery latency remains within acceptable bounds

---

### Edge Cases

- What happens when a user sends a message to a completed interaction? The message is rejected with an error indicating the interaction is no longer accepting messages.
- What happens when an interaction's agent crashes mid-execution? The interaction transitions to "failed" with error metadata. Messages sent before the crash are preserved. The user can start a new interaction from the failed point.
- What happens when two messages claim the same parent_message_id? Both are accepted — causal ordering supports branching within the message DAG (a single parent can have multiple children).
- What happens when a branch merge conflicts with another merge? The second merge is flagged as a conflict. Both merge records are preserved. The user must resolve the conflict before the branch is considered fully merged.
- What happens when a goal is abandoned while interactions are still linked to it? The linked interactions continue running (goal abandonment does not cancel interactions). The interactions' correlation context still references the GID for audit purposes.
- What happens when an attention request targets an agent that is offline? The attention request is persisted and available for retrieval when the agent or its operator comes online. A retry or escalation policy can be configured per workspace.
- What happens when a conversation exceeds the message limit? The system enforces a configurable maximum messages per conversation (default: 10,000). Beyond the limit, new messages are rejected until older messages are archived or the limit is raised.
- What happens when a workspace goal receives a message after being completed? The message is rejected with an error indicating the goal is no longer accepting messages. The goal must be reopened (transitioned back to "active") before new messages can be posted.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST support creation, retrieval, update, and deletion of conversations within a workspace, each with a unique identifier, title, metadata, and workspace scope
- **FR-002**: The system MUST support bounded interactions within conversations, each with its own state machine (initializing → ready → running → waiting → paused → completed/failed/canceled), participant list, and message stream
- **FR-003**: The system MUST allow multiple concurrent interactions within the same conversation without state collision or message interleaving
- **FR-004**: The system MUST maintain causal ordering of messages within an interaction by linking each message to its parent message, forming a directed acyclic graph
- **FR-005**: The system MUST support mid-process message injection into a running interaction, preserving causal position in the message DAG
- **FR-006**: The system MUST support workspace goals with a lifecycle (active → paused → completed/abandoned), a unique Goal ID (GID), and the ability to post and query goal messages
- **FR-007**: The system MUST include the Goal ID as a first-class field in the correlation context for all goal-linked interactions and events
- **FR-008**: The system MUST store workspace goal messages with workspace ID, goal ID, participant identity (agent FQN or user ID), content, timestamp, and optional interaction linkage
- **FR-009**: The system MUST publish events when goal messages are posted so that subscribed agents can self-select which goals to act on
- **FR-010**: The system MUST reject messages posted to completed or abandoned goals
- **FR-011**: The system MUST support attention requests from agents specifying target, urgency level, context summary, and related execution/interaction/goal references
- **FR-012**: The system MUST publish attention requests on a dedicated channel distinct from operational monitoring alerts
- **FR-013**: The system MUST deliver attention signals to target users in real time when they are connected
- **FR-014**: The system MUST allow target users to query their pending attention requests and dismiss or resolve them
- **FR-015**: The system MUST support conversation branching — forking an interaction at a specific message point to create a parallel thread sharing history up to the branch point
- **FR-016**: The system MUST support branch merging — combining a branch's messages back into the parent interaction with a documented merge record
- **FR-017**: The system MUST detect and flag merge conflicts when merging branches that contain contradictory conclusions
- **FR-018**: The system MUST support real-time subscriptions to conversation and interaction channels, delivering message events, state transitions, and branch/merge operations
- **FR-019**: The system MUST enforce workspace-scoped access control on all conversation, interaction, goal, and subscription operations
- **FR-020**: The system MUST publish events for interaction lifecycle transitions (started, completed, failed, canceled), message receipt, branch creation, branch merging, and goal state changes
- **FR-021**: The system MUST enforce a configurable maximum message count per conversation (default: 10,000)
- **FR-022**: The system MUST preserve all messages and state history for failed or canceled interactions for audit purposes

### Key Entities

- **Conversation**: A container for one or more interactions within a workspace. Has a unique ID, title, workspace ID, creator identity, metadata, and message count. Supports branching. Conversations can be soft-deleted (preserving audit history).
- **Interaction**: A bounded unit of work within a conversation. Has its own state machine (8 states), participant list, message stream, and optional goal linkage. Represents a single agent task or user-agent dialogue turn.
- **InteractionMessage**: A single message within an interaction. Contains sender identity (agent FQN or user ID), content, timestamp, parent_message_id (for causal ordering), message type (user, agent, system, injection), and metadata. Forms a DAG within the interaction.
- **InteractionParticipant**: A record linking an agent or user to an interaction, with role (initiator, responder, observer) and join/leave timestamps.
- **WorkspaceGoalMessage**: A timestamped contribution to a workspace goal. Contains workspace_id, goal_id, participant identity, content, and optional interaction linkage. Forms the super-context for goal-oriented execution.
- **ConversationBranch**: A record representing a fork point in a conversation. Links a parent interaction, a branch interaction, and the message at which the branch occurred. Tracks branch status (active, merged, abandoned).
- **BranchMergeRecord**: A record documenting the merging of a branch back into its parent interaction. Contains the branch ID, merge timestamp, conflict flag, and conflict resolution details if applicable.
- **AttentionRequest**: An out-of-band signal from an agent requesting human input or peer assistance. Contains source agent FQN, target identity, urgency level, context summary, related execution/interaction/goal IDs, status (pending, acknowledged, resolved, dismissed), and timestamps.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Creating a conversation and starting an interaction completes within 300 milliseconds
- **SC-002**: Mid-process message injection is delivered to the running interaction within 200 milliseconds
- **SC-003**: Real-time event delivery to subscribed clients occurs within 500 milliseconds of the triggering action
- **SC-004**: 100 concurrent interactions per workspace operate without state corruption or message leakage — zero cross-interaction contamination
- **SC-005**: Goal messages are available for context assembly within 1 second of posting
- **SC-006**: Attention requests are delivered to connected target users within 500 milliseconds
- **SC-007**: Conversation branching and merging preserve 100% of messages — zero data loss on merge
- **SC-008**: Causal ordering is maintained in 100% of interactions — every message has a valid parent reference forming a valid DAG
- **SC-009**: All interaction state transitions are valid — zero illegal state transitions under any conditions
- **SC-010**: Test coverage of the interactions and conversations subsystem is at least 95%

## Assumptions

- Workspace membership and access control are provided by the workspaces bounded context (feature 018) via in-process service interface.
- Agent identity and FQN resolution are provided by the registry bounded context (feature 021) via in-process service interface.
- Real-time event delivery leverages the WebSocket gateway (feature 019) — this bounded context publishes events; the WebSocket hub consumes and distributes them.
- The context engineering service (feature 022) consumes workspace goal messages for super-context assembly via an in-process interface from this bounded context.
- Causal ordering is enforced at the application level (parent_message_id references) — not via database-level ordering constraints. The message DAG is reconstructable from these references.
- Conversation deletion is a soft delete — all data is preserved for audit and compliance, but excluded from active queries.
- The default maximum messages per conversation (10,000) is configurable per workspace via workspace settings.
- Attention requests are stored in the interactions bounded context's own tables — they are not stored in a separate notifications system.
- Goal lifecycle state transitions are validated — only valid transitions are allowed (e.g., "active" → "paused" or "completed," not "completed" → "active" unless explicitly reopened).
- Interaction state machine transitions are deterministic and validated — invalid transitions (e.g., "completed" → "running") are rejected.
- The event topic for this bounded context is `interaction.events` with additional `workspace.goal` and `interaction.attention` topics as specified in the constitution's event topology.
