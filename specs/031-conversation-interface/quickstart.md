# Quickstart & Test Scenarios: Conversation Interface

**Feature**: 031-conversation-interface  
**Date**: 2026-04-12

These scenarios define the minimal test cases to verify each user story independently. They serve as both integration test criteria and acceptance verification scripts.

---

## Scenario 1: Message List Renders with Correct Alignment

**Story**: US1 — Message List and Streaming  
**Verifies**: FR-001, FR-002

**Setup**: Conversation with 3 messages: user message, agent message, system message

**Expected**:
- User message: right-aligned, primary color background
- Agent message: left-aligned, muted background, agent name header
- System message: centered, italic, no background
- Messages appear in chronological order

---

## Scenario 2: New Messages Stream in Real Time

**Story**: US1  
**Verifies**: FR-003, SC-001

**Setup**: WebSocket mock emits `message.created` event after page load

**Expected**:
- New message appears in list within 500ms of WebSocket event
- No page refresh required
- Message count in list increases by 1

---

## Scenario 3: Auto-Scroll Behavior

**Story**: US1  
**Verifies**: FR-004, FR-005

**Setup Part A (at bottom)**: User is at the bottom → new message arrives  
**Expected Part A**: View auto-scrolls to show new message; sentinel intersection detected

**Setup Part B (scrolled up)**: User scrolls up → new message arrives  
**Expected Part B**: Auto-scroll does NOT activate; "1 new message" pill appears; clicking pill scrolls to bottom

---

## Scenario 4: Typing Indicator Shows and Hides

**Story**: US1  
**Verifies**: FR-006

**Setup**: Mock WebSocket emits `typing.started`, then `typing.stopped` after 2 seconds

**Expected**:
- Typing indicator appears below last message after `typing.started`
- Typing indicator disappears after `typing.stopped`

---

## Scenario 5: Markdown Renders Correctly

**Story**: US2 — Rich Message Rendering  
**Verifies**: FR-007

**Setup**: Agent message content includes: `# Heading`, `**bold**`, `- list item`, `| col1 | col2 |`

**Expected**:
- `# Heading` renders as an `<h1>` element, not literal `#`
- `**bold**` renders as bold text
- List renders as `<ul>/<li>`
- Table renders as a styled table
- No raw Markdown symbols visible

---

## Scenario 6: Code Block With Syntax Highlight and Copy

**Story**: US2  
**Verifies**: FR-008, SC-004

**Setup**: Agent message with fenced code block:
```
```python
def hello():
    return "world"
```
```

**Expected**:
- Code renders with Python syntax highlighting (keywords colored)
- Copy button visible in code block header
- Clicking copy button copies code content to clipboard
- Highlight.js loads lazily (not blocking initial render)

---

## Scenario 7: JSON Viewer Renders Collapsible Tree

**Story**: US2  
**Verifies**: FR-009

**Setup**: Agent message with ` ```json ` code block containing nested JSON

**Expected**:
- JSON rendered in `JsonViewer` component, not plain text
- Root object/array is expanded by default
- Nested keys have expand/collapse toggles
- Clicking a toggle shows/hides nested content

---

## Scenario 8: File Attachment Renders

**Story**: US2  
**Verifies**: FR-010

**Setup Part A (image)**: Message with `.png` attachment  
**Expected Part A**: Image thumbnail shown; clicking opens Dialog lightbox

**Setup Part B (PDF)**: Message with `.pdf` attachment  
**Expected Part B**: File card shows filename, file type icon, download link

---

## Scenario 9: Interaction Tabs Switch Message List

**Story**: US3 — Interaction Tabs and Status Bar  
**Verifies**: FR-012, FR-013, SC-005

**Setup**: Conversation with 2 interactions: Interaction A (3 messages), Interaction B (2 messages)

**Expected**:
- Two tabs shown, one per interaction
- Clicking Interaction B tab: message list updates to show only B's 2 messages
- Tab switch completes within 300ms

---

## Scenario 10: Status Bar Shows Live Metadata

**Story**: US3  
**Verifies**: FR-014, FR-015

**Setup**: Active interaction with agent `finance-ops:analyzer`, reasoning_mode=`chain_of_thought`, self_correction_count=3, state=`active`

**Expected**:
- State badge shows "Active" (default variant)
- Agent identity shows "finance-ops:analyzer"
- Reasoning mode shows "Chain of Thought"
- Self-correction count shows "3 corrections"

**Update via WebSocket**: Mock emits `interaction.state_changed` with state=`completed`  
**Expected after update**: State badge updates to "Completed" (secondary variant) without page refresh

---

## Scenario 11: Unread Tab Badge

**Story**: US3  
**Verifies**: FR-016

**Setup**: User is on Interaction A tab; mock emits `message.created` on Interaction B

**Expected**: Interaction B tab shows a dot/badge indicating new activity; clicking the tab clears the badge

---

## Scenario 12: Mid-Process Injection Sends Message

**Story**: US4 — Mid-Process Injection  
**Verifies**: FR-017, FR-018, FR-019

**Setup**: `isAgentProcessing=true` in Zustand (mock `typing.started` event)

**Expected**:
- Input field is enabled (not disabled)
- Banner above input reads "Agent is processing — your message will be delivered as guidance"
- User types and clicks Send → POST `/interactions/{id}/messages` called with `is_mid_process_injection: true`
- Message appears in list immediately with `MidProcessBadge` ("sent during processing")

**Setup 2**: `isAgentProcessing=false`  
**Expected 2**: Banner absent; message sent normally, no `MidProcessBadge`

---

## Scenario 13: Branch Creation From Message

**Story**: US5 — Branching  
**Verifies**: FR-020, FR-021, FR-024

**Setup**: Click message action menu → "Branch from here"

**Expected**:
- `BranchCreationDialog` opens with name field and optional description field
- User enters "Approach B" → clicks Confirm
- POST `/conversations/{id}/branches` called with `originating_message_id`
- New tab "Approach B" appears in tab strip
- Originating message in main thread shows a branch indicator icon

---

## Scenario 14: Branch Merge Returns Content to Main Thread

**Story**: US5 — Merging  
**Verifies**: FR-022, FR-023, FR-025, SC-007

**Setup**: Branch "Approach B" has 2 messages; user opens `MergeSheet`

**Expected**:
- Sheet shows both branch messages with checkboxes
- User selects message 1 → clicks "Merge selected"
- POST `/conversations/{id}/branches/{branch_id}/merge` called with `message_ids: [msg1_id]`
- Message 1 appears in main thread with `MergedFromBadge` reading "from: Approach B"
- Message 2 does NOT appear in main thread

**Empty branch edge case**:
- Open `MergeSheet` for empty branch → "Merge selected" button is disabled

---

## Scenario 15: Workspace Goal View — Real-Time Feed

**Story**: US6 — Workspace Goal View  
**Verifies**: FR-026, FR-027, FR-028, FR-029, FR-030

**Setup**: Workspace with 2 active goals. Open goal panel → GoalSelector shows both goals.

**Select goal "Q2 Sales Analysis"**:
- Goal message stream loads with past messages
- Each message shows agent attribution + timestamp + interaction link
- Goal lifecycle badge shows "Active"

**Mock WS `goal.message_created`**:
- New message appears in stream in real time

**User posts "Focus on APAC region"**:
- POST `/workspaces/{id}/goals/{goal_id}/messages` called
- Message appears immediately in stream

---

## Scenario 16: Goal Completed — Posting Disabled

**Story**: US6  
**Verifies**: FR-031

**Setup**: Mock WS `goal.state_changed` with status=`completed` while goal panel open

**Expected**:
- Lifecycle badge updates to "Completed"
- Message input area shows "This goal has been completed" message and is disabled

---

## Scenario 17: WebSocket Reconnection

**Story**: US1  
**Verifies**: FR-033, FR-034, FR-035, SC-012

**Setup**: Mock WebSocket disconnect

**Expected**:
- Connection status banner appears: "Reconnecting..."
- User sends a message → message queued locally
- Mock WebSocket reconnects → banner disappears
- Queued message delivered (POST called)
- Any missed messages fetched (TanStack Query invalidated for conversation messages)

---

## Scenario 18: Long Conversation Performance

**Story**: US1  
**Verifies**: FR-036, SC-002

**Setup**: Conversation with 1,000 messages rendered

**Expected**:
- Initial render < 1s (only visible messages rendered, rest virtualized)
- Scrolling is smooth (no visible jank, 60fps)
- DOM node count stays low (< 50 message DOM nodes in the viewport at any time)

---

## Scenario 19: Long Message Truncation

**Story**: US1  
**Verifies**: FR-037

**Setup**: Agent message with 60,000 characters

**Expected**:
- Message shows first ~500 characters then "…show more" button
- Clicking "show more" expands the full content
- Clicking "show less" collapses back

---

## Scenario 20: Dark Mode Renders Correctly

**Story**: All stories  
**Verifies**: FR-040, SC-010

**Setup**: Apply `.dark` class to `<html>` element

**Expected**:
- All semantic color tokens render correctly (user bubble readable, agent bubble readable, badges readable)
- No hardcoded colors produce invisible-text or invisible-border issues
- Syntax highlighting theme adapts to dark background

---

## Test Configuration Notes

- WebSocket events: Mock `lib/ws.ts` WebSocketClient via `vi.fn()` to emit events without a real server
- API calls: MSW service worker intercepts all `/api/v1/...` requests with fixture responses
- Zustand: Reset store before each test with `act(() => useConversationStore.setState(initialState))`
- Virtualization: Mock `@tanstack/react-virtual` `useVirtualizer` to return fixed-height items in tests
- Clipboard: Mock `navigator.clipboard.writeText` with `vi.fn()`
- IntersectionObserver: Mock with `vi.fn()` that accepts a callback to control sentinel visibility
