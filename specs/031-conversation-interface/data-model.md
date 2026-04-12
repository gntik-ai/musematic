# Data Model: Conversation Interface

**Feature**: 031-conversation-interface  
**Date**: 2026-04-12  
**Type**: Frontend — TypeScript types, Zustand store interfaces, API response shapes

---

## TypeScript Types

### Core Domain Types (consumed from backend API)

```typescript
// Sender type for message alignment
type MessageSenderType = "user" | "agent" | "system"

// Message lifecycle within streaming
type MessageStatus = "streaming" | "complete" | "failed"

// Interaction state (maps to backend ExecutionStatus)
type InteractionState =
  | "active"
  | "completed"
  | "failed"
  | "awaiting_approval"
  | "cancelled"

// Reasoning mode labels (from backend interaction metadata)
type ReasoningMode =
  | "chain_of_thought"
  | "tree_of_thought"
  | "none"

// Branch lifecycle
type BranchStatus = "active" | "merged" | "abandoned"

// Goal lifecycle
type GoalStatus = "active" | "paused" | "completed" | "abandoned"

interface Message {
  id: string
  conversation_id: string
  interaction_id: string
  sender_type: MessageSenderType
  sender_id: string            // user_id or agent_fqn
  sender_display_name: string
  content: string              // Markdown text
  attachments: MessageAttachment[]
  status: MessageStatus
  is_mid_process_injection: boolean
  branch_origin: string | null // branch name if merged from a branch
  created_at: string           // ISO8601
  updated_at: string
}

interface MessageAttachment {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  url: string                  // signed object storage URL
}

interface Interaction {
  id: string
  conversation_id: string
  agent_id: string
  agent_fqn: string
  agent_display_name: string
  state: InteractionState
  reasoning_mode: ReasoningMode
  self_correction_count: number
  created_at: string
  updated_at: string
}

interface Conversation {
  id: string
  workspace_id: string
  title: string
  created_at: string
  interactions: Interaction[]
  branches: ConversationBranch[]
}

interface ConversationBranch {
  id: string
  conversation_id: string
  name: string
  description: string | null
  originating_message_id: string
  status: BranchStatus
  created_at: string
}

interface WorkspaceGoal {
  id: string
  workspace_id: string
  title: string
  description: string | null
  status: GoalStatus
  created_at: string
}

interface GoalMessage {
  id: string
  goal_id: string
  sender_type: "agent" | "user" | "system"
  sender_id: string
  sender_display_name: string
  agent_fqn: string | null     // null for user/system messages
  content: string
  originating_interaction_id: string | null  // link to triggering interaction
  created_at: string
}
```

---

## Zustand Store

### `useConversationStore`

Scoped to the mounted `[conversationId]/page.tsx` — one instance per conversation view.

```typescript
interface BranchTab {
  id: string            // conversation branch ID, or "main" for the main thread
  name: string          // display name
  interactionId: string | null  // null for branch tabs (branches span interactions)
}

interface ConversationStore {
  // Tab management
  activeBranchId: string | null   // null = main thread
  branchTabs: BranchTab[]

  // Real-time processing state
  isAgentProcessing: boolean
  processingInteractionId: string | null

  // Auto-scroll
  autoScrollEnabled: boolean
  pendingMessageCount: number     // messages arrived while scrolled up

  // Goal panel
  goalPanelOpen: boolean
  selectedGoalId: string | null

  // Actions
  setActiveBranch: (branchId: string | null) => void
  setAgentProcessing: (processing: boolean, interactionId: string | null) => void
  enableAutoScroll: () => void
  pauseAutoScroll: () => void
  incrementPending: () => void
  clearPending: () => void
  setGoalPanelOpen: (open: boolean) => void
  setSelectedGoal: (goalId: string | null) => void
  addBranchTab: (branch: ConversationBranch) => void
}
```

### `useAuthStore` (existing, from feature 015)

Used to read `currentUser.id` for message sender identification.

### `useWorkspaceStore` (existing, from feature 015)

Used to read `currentWorkspace.id` for goal panel goal list queries.

---

## WebSocket Event Payloads

Events received on channel `conversation:{conversationId}`:

```typescript
// New message or streaming start
interface WsMessageCreated {
  event_type: "message.created"
  message: Message
}

// Partial streaming chunk
interface WsMessageStreamed {
  event_type: "message.streamed"
  message_id: string
  interaction_id: string
  delta: string              // text to append
}

// Streaming complete — final content
interface WsMessageCompleted {
  event_type: "message.completed"
  message: Message           // final, complete message object
}

// Agent started processing
interface WsTypingStarted {
  event_type: "typing.started"
  interaction_id: string
  agent_fqn: string
}

// Agent stopped processing (includes when message.completed fires)
interface WsTypingStopped {
  event_type: "typing.stopped"
  interaction_id: string
}

// Interaction metadata update (state, reasoning mode, self-correction count)
interface WsInteractionStateChanged {
  event_type: "interaction.state_changed"
  interaction: Interaction
}

// New branch created
interface WsBranchCreated {
  event_type: "branch.created"
  branch: ConversationBranch
}

// Branch merged
interface WsBranchMerged {
  event_type: "branch.merged"
  branch_id: string
  merged_message_ids: string[]
}
```

Events received on channel `workspace:{workspaceId}`:

```typescript
// New goal message
interface WsGoalMessageCreated {
  event_type: "goal.message_created"
  message: GoalMessage
}

// Goal lifecycle change
interface WsGoalStateChanged {
  event_type: "goal.state_changed"
  goal: WorkspaceGoal
}
```

---

## TanStack Query Keys

```typescript
const queryKeys = {
  conversation: (id: string) => ["conversation", id] as const,
  messages: (conversationId: string, branchId: string | null) =>
    ["messages", conversationId, branchId ?? "main"] as const,
  interaction: (id: string) => ["interaction", id] as const,
  goals: (workspaceId: string) => ["goals", workspaceId] as const,
  goalMessages: (goalId: string) => ["goal-messages", goalId] as const,
}
```

---

## Component Prop Interfaces

### `MessageBubble`

```typescript
interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean        // true while delta chunks are arriving
  streamingContent?: string   // accumulated delta text (while streaming)
  showBranchOrigin?: boolean  // show merged-from badge
}
```

### `InteractionTab`

```typescript
interface InteractionTabProps {
  interaction: Interaction
  isActive: boolean
  hasUnreadMessages: boolean
  onClick: () => void
}
```

### `StatusBar`

```typescript
interface StatusBarProps {
  interaction: Interaction
  isProcessing: boolean
}
```

### `MessageInput`

```typescript
interface MessageInputProps {
  interactionId: string
  isAgentProcessing: boolean
  onSend: (content: string, isMidProcess: boolean) => Promise<void>
}
```

### `BranchCreationDialog`

```typescript
interface BranchCreationDialogProps {
  open: boolean
  originatingMessageId: string
  conversationId: string
  onClose: () => void
  onCreated: (branch: ConversationBranch) => void
}
```

### `MergeSheet`

```typescript
interface MergeSheetProps {
  open: boolean
  branch: ConversationBranch
  branchMessages: Message[]
  conversationId: string
  onClose: () => void
  onMerged: (mergedMessageIds: string[]) => void
}
```

### `GoalFeed`

```typescript
interface GoalFeedProps {
  workspaceId: string
  selectedGoalId: string | null
  onGoalSelect: (goalId: string) => void
}
```

---

## Source File Structure

```text
apps/web/
├── app/(main)/conversations/
│   ├── layout.tsx                          # Conversation shell (goal panel toggle button)
│   ├── page.tsx                            # Conversation list / empty state
│   └── [conversationId]/
│       ├── page.tsx                        # Main conversation view
│       └── loading.tsx                     # Skeleton loading state
│
├── components/features/conversations/
│   ├── ConversationView.tsx                # Root component: tabs + status bar + message list + input
│   ├── MessageList.tsx                     # Virtualized scrollable list with auto-scroll
│   ├── MessageBubble.tsx                   # Single message: alignment, content, attachments, badges
│   ├── MessageContent.tsx                  # Markdown / CodeBlock / JsonViewer dispatch
│   ├── CodeBlock.tsx                       # Syntax highlight + copy button + collapse
│   ├── AttachmentCard.tsx                  # Image preview (Dialog) or download card
│   ├── InteractionTabs.tsx                 # Tab strip + activity badges
│   ├── StatusBar.tsx                       # State badge + agent info + reasoning mode + correction count
│   ├── MessageInput.tsx                    # Textarea + send button + mid-process banner
│   ├── TypingIndicator.tsx                 # Animated 3-dot indicator
│   ├── NewMessagesPill.tsx                 # "↓ N new messages" scroll-to-bottom pill
│   ├── MidProcessBadge.tsx                 # Inline badge on injected messages
│   ├── MergedFromBadge.tsx                 # Inline badge showing branch origin
│   ├── BranchCreationDialog.tsx            # Dialog: branch name + description + confirm
│   ├── MergeSheet.tsx                      # Sheet: message checklist + merge confirm
│   └── BranchOriginIndicator.tsx           # Visual indicator on branch-point messages
│
├── components/features/goals/
│   ├── GoalFeed.tsx                        # Goal sheet panel: selector + message stream + input
│   ├── GoalSelector.tsx                    # shadcn Select populated from workspace goals
│   ├── GoalMessageBubble.tsx               # Message bubble variant with agent attribution + interaction link
│   └── GoalLifecycleIndicator.tsx          # State badge: Active/Paused/Completed/Abandoned
│
├── lib/hooks/
│   ├── use-conversation.ts                 # TanStack Query: fetch conversation + interactions
│   ├── use-messages.ts                     # TanStack Query: paginated message history
│   ├── use-conversation-ws.ts              # WebSocket: subscribe + dispatch to Zustand + Query cache
│   ├── use-auto-scroll.ts                  # useRef sentinel + IntersectionObserver hook
│   ├── use-message-stream.ts               # Streaming buffer: Map<id, string> + rAF flush
│   ├── use-branch.ts                       # TanStack Mutation: create branch + merge branch
│   ├── use-send-message.ts                 # TanStack Mutation: POST /interactions/{id}/messages
│   ├── use-workspace-goals.ts              # TanStack Query: workspace goals + goal messages
│   └── use-goal-ws.ts                      # WebSocket: subscribe to workspace channel for goal events
│
└── lib/stores/
    └── conversation-store.ts               # Zustand: tab state, processing flag, scroll mode, goal panel
```
