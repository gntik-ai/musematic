# Feature Specification: Agent Marketplace UI

**Feature Branch**: `035-agent-marketplace`  
**Created**: 2026-04-12  
**Status**: Draft  
**Input**: User description: "Marketplace search with natural-language support, faceted filtering, agent cards grid, agent detail page, comparison view, recommendation carousel, invocation flow, ratings and reviews, and creator analytics"

**Requirements Traceability**: FEAT-FE-003

## User Scenarios & Testing

### User Story 1 - Marketplace Search and Browse (Priority: P1)

A platform user navigates to the marketplace to discover agents. They see a search bar at the top where they can type a natural-language query (e.g., "financial analysis agent that handles KYC compliance"). As the user types, results update after a brief pause. Below the search bar, a sidebar presents faceted filters for capability, maturity level, trust tier, certification status, cost tier, and tags. The main area displays agent cards in a responsive grid. Each card shows the agent's name, short description, maturity badge, trust badge, average rating (stars), and cost indicator. The user can also sort results by relevance, maturity, rating, or cost. Clicking a card navigates to the agent's detail page.

**Why this priority**: Search and browse is the entry point for all marketplace interactions. Without it, users cannot discover agents and no other marketplace feature has value. It delivers a complete, standalone discovery experience.

**Independent Test**: Can be fully tested by navigating to the marketplace page, typing a search query, applying a filter (e.g., maturity=production), and verifying that the cards grid updates with relevant results showing all required metadata badges.

**Acceptance Scenarios**:

1. **Given** a platform user on the marketplace page, **When** they type "financial analysis" in the search bar, **Then** results update within 1 second after the user stops typing, showing agents matching the query.
2. **Given** search results displayed, **When** the user selects "maturity: production" in the filter sidebar, **Then** the grid updates to show only production-maturity agents, and the active filter is visually indicated.
3. **Given** search results displayed, **When** the user clears all filters and search text, **Then** the grid shows all available agents in the default order.
4. **Given** a marketplace with 200+ agents, **When** the user scrolls through results, **Then** additional results load progressively without a full page refresh.
5. **Given** a search query with no matches, **When** results are displayed, **Then** the user sees an empty state with a clear message and suggestions to broaden their search.
6. **Given** search results, **When** the user selects "sort by rating", **Then** agents are reordered by average rating (highest first) while maintaining any active filters.

---

### User Story 2 - Agent Detail Page (Priority: P1)

A platform user clicks on an agent card in the marketplace grid to view its full detail page. The page displays the agent's complete metadata: name, description, namespace, version, declared capabilities, maturity level and history, trust tier and certification status, attached policies, quality metrics (evaluation scores, robustness data), and cost information. A revisions section shows the agent's version history. Trust signals (certification badges, trust tier progression, latest evaluation results) are prominently displayed to help the user assess agent reliability.

**Why this priority**: The detail page is the primary decision surface — users need comprehensive information to decide whether to invoke an agent. It is the natural companion to search/browse and together they form the core marketplace experience.

**Independent Test**: Can be fully tested by navigating to a specific agent's detail page and verifying all metadata sections are populated: capabilities list, maturity badge, trust signals, revision history, policy summary, and quality metrics.

**Acceptance Scenarios**:

1. **Given** a user on the marketplace grid, **When** they click an agent card, **Then** they are navigated to that agent's detail page showing all metadata sections.
2. **Given** an agent detail page, **When** the user views the trust signals section, **Then** they see the agent's trust tier, certification badges, latest evaluation scores, and trust tier progression timeline.
3. **Given** an agent with multiple revisions, **When** the user views the revisions section, **Then** they see a chronological list of versions with change descriptions and dates.
4. **Given** an agent detail page, **When** the user views attached policies, **Then** the policies are listed with their names, types, and enforcement status.
5. **Given** an agent that has been archived or is no longer available, **When** the user navigates to its detail page via a direct link, **Then** they see a clear "agent unavailable" message with a link back to the marketplace.

---

### User Story 3 - Agent Comparison (Priority: P2)

A platform user evaluating multiple agents selects 2 to 4 agents for side-by-side comparison. The comparison view displays a table with each agent as a column and key attributes as rows: capabilities, maturity, trust tier, average rating, cost tier, latest evaluation scores, and policy restrictions. The user can add or remove agents from the comparison. This enables informed decision-making when multiple agents could serve the same purpose.

**Why this priority**: Comparison is a key decision-support tool when multiple agents match a user's needs. It depends on the detail page metadata being available (US2) but provides significant incremental value for agent selection.

**Independent Test**: Can be fully tested by selecting 3 agents from the marketplace, opening the comparison view, and verifying that all attributes appear in aligned columns with correct values for each agent.

**Acceptance Scenarios**:

1. **Given** a user browsing the marketplace, **When** they select 2 agents for comparison, **Then** a comparison view opens showing both agents in side-by-side columns with key attributes as rows.
2. **Given** a comparison view with 3 agents, **When** the user adds a 4th agent, **Then** the 4th column is added to the comparison table.
3. **Given** a comparison view with 4 agents, **When** the user attempts to add a 5th, **Then** the system prevents the addition and shows a message that the maximum of 4 agents has been reached.
4. **Given** a comparison view, **When** the user removes one agent, **Then** that column is removed and the remaining agents stay in their positions.
5. **Given** agents with different sets of capabilities, **When** displayed in comparison, **Then** missing capabilities for an agent show an empty/not-applicable indicator rather than being omitted.

---

### User Story 4 - Ratings and Reviews (Priority: P2)

A platform user views an agent's average rating (displayed as stars) and review count on both the agent card in the grid and the detail page. On the detail page, a reviews section shows a chronological list of user reviews, each with a star rating, text comment, and date. The user can submit their own review using a star rating selector and a text input. If the user has already reviewed this agent, they see an option to edit their existing review instead.

**Why this priority**: Ratings and reviews provide social proof and community-driven quality signals. They enhance the discovery experience (US1, US2) by giving users peer feedback on agent quality.

**Independent Test**: Can be fully tested by navigating to an agent's detail page, viewing existing reviews, submitting a new review with 4 stars and text, and verifying the review appears in the list and the average rating updates.

**Acceptance Scenarios**:

1. **Given** an agent card in the marketplace grid, **When** displayed, **Then** the card shows the average star rating and review count.
2. **Given** an agent detail page with 10 reviews, **When** the user views the reviews section, **Then** all 10 reviews are listed with star rating, text, author name, and date.
3. **Given** a logged-in user who has not reviewed this agent, **When** they submit a review with 4 stars and text, **Then** the review is saved, appears at the top of the review list, and the average rating recalculates.
4. **Given** a user who has already reviewed this agent, **When** they visit the reviews section, **Then** they see an option to edit their existing review instead of submitting a new one.
5. **Given** an agent with zero reviews, **When** the detail page is viewed, **Then** the ratings section shows "No reviews yet" with an invitation to be the first reviewer.

---

### User Story 5 - Agent Invocation (Priority: P2)

A platform user decides to use an agent and clicks a "Start Conversation" button on the agent's detail page. A modal or flow prompts the user to select a target workspace (from their available workspaces), optionally provide an initial task brief (a short description of what they want the agent to do), and confirm. On confirmation, the user is redirected to the conversations interface with the agent pre-selected and the task brief pre-filled.

**Why this priority**: Invocation converts discovery into usage — without it, the marketplace is informational-only. It depends on the detail page (US2) and requires workspace context.

**Independent Test**: Can be fully tested by clicking "Start Conversation" on an agent's detail page, selecting a workspace, entering a task brief, and verifying the redirect to the conversations page with the agent and brief pre-loaded.

**Acceptance Scenarios**:

1. **Given** a user on an agent detail page, **When** they click "Start Conversation", **Then** a workspace selector appears showing only workspaces where the user has member-or-higher access.
2. **Given** the workspace selector, **When** the user selects a workspace and enters an optional task brief, **Then** they can confirm and are redirected to the conversations interface.
3. **Given** a user with only one workspace, **When** they click "Start Conversation", **Then** the workspace is auto-selected and the user goes directly to the task brief step.
4. **Given** a user who is not logged in, **When** they click "Start Conversation", **Then** they are redirected to the login page with a return URL preserving the agent and intended action.
5. **Given** a confirmed invocation, **When** the user arrives at the conversations page, **Then** the selected agent is pre-loaded and the task brief text (if provided) is pre-filled in the message input.

---

### User Story 6 - Recommendation Carousel (Priority: P3)

A platform user sees a "Recommended for you" carousel on the marketplace page, positioned above or below the search results grid. The carousel presents a curated set of agents based on the user's workspace context, recent interactions, and usage patterns. Each recommendation appears as a compact card that the user can click to navigate to the agent's detail page. When insufficient personalization data exists (e.g., a new user), the carousel shows popular or trending agents instead.

**Why this priority**: Recommendations enhance discovery beyond explicit search. They provide a passive discovery channel and surface agents the user might not have searched for. This feature depends on backend recommendation intelligence and is not required for core marketplace usage.

**Independent Test**: Can be fully tested by loading the marketplace page as a user with interaction history and verifying the carousel displays personalized suggestions; then loading as a new user and verifying it shows popular/trending agents.

**Acceptance Scenarios**:

1. **Given** a user with prior agent interactions, **When** they load the marketplace page, **Then** a "Recommended for you" carousel displays at least 3 relevant agent cards.
2. **Given** a new user with no interaction history, **When** they load the marketplace page, **Then** the carousel displays popular or trending agents instead of personalized recommendations.
3. **Given** the recommendation carousel, **When** the user clicks a recommended agent card, **Then** they navigate to that agent's detail page.
4. **Given** the recommendation carousel, **When** fewer than 3 agents are available to recommend, **Then** the carousel is hidden rather than showing an incomplete set.

---

### User Story 7 - Creator Analytics (Priority: P3)

An agent creator (owner) views an analytics tab on their agent's detail page. This tab displays usage data: a chart showing invocations over time (past 30 days), a satisfaction trend chart derived from ratings over time, and a list of common failure scenarios. The analytics tab is only visible to the agent's creator or workspace administrators.

**Why this priority**: Creator analytics provide feedback to agent builders about how their agents are performing. This is a secondary concern after the primary consumer experience (US1-US5) and recommendation system (US6) are in place.

**Independent Test**: Can be fully tested by logging in as an agent creator, navigating to their agent's detail page, and verifying the analytics tab shows usage chart, satisfaction trend, and common failures — while verifying a non-owner user does not see this tab.

**Acceptance Scenarios**:

1. **Given** an agent creator viewing their agent's detail page, **When** they click the analytics tab, **Then** a usage chart shows daily invocation counts for the past 30 days.
2. **Given** the analytics tab, **When** the creator views satisfaction trend, **Then** a chart shows average rating over time with data points per week.
3. **Given** the analytics tab, **When** the creator views common failures, **Then** a list shows the most frequent failure categories with occurrence counts.
4. **Given** a non-owner user viewing the same agent's detail page, **When** they look at the available tabs, **Then** the analytics tab is not visible.
5. **Given** an agent with no usage data yet, **When** the creator views the analytics tab, **Then** an empty state shows "No usage data yet" with guidance on how to promote the agent.

---

### Edge Cases

- What happens when a user clicks on an agent card for an agent that was just archived? The detail page displays an "agent unavailable" message with a link back to the marketplace.
- What happens when the search service is unavailable? The marketplace page shows a degraded state with a "search temporarily unavailable" banner, and the recommendation carousel still loads if available.
- What happens when a user submits a review without text? The system accepts the review with only a star rating; text is optional.
- What happens when a user attempts to compare agents from different workspaces? Comparison is workspace-scoped; only agents visible to the user within their current workspace context can be compared.
- What happens when the recommendation engine returns no results? The carousel section is hidden entirely rather than showing an empty carousel.
- What happens when a user navigates to the marketplace on a mobile device? The layout adapts: the filter sidebar collapses to a filter button/drawer, agent cards stack vertically, and the comparison view allows horizontal scrolling.
- What happens when a user tries to invoke an agent they don't have visibility to use? The "Start Conversation" button is disabled with a tooltip explaining the visibility restriction.
- What happens when a user submits a review with inappropriate content? Review content is submitted as-is; moderation (if needed) is handled by backend systems outside the scope of this feature.

## Requirements

### Functional Requirements

**Search and Browse**

- **FR-001**: System MUST provide a natural-language search bar that sends queries to the search service after a brief input pause (debounce), displaying results without full page reload
- **FR-002**: System MUST provide a faceted filter sidebar with filter groups for capability, maturity level, trust tier, certification status, cost tier, and tags
- **FR-003**: System MUST display search results as a responsive grid of agent cards, each showing agent name, short description, maturity badge, trust badge, average star rating, review count, and cost indicator
- **FR-004**: System MUST support sorting search results by relevance, maturity level, rating, and cost
- **FR-005**: System MUST progressively load additional results as the user scrolls (pagination or infinite scroll) without a full page reload

**Agent Detail**

- **FR-006**: System MUST display a full agent detail page with: name, description, namespace, version, declared capabilities, maturity level and history, trust tier and certification status, attached policies, quality metrics (evaluation scores, robustness), and cost information
- **FR-007**: System MUST display the agent's revision history as a chronological list of versions with change descriptions and dates
- **FR-008**: System MUST display trust signals prominently, including trust tier, certification badges, latest evaluation results, and trust tier progression timeline

**Comparison**

- **FR-009**: System MUST support selecting 2 to 4 agents for side-by-side comparison in a tabular layout with agents as columns and attributes as rows
- **FR-010**: System MUST allow adding and removing agents from the comparison view, enforcing a maximum of 4 agents
- **FR-011**: System MUST display a "not applicable" indicator when an agent lacks an attribute that other compared agents have

**Ratings and Reviews**

- **FR-012**: System MUST display the average star rating and total review count on both agent cards and the agent detail page
- **FR-013**: System MUST display a reviews list on the detail page showing each review's star rating, text, author name, and date
- **FR-014**: System MUST allow logged-in users to submit a review consisting of a star rating (1-5) and optional text
- **FR-015**: System MUST allow users who have already reviewed an agent to edit their existing review rather than submitting a duplicate

**Invocation**

- **FR-016**: System MUST provide a "Start Conversation" button on the agent detail page that initiates the invocation flow
- **FR-017**: System MUST present a workspace selector showing only workspaces where the current user has member-or-higher access
- **FR-018**: System MUST allow the user to provide an optional task brief (text input) before confirming invocation
- **FR-019**: System MUST redirect the user to the conversations interface with the selected agent pre-loaded and task brief pre-filled upon confirmation

**Recommendations**

- **FR-020**: System MUST display a "Recommended for you" carousel on the marketplace page showing at least 3 agent cards when personalization data is available
- **FR-021**: System MUST fall back to showing popular or trending agents when insufficient personalization data exists for the current user
- **FR-022**: System MUST hide the recommendation carousel entirely when fewer than 3 agents are available to recommend

**Creator Analytics**

- **FR-023**: System MUST display an analytics tab on the agent detail page visible only to the agent's creator and workspace administrators
- **FR-024**: System MUST show a usage chart displaying daily invocation counts for the configurable past time period (default: 30 days)
- **FR-025**: System MUST show a satisfaction trend chart displaying average rating over time with weekly data points
- **FR-026**: System MUST show a common failures list displaying the most frequent failure categories with occurrence counts

**Cross-Cutting**

- **FR-027**: System MUST be fully keyboard-navigable and compatible with screen readers (WCAG 2.1 AA compliance)
- **FR-028**: System MUST render correctly in both light and dark display modes
- **FR-029**: System MUST provide a responsive layout that adapts to mobile (filters collapse to drawer, cards stack vertically, comparison scrolls horizontally) and desktop viewports

### Key Entities

- **Agent Card**: A compact representation of an agent in the search results grid, showing name, description, maturity badge, trust badge, average rating, review count, and cost indicator
- **Agent Detail**: The full metadata view of a single agent, including all card fields plus capabilities, revision history, trust signals, policies, quality metrics, and cost breakdown
- **Agent Review**: A user-submitted evaluation of an agent, containing a star rating (1-5), optional text, author identity, and submission date
- **Agent Comparison**: A temporary selection of 2-4 agents for side-by-side attribute comparison
- **Recommendation**: A suggested agent derived from personalization data or popularity metrics, displayed in the carousel

## Success Criteria

### Measurable Outcomes

- **SC-001**: Users complete a search-to-detail navigation (type query, view results, click agent card) in under 5 seconds
- **SC-002**: Search results appear within 1 second of user input completion (after debounce period)
- **SC-003**: Faceted filters update results without full page reload, maintaining user scroll position when possible
- **SC-004**: Agent comparison supports up to 4 agents in a readable, aligned side-by-side view
- **SC-005**: Review submission (select rating, type text, submit) completes in under 30 seconds for the user
- **SC-006**: All interactive elements are navigable via keyboard and announce correctly to screen readers
- **SC-007**: Dark mode renders all marketplace components correctly with no readability issues
- **SC-008**: Mobile layout adapts gracefully: cards stack vertically, filters collapse to a drawer, comparison view scrolls horizontally
- **SC-009**: Creator analytics tab displays usage data for at least the past 30 days
- **SC-010**: Recommendation carousel displays at least 3 relevant agents for users with interaction history
- **SC-011**: Test coverage is at least 95% across all marketplace UI components

## Assumptions

- Backend search and marketplace APIs (marketplace/ bounded context, feature 021 Agent Registry) exist or will be available before this UI is implemented
- The authentication system and workspace context are available from existing platform infrastructure (features 014, 018)
- The agent search API supports both natural-language queries and structured faceted filters
- The recommendation engine API (marketplace_intelligence/ bounded context) is available for the recommendations carousel
- Review storage and retrieval is handled by backend APIs; this feature implements only the frontend
- Invocation redirects to the conversations UI (feature 024 Interactions & Conversations); the conversations page accepts agent pre-selection and task brief parameters via URL or state
- Agent profile images or avatars are not required for v1; initials or icon placeholders are used
- Review moderation is handled by backend systems and is out of scope for this UI feature
- The analytics data (usage, satisfaction, failures) is provided by the analytics backend (feature 020); this feature visualizes it
- The comparison feature is session-scoped (selections are not persisted across sessions)
