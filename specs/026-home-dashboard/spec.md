# Feature Specification: Home Dashboard

**Feature Branch**: `026-home-dashboard`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Home page with recent activity feed, pending actions, quick actions, workspace summary metrics, and real-time updates via WebSocket."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Workspace Summary Overview (Priority: P1)

A user logs in and lands on the home dashboard within their active workspace. They immediately see a summary of key operational metrics: how many agents are currently active, how many workflow executions are running, how many items need their approval, and the workspace's current cost for the billing period. Each metric is displayed as a card with the current value, a label, and a visual indicator of change compared to the previous period (up, down, or stable). The user can glance at this grid and quickly assess the overall health and activity level of their workspace without navigating to individual sections.

**Why this priority**: The summary grid is the single most valuable component — it gives an at-a-glance operational picture. Even without the activity feed or pending actions, a user gains immediate value from seeing their workspace health.

**Independent Test**: Navigate to the home page as an authenticated user with an active workspace. Verify the metric cards display: active agents count, running executions count, pending approvals count, and current cost. Verify the change indicator reflects the actual difference from the prior period. Verify the data refreshes when the workspace context changes.

**Acceptance Scenarios**:

1. **Given** an authenticated user in a workspace with 5 active agents, 3 running executions, 2 pending approvals, and $142 cost, **When** they view the home dashboard, **Then** they see 4 metric cards displaying these values with appropriate labels
2. **Given** a workspace where active agents increased from 3 to 5 since the prior period, **When** the user views the metric card, **Then** the card shows an upward change indicator with "+2" context
3. **Given** a user who switches workspaces via the workspace selector, **When** the workspace changes, **Then** all metric cards update to reflect the newly selected workspace's data within 2 seconds
4. **Given** a workspace with zero activity (no agents, no executions, no approvals, $0 cost), **When** the user views the home dashboard, **Then** all metric cards display "0" with appropriate empty-state styling

---

### User Story 2 — Recent Activity Feed (Priority: P1)

A user wants to see what has been happening recently in their workspace — the latest interactions, workflow executions, and significant events. The home dashboard shows a chronological feed of the 10 most recent activities, each displayed as a timeline entry showing what happened (e.g., "Execution completed: daily-report-generator", "New interaction started: support-ops:triage-agent"), when it happened (relative time like "3 minutes ago"), and the current status (completed, running, failed, etc.). The user can click on any activity item to navigate to its detail page.

**Why this priority**: The activity feed provides situational awareness — what's happening right now. Together with the summary metrics (US1), this gives a complete operational snapshot.

**Independent Test**: Navigate to the home page with a workspace that has at least 10 recent activities. Verify the timeline displays 10 entries sorted by most recent first. Verify each entry shows description, relative timestamp, and status. Click an entry — verify navigation to the correct detail page. Verify the feed updates when a new event arrives via WebSocket.

**Acceptance Scenarios**:

1. **Given** a workspace with 25 recent activities, **When** the user views the activity feed, **Then** only the 10 most recent activities are displayed in reverse chronological order
2. **Given** a recent activity for a completed execution, **When** the user views the timeline entry, **Then** they see the execution name, "completed" status badge, and relative timestamp (e.g., "5 min ago")
3. **Given** a timeline entry for an interaction, **When** the user clicks on it, **Then** they are navigated to the interaction detail page
4. **Given** an empty workspace with no activities, **When** the user views the activity feed, **Then** an empty state message is displayed (e.g., "No recent activity — start by creating an agent or running a workflow")
5. **Given** a new execution completes while the user is viewing the dashboard, **When** a real-time event is received, **Then** the activity feed updates to show the new entry at the top without a page refresh

---

### User Story 3 — Pending Actions (Priority: P2)

A user wants to know if anything requires their attention — pending approvals for agent executions, failed executions that need investigation, or attention requests from agents. The home dashboard displays a "Pending Actions" section showing these items as a list of cards, each with a brief description, urgency level, and a call-to-action button. Items are ordered by urgency (high urgency first). The user can act on items directly from the dashboard (approve/reject, navigate to failure details) or dismiss them.

**Why this priority**: Pending actions drive user engagement and reduce response time to critical events. However, the dashboard is still useful without this section — the summary and activity feed (US1+US2) provide the core value.

**Independent Test**: Navigate to the home page with a workspace that has 2 pending approvals and 1 failed execution. Verify the pending actions section shows 3 cards. Verify the failed execution card appears first (higher urgency). Click "View Details" on the failed execution — verify navigation. Click "Approve" on a pending approval — verify the approval is processed and the card is removed.

**Acceptance Scenarios**:

1. **Given** a workspace with 2 pending approvals and 1 failed execution, **When** the user views the pending actions section, **Then** they see 3 cards sorted by urgency (failed execution first, then approvals)
2. **Given** a pending approval card, **When** the user clicks "Approve," **Then** the approval is submitted and the card is removed from the list with a success notification
3. **Given** a failed execution card, **When** the user clicks "View Details," **Then** they navigate to the execution detail page showing failure information
4. **Given** a workspace with no pending actions, **When** the user views the section, **Then** a positive empty state message is displayed (e.g., "All clear — no pending actions")
5. **Given** a new attention request arrives while the user is viewing the dashboard, **When** the real-time event is received, **Then** a new pending action card appears with the attention request details

---

### User Story 4 — Quick Actions (Priority: P2)

A user wants to perform common actions directly from the home dashboard without navigating through multiple pages. The dashboard provides a "Quick Actions" bar with buttons for the four most common operations: start a new conversation, upload an agent, create a workflow, and browse the marketplace. Each button is clearly labeled with an icon and navigates the user to the relevant page or opens a creation dialog.

**Why this priority**: Quick actions reduce navigation friction for the most common tasks. They are a convenience feature that improves workflow speed but are not essential for the dashboard's informational purpose.

**Independent Test**: Navigate to the home page. Verify the quick actions bar displays 4 buttons. Click "New Conversation" — verify navigation to the conversation creation page. Click "Upload Agent" — verify navigation to the agent upload page. Click "Create Workflow" — verify navigation to the workflow editor. Click "Browse Marketplace" — verify navigation to the marketplace page.

**Acceptance Scenarios**:

1. **Given** an authenticated user on the home dashboard, **When** they view the quick actions bar, **Then** they see 4 buttons: "New Conversation," "Upload Agent," "Create Workflow," "Browse Marketplace" with appropriate icons
2. **Given** the quick actions bar, **When** the user clicks "New Conversation," **Then** they are navigated to the conversation creation page within the current workspace
3. **Given** a user with viewer role (read-only), **When** they view the quick actions bar, **Then** action buttons requiring write permissions (Upload Agent, Create Workflow) are disabled with a tooltip explaining the permission requirement

---

### User Story 5 — Real-Time Dashboard Updates (Priority: P3)

A user is monitoring their workspace and leaves the home dashboard open. As events occur (executions complete, new approvals arrive, agent status changes), the dashboard updates automatically without requiring a page refresh. The activity feed gains new entries, pending action counts change, and metric cards update their values. If the WebSocket connection is lost, the user sees a subtle connection status indicator and the dashboard gracefully falls back to periodic polling until the connection is restored.

**Why this priority**: Real-time updates make the dashboard a live monitoring tool. Without it, the dashboard is still functional (data loads on page visit) but requires manual refresh to see changes.

**Independent Test**: Open the dashboard in a browser. Trigger a workflow execution from another session. Verify the activity feed updates within 1 second. Verify the "running executions" metric card increments. Disconnect the network — verify a connection status indicator appears. Reconnect — verify the indicator disappears and data synchronizes.

**Acceptance Scenarios**:

1. **Given** the dashboard is open, **When** a new execution completes, **Then** the activity feed updates with a new entry and the metric cards refresh within 1 second
2. **Given** the dashboard is open, **When** a new pending approval arrives, **Then** the pending actions section adds a new card and the "pending approvals" metric card increments
3. **Given** the WebSocket connection drops, **When** the user is viewing the dashboard, **Then** a subtle connection indicator appears and the dashboard falls back to periodic polling (every 30 seconds)
4. **Given** the connection is restored after a drop, **When** the WebSocket reconnects, **Then** the connection indicator disappears and any missed events are synchronized

---

### Edge Cases

- What happens when the workspace has thousands of activities? The activity feed shows only the 10 most recent. Older activities are accessible from the dedicated activity log page, not from the home dashboard.
- What happens when a pending action is resolved by another user while the dashboard is open? The real-time update removes the resolved action from the pending actions list. If the user clicks an already-resolved action, they see a "This action has already been resolved" message rather than an error.
- What happens when metric data is temporarily unavailable (e.g., analytics service is down)? The metric card displays a loading skeleton for up to 5 seconds, then shows a "Data unavailable" state with a retry button. Other cards that have data display normally — partial failures do not block the entire dashboard.
- What happens when the user has no workspace selected? The dashboard redirects to the workspace selector page. Once a workspace is selected, the user is returned to the home dashboard with data loaded for that workspace.
- What happens when the user's screen is very narrow (mobile)? The metric card grid reflows from a 4-column layout to a 2-column or single-column layout. The activity feed and pending actions stack vertically. Quick actions collapse into a compact row or dropdown.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST display a workspace summary with four metric cards: active agents count, running executions count, pending approvals count, and current billing period cost
- **FR-002**: Each metric card MUST show the current value, a descriptive label, and a change indicator (increase, decrease, or stable) compared to the previous period
- **FR-003**: The system MUST display a chronological activity feed showing the 10 most recent interactions and executions in the current workspace
- **FR-004**: Each activity feed entry MUST display a description, relative timestamp, and status indicator
- **FR-005**: Activity feed entries MUST be clickable and navigate to the corresponding detail page (interaction detail or execution detail)
- **FR-006**: The system MUST display a pending actions section listing items requiring user action: pending approvals, failed executions, and attention requests
- **FR-007**: Pending actions MUST be sorted by urgency level (highest urgency first)
- **FR-008**: The system MUST support inline actions on pending action cards (approve/reject for approvals, navigate for failures)
- **FR-009**: The system MUST display a quick actions bar with four navigation buttons: New Conversation, Upload Agent, Create Workflow, Browse Marketplace
- **FR-010**: Quick action buttons MUST respect the user's workspace role — write actions are disabled for read-only roles with an explanatory tooltip
- **FR-011**: The system MUST receive real-time updates via a persistent connection and update the activity feed, pending actions, and metric cards without page refresh
- **FR-012**: The system MUST display appropriate empty states when any section has no data (zero metrics, no activities, no pending actions)
- **FR-013**: The system MUST handle partial data failures gracefully — if one section's data is unavailable, other sections continue to display normally
- **FR-014**: The system MUST update all dashboard data when the user switches workspaces
- **FR-015**: The system MUST be fully keyboard navigable and compatible with screen readers
- **FR-016**: The system MUST render correctly in both light and dark color modes
- **FR-017**: The system MUST be responsive across desktop (1024px+) and mobile (320px+) screen widths
- **FR-018**: The system MUST display a connection status indicator when the real-time connection is lost and fall back to periodic polling (every 30 seconds)

### Key Entities

- **WorkspaceSummary**: Aggregated metrics for a workspace — active agents count, running executions count, pending approvals count, current cost, and per-metric change indicators (delta value, direction: up/down/stable)
- **ActivityEntry**: A single item in the recent activity feed — activity type (interaction or execution), display title, status (running, completed, failed, etc.), timestamp, and a link to the detail resource
- **PendingAction**: An item requiring user action — action type (approval, failed execution, attention request), description, urgency level (high, medium, low), creation timestamp, and available actions (approve, reject, view details, dismiss)
- **QuickAction**: A navigable shortcut — label, icon identifier, target page path, and required permission (if any)

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The home dashboard loads and displays all sections (summary, activity, pending actions, quick actions) within 2 seconds of navigation
- **SC-002**: Real-time updates appear on the dashboard within 1 second of the originating event
- **SC-003**: Users can identify the current state of their workspace (health, recent activity, pending items) within 5 seconds of viewing the dashboard
- **SC-004**: All interactive elements (buttons, links, cards) are reachable via keyboard navigation with visible focus indicators
- **SC-005**: The dashboard renders correctly on screen widths from 320px to 2560px without horizontal scrolling or content overflow
- **SC-006**: Partial failures (one section's data unavailable) do not prevent other sections from displaying — zero full-page error states caused by single-section failures
- **SC-007**: The dashboard gracefully handles WebSocket disconnection within 3 seconds (indicator shown, fallback activated) and reconnection within 5 seconds (indicator removed, data synchronized)
- **SC-008**: Dark mode and light mode both pass visual contrast requirements (WCAG AA: 4.5:1 for normal text, 3:1 for large text)
- **SC-009**: Test coverage of the home dashboard feature is at least 95%

## Assumptions

- The user is authenticated and has at least one workspace with membership. Unauthenticated access redirects to the login page (feature 017).
- Workspace summary metrics (active agents, running executions, pending approvals, cost) are available via existing backend API endpoints from the analytics (feature 020), registry (feature 021), and workspaces (feature 018) bounded contexts.
- The activity feed data (recent interactions and executions) is available from the interactions (feature 024) and execution bounded contexts via existing list API endpoints, sorted by recency.
- Pending actions (approvals, failed executions, attention requests) are retrievable from the existing approval, execution, and attention API endpoints.
- The WebSocket real-time gateway (feature 019) provides event subscriptions for execution events, interaction events, and attention events that the dashboard listens to.
- The existing shared Timeline, MetricCard, StatusBadge, and EmptyState components (feature 015 scaffold) are available and do not need to be created from scratch.
- Quick action target pages (conversation creation, agent upload, workflow editor, marketplace) may or may not exist yet. Quick action buttons navigate to the route even if the target page is not yet implemented — the app's routing handles unbuilt pages with a placeholder.
- The "previous period" for metric change comparison is the prior calendar day for daily metrics and the prior billing cycle for cost. This is determined by the analytics API, not by the dashboard.
- The dashboard page is the default landing page after login for workspaces. If no workspace is selected, the user is redirected to the workspace selector.
