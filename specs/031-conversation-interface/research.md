# Research: Conversation Interface

**Feature**: 031-conversation-interface  
**Date**: 2026-04-12  
**Status**: Complete

---

## Decision 1: Virtual Scroll Library

**Decision**: `@tanstack/react-virtual` (v3) for message list virtualization.

**Rationale**: TanStack is already the project's choice for server state (TanStack Query v5) and tabular data (TanStack Table v8). Adding `@tanstack/react-virtual` keeps the dependency family consistent and avoids a second virtual-scroll library. It integrates directly with `ScrollArea` from shadcn by exposing a `virtualizer` hook that provides item measurements and offsetting — no opinionated wrapper components to fight against shadcn's styling.

**Alternatives considered**: `react-window` (Facebook) — good performance but older API, needs bridging to work with shadcn's ScrollArea. `react-virtuoso` — excellent list-specific API but adds a new dependency family. Manual windowing — fragile and hard to maintain for varying message heights.

---

## Decision 2: Auto-Scroll Strategy

**Decision**: Use a `useRef` sentinel `<div>` at the bottom of the message list, observed by a single `IntersectionObserver`. When the sentinel is visible, the user is "at the bottom" and auto-scroll is active. When hidden (user scrolled up), auto-scroll is paused. On new message arrival while paused, a "↓ N new messages" pill badge appears. Clicking the badge or the sentinel becoming visible again re-enables auto-scroll.

**Rationale**: `IntersectionObserver` is a browser-native, performant API that fires only when visibility changes — no scroll-event polling (which would run on every pixel of scroll). The sentinel pattern decouples the scroll logic from message rendering.

**Alternatives considered**: Scroll event listener + `scrollTop >= scrollHeight - clientHeight - threshold` — works but fires on every scroll pixel and requires throttling. Manually tracking scroll position in Zustand — unnecessary complexity.

---

## Decision 3: WebSocket Integration

**Decision**: Reuse `lib/ws.ts` WebSocketClient from feature 015 (Next.js scaffold). Subscribe to these channels per conversation view:

| Channel | Event types consumed |
|---|---|
| `conversation:{conversationId}` | `message.created`, `message.streamed` (partial chunk), `message.completed`, `typing.started`, `typing.stopped`, `interaction.state_changed`, `branch.created`, `branch.merged` |
| `workspace:{workspaceId}` (already open) | `goal.message_created`, `goal.state_changed` |

Message streaming (partial chunks) uses a `message.streamed` event with `{message_id, delta}`. The component accumulates deltas in a local `Map<message_id, string>` held in component state (not Zustand — it changes too rapidly for global store efficiency).

**Alternatives considered**: Server-Sent Events (SSE) for streaming — unidirectional only, can't carry typing events. Polling — violates constitution §III (Kafka/WebSocket for async coordination).

---

## Decision 4: Zustand Store Structure

**Decision**: One conversation Zustand store (`useConversationStore`) per mounted conversation page, managing:

```typescript
interface ConversationStore {
  activeInteractionId: string | null
  isAgentProcessing: boolean         // true while typing.started without typing.stopped
  autoScrollEnabled: boolean
  pendingMessageCount: number        // unread count while auto-scroll paused
  branchTabs: BranchTab[]            // [{id, name, isActive}]
}
```

TanStack Query handles server state (conversation data, message history, goal messages). Zustand handles ephemeral UI state only (active tab, scroll mode, processing flag).

**Alternatives considered**: All state in TanStack Query — streaming partial message chunks mutate too rapidly for React Query's cache (causes excessive re-renders). All state in component `useState` — branch/tab state needs to be accessible across `MessageList` + `StatusBar` + `InteractionTabs` without prop-drilling.

---

## Decision 5: Message Streaming Architecture

**Decision**: Incoming `message.streamed` events are accumulated in a `useRef<Map<string, string>>` (streaming buffer) inside the `MessageList` component. This avoids Zustand and TanStack Query for rapidly-changing partial content. When `message.completed` arrives, the final content is written to the TanStack Query cache (via `queryClient.setQueryData`) and the streaming buffer entry is cleared.

**Rationale**: A `useRef` Map does not trigger React re-renders on write. The component uses `requestAnimationFrame` to batch buffer reads and render the partial content at 60fps. Writing to TanStack Query cache only on completion keeps the cache consistent with the server state.

**Alternatives considered**: Write every chunk to TanStack Query cache — 50+ cache writes per second per streaming message causes excessive re-renders. Write chunks to Zustand — same problem. Direct DOM mutation — bypasses React entirely, unsafe and hard to test.

---

## Decision 6: Markdown and Code Rendering

**Decision**: 
- Markdown: `react-markdown` + `remark-gfm` — already in constitution stack for "Agent message rendering"
- Syntax highlighting: `highlight.js` (lazy loaded) — already in constitution stack
- JSON viewer: Reuse `JsonViewer` shared component from feature 015 scaffold
- Code blocks: Custom `CodeBlock` component (wraps `highlight.js`) with language detection, copy-to-clipboard via `navigator.clipboard.writeText`, and a collapse toggle for blocks > 40 lines

JSON detection heuristic: if a code block has `json` language specifier OR the content trims to a valid `JSON.parse()` result, render `JsonViewer` instead of plain `CodeBlock`.

**Alternatives considered**: `prism-react-renderer` — more flexible but adds a dependency when `highlight.js` is already present. `monaco-editor` for code blocks — too heavy (Monaco is for editable code, not display).

---

## Decision 7: File Attachment Rendering

**Decision**: Attachment references in messages are rendered as:
- **Images** (`.png`, `.jpg`, `.gif`, `.webp`, `.svg`): `<img>` wrapped in a `Dialog` (shadcn) for lightbox preview
- **Other files**: A download card showing filename, file type icon (Lucide), and a download link to the object storage URL

Attachment metadata (filename, size, mime_type, url) is carried in the message object from the backend. No client-side upload in this feature (upload is out of scope per assumptions).

**Alternatives considered**: Inline PDF rendering — too complex for v1, deferred. Video preview — same.

---

## Decision 8: Branch and Merge State Model

**Decision**: Branches are first-class tabs in the conversation view. The tab order is: main thread first, then branches in creation order. Branch tabs show the branch name truncated to 20 characters.

Merge flow:
1. User clicks "Merge" button on a branch tab → a `Sheet` (shadcn side panel) opens
2. Sheet shows all branch messages as a checklist (multiple select)
3. User selects messages → clicks "Merge selected" → calls `POST /conversations/{id}/branches/{branch_id}/merge` with selected message IDs
4. On success, selected messages appear in the main thread with a `MergedFromBadge` component showing the branch name

Branch creation flow:
1. Long-press or right-click a message (or dedicated "Branch from here" button in message actions menu) → `Dialog` opens asking for name + optional description
2. On confirm → calls `POST /conversations/{id}/branches`
3. On success → new tab appears, WebSocket `branch.created` event triggers tab list update

**Alternatives considered**: Inline merge diff UI — too complex. Automatic merge of all branch messages — user needs control over what merges back.

---

## Decision 9: Mid-Process Injection UX

**Decision**: The message input area (`MessageInput` component) is always enabled — it is never disabled while the agent is processing. When `isAgentProcessing=true` from Zustand:
- A subtle banner appears above the input: "Agent is processing — your message will be delivered as guidance"
- The send button shows a secondary visual style (still clickable)
- After sending, the message receives a `MidProcessBadge` ("sent during processing")

The injection is delivered via the same `POST /interactions/{id}/messages` endpoint with an `is_mid_process=true` flag.

**Alternatives considered**: Disable input while processing — bad UX, prevents user from redirecting agent. Separate "interrupt" button — confusing UX (users don't think in terms of interrupts).

---

## Decision 10: Goal View Integration

**Decision**: The Workspace Goal View is a separate route segment: `app/(main)/conversations/goals/page.tsx` — or alternatively a toggle within the conversations layout. Given that goals are workspace-level (not tied to a single conversation), the goal view is a **sidebar panel** within the conversations layout, togglable via a "Goals" button in the conversation shell.

Goal messages use the same `MessageBubble` component as conversation messages, with an additional `agent_fqn` attribution line below the message content. The `GoalSelector` is a shadcn `Select` populated from `GET /workspaces/{id}/goals`. Goal posting uses `POST /workspaces/{id}/goals/{goal_id}/messages`.

**Alternatives considered**: Separate page route — requires navigation, breaks the "real-time side-by-side" use case. Full-width goal view — better for dedicated goal work, but the spec describes it as a companion to conversations, not a replacement.

---

## Decision 11: Accessibility Strategy

**Decision**:
- Message list: `role="log"` on the container, `aria-live="polite"` for new messages (not "assertive" — assertive interrupts screen reader too aggressively for chat)
- Interaction tabs: shadcn `Tabs` uses `role="tablist"` / `role="tab"` / `role="tabpanel"` natively
- Branch dialog: shadcn `Dialog` traps focus and provides `aria-modal`
- Merge sheet: shadcn `Sheet` provides accessible slide-in panel
- New message pill badge: `aria-label="N new messages, click to scroll"` 
- Keyboard shortcut: `Ctrl/Cmd+Enter` to send message

---

## Decision 12: Test Strategy

**Decision**: Vitest + React Testing Library (RTL) + MSW for API mocks + `vi.fn()` for WebSocket client mock. Key test categories:

1. **Unit**: `useAutoScroll` hook, RRF merge, streaming buffer accumulation, Markdown rendering snapshot
2. **Integration (RTL)**: Message list renders correct bubble alignment; tab switching updates displayed messages; branch creation dialog flow; mid-process injection banner; merge sheet selection flow
3. **E2E** (Playwright, scope-limited): Real-time message delivery via WebSocket mock; auto-scroll behavior with large message count
4. **Accessibility**: `axe-core` via `@axe-core/react` in development for automated a11y checks; `@testing-library/jest-dom` for ARIA role assertions

No Storybook stories required (not in the constitution stack).

---

## Decision 13: Route Structure

**Decision**: 

```
app/(main)/
  conversations/
    page.tsx                    # Conversation list (empty state if none)
    layout.tsx                  # Conversation shell (goal panel toggle)
    [conversationId]/
      page.tsx                  # Main conversation view
      loading.tsx               # Skeleton loading state
```

Goal view is rendered as a `Sheet` panel (shadcn) toggled from the conversation shell layout, not a separate route. This allows the goal panel to be open alongside any conversation without losing the conversation context.

---

## Decision 14: Performance Targets Mapping

| SC | Target | Strategy |
|---|---|---|
| SC-001 (new msg < 500ms) | WebSocket push, no polling | Feature 019 WebSocket gateway already provides this |
| SC-002 (smooth with 1000+ msgs) | Virtualized list | `@tanstack/react-virtual` with dynamic heights |
| SC-004 (Markdown < 1s) | Lazy `highlight.js` | Dynamic import, code blocks highlight after initial render |
| SC-005 (tab switch < 300ms) | Optimistic local state | Switch tab immediately, load messages from cache first |
| SC-012 (reconnect < 10s) | Reconnect backoff in ws.ts | `lib/ws.ts` already implements exponential backoff 1s→30s cap |
