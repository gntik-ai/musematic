# Feature Specification: Conversation Interface

**Feature Branch**: `031-conversation-interface`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: "Chat-style conversation view with real-time message streaming, Markdown rendering, multiple interaction tabs, reasoning mode indicator, self-correction progress, mid-process injection, and conversation branching/merging. Workspace goal view with real-time goal message feed."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Message List and Real-Time Streaming (Priority: P1)

A workspace member opens a conversation to interact with an agent. They see a scrollable message list with previous messages displayed as bubbles: their own messages aligned right, agent responses aligned left, and system notifications centered. As the agent responds, new messages appear in real time without the user refreshing the page. The view automatically scrolls to the latest message. While the agent is composing a response, a typing indicator is shown so the user knows the agent is working.

**Why this priority**: The message list is the fundamental interaction surface. Without it, no conversation can take place — all other features (tabs, branching, goal view) build on top of this core.

**Independent Test**: Open a conversation → see previous messages in correct bubble layout (user right, agent left, system center). Send a message → agent response streams in real time → view auto-scrolls to bottom. While agent is processing → typing indicator is visible. Scroll up to read old messages → auto-scroll pauses. New message arrives → auto-scroll resumes only when user is near the bottom.

**Acceptance Scenarios**:

1. **Given** a conversation with existing messages, **When** the user opens it, **Then** messages are displayed in chronological order with correct alignment (user right, agent left, system centered).
2. **Given** an open conversation, **When** the agent sends a new message, **Then** the message appears in real time without a page refresh.
3. **Given** the user is at the bottom of the message list, **When** a new message arrives, **Then** the view auto-scrolls to show the latest message.
4. **Given** the user has scrolled up to read older messages, **When** a new message arrives, **Then** auto-scroll does NOT activate (preserving the user's reading position), and a "new message" indicator appears.
5. **Given** the agent is processing a response, **When** the user looks at the conversation, **Then** a typing indicator (animated) is visible below the last message.

---

### User Story 2 — Rich Message Rendering (Priority: P1)

Agent responses often include structured content: Markdown formatting (headings, bold, lists, tables), fenced code blocks with syntax highlighting and a copy button, embedded JSON structures that can be expanded/collapsed, and file attachment references that can be previewed or downloaded. The rendering must be consistent and readable, ensuring that complex agent outputs are presented clearly rather than as raw text.

**Why this priority**: Agents produce rich, structured output as their core value. Without proper rendering, code blocks become unreadable walls of text and JSON structures lose their hierarchy — fundamentally degrading the user's ability to act on agent responses.

**Independent Test**: Agent sends a response with Markdown headings + a Python code block + a JSON payload + a file attachment → all render correctly: headings are styled, code block has syntax highlighting and a copy button, JSON is collapsible, file attachment shows a preview/download link. No raw Markdown symbols are visible.

**Acceptance Scenarios**:

1. **Given** an agent message containing Markdown (headings, bold, lists, tables), **When** it is displayed, **Then** the content is rendered as formatted rich text, not raw Markdown.
2. **Given** an agent message containing a fenced code block, **When** it is displayed, **Then** the code block shows syntax highlighting and includes a "copy to clipboard" button.
3. **Given** an agent message containing a JSON structure, **When** it is displayed, **Then** the JSON is shown in a collapsible viewer that allows the user to expand/collapse nested keys.
4. **Given** an agent message referencing a file attachment, **When** it is displayed, **Then** the attachment shows a preview (if applicable, e.g., images) and a download link.
5. **Given** a very long code block or JSON structure, **When** it is displayed, **Then** the content area is scrollable without overflowing the message bubble.

---

### User Story 3 — Interaction Tabs and Status Bar (Priority: P1)

A conversation can contain multiple interactions — distinct exchanges between the user and different agents or the same agent in different modes. The user sees tabs at the top of the conversation view, one per interaction. Switching tabs changes the message list to show only that interaction's messages. A status bar below the tabs shows the current interaction's state (active, completed, failed, awaiting approval), the agent's identity, its current reasoning mode (e.g., chain-of-thought, tree-of-thought, or none), and the number of self-correction iterations it has performed in the current response cycle.

**Why this priority**: Multi-interaction support and status visibility are essential for the agentic mesh use case where one conversation may involve multiple agents. Without tabs, users cannot navigate between different agent interactions within a single conversation.

**Independent Test**: Open a conversation with 3 interactions → see 3 tabs → click each tab → message list updates to that interaction's messages. Status bar shows the active interaction's agent name, state badge ("Active"), reasoning mode ("chain-of-thought"), and self-correction count ("2 corrections"). When state changes (e.g., interaction completes), the status bar and tab badge update in real time.

**Acceptance Scenarios**:

1. **Given** a conversation with multiple interactions, **When** the user views it, **Then** a tab is shown for each interaction, labeled with the agent name or interaction title.
2. **Given** multiple interaction tabs, **When** the user clicks a different tab, **Then** the message list switches to display only that interaction's messages.
3. **Given** an active interaction, **When** the user views the status bar, **Then** it displays: the interaction state (active/completed/failed/awaiting-approval), agent identity, reasoning mode, and self-correction iteration count.
4. **Given** an interaction's state changes (e.g., from active to completed), **When** the change occurs, **Then** the status bar updates in real time and the tab shows a visual indicator (e.g., a badge or icon change).
5. **Given** the agent is in "tree-of-thought" reasoning mode with 3 self-correction iterations, **When** the user views the status bar, **Then** the reasoning mode reads "tree-of-thought" and the self-correction count displays "3".

---

### User Story 4 — Mid-Process Message Injection (Priority: P2)

While an agent is still processing a response (typing indicator visible), the user can send a new message to provide additional context, redirect the agent, or ask it to change approach. This "mid-process injection" does not cancel or interrupt the agent's current processing — it queues the user's message so the agent can incorporate it. The injected message appears in the message list immediately with a visual indicator that it was sent mid-process.

**Why this priority**: Mid-process injection enables fluid human-agent collaboration, a key differentiator for agentic workflows. However, conversations are still fully functional without it (users can wait for the agent to finish, then redirect), so it is an enhancement.

**Independent Test**: Agent is processing (typing indicator visible) → user types and sends a message → message appears immediately in the list with a "sent during processing" indicator → agent eventually responds (incorporating or acknowledging the injection). If the agent has already finished processing before the injection is delivered, the message is treated as a normal follow-up.

**Acceptance Scenarios**:

1. **Given** the agent is processing a response, **When** the user types and sends a message, **Then** the message appears in the list immediately, marked as a mid-process injection.
2. **Given** a mid-process injection has been sent, **When** the agent finishes processing, **Then** the agent's next response acknowledges or incorporates the injected context (behavior depends on the agent, not this UI feature).
3. **Given** the agent is NOT processing, **When** the user sends a message, **Then** the message is treated as a normal message (no mid-process indicator).
4. **Given** the message input area, **When** the agent is processing, **Then** the input field remains enabled (not disabled or grayed out) and includes a hint that the message will be injected mid-process.

---

### User Story 5 — Conversation Branching and Merging (Priority: P2)

When a user wants to explore an alternative approach without losing the current conversation thread, they can branch the conversation. Branching creates a parallel thread starting from a selected message, with a name and description provided by the user. The branch appears as a separate tab within the conversation. When the branched exploration is complete, the user can merge results back into the main thread by selecting which messages or conclusions from the branch to include. Merged content appears in the main thread with a visual indicator of its branch origin.

**Why this priority**: Branching enables exploratory workflows — critical for complex agent-assisted decision-making (e.g., "try approach A in one branch, approach B in another, then merge the best results"). However, linear conversations are fully functional without branching, making this an enhancement.

**Independent Test**: Select a message → choose "Branch" → enter name "Approach B" → a new tab appears for the branch → send messages in the branch → choose "Merge" → select specific messages → they appear in the main thread with a "merged from: Approach B" indicator. Main thread messages are unchanged.

**Acceptance Scenarios**:

1. **Given** a message in the conversation, **When** the user chooses to branch from it, **Then** a dialog asks for a branch name and optional description, and a new conversation branch is created starting from that message.
2. **Given** a branched conversation, **When** the user views the conversation, **Then** the branch appears as an additional tab with its name as the tab label.
3. **Given** a completed branch, **When** the user chooses to merge, **Then** a selection interface shows the branch's messages and allows the user to pick which messages/conclusions to merge back.
4. **Given** selected branch content being merged, **When** the merge is confirmed, **Then** the selected content appears in the main thread with a visual indicator showing the branch of origin.
5. **Given** a conversation with active branches, **When** the user views the main thread, **Then** branch points are visually indicated (e.g., a branch icon at the originating message).

---

### User Story 6 — Workspace Goal View (Priority: P3)

When a workspace has active goals, the user can open a goal view that shows a real-time feed of goal messages — similar to a channel. The goal view includes a goal selector to switch between active goals, a message stream showing which agents are contributing (agent attribution per message), what they posted, and which interactions they triggered. A lifecycle indicator shows the goal's current state (active, paused, completed, abandoned). Users can post new messages into the goal stream to inject human guidance visible to all agents subscribed to that goal.

**Why this priority**: The goal view is a strategic differentiator for workspace-level coordination — it gives users a "mission control" view of multi-agent collaboration toward a shared objective. However, individual conversations and interactions are fully functional without it, and it depends on the workspace goals system already being in place.

**Independent Test**: Open workspace with 2 active goals → goal selector shows both → select "Q2 Sales Analysis" → real-time feed shows messages from 3 agents → each message shows agent attribution. Goal state shows "Active". User posts "Focus on APAC region" → message appears in stream immediately → agents subscribed to that goal can see it.

**Acceptance Scenarios**:

1. **Given** a workspace with multiple active goals, **When** the user opens the goal view, **Then** a goal selector lists all goals with their lifecycle state.
2. **Given** a selected goal, **When** the user views the goal stream, **Then** messages appear in chronological order with agent attribution (which agent posted each message), timestamps, and links to the interaction that triggered the message.
3. **Given** a goal stream, **When** a new goal message arrives, **Then** it appears in real time (streamed, not polled).
4. **Given** the goal view, **When** the user types and sends a message, **Then** the message is posted into the goal stream as human guidance, visible to all subscribed agents.
5. **Given** a goal with lifecycle state "Active", **When** the state changes to "Completed", **Then** the lifecycle indicator updates in real time and posting new messages is disabled with a "goal completed" message.
6. **Given** the goal selector, **When** the user switches goals, **Then** the message stream updates to show the newly selected goal's messages.

---

### Edge Cases

- What happens when the WebSocket connection is lost? The interface shows a connection status banner (e.g., "Reconnecting...") and attempts automatic reconnection with backoff. Messages sent while disconnected are queued locally and delivered upon reconnection. Once reconnected, any missed messages are fetched to fill the gap.
- What happens when a conversation has hundreds of messages? The message list uses virtualized scrolling so that only visible messages are rendered, ensuring smooth performance regardless of conversation length.
- What happens when an agent sends an extremely long message (e.g., 50,000+ characters)? The message is rendered in a collapsible container, initially showing a truncated preview (first ~500 characters) with an "expand" action to reveal the full content.
- What happens when a user tries to merge a branch that has no messages? The merge action is disabled (grayed out) with a tooltip explaining that the branch has no content to merge.
- What happens when multiple interactions are active simultaneously? Each interaction has its own tab and typing indicator. Only the currently selected tab's typing indicator is visible; other tabs show a small badge (e.g., a dot) to indicate activity.
- What happens when the user tries to branch from a message that is already a branch point? The system allows it (nested branches are permitted). The new branch starts from the same message but is a separate parallel thread.
- What happens when a workspace goal has no messages yet? The goal stream shows an empty state with a prompt encouraging the user to post the first message or wait for agent contributions.

## Requirements *(mandatory)*

### Functional Requirements

**Message List and Streaming**

- **FR-001**: System MUST display conversation messages in a scrollable list with chronological ordering
- **FR-002**: System MUST render user messages aligned right, agent messages aligned left, and system messages centered
- **FR-003**: System MUST stream new messages in real time as they are produced, without requiring a page refresh
- **FR-004**: System MUST auto-scroll to the latest message when the user is at or near the bottom of the message list
- **FR-005**: System MUST pause auto-scroll when the user has scrolled up, and show a "new message" indicator for unread messages
- **FR-006**: System MUST display a typing indicator when the agent is actively processing a response

**Rich Content Rendering**

- **FR-007**: System MUST render Markdown content in agent messages (headings, bold, italic, lists, tables, links)
- **FR-008**: System MUST render fenced code blocks with syntax highlighting and a "copy to clipboard" button
- **FR-009**: System MUST render JSON structures in a collapsible tree viewer that allows expanding/collapsing nested keys
- **FR-010**: System MUST render file attachment references with preview (for images) and download link
- **FR-011**: System MUST handle long content (code blocks, JSON) with scrollable containers that do not overflow the message bubble

**Interaction Tabs**

- **FR-012**: System MUST display one tab per interaction within a conversation
- **FR-013**: System MUST switch the message list to show the selected interaction's messages when the user clicks a tab
- **FR-014**: System MUST display a status bar showing: interaction state (active/completed/failed/awaiting-approval), agent identity, current reasoning mode, and self-correction iteration count
- **FR-015**: System MUST update the status bar and tab indicators in real time when interaction state or metadata changes
- **FR-016**: System MUST show an activity indicator (badge or dot) on tabs with new messages that are not currently selected

**Mid-Process Injection**

- **FR-017**: System MUST allow users to send messages while the agent is processing (input field must remain enabled)
- **FR-018**: System MUST display mid-process injected messages immediately in the message list with a visual indicator distinguishing them from normal messages
- **FR-019**: System MUST include a hint in the input area when the agent is processing, informing the user that their message will be injected mid-process

**Branching and Merging**

- **FR-020**: System MUST allow users to create a branch from any message in the conversation, providing a name and optional description
- **FR-021**: System MUST display branches as additional tabs within the conversation
- **FR-022**: System MUST allow users to merge selected messages from a branch back into the main thread
- **FR-023**: System MUST display merged content with a visual indicator of the branch of origin
- **FR-024**: System MUST show branch points visually on originating messages in the main thread
- **FR-025**: System MUST disable the merge action when the branch contains no messages

**Workspace Goal View**

- **FR-026**: System MUST display a goal selector listing all workspace goals with their lifecycle state
- **FR-027**: System MUST display a real-time message stream for the selected goal with agent attribution per message
- **FR-028**: System MUST show which interaction each goal message originated from, as a clickable link
- **FR-029**: System MUST allow users to post new messages into the goal stream as human guidance
- **FR-030**: System MUST display a lifecycle indicator showing the goal's state (active/paused/completed/abandoned) and update it in real time
- **FR-031**: System MUST disable message posting when the goal state is completed or abandoned
- **FR-032**: System MUST update the goal message stream when the user switches between goals via the selector

**Resilience and Performance**

- **FR-033**: System MUST display a connection status indicator when the real-time connection is lost and automatically attempt reconnection
- **FR-034**: System MUST queue messages sent during disconnection and deliver them upon reconnection
- **FR-035**: System MUST fetch missed messages after reconnection to fill any gap
- **FR-036**: System MUST use virtualized rendering for the message list to maintain performance with large conversation histories
- **FR-037**: System MUST truncate extremely long messages (50,000+ characters) with an expand/collapse control

**Accessibility and Responsiveness**

- **FR-038**: System MUST be keyboard-navigable (tab through messages, tabs, input area, actions)
- **FR-039**: System MUST be compatible with screen readers (semantic markup, ARIA labels for interactive elements)
- **FR-040**: System MUST render correctly in dark mode and light mode
- **FR-041**: System MUST be responsive, adapting layout for mobile and desktop viewports

### Key Entities

- **ConversationView**: The primary UI surface for a conversation — holds the message list, interaction tabs, status bar, and input area. Identified by conversation ID.
- **MessageBubble**: A single rendered message — contains the sender identity, message content (text, rich content, attachments), timestamp, alignment (left/right/center), and optional indicators (mid-process, branch origin).
- **InteractionTab**: A tab within a conversation representing one interaction — shows the agent identity, state badge, and activity indicator when not selected.
- **StatusBar**: A persistent bar showing the current interaction's runtime metadata — state, agent identity, reasoning mode label, self-correction count.
- **BranchView**: A parallel conversation thread created from a specific message — has a name, description, its own tab, and can be merged back into the originating thread.
- **GoalFeedView**: A real-time message stream for a workspace goal — shows agent-attributed messages, a lifecycle state indicator, and supports user message posting.
- **GoalSelector**: A control for switching between workspace goals — lists goal names and states, updates the goal feed when selection changes.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: New messages appear in the conversation within 500 milliseconds of being produced by the agent
- **SC-002**: The message list remains smooth (no visible jank or frame drops) with conversations containing 1,000+ messages
- **SC-003**: Users can send a mid-process message in under 2 seconds (from pressing send to seeing it in the list)
- **SC-004**: Markdown, code blocks, and JSON structures render completely within 1 second of the message appearing
- **SC-005**: Tab switching between interactions completes within 300 milliseconds
- **SC-006**: Branch creation (from selecting "branch" to seeing the new tab) completes within 2 seconds
- **SC-007**: Merge action (from confirming selection to seeing merged content in the main thread) completes within 2 seconds
- **SC-008**: Goal stream messages appear within 500 milliseconds of being posted
- **SC-009**: The interface is fully keyboard-navigable — all interactive elements are reachable via Tab and operable via Enter/Space
- **SC-010**: Dark mode and light mode render without visual artifacts (no unreadable text, invisible borders, or broken layouts)
- **SC-011**: The conversation interface is usable on mobile viewports (320px minimum width) with no horizontal scrolling required
- **SC-012**: Automatic reconnection succeeds within 10 seconds of connection loss (on stable network) and queued messages are delivered
- **SC-013**: Test coverage of at least 95% across all conversation interface components

## Assumptions

- The backend conversations/interactions API (feature 024) provides the data model for conversations, interactions, messages, branches, and merge records. This feature consumes that data; it does not define the data model.
- The WebSocket gateway (feature 019) is operational and provides the `conversation:{id}` channel for real-time message streaming. This feature subscribes to that channel; it does not implement the WebSocket server.
- Workspace goals and goal messages are provided by the workspaces bounded context (feature 018). This feature displays them; it does not manage goal lifecycle.
- Reasoning mode and self-correction iteration count are included in the interaction metadata provided by the backend via WebSocket updates. This feature displays them; it does not compute them.
- The "typing indicator" is triggered by a WebSocket event from the backend when the agent starts processing. The specific mechanism (heartbeat vs. explicit event) is a backend concern.
- File attachments are stored in object storage and referenced by URL in message content. This feature renders the reference; it does not handle upload.
- Branch creation and merge are operations on the backend (feature 024 provides the API). This feature provides the UI and calls the API; it does not implement branching/merging logic.
- Mid-process message injection is supported by the backend interaction model — the backend accepts messages for an interaction even while the agent is processing. This feature sends the message; the backend handles delivery to the agent.
- The shell layout (sidebar, navigation, workspace context) already exists (feature 015). This feature plugs into the main content area.
- Message virtualization is needed only when a conversation exceeds ~100 messages. Below that threshold, all messages can be rendered directly.
