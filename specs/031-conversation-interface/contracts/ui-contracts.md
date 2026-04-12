# UI Contracts: Conversation Interface

**Feature**: 031-conversation-interface  
**Date**: 2026-04-12

This document defines the external contracts this feature depends on (backend APIs and WebSocket events) and the component contracts it exposes to other frontend features.

---

## Backend API Contracts Consumed

All endpoints use JWT Bearer auth. Base prefix: `/api/v1`.

### Conversations and Interactions

| Method | Endpoint | Description | Used by |
|---|---|---|---|
| `GET` | `/conversations/{id}` | Load conversation with interactions + branches | `use-conversation.ts` on page mount |
| `GET` | `/interactions/{id}/messages` | Paginated message history (cursor-based) | `use-messages.ts` on tab open |
| `POST` | `/interactions/{id}/messages` | Send message (incl. mid-process injection) | `use-send-message.ts` |
| `POST` | `/conversations/{id}/branches` | Create a conversation branch | `use-branch.ts` |
| `POST` | `/conversations/{id}/branches/{branch_id}/merge` | Merge selected messages back | `use-branch.ts` |
| `GET` | `/conversations/{id}/branches/{branch_id}/messages` | Messages in a branch | `use-messages.ts` for branch tab |

**Send message request**:
```json
{
  "content": "Please focus on APAC data only",
  "is_mid_process_injection": true
}
```

**Create branch request**:
```json
{
  "name": "Approach B",
  "description": "Explore the cost-reduction angle",
  "originating_message_id": "uuid"
}
```

**Merge branch request**:
```json
{
  "message_ids": ["uuid1", "uuid2"]
}
```

---

### Workspace Goals

| Method | Endpoint | Description | Used by |
|---|---|---|---|
| `GET` | `/workspaces/{id}/goals` | List workspace goals with lifecycle state | `use-workspace-goals.ts` |
| `GET` | `/workspaces/{id}/goals/{goal_id}/messages` | Goal message history (cursor-based) | `use-workspace-goals.ts` on goal select |
| `POST` | `/workspaces/{id}/goals/{goal_id}/messages` | Post human guidance to goal stream | `GoalFeed.tsx` send handler |

**Post goal message request**:
```json
{
  "content": "Focus on APAC region for this analysis"
}
```

---

## WebSocket Channel Subscriptions

### Channel: `conversation:{conversationId}`

Subscribed when `[conversationId]/page.tsx` mounts. Unsubscribed on unmount.

| Event type | Payload fields | Consumer |
|---|---|---|
| `message.created` | `message: Message` | `use-conversation-ws.ts` → add to Query cache |
| `message.streamed` | `message_id, interaction_id, delta: string` | `use-message-stream.ts` → streaming buffer |
| `message.completed` | `message: Message` | `use-conversation-ws.ts` → replace in Query cache, clear streaming buffer |
| `typing.started` | `interaction_id, agent_fqn` | `use-conversation-ws.ts` → set `isAgentProcessing=true` in Zustand |
| `typing.stopped` | `interaction_id` | `use-conversation-ws.ts` → set `isAgentProcessing=false` |
| `interaction.state_changed` | `interaction: Interaction` | `use-conversation-ws.ts` → update interaction in Query cache |
| `branch.created` | `branch: ConversationBranch` | `use-conversation-ws.ts` → add to branch tabs in Zustand |
| `branch.merged` | `branch_id, merged_message_ids: string[]` | `use-conversation-ws.ts` → update main thread messages |

### Channel: `workspace:{workspaceId}`

Already subscribed by existing workspace context (feature 015). This feature adds listeners for:

| Event type | Payload fields | Consumer |
|---|---|---|
| `goal.message_created` | `message: GoalMessage` | `use-goal-ws.ts` → append to goal messages Query cache |
| `goal.state_changed` | `goal: WorkspaceGoal` | `use-goal-ws.ts` → update goal in Query cache |

---

## Component Contracts (exported from this feature)

These components are designed for potential reuse by other frontend features (workbench sidebars, agent inspection panels, etc.).

### `MessageBubble`

**Purpose**: Render a single message in a chat-style bubble.

**Props**:
```typescript
{
  message: Message
  isStreaming?: boolean       // shows streaming shimmer
  streamingContent?: string  // partial text while streaming
  showBranchOrigin?: boolean // show merged-from badge
  onBranchFrom?: () => void  // callback for "Branch from here" action
}
```

**Visual contract**:
- `user` → right-aligned, primary color background
- `agent` → left-aligned, muted background, agent avatar + name header
- `system` → centered, italic, no avatar
- Streaming: text content has a pulsing cursor at the end

---

### `GoalFeed`

**Purpose**: Self-contained goal view panel — includes selector, message stream, and input.

**Props**:
```typescript
{
  workspaceId: string
  initialGoalId?: string     // pre-select a specific goal
  className?: string         // for width/height override in Sheet context
}
```

---

### `StatusBar`

**Purpose**: Show live interaction metadata.

**Props**:
```typescript
{
  interaction: Interaction
  isProcessing: boolean
}
```

**Visual contract**:
- State badge: shadcn `Badge` with variant mapping:
  - `active` → `default`
  - `completed` → `secondary`
  - `failed` → `destructive`
  - `awaiting_approval` → `outline` + pulsing animation
- Reasoning mode: plain text label (`"Chain of Thought"`, `"Tree of Thought"`, `"—"`)
- Self-correction count: `"N corrections"` (hidden if 0)

---

## Accessibility Contract

All interactive elements MUST meet these requirements:

| Element | Requirement |
|---|---|
| Message list | `role="log"`, `aria-live="polite"`, `aria-label="Conversation messages"` |
| Interaction tabs | shadcn `Tabs` — native `role="tablist"`, `role="tab"`, `role="tabpanel"` |
| Send button | `aria-label="Send message"` |
| Branch button | `aria-label="Branch from this message"` |
| Merge confirm button | `aria-label="Merge selected messages into main thread"` |
| New messages pill | `role="button"`, `aria-label="N new messages, scroll to bottom"` |
| Typing indicator | `aria-label="Agent is typing"`, `aria-live="polite"` |
| Goal lifecycle badge | `aria-label="Goal status: {status}"` |

**Keyboard navigation**:
- `Tab` moves through: interaction tabs → message list (focused message) → input → send button → branch/merge actions
- `Enter` / `Space` activates focused tab, button, or message action
- `Ctrl/Cmd+Enter` sends message from input
- `Escape` closes `Dialog` (branch creation) and `Sheet` (merge panel)

---

## Dark Mode Token Contract

All components MUST use Tailwind semantic color tokens only (no hardcoded hex or `gray-N`):

| Use | Token |
|---|---|
| User message bubble | `bg-primary text-primary-foreground` |
| Agent message bubble | `bg-muted text-muted-foreground` |
| System message | `text-muted-foreground` (no background) |
| Status bar | `bg-card border-b border-border` |
| Processing banner | `bg-yellow-500/10 text-yellow-700 dark:text-yellow-300` |
| Mid-process badge | `bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200` |
| Merged-from badge | `bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200` |
