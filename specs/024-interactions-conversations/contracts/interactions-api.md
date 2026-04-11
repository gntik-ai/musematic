# API Contracts: Interactions and Conversations

**Feature**: 024-interactions-conversations  
**Date**: 2026-04-11  
**Base path**: `/api/v1/interactions`  
**Auth**: JWT Bearer (all endpoints require `workspace_id` claim)

---

## REST Endpoints

### Conversations

#### 1. Create Conversation

**POST** `/api/v1/interactions/conversations`

**Request Body**:
```json
{
  "title": "Q2 Report Discussion",
  "metadata": {"priority": "high"}
}
```

**Response** `201 Created`: `ConversationResponse`

---

#### 2. Get Conversation

**GET** `/api/v1/interactions/conversations/{conversation_id}`

**Response** `200 OK`: `ConversationResponse`

---

#### 3. List Conversations

**GET** `/api/v1/interactions/conversations`

**Query Parameters**: `page` (int), `page_size` (int, max 100)

**Response** `200 OK`: Paginated list of `ConversationResponse`

---

#### 4. Update Conversation

**PATCH** `/api/v1/interactions/conversations/{conversation_id}`

**Request Body**: `ConversationUpdate`

**Response** `200 OK`: `ConversationResponse`

---

#### 5. Delete Conversation

**DELETE** `/api/v1/interactions/conversations/{conversation_id}`

Soft-deletes the conversation and cascade-soft-deletes all interactions and messages.

**Response** `204 No Content`

---

### Interactions

#### 6. Create Interaction

**POST** `/api/v1/interactions/`

**Request Body**:
```json
{
  "conversation_id": "uuid",
  "goal_id": "uuid-or-null"
}
```

**Response** `201 Created`: `InteractionResponse` (state: "initializing")

---

#### 7. Get Interaction

**GET** `/api/v1/interactions/{interaction_id}`

**Response** `200 OK`: `InteractionResponse`

---

#### 8. List Interactions in Conversation

**GET** `/api/v1/interactions/conversations/{conversation_id}/interactions`

**Query Parameters**: `state` (enum, optional), `page`, `page_size`

**Response** `200 OK`: Paginated list of `InteractionResponse`

---

#### 9. Transition Interaction State

**POST** `/api/v1/interactions/{interaction_id}/transition`

**Request Body**:
```json
{
  "trigger": "start",
  "error_metadata": null
}
```

**Response** `200 OK`: `InteractionResponse` (with new state)

**Error Responses**:
- `409 Conflict` — invalid state transition (includes current state and attempted trigger)

---

### Messages

#### 10. Send Message

**POST** `/api/v1/interactions/{interaction_id}/messages`

**Request Body**: `MessageCreate`

**Response** `201 Created`: `MessageResponse`

**Error Responses**:
- `409 Conflict` — interaction not in a message-accepting state (not "running" or "waiting")
- `422 Unprocessable Entity` — `parent_message_id` does not belong to this interaction
- `429 Too Many Requests` — conversation message limit reached

---

#### 11. Inject Mid-Process Message

**POST** `/api/v1/interactions/{interaction_id}/inject`

Injects a message into a running interaction. Automatically sets `parent_message_id` to the most recent agent message and `message_type` to "injection."

**Request Body**: `MessageInject`

**Response** `201 Created`: `MessageResponse`

**Error Responses**:
- `409 Conflict` — interaction not in "running" state

---

#### 12. List Messages

**GET** `/api/v1/interactions/{interaction_id}/messages`

**Query Parameters**: `page`, `page_size` (max 100)

Returns messages in chronological order with `parent_message_id` for DAG reconstruction.

**Response** `200 OK`: Paginated list of `MessageResponse`

---

### Participants

#### 13. Add Participant

**POST** `/api/v1/interactions/{interaction_id}/participants`

**Request Body**: `ParticipantAdd`

**Response** `201 Created`: `ParticipantResponse`

---

#### 14. Remove Participant

**DELETE** `/api/v1/interactions/{interaction_id}/participants/{identity}`

Sets `left_at` timestamp. Does not delete the record (preserves audit).

**Response** `204 No Content`

---

#### 15. List Participants

**GET** `/api/v1/interactions/{interaction_id}/participants`

**Response** `200 OK`: List of `ParticipantResponse`

---

### Workspace Goals

#### 16. Post Goal Message

**POST** `/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages`

**Request Body**: `GoalMessageCreate`

**Response** `201 Created`: `GoalMessageResponse`

**Error Responses**:
- `409 Conflict` — goal is in "completed" or "abandoned" status (not accepting messages)

---

#### 17. List Goal Messages

**GET** `/api/v1/workspaces/{workspace_id}/goals/{goal_id}/messages`

**Query Parameters**: `page`, `page_size` (max 100)

**Response** `200 OK`: Paginated list of `GoalMessageResponse`

---

### Branching

#### 18. Create Branch

**POST** `/api/v1/interactions/branches`

**Request Body**: `BranchCreate`

Creates a new branch interaction with messages copied from the parent interaction up to (and including) the branch point message. Returns the branch metadata.

**Response** `201 Created`: `BranchResponse`

---

#### 19. Merge Branch

**POST** `/api/v1/interactions/branches/{branch_id}/merge`

**Request Body**: `BranchMerge`

Merges branch messages into the parent interaction. Sets `conflict_detected` if another branch from the same point was already merged.

**Response** `200 OK`: `MergeRecordResponse`

---

#### 20. Abandon Branch

**POST** `/api/v1/interactions/branches/{branch_id}/abandon`

Marks the branch as "abandoned." Messages remain for audit but are excluded from the parent.

**Response** `200 OK`: `BranchResponse`

---

#### 21. List Branches

**GET** `/api/v1/interactions/conversations/{conversation_id}/branches`

**Response** `200 OK`: List of `BranchResponse`

---

### Attention Requests

#### 22. Create Attention Request

**POST** `/api/v1/interactions/attention`

**Request Body**: `AttentionRequestCreate`

**Response** `201 Created`: `AttentionRequestResponse`

Publishes event on `interaction.attention` topic.

---

#### 23. List My Attention Requests

**GET** `/api/v1/interactions/attention`

**Query Parameters**: `status` (enum, optional), `page`, `page_size`

Returns attention requests where `target_identity` matches the authenticated user.

**Response** `200 OK`: Paginated list of `AttentionRequestResponse`

---

#### 24. Resolve Attention Request

**POST** `/api/v1/interactions/attention/{request_id}/resolve`

**Request Body**: `AttentionResolve`

**Response** `200 OK`: `AttentionRequestResponse`

---

## Internal Interfaces

### `get_goal_messages()`

Consumed by context engineering service (feature 022, `WorkspaceGoalHistoryAdapter`).

```python
async def get_goal_messages(
    self,
    workspace_id: UUID,
    goal_id: UUID,
    limit: int = 100,
) -> list[GoalMessageResponse]:
    """
    In-process retrieval of goal messages for context assembly.
    Returns messages in chronological order.
    """
```

### `get_conversation_history()`

Consumed by context engineering service (feature 022, `ConversationHistoryAdapter`).

```python
async def get_conversation_history(
    self,
    interaction_id: UUID,
    limit: int = 50,
) -> list[MessageResponse]:
    """
    In-process retrieval of interaction messages for context assembly.
    Returns most recent `limit` messages in chronological order.
    """
```

### `check_subscription_access()`

Consumed by WebSocket gateway (feature 019) for access verification on subscription requests.

```python
async def check_subscription_access(
    self,
    user_id: str,
    channel_type: str,  # "conversation" | "interaction" | "attention"
    channel_id: UUID,
    workspace_id: UUID,
) -> bool:
    """
    Verifies the user has workspace membership and the conversation/interaction
    belongs to that workspace. Returns True if access granted.
    """
```

---

## Events

| Topic | Event Type | Payload | Key | Trigger |
|---|---|---|---|---|
| `interaction.events` | `interaction.started` | `InteractionStartedPayload` | interaction_id | Interaction transitions to "running" |
| `interaction.events` | `interaction.completed` | `InteractionCompletedPayload` | interaction_id | Interaction transitions to "completed" |
| `interaction.events` | `interaction.failed` | `InteractionFailedPayload` | interaction_id | Interaction transitions to "failed" |
| `interaction.events` | `interaction.canceled` | `InteractionCanceledPayload` | interaction_id | Interaction transitions to "canceled" |
| `interaction.events` | `message.received` | `MessageReceivedPayload` | interaction_id | Message sent or injected |
| `interaction.events` | `branch.merged` | `BranchMergedPayload` | interaction_id | Branch merged into parent |
| `workspace.goal` | `goal.message.posted` | `GoalMessagePostedPayload` | workspace_id | Goal message posted |
| `workspace.goal` | `goal.status.changed` | `GoalStatusChangedPayload` | workspace_id | Goal status transitioned |
| `interaction.attention` | `attention.requested` | `AttentionRequestedPayload` | target_identity | Attention request created |
