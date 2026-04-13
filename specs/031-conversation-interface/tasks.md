# Tasks: Conversation Interface

**Input**: Design documents from `specs/031-conversation-interface/`  
**Feature**: 031-conversation-interface  
**Branch**: `031-conversation-interface`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US6)
- Exact file paths included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directory structure and Zustand store foundation shared by all stories.

- [X] T001 Create all feature directories: `apps/web/app/(main)/conversations/`, `apps/web/app/(main)/conversations/[conversationId]/`, `apps/web/components/features/conversations/`, `apps/web/components/features/goals/` (add `__placeholder__` files if needed to satisfy Next.js static analysis)
- [X] T002 Create `apps/web/lib/stores/conversation-store.ts` — Zustand store with: `activeBranchId: string | null`, `branchTabs: BranchTab[]`, `isAgentProcessing: boolean`, `processingInteractionId: string | null`, `autoScrollEnabled: boolean`, `pendingMessageCount: number`, `goalPanelOpen: boolean`, `selectedGoalId: string | null`, and all action methods (`setActiveBranch`, `setAgentProcessing`, `enableAutoScroll`, `pauseAutoScroll`, `incrementPending`, `clearPending`, `setGoalPanelOpen`, `setSelectedGoal`, `addBranchTab`) per data-model.md

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: TypeScript types, route scaffolding, and MSW handlers shared by all user stories.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T003 Create `apps/web/types/conversations.ts` with all TypeScript domain types from data-model.md: `Message`, `MessageAttachment`, `Interaction`, `Conversation`, `ConversationBranch`, `WorkspaceGoal`, `GoalMessage`, and all enum types (`MessageSenderType`, `MessageStatus`, `InteractionState`, `ReasoningMode`, `BranchStatus`, `GoalStatus`), plus all WebSocket event payload interfaces (`WsMessageCreated`, `WsMessageStreamed`, `WsMessageCompleted`, `WsTypingStarted`, `WsTypingStopped`, `WsInteractionStateChanged`, `WsBranchCreated`, `WsBranchMerged`, `WsGoalMessageCreated`, `WsGoalStateChanged`), and `queryKeys` factory object
- [X] T004 [P] Create `apps/web/app/(main)/conversations/layout.tsx` — Next.js layout for the conversations route group: renders `{children}` alongside a goal panel `Sheet` (shadcn) toggled by a `GoalFeed` button in the top bar; placeholder `GoalFeed` rendered in the Sheet for now; reads `goalPanelOpen` + `setGoalPanelOpen` from `useConversationStore`
- [X] T005 [P] Create `apps/web/app/(main)/conversations/page.tsx` — conversation list page: `useQuery` to `GET /conversations` with `queryKeys.conversationList(workspaceId)`; render shadcn `Card` list of conversations; empty state using existing `EmptyState` shared component; each item navigates to `/conversations/{id}`
- [X] T006 [P] Create `apps/web/app/(main)/conversations/[conversationId]/loading.tsx` — skeleton loading state using shadcn `Skeleton` components: 3-tab skeleton header + status bar skeleton + 5-message skeleton list
- [X] T007 [P] Create `apps/web/tests/mocks/handlers/conversations.ts` — MSW request handlers for all 8 API endpoints in contracts/ui-contracts.md: `GET /conversations/:id` (returns fixture conversation + interactions + branches), `GET /interactions/:id/messages` (returns cursor-paginated messages fixture), `POST /interactions/:id/messages` (201 with echo message), `POST /conversations/:id/branches` (201 with fixture branch), `POST /conversations/:id/branches/:branchId/merge` (200), `GET /workspaces/:id/goals` (returns 2 fixture goals), `GET /workspaces/:id/goals/:goalId/messages` (returns paginated goal messages), `POST /workspaces/:id/goals/:goalId/messages` (201 with echo)

**Checkpoint**: Foundation ready — all user story phases can now proceed.

---

## Phase 3: User Story 1 — Message List and Real-Time Streaming (Priority: P1) 🎯 MVP

**Goal**: Scrollable virtualized message list with WebSocket real-time streaming, auto-scroll, typing indicator, and reconnection banner. Users can see messages appear live as the agent produces them.

**Independent Test**: Open `/conversations/{id}` → message list shows existing messages with correct alignment (user right, agent left, system center). Mock WS `message.created` event → message appears without refresh. Scroll to top → `NewMessagesPill` appears when new message arrives. `typing.started` WS event → `TypingIndicator` visible below last message. `typing.stopped` → indicator gone.

- [X] T008 [P] [US1] Write `apps/web/tests/unit/hooks/use-auto-scroll.test.ts` — unit tests: IntersectionObserver callback sets `autoScrollEnabled=true` when sentinel enters viewport; sets `false` + calls `incrementPending()` when sentinel exits viewport; `enableAutoScroll()` action clears pending count; `sentinelRef` is a valid React ref
- [X] T009 [P] [US1] Write `apps/web/tests/unit/hooks/use-message-stream.test.ts` — unit tests: `addDelta(id, "hello ")` + `addDelta(id, "world")` → `getStreamingContent(id)` returns `"hello world"`; `clearStream(id)` → `getStreamingContent(id)` returns `""`; rAF callback flushes buffer to state on next frame
- [X] T010 [P] [US1] Write `apps/web/tests/integration/conversations/MessageList.test.tsx` — RTL tests for quickstart scenarios 1–4: correct bubble alignment (user=right, agent=left, system=center); WS mock emits `message.created` → message appears; auto-scroll pauses when scrolled up + pill appears; `TypingIndicator` shows on `typing.started`, hides on `typing.stopped`
- [X] T011 [US1] Create `apps/web/lib/hooks/use-auto-scroll.ts` — custom hook: `sentinelRef` (`useRef<HTMLDivElement>`), `IntersectionObserver` watching the sentinel; on enter: call `enableAutoScroll()` + `clearPending()` from Zustand; on exit: call `pauseAutoScroll()`; expose `scrollToBottom()` function that programmatically scrolls the sentinel into view; cleanup observer on unmount
- [X] T012 [US1] Create `apps/web/lib/hooks/use-message-stream.ts` — custom hook: `bufferRef = useRef<Map<string, string>>(new Map())`; `addDelta(messageId, delta)` appends to Map entry; `clearStream(messageId)` deletes entry; `requestAnimationFrame` loop reads buffer into local React state `streamingContent: Map<string, string>` at ~60fps; expose `getStreamingContent(messageId): string | undefined` from state
- [X] T013 [US1] Create `apps/web/lib/hooks/use-messages.ts` — `useInfiniteQuery` (TanStack Query v5) for `GET /interactions/{interactionId}/messages?cursor={cursor}&limit=50`; support `branchId` param (calls `GET /conversations/{id}/branches/{branchId}/messages` instead); `getNextPageParam` reads `next_cursor` from response; expose `messages` as flattened `Message[]` sorted by `created_at` ascending
- [X] T014 [US1] Create `apps/web/lib/hooks/use-conversation-ws.ts` — subscribe `lib/ws.ts` WebSocketClient to `conversation:{conversationId}` channel; dispatch events: `typing.started` → `store.setAgentProcessing(true, interaction_id)`; `typing.stopped` → `store.setAgentProcessing(false, null)`; `message.created` → `queryClient.setQueryData(queryKeys.messages(...), appendMessage)` + `store.incrementPending()` if `!autoScrollEnabled`; `message.streamed` → `addDelta(message_id, delta)` via `use-message-stream.ts`; `message.completed` → `queryClient.setQueryData` with final message, `clearStream(message_id)`; `branch.created` → `store.addBranchTab()`; return `isConnected: boolean` from `lib/ws.ts` connection state
- [X] T015 [US1] Create `apps/web/components/features/conversations/TypingIndicator.tsx` — three animated dots using Tailwind `animate-bounce` with staggered delays; `aria-label="Agent is typing"` with `aria-live="polite"`; only rendered when `isAgentProcessing` from Zustand. Create `apps/web/components/features/conversations/NewMessagesPill.tsx` — floating pill button positioned absolute bottom-center of message list; shows `↓ {count} new message{count > 1 ? "s" : ""}`, `role="button"`, `aria-label="N new messages, scroll to bottom"`, click calls `scrollToBottom()` from `use-auto-scroll.ts`; only rendered when `pendingMessageCount > 0`
- [X] T016 [US1] Create `apps/web/components/features/conversations/MessageBubble.tsx` — `user` sender: `flex justify-end`, bubble with `bg-primary text-primary-foreground`, right-aligned; `agent` sender: `flex justify-start`, bubble with `bg-muted`, agent name header above; `system` sender: `text-center text-muted-foreground italic`; content truncated at 50,000 chars with "…show more / show less" toggle; renders `isStreaming` shimmer (pulsing cursor at end of `streamingContent`); placeholder children slot for rich content (populated in US2); `aria-label` with sender name; note: `MidProcessBadge` and `MergedFromBadge` conditionally rendered (components created in US4/US5 — import with `?? null` guard until then)
- [X] T017 [US1] Create `apps/web/components/features/conversations/MessageList.tsx` — `@tanstack/react-virtual` `useVirtualizer` with `estimateSize={() => 100}` and `measureElement` for dynamic heights; renders `virtualizerItems` mapped to `MessageBubble`; auto-scroll via `use-auto-scroll.ts` sentinel `<div>` at end; renders `TypingIndicator` after last item when `isAgentProcessing`; renders `NewMessagesPill` overlay when `pendingMessageCount > 0`; `role="log"` + `aria-live="polite"` + `aria-label="Conversation messages"`. Create `apps/web/app/(main)/conversations/[conversationId]/page.tsx` — fetches conversation via `useQuery(queryKeys.conversation(id))`, mounts `use-conversation-ws.ts`, renders `MessageList` with `use-messages.ts` data and `use-message-stream.ts` streaming content

**Checkpoint**: User Story 1 fully functional — live message streaming, auto-scroll, and typing indicator all work independently.

---

## Phase 4: User Story 2 — Rich Message Rendering (Priority: P1)

**Goal**: Agent messages render Markdown, code blocks with syntax highlighting and copy, collapsible JSON viewers, and file attachment cards (image lightbox or download).

**Independent Test**: Agent message with `# Heading` → renders `<h1>`. Python code block → syntax colored + copy button (clipboard mock). ` ```json ` code block → `JsonViewer` with expand/collapse. `.png` attachment → image thumbnail + Dialog lightbox. `.pdf` attachment → download card with filename + Lucide icon.

- [X] T018 [P] [US2] Write `apps/web/tests/integration/conversations/MessageContent.test.tsx` — RTL tests for quickstart scenarios 5–8: Markdown headings/bold/lists/tables render as HTML (not raw symbols), code block has copy button, JSON block shows collapsible viewer, PNG attachment shows image, PDF attachment shows download link
- [X] T019 [US2] Create `apps/web/components/features/conversations/MessageContent.tsx` — routes to the correct renderer: if content is plain text (no Markdown, no code fences, no JSON) → `<p>` with text; if Markdown → `<ReactMarkdown>` with `remark-gfm`; for code blocks inside `react-markdown`: custom `code` renderer checks language + tries `JSON.parse` → if valid JSON renders `JsonViewer`, else renders `CodeBlock`; top-level detection heuristic: if entire content trims to valid `JSON.parse()` result → render `JsonViewer` directly
- [X] T020 [US2] Create `apps/web/components/features/conversations/CodeBlock.tsx` — renders `<pre><code>` with `highlight.js` applied via `dynamic(() => import("highlight.js"))` (lazy); language detection from fenced block language string; copy-to-clipboard button using `navigator.clipboard.writeText()` with a "Copied!" transient state (1.5s timeout); collapse toggle when block exceeds 40 lines (show first 10 + "show all N lines" button); `aria-label` on copy button
- [X] T021 [US2] Create `apps/web/components/features/conversations/AttachmentCard.tsx` — if `mime_type` starts with `image/`: render `<img>` thumbnail + shadcn `Dialog` for lightbox on click; otherwise: render download card with Lucide icon (FileText for generic, FileCode for code, FileImage for non-image image types), filename, formatted size (`date-fns` format not needed — use `Intl.NumberFormat` for bytes), anchor `download` link to `attachment.url`
- [X] T022 [US2] Update `apps/web/components/features/conversations/MessageBubble.tsx` — replace content placeholder slot with `<MessageContent content={message.content} />` and `{message.attachments.map(a => <AttachmentCard key={a.id} attachment={a} />)}` below the content; ensure streaming content (`streamingContent` prop) is passed to `MessageContent` when `isStreaming=true` (pass raw string, `MessageContent` renders as plain text during streaming)

**Checkpoint**: User Story 2 fully functional — all rich content types render correctly and independently of the streaming/WS features.

---

## Phase 5: User Story 3 — Interaction Tabs and Status Bar (Priority: P1)

**Goal**: One shadcn tab per interaction, tab switching updates the message list, status bar shows live interaction state/agent/reasoning mode/self-correction count with real-time updates.

**Independent Test**: Conversation with 2 interactions → 2 tabs shown → click tab B → message list switches to B's messages → tab switch completes in < 300ms. Mock WS `interaction.state_changed` → status bar state badge updates without refresh. Self-correction count shows "3 corrections" when `self_correction_count=3`.

- [X] T023 [P] [US3] Write `apps/web/tests/integration/conversations/InteractionTabs.test.tsx` — RTL tests for quickstart scenarios 9–11: 2 tabs rendered, click tab B switches message list, tab B shows unread dot when WS message arrives while tab A is active, status bar shows correct state badge/agent/reasoning/correction values, WS `interaction.state_changed` updates status bar in real time
- [X] T024 [US3] Create `apps/web/lib/hooks/use-conversation.ts` — `useQuery(queryKeys.conversation(id))` fetching `GET /conversations/{id}` returning `Conversation` with nested `interactions` and `branches`; also export `useInteraction(interactionId)` reading from cache; TanStack Query `staleTime: 30_000` (30s)
- [X] T025 [US3] Create `apps/web/components/features/conversations/InteractionTabs.tsx` — shadcn `Tabs` component: `TabsList` with one `TabsTrigger` per interaction labeled with `interaction.agent_display_name`; active tab = `activeBranchId === null ? activeInteractionId` (from Zustand); unread activity badge (Tailwind dot) on non-active tabs when `hasUnreadMessages` is true; emit `store.setActiveBranch(null)` + update `activeInteractionId` on click; branch tabs (if any from `store.branchTabs`) appended after interaction tabs with italic label
- [X] T026 [US3] Create `apps/web/components/features/conversations/StatusBar.tsx` — renders below tab strip; reads `interaction: Interaction` + `isProcessing: boolean` from props; state badge: shadcn `Badge` with variant mapping (`active`→`default`, `completed`→`secondary`, `failed`→`destructive`, `awaiting_approval`→`outline` with `animate-pulse`); agent FQN as plain text; reasoning mode label: `"Chain of Thought"` / `"Tree of Thought"` / `"—"`; self-correction count: `"{n} corrections"` hidden when 0
- [X] T027 [US3] Create `apps/web/components/features/conversations/ConversationView.tsx` — root composition component: `InteractionTabs` + `StatusBar` + `MessageList` (filtered to `activeInteractionId`) + `MessageInput`; reads `activeInteractionId` from local state (initialized to `conversation.interactions[0].id`); passes `isAgentProcessing` from Zustand to `StatusBar` and `MessageInput`; wire into `[conversationId]/page.tsx` replacing previous direct `MessageList` render
- [X] T028 [US3] Extend `apps/web/lib/hooks/use-conversation-ws.ts` — add handler for `interaction.state_changed` event: call `queryClient.setQueryData(queryKeys.conversation(id), updateInteractionInCache)` to patch the interaction's `state`, `reasoning_mode`, and `self_correction_count` in the cached `Conversation` object; this triggers `StatusBar` re-render automatically via TanStack Query reactivity

**Checkpoint**: User Story 3 fully functional — multi-interaction navigation and live status bar work independently.

---

## Phase 6: User Story 4 — Mid-Process Message Injection (Priority: P2)

**Goal**: Input is always enabled. When agent is processing, a banner informs the user their message will be injected. Sent messages get an amber "sent during processing" badge.

**Independent Test**: Mock `typing.started` → banner appears above input reading "Agent is processing — your message will be delivered as guidance". Input is enabled. Send "redirect please" → POST `/interactions/{id}/messages` body includes `is_mid_process_injection: true`. Message appears with amber `MidProcessBadge`. Without processing active → no banner, no badge.

- [X] T029 [P] [US4] Write `apps/web/tests/integration/conversations/MessageInput.test.tsx` — RTL tests for quickstart scenario 12: input enabled when `isAgentProcessing=true`, banner text correct, send calls POST with `is_mid_process_injection: true`, `MidProcessBadge` on resulting message; scenario without processing: no banner, POST has `is_mid_process_injection: false`
- [X] T030 [US4] Create `apps/web/lib/hooks/use-send-message.ts` — TanStack `useMutation` calling `POST /interactions/{id}/messages`; `onMutate` optimistically appends message to TanStack Query cache with `status: "streaming"`; reads `store.isAgentProcessing` at mutation call time to set `is_mid_process_injection`; `onSuccess` replaces optimistic entry with server-returned message; `onError` removes optimistic entry and toasts error
- [X] T031 [US4] Create `apps/web/components/features/conversations/MessageInput.tsx` — shadcn `Textarea` with auto-resize (CSS `field-sizing: content` or `onInput` height sync); `Button` for send; mid-process banner: `<div>` with amber tokens visible only when `isAgentProcessing=true` from props; `Ctrl+Cmd+Enter` keyboard shortcut via `onKeyDown`; on send: call `useSendMessage().mutate({content, is_mid_process_injection})` from `use-send-message.ts`; clear input on successful send; `aria-label="Type a message"` on textarea; send button `aria-label="Send message"`
- [X] T032 [US4] Create `apps/web/components/features/conversations/MidProcessBadge.tsx` — small amber `Badge` component (shadcn `Badge` with custom Tailwind classes `bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200`) showing "sent during processing"; update `apps/web/components/features/conversations/MessageBubble.tsx` to import and render `<MidProcessBadge />` below bubble content when `message.is_mid_process_injection === true`

**Checkpoint**: User Story 4 fully functional — mid-process injection with banner, badge, and correct API flag works independently.

---

## Phase 7: User Story 5 — Conversation Branching and Merging (Priority: P2)

**Goal**: Users can create a named branch from any message (new tab appears), explore it, then selectively merge messages back into the main thread with a visual origin badge.

**Independent Test**: Click "Branch from here" on a message → `BranchCreationDialog` opens → enter "Approach B" → POST `/conversations/{id}/branches` → new "Approach B" tab appears → switch to branch tab → messages load. Open `MergeSheet` → select 1 of 2 messages → confirm → POST merge with selected IDs → selected message appears in main thread with purple `MergedFromBadge("from: Approach B")`. Empty branch → Merge button disabled.

- [X] T033 [P] [US5] Write `apps/web/tests/integration/conversations/BranchCreation.test.tsx` — RTL tests for quickstart scenario 13: message action "Branch from here" opens dialog, name field required (empty → validation error), submit calls POST with `originating_message_id`, new tab appears in strip, originating message shows branch fork icon
- [X] T034 [P] [US5] Write `apps/web/tests/integration/conversations/MergeSheet.test.tsx` — RTL tests for quickstart scenario 14: sheet shows branch messages as checklist, selecting 1 of 2 + confirm calls POST merge with correct IDs, merged message appears in main thread with badge, empty branch → confirm button disabled
- [X] T035 [US5] Create `apps/web/lib/hooks/use-branch.ts` — `useCreateBranch`: TanStack `useMutation` calling `POST /conversations/{id}/branches`; on success: call `store.addBranchTab(branch)` and invalidate `queryKeys.conversation(id)`; `useMergeBranch`: TanStack `useMutation` calling `POST /conversations/{id}/branches/{branchId}/merge`; on success: invalidate messages query for main thread to fetch merged messages
- [X] T036 [US5] Create `apps/web/components/features/conversations/BranchCreationDialog.tsx` — shadcn `Dialog`; form with React Hook Form + Zod: `name: z.string().min(1).max(50)` (required), `description: z.string().max(200).optional()`; submit calls `useCreateBranch().mutate({name, description, originating_message_id})`; `DialogTrigger` used as a controlled dialog (open/close via props); loading state on submit button; `aria-modal`, focus trap via shadcn Dialog
- [X] T037 [US5] Create `apps/web/components/features/conversations/MergeSheet.tsx` — shadcn `Sheet` (side panel); renders branch messages as `Checkbox` (shadcn) + `MessageBubble` list; tracks `selectedIds: Set<string>` in local state; confirm button disabled when `selectedIds.size === 0`; on confirm calls `useMergeBranch().mutate({branchId, message_ids: [...selectedIds]})`; `aria-label` on each checkbox
- [X] T038 [US5] Create `apps/web/components/features/conversations/MergedFromBadge.tsx` — small purple `Badge` showing `"from: {branchName}"` with `bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200`; update `apps/web/components/features/conversations/MessageBubble.tsx` to import and render `<MergedFromBadge branchName={message.branch_origin} />` when `message.branch_origin !== null`. Create `apps/web/components/features/conversations/BranchOriginIndicator.tsx` — small Lucide `GitBranch` icon rendered inline on the `MessageBubble` of the `originating_message_id` (flag set by conversation query data)
- [X] T039 [US5] Extend `apps/web/components/features/conversations/InteractionTabs.tsx` — read `store.branchTabs` from Zustand; render branch tabs after interaction tabs using same shadcn `TabsTrigger`; clicking a branch tab: calls `store.setActiveBranch(branchId)` and passes `branchId` to `use-messages.ts` so it queries branch messages; add "Branch from here" menu item to each `MessageBubble` via an `aria-label`-ed shadcn `DropdownMenu` (3-dot action button on hover) that triggers `BranchCreationDialog` for that message
- [X] T040 [US5] Extend `apps/web/lib/hooks/use-conversation-ws.ts` — add handlers: `branch.created` event → `store.addBranchTab(branch)` + `queryClient.invalidateQueries(queryKeys.conversation(id))`; `branch.merged` event → `queryClient.invalidateQueries(queryKeys.messages(id, null))` to refresh main thread with newly merged messages

**Checkpoint**: User Story 5 fully functional — branch creation, branch tab navigation, and merge-with-origin-badge all work independently.

---

## Phase 8: User Story 6 — Workspace Goal View (Priority: P3)

**Goal**: A togglable goal panel (Sheet) shows a real-time goal message feed with agent attribution, lifecycle indicator, goal selector, and a message input that is disabled when the goal is completed/abandoned.

**Independent Test**: Click "Goals" in conversation layout → Sheet opens → `GoalSelector` shows 2 goals → select "Q2 Sales Analysis" → goal messages load with agent FQN attribution + interaction links. Mock WS `goal.message_created` → message appears in real time. Post "Focus on APAC" → POST goal message called. Mock `goal.state_changed` with status=`completed` → badge updates, input shows "Goal completed" and is disabled.

- [X] T041 [P] [US6] Write `apps/web/tests/integration/goals/GoalFeed.test.tsx` — RTL tests for quickstart scenarios 15–16: goal selector shows 2 goals, switching goals loads different messages, new WS message appears in real time, posting calls POST, goal completed → input disabled + "Goal completed" message shown
- [X] T042 [US6] Create `apps/web/lib/hooks/use-workspace-goals.ts` — `useGoals(workspaceId)`: `useQuery(queryKeys.goals(workspaceId))` calling `GET /workspaces/{id}/goals`; `useGoalMessages(goalId)`: `useInfiniteQuery(queryKeys.goalMessages(goalId))` calling `GET /workspaces/{id}/goals/{goalId}/messages?cursor=&limit=50`; `usePostGoalMessage()`: `useMutation` calling `POST /workspaces/{id}/goals/{goalId}/messages` with optimistic update appending to goal messages cache
- [X] T043 [US6] Create `apps/web/lib/hooks/use-goal-ws.ts` — subscribe to `workspace:{workspaceId}` channel in `lib/ws.ts` (additive — does not open a new connection, just registers additional event handlers); handle `goal.message_created` → `queryClient.setQueryData(queryKeys.goalMessages(goalId), appendGoalMessage)`; handle `goal.state_changed` → `queryClient.setQueryData(queryKeys.goals(workspaceId), updateGoalInList)` and patch selected goal state in Zustand
- [X] T044 [US6] Create `apps/web/components/features/goals/GoalSelector.tsx` — shadcn `Select` component populated from `useGoals(workspaceId)` data; each option shows goal title + `GoalLifecycleIndicator` badge inline; on change: call `store.setSelectedGoal(goalId)`. Create `apps/web/components/features/goals/GoalLifecycleIndicator.tsx` — shadcn `Badge` with status→variant mapping: `active`→`default`, `paused`→`outline`, `completed`→`secondary`, `abandoned`→`destructive`; text is the capitalized status string
- [X] T045 [US6] Create `apps/web/components/features/goals/GoalMessageBubble.tsx` — extends basic message rendering: renders sender type alignment (agent=left, user=right, system=center) reusing same Tailwind classes as `MessageBubble`; adds agent FQN attribution line below agent message content (`text-xs text-muted-foreground`); renders clickable `Link` to `/conversations/{originating_interaction_id}` when `originating_interaction_id` is set (showing "↗ view interaction")
- [X] T046 [US6] Create `apps/web/components/features/goals/GoalFeed.tsx` — `GoalSelector` at top; virtualized message list (reuse `@tanstack/react-virtual` pattern) of `GoalMessageBubble` components from `useGoalMessages(selectedGoalId)`; `TypingIndicator` not needed (goals don't have per-goal typing events); message input at bottom: shadcn `Textarea` + send button disabled when `selectedGoal.status` is `"completed"` or `"abandoned"`, showing `"This goal has been {status}"` placeholder text; send calls `usePostGoalMessage().mutate({content})` from `use-workspace-goals.ts`
- [X] T047 [US6] Update `apps/web/app/(main)/conversations/layout.tsx` — render `GoalFeed` inside the Sheet component (replace the placeholder): `<GoalFeed workspaceId={currentWorkspace.id} initialGoalId={store.selectedGoalId} className="h-full" />`; mount `use-goal-ws.ts` at layout level so WS goal events are active whenever any conversation page is open

**Checkpoint**: User Story 6 fully functional — goal panel, real-time goal feed, agent attribution, and lifecycle-gated posting all work independently.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Accessibility, dark mode, responsiveness, connection status, coverage validation, and linting.

- [X] T048 Audit and add ARIA attributes across all components in `apps/web/components/features/conversations/` and `apps/web/components/features/goals/`: `MessageList` needs `role="log"` + `aria-live="polite"` + `aria-label="Conversation messages"` (per contracts/ui-contracts.md); verify all buttons have `aria-label`; verify shadcn Tabs emits `role="tablist"` / `role="tab"` / `role="tabpanel"`; add `Ctrl/Cmd+Enter` hint to `MessageInput` as `aria-describedby` tooltip
- [ ] T049 [P] Dark mode token audit across all conversation and goal components: verify no hardcoded hex colors or `gray-N` classes; confirm all color usage matches the token map in contracts/ui-contracts.md (`bg-primary`, `bg-muted`, `text-primary-foreground`, etc.); run visual check in `.dark` mode using Playwright screenshot or Storybook if available
- [ ] T050 [P] Responsive audit: verify `apps/web/app/(main)/conversations/` layout renders correctly at 320px viewport width (no horizontal scroll, tabs wrap or scroll horizontally, status bar text truncates not overflows, sheet panel is full-width on mobile); apply `min-w-0 truncate` as needed to text elements in `InteractionTabs`, `StatusBar`, `GoalSelector`
- [X] T051 [P] Wire connection status banner in `apps/web/app/(main)/conversations/layout.tsx`: import existing `ConnectionStatusBanner` shared component (from feature 015 scaffold); show it when `!isConnected` from `use-conversation-ws.ts`; ensure queued messages are retried on reconnect by calling `useSendMessage().mutate` for any pending items in a `useEffect` keyed on `isConnected` transition `false → true`
- [ ] T052 [P] Validate test coverage ≥ 95%: run `pnpm test --coverage --reporter=lcov` scoped to `components/features/conversations/`, `components/features/goals/`, `lib/hooks/use-conversation*.ts`, `lib/hooks/use-message*.ts`, `lib/hooks/use-branch*.ts`, `lib/hooks/use-goal*.ts`, `lib/stores/conversation-store.ts`; add missing tests for any component below threshold
- [X] T053 [P] Run `pnpm lint` (ESLint) and `pnpm typecheck` (tsc --noEmit) on `apps/web/`; fix all type errors and lint violations in the new files; ensure no `any` types remain in `types/conversations.ts` or any hook/component file

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 Core Streaming (Phase 3)**: Depends on Foundational only
- **US2 Rich Rendering (Phase 4)**: Depends on Foundational + US1 (`MessageBubble.tsx` must exist to extend)
- **US3 Tabs+StatusBar (Phase 5)**: Depends on Foundational + US1 (`ConversationView` wraps `MessageList`)
- **US4 Mid-Process (Phase 6)**: Depends on Foundational + US1 (`MessageList` + `MessageBubble` must exist)
- **US5 Branching (Phase 7)**: Depends on Foundational + US1 + US3 (extends `InteractionTabs`)
- **US6 Goal View (Phase 8)**: Depends on Foundational + US1 (reuses `@tanstack/react-virtual` pattern from `MessageList`)
- **Polish (Phase 9)**: Depends on all user story phases

### User Story Independence Summary

| Story | Can Start After | Integrates With |
|---|---|---|
| US1 Core Streaming | Foundational | — |
| US2 Rich Rendering | Foundational + US1 | US1 (`MessageBubble`) |
| US3 Tabs+StatusBar | Foundational + US1 | US1 (`MessageList` + page) |
| US4 Mid-Process | Foundational + US1 | US1 (`MessageBubble`) |
| US5 Branching | Foundational + US1 + US3 | US1 (`MessageBubble`), US3 (`InteractionTabs`) |
| US6 Goal View | Foundational + US1 | US1 (`@tanstack/react-virtual` pattern) |

### Within Each User Story

- Test tasks (marked [P]) written alongside implementation
- Types/hooks before components
- Components before route pages
- Core rendering before extension (e.g., US1 MessageBubble before US2 rich content)

### Parallel Opportunities

- T003–T007 (foundational): T004, T005, T006, T007 all independent files, run in parallel
- T008, T009, T010 (US1 tests): all test files, run in parallel alongside T011-T014
- T033, T034 (US5 tests): two different test files, run in parallel
- T049, T050, T051, T052, T053 (polish): all independent audits, run in parallel

---

## Parallel Execution Examples

### Phase 2 — Foundational

```bash
# All 4 can run simultaneously:
Task T004: "Create conversations/layout.tsx shell"
Task T005: "Create conversations/page.tsx list page"
Task T006: "Create [conversationId]/loading.tsx skeleton"
Task T007: "Create MSW handlers for all 8 API endpoints"
```

### Phase 3 — User Story 1

```bash
# Tests and implementation can start in parallel:
Task T008: "Write use-auto-scroll.test.ts"
Task T009: "Write use-message-stream.test.ts"
Task T010: "Write MessageList.test.tsx"
Task T011: "Implement use-auto-scroll.ts"   # independent file
Task T012: "Implement use-message-stream.ts" # independent file
Task T013: "Implement use-messages.ts"       # independent file
# T014 (use-conversation-ws.ts) depends on T011-T013 to reference them
# T015-T017 depend on T011-T014
```

### Phase 9 — Polish

```bash
# All 5 run simultaneously (different concerns):
Task T049: "Dark mode token audit"
Task T050: "Responsive 320px audit"
Task T051: "Connection banner wiring"
Task T052: "Coverage validation"
Task T053: "ESLint + TypeScript check"
```

---

## Implementation Strategy

### MVP First (User Stories 1–3 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T007) — **critical blocker**
3. Complete Phase 3: US1 Core Streaming (T008–T017)
4. Complete Phase 4: US2 Rich Rendering (T018–T022)
5. Complete Phase 5: US3 Tabs+StatusBar (T023–T028)
6. **STOP and VALIDATE**: All 3 P1 stories work end-to-end in a running browser
7. Demo: Open a conversation → see streaming messages → switch tabs → status bar updates → Markdown renders

### Full Incremental Delivery

1. Setup + Foundational → project wired
2. US1 → live chat streaming working
3. US2 → rich agent responses readable
4. US3 → multi-agent navigation + status visibility
5. US4 → mid-process guidance enabled
6. US5 → exploratory branching unlocked
7. US6 → workspace goal coordination visible

### Parallel Team Strategy

With 3 developers after Foundational completes:
- **Dev A**: US1 Core Streaming → US2 Rich Rendering (sequential — US2 extends MessageBubble)
- **Dev B**: US3 Tabs+StatusBar (independent of US2 content rendering) → US4 Mid-Process
- **Dev C**: US6 Goal View (independent of US2/US3/US4) → Polish

---

## Notes

- `[P]` tasks operate on distinct files — no merge conflicts when parallelized
- `@tanstack/react-virtual` is a new `apps/web` dependency — add to `apps/web/package.json` in T001 or T017
- All color tokens follow contracts/ui-contracts.md dark-mode token contract — no hardcoded colors anywhere
- `navigator.clipboard` needs `secure context` (HTTPS or localhost) — MSW + JSDOM tests need `vi.stubGlobal("navigator", ...)` mock
- `IntersectionObserver` not available in JSDOM — mock with `vi.fn()` in test setup (`apps/web/tests/setup.ts`)
- `lib/ws.ts` WebSocketClient (feature 015) must not be opened twice for the same channel — `use-goal-ws.ts` adds listeners to the existing workspace channel, it does not create a new WebSocket connection
- `highlight.js` is already listed in the constitution as lazy — use `dynamic(() => import("highlight.js/lib/core"), { ssr: false })` in `CodeBlock.tsx`
- Commit after each phase checkpoint to keep history clean and bisectable
