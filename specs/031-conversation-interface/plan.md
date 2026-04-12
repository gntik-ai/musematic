# Implementation Plan: Conversation Interface

**Branch**: `031-conversation-interface` | **Date**: 2026-04-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/031-conversation-interface/spec.md`

## Summary

Implement the conversation interface as a React/Next.js frontend feature within `apps/web/`. The feature provides a chat-style conversation view with real-time WebSocket streaming (via the existing `lib/ws.ts` client), virtualized message list (`@tanstack/react-virtual`), rich content rendering (Markdown + code blocks + JSON viewer + file attachments), multi-interaction tabs with a live status bar, mid-process message injection, conversation branching/merging, and a workspace goal feed panel. All UI uses shadcn/ui primitives with Tailwind semantic tokens for dark-mode correctness.

## Technical Context

**Language/Version**: TypeScript 5.x (strict)  
**Primary Dependencies**: Next.js 14+ App Router, React 18+, shadcn/ui (all UI primitives), Tailwind CSS 3.4+, TanStack Query v5, Zustand 5.x, `@tanstack/react-virtual` v3 (new dependency — virtual list), `react-markdown` + `remark-gfm` (already in stack), `highlight.js` lazy (already in stack), React Hook Form 7.x + Zod 3.x (branch creation form), date-fns 4.x, Lucide React  
**Storage**: No new persistent storage — reads from backend API (feature 024 conversations/interactions + feature 018 workspaces goals) and WebSocket channels (feature 019)  
**Testing**: Vitest + React Testing Library + MSW + Playwright (existing constitution stack)  
**Target Platform**: Browser (web app, `apps/web/`)  
**Project Type**: Frontend feature — React component tree + hooks  
**Performance Goals**: New messages appear in < 500ms (SC-001); smooth 60fps scroll with 1,000+ messages (SC-002); Markdown render < 1s (SC-004); tab switch < 300ms (SC-005)  
**Constraints**: shadcn/ui for ALL UI primitives (no custom CSS files); all color tokens must be Tailwind semantic (dark mode compliance); `@tanstack/react-virtual` for virtualization when messages > 100  
**Scale/Scope**: 41 FRs, 6 user stories, ~25 new components + hooks

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Principle | Status | Notes |
|---|---|---|---|
| G-Frontend shadcn/ui | All UI primitives from shadcn, no alternative component libraries | PASS | All dialogs, sheets, tabs, selects, badges use shadcn |
| G-Frontend Tailwind | Utility-first, no custom CSS files except global tokens | PASS | All styling via Tailwind classes; dark mode via semantic token classes |
| G-Frontend TanStack Query | All API data fetching via TanStack Query | PASS | `use-conversation.ts`, `use-messages.ts`, `use-workspace-goals.ts` all use TQ v5 |
| G-Frontend Zustand | Auth state, workspace context, UI preferences via Zustand | PASS | `conversation-store.ts` manages tab state, processing flag, scroll mode |
| G-Frontend Forms | React Hook Form + Zod for forms | PASS | Branch creation dialog uses RHF + Zod |
| G-III-Kafka/WS | Async event coordination via Kafka/WebSocket | PASS | Real-time messages via existing `lib/ws.ts` WebSocket client (feature 019) |
| G-I Modular monolith | Frontend lives in `apps/web/` | PASS | No new services — feature 031 is purely frontend in `apps/web/` |
| G-IX Zero-trust | Visibility enforcement | PASS | All conversation and goal data fetched with JWT — backend enforces visibility; no client-side bypass |

**All applicable gates PASS.** No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/031-conversation-interface/
├── plan.md              # This file
├── research.md          # Phase 0 output — 14 decisions
├── data-model.md        # Phase 1 output — TypeScript types, Zustand store, WS events, component props
├── quickstart.md        # Phase 1 output — 20 test scenarios
├── contracts/
│   └── ui-contracts.md  # Phase 1 output — backend API contracts consumed, component contracts
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code

```text
apps/web/
├── app/(main)/conversations/
│   ├── layout.tsx                          # Conversation shell (goal panel toggle)
│   ├── page.tsx                            # Conversation list / empty state
│   └── [conversationId]/
│       ├── page.tsx                        # Main conversation view
│       └── loading.tsx                     # Skeleton loading state
│
├── components/features/conversations/
│   ├── ConversationView.tsx                # Root: tabs + status bar + message list + input
│   ├── MessageList.tsx                     # @tanstack/react-virtual + auto-scroll sentinel
│   ├── MessageBubble.tsx                   # Alignment + content dispatch + badges
│   ├── MessageContent.tsx                  # Markdown / CodeBlock / JsonViewer router
│   ├── CodeBlock.tsx                       # highlight.js (lazy) + copy + collapse
│   ├── AttachmentCard.tsx                  # Image Dialog lightbox or download card
│   ├── InteractionTabs.tsx                 # shadcn Tabs with activity badge
│   ├── StatusBar.tsx                       # State badge + agent + reasoning + correction count
│   ├── MessageInput.tsx                    # Textarea + send + mid-process banner
│   ├── TypingIndicator.tsx                 # Animated 3-dot
│   ├── NewMessagesPill.tsx                 # "↓ N new messages" pill
│   ├── MidProcessBadge.tsx                 # Inline badge on injected messages
│   ├── MergedFromBadge.tsx                 # Branch origin badge
│   ├── BranchCreationDialog.tsx            # RHF + Zod dialog
│   ├── MergeSheet.tsx                      # shadcn Sheet with message checklist
│   └── BranchOriginIndicator.tsx           # Visual indicator on branch-point messages
│
├── components/features/goals/
│   ├── GoalFeed.tsx                        # Goal sheet panel root
│   ├── GoalSelector.tsx                    # shadcn Select from workspace goals
│   ├── GoalMessageBubble.tsx               # Message + agent attribution + interaction link
│   └── GoalLifecycleIndicator.tsx          # State badge (Active/Paused/Completed/Abandoned)
│
├── lib/hooks/
│   ├── use-conversation.ts                 # TanStack Query: conversation + interactions + branches
│   ├── use-messages.ts                     # TanStack Query: paginated message history
│   ├── use-conversation-ws.ts              # WebSocket subscriptions + Zustand/Query dispatch
│   ├── use-auto-scroll.ts                  # IntersectionObserver sentinel hook
│   ├── use-message-stream.ts               # useRef Map streaming buffer + rAF flush
│   ├── use-branch.ts                       # TanStack Mutation: create + merge branch
│   ├── use-send-message.ts                 # TanStack Mutation: POST message
│   ├── use-workspace-goals.ts              # TanStack Query: goals + goal messages
│   └── use-goal-ws.ts                      # WebSocket: workspace channel goal events
│
└── lib/stores/
    └── conversation-store.ts               # Zustand: tab state, processing, scroll, goal panel
```

## Implementation Phases

### Phase 1 — Core Message List and Streaming (US1: P1)

**Goal**: Scrollable virtualized message list with real-time WebSocket streaming, auto-scroll, typing indicator, and connection resilience.

**Tasks**:
- `conversation-store.ts`: Zustand store with `isAgentProcessing`, `autoScrollEnabled`, `pendingMessageCount`
- `use-conversation-ws.ts`: WebSocket subscription to `conversation:{id}` channel; dispatch `typing.started/stopped` → Zustand; dispatch `message.created/completed` → TanStack Query cache
- `use-message-stream.ts`: Streaming buffer (`useRef<Map<string, string>>`), `requestAnimationFrame` flush
- `use-auto-scroll.ts`: `IntersectionObserver` sentinel hook
- `use-messages.ts`: TanStack Query paginated message fetch
- `MessageList.tsx`: `@tanstack/react-virtual` + auto-scroll sentinel + `NewMessagesPill`
- `MessageBubble.tsx`: Alignment based on `sender_type`, truncation at 50k chars + expand toggle
- `TypingIndicator.tsx`: Animated 3-dot, conditionally rendered from Zustand `isAgentProcessing`
- `[conversationId]/page.tsx`, `loading.tsx`: Route with Suspense skeleton

### Phase 2 — Rich Message Rendering (US2: P1)

**Goal**: Markdown, code syntax highlighting, JSON viewer, file attachments.

**Tasks**:
- `MessageContent.tsx`: Routes to `react-markdown`, `CodeBlock`, or `JsonViewer` based on content type
- `CodeBlock.tsx`: `highlight.js` dynamic import + language detection + copy button (`navigator.clipboard`) + collapse for blocks > 40 lines
- JSON detection heuristic: `language === "json"` OR valid `JSON.parse` result → render `JsonViewer` (reuse existing shared component)
- `AttachmentCard.tsx`: Image → `Dialog` lightbox; other files → download card with Lucide file icon
- `MessageBubble.tsx`: Wire `MessageContent` + `AttachmentCard` list

### Phase 3 — Interaction Tabs and Status Bar (US3: P1)

**Goal**: Multi-interaction tab strip, live status bar with real-time updates.

**Tasks**:
- `InteractionTabs.tsx`: shadcn `Tabs` with one tab per interaction; unread badge from Zustand
- `StatusBar.tsx`: State badge (shadcn `Badge`), agent FQN, reasoning mode label, self-correction count
- `use-conversation.ts`: TanStack Query for conversation + interactions; update interaction on `interaction.state_changed` WS event
- `use-conversation-ws.ts`: Add `interaction.state_changed` → invalidate interaction query
- `ConversationView.tsx`: Compose `InteractionTabs` + `StatusBar` + `MessageList` + `MessageInput`

### Phase 4 — Mid-Process Injection (US4: P2)

**Goal**: Message input always enabled; mid-process banner and badge.

**Tasks**:
- `MessageInput.tsx`: Always enabled; show processing banner when `isAgentProcessing=true`; `Ctrl/Cmd+Enter` keyboard shortcut
- `use-send-message.ts`: TanStack Mutation calling `POST /interactions/{id}/messages`; detect `is_mid_process` from Zustand state at send time
- `MidProcessBadge.tsx`: Amber badge on injected messages
- `MessageBubble.tsx`: Render `MidProcessBadge` when `message.is_mid_process_injection=true`

### Phase 5 — Branching and Merging (US5: P2)

**Goal**: Branch from message, branch tabs, merge selected messages back with origin badge.

**Tasks**:
- `BranchCreationDialog.tsx`: React Hook Form + Zod (name required ≤ 50 chars, description optional ≤ 200 chars) + submit → `use-branch.ts`
- `use-branch.ts`: Mutations for `POST /conversations/{id}/branches` and `POST /conversations/{id}/branches/{branch_id}/merge`; on branch created → add tab to Zustand
- `BranchOriginIndicator.tsx`: Icon on originating message (branch fork icon from Lucide)
- `MergeSheet.tsx`: shadcn `Sheet` with checklist of branch messages; disable confirm when none selected; on confirm → call merge mutation
- `MergedFromBadge.tsx`: Purple badge showing branch name on merged messages
- `conversation-store.ts`: Add `branchTabs` array + `addBranchTab` + `activeBranchId` + `setActiveBranch`
- `InteractionTabs.tsx`: Extend to include branch tabs after interaction tabs
- `use-conversation-ws.ts`: Handle `branch.created` and `branch.merged` events

### Phase 6 — Workspace Goal View (US6: P3)

**Goal**: Goal feed panel with selector, real-time stream, lifecycle indicator, posting.

**Tasks**:
- `use-workspace-goals.ts`: TanStack Query for goals list + goal messages (cursor-based pagination)
- `use-goal-ws.ts`: Subscribe to `workspace:{id}` channel for `goal.message_created` + `goal.state_changed` events → update Query cache
- `GoalSelector.tsx`: shadcn `Select` populated from workspace goals query; updates `selectedGoalId` in Zustand
- `GoalMessageBubble.tsx`: Extends `MessageBubble` with agent FQN attribution + clickable interaction link
- `GoalLifecycleIndicator.tsx`: shadcn `Badge` with status → variant mapping
- `GoalFeed.tsx`: Compose `GoalSelector` + `GoalMessageBubble` list + post input (disabled when goal completed/abandoned)
- `conversations/layout.tsx`: Add goal panel `Sheet` toggle button; render `GoalFeed` inside Sheet
- `conversation-store.ts`: Add `goalPanelOpen` + `selectedGoalId`

### Phase 7 — Polish and Integration

**Goal**: Accessibility, dark mode, responsiveness, connection status, full test coverage, linting.

**Tasks**:
- ARIA attributes: `role="log"` + `aria-live="polite"` on message list; all interactive labels
- Connection status banner: Wire `lib/ws.ts` connection state to a `ConnectionStatusBanner` (already exists in feature 015 scaffold)
- Message queue on disconnect: Hook into `lib/ws.ts` reconnect callback to re-deliver pending sends
- Dark mode audit: Verify all components use semantic tokens only (no hardcoded colors)
- Responsive audit: Test at 320px min width (mobile); verify no horizontal scroll
- `conftest` / MSW handlers for all API endpoints + WS mock
- Validate 95%+ coverage: run `pnpm test --coverage`
- ESLint + TypeScript strict pass: `pnpm lint && pnpm typecheck`

## Complexity Tracking

No constitution violations — no entries required.
