# Feature Specification: Next.js Application Scaffold — Frontend Foundation

**Feature Branch**: `015-nextjs-app-scaffold`  
**Created**: 2026-04-11  
**Status**: Draft  
**Input**: User description: "Initialize Next.js 14+ with App Router, TypeScript, shadcn/ui, Tailwind CSS, TanStack Query, Zustand, typed API client, WebSocket client, app shell with sidebar navigation, command palette, and all shared UI components."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Project Setup and Theme Configuration (Priority: P1)

A frontend developer initializes the application codebase and configures the visual foundation. The application starts successfully, renders a default page with the configured theme, and supports both light and dark modes. The developer can verify that all core dependencies are installed, the build compiles without errors, and the design system (color palette, typography, spacing) is applied consistently.

**Why this priority**: Nothing else can be built without a working project scaffold, build pipeline, and design system. This is the absolute foundation.

**Independent Test**: Run the development server. Open the application in a browser. Verify the page renders with the brand theme. Toggle dark mode. Verify all colors update correctly. Run the build process. Verify it completes without errors.

**Acceptance Scenarios**:

1. **Given** a fresh clone of the repository, **When** the developer runs the install and start commands, **Then** the application starts and renders a default page within 30 seconds
2. **Given** the running application, **When** the user toggles dark mode, **Then** all UI elements update to the dark color scheme without page reload
3. **Given** the design system configuration, **When** any component renders, **Then** it uses the brand colors, typography, and spacing tokens — not browser defaults
4. **Given** the application in a browser, **When** the viewport is resized from desktop to mobile, **Then** the layout adapts responsively with no overlapping elements

---

### User Story 2 — App Shell and Navigation (Priority: P1)

When a user lands on the application, they see a consistent shell with a collapsible sidebar, a top header with workspace selector and user menu, breadcrumb navigation, and a command palette accessible via keyboard shortcut. The sidebar shows navigation items filtered by the user's role — users only see links they have permission to access. The app shell wraps all pages and persists across navigation.

**Why this priority**: The app shell is the container for all future features. Without it, there is no way to navigate between bounded context UIs. It also establishes the role-aware filtering pattern used throughout the platform.

**Independent Test**: Open the application as a user with the "viewer" role. Verify the sidebar shows only read-only navigation items. Switch to an "admin" role. Verify admin-only items appear. Collapse the sidebar. Verify it minimizes to icons only. Open the command palette with the keyboard shortcut. Search for a navigation item. Select it. Verify the page navigates correctly.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** they land on the application, **Then** they see a sidebar with navigation items, a header with workspace selector, notifications icon, and user avatar menu
2. **Given** the sidebar in expanded state, **When** the user clicks the collapse toggle, **Then** the sidebar collapses to show only icons, and the main content area expands to fill the freed space
3. **Given** a user with the "viewer" role, **When** the sidebar renders, **Then** only navigation items permitted for "viewer" are visible — admin-only items are hidden
4. **Given** the application is focused, **When** the user presses the command palette shortcut, **Then** a search dialog opens where they can type to find and navigate to any accessible page or action
5. **Given** multi-level page navigation, **When** the user navigates to a nested page, **Then** breadcrumbs update to reflect the full path and each segment is clickable

---

### User Story 3 — API Communication Layer (Priority: P1)

Frontend developers need a typed client for communicating with the backend API. The client handles authentication token injection, automatic token refresh on expiry, structured error handling, and request retries for transient failures. Server state management wraps the client to provide caching, background refetching, and optimistic updates across all UI components.

**Why this priority**: Every bounded context UI depends on API communication. Without a standardized client, each context would implement its own fetch logic, leading to inconsistent error handling and duplicated auth logic.

**Independent Test**: Call a protected endpoint through the API client. Verify the JWT is injected automatically. Simulate a 401 response. Verify the client refreshes the token and retries the request. Simulate a network error. Verify the client retries with backoff. Verify the server state layer caches responses and refetches in the background.

**Acceptance Scenarios**:

1. **Given** a logged-in user, **When** the API client makes a request, **Then** the stored JWT access token is automatically injected in the Authorization header
2. **Given** an expired access token, **When** a request returns 401, **Then** the client uses the refresh token to obtain a new access token and retries the original request — the user sees no interruption
3. **Given** a transient network error, **When** a request fails, **Then** the client retries up to 3 times with exponential backoff before surfacing the error
4. **Given** a successful API response, **When** the same data is requested again within the cache window, **Then** the cached response is returned immediately while a background refetch updates the cache
5. **Given** an API error response, **When** the error is surfaced to the UI, **Then** it includes a human-readable message, error code, and any relevant details — not raw HTTP status codes

---

### User Story 4 — Real-Time Updates via WebSocket (Priority: P2)

Platform operators and users need real-time updates for execution status, notifications, and workspace activity. The WebSocket client establishes a persistent connection, automatically reconnects on disconnection, and provides a subscription model so components can subscribe to specific event channels. Connection state is visible to the user (connected/reconnecting indicator).

**Why this priority**: Real-time updates enhance the user experience significantly but the application can function without them using polling or manual refresh. Core page rendering and API communication (US1–US3) are prerequisites.

**Independent Test**: Open the application. Verify a WebSocket connection is established. Simulate a server disconnection. Verify the client shows a "reconnecting" indicator and automatically reconnects. Subscribe to an event channel. Send an event. Verify the subscribed component updates in real time.

**Acceptance Scenarios**:

1. **Given** an authenticated user, **When** the application loads, **Then** a WebSocket connection is established to the server
2. **Given** an active WebSocket connection, **When** the server sends an event on a subscribed channel, **Then** the subscribed component receives and processes the event in under 100 milliseconds
3. **Given** a lost WebSocket connection, **When** the client detects disconnection, **Then** it shows a visual indicator and begins reconnection attempts with exponential backoff
4. **Given** successful reconnection, **When** the connection is restored, **Then** the visual indicator disappears and all subscriptions are re-established automatically

---

### User Story 5 — Shared UI Components Library (Priority: P1)

Frontend developers need a set of reusable, themed components that maintain visual consistency across all bounded context UIs. These components include data display (tables, metric cards, status badges, timelines, score gauges), user input (search fields, filter bars), feedback (empty states, confirmation dialogs), and content display (code blocks, JSON viewers). Each component respects the design system, supports dark mode, is keyboard navigable, and is accessible to screen readers.

**Why this priority**: Shared components prevent inconsistency across bounded contexts and accelerate development. Without them, each bounded context would build its own table/badge/card implementations, leading to visual fragmentation and duplicated effort.

**Independent Test**: Render each shared component in isolation with sample data. Verify consistent styling in both light and dark mode. Navigate each interactive component using keyboard only. Verify ARIA labels are present for screen readers. Resize the viewport. Verify responsive behavior.

**Acceptance Scenarios**:

1. **Given** tabular data, **When** the data table component renders, **Then** it displays sortable columns, filterable rows, and paginated results with clear visual feedback on sort/filter state
2. **Given** a numeric metric, **When** the metric card renders, **Then** it shows the value, a trend indicator (up/down/neutral), and an optional sparkline chart
3. **Given** a status value, **When** the status badge renders, **Then** it displays a color-coded badge matching the status semantics (green for healthy, yellow for warning, red for error)
4. **Given** any shared component in dark mode, **When** the theme toggles, **Then** all colors, borders, and backgrounds update to the dark palette without visual artifacts
5. **Given** a data table with no data, **When** it renders, **Then** it shows a styled empty state with a message and optional call-to-action
6. **Given** a destructive action trigger, **When** the user initiates it, **Then** a confirmation dialog appears requiring explicit confirmation before proceeding
7. **Given** structured data (JSON), **When** the JSON viewer renders, **Then** it displays syntax-highlighted, collapsible JSON with copy functionality

---

### User Story 6 — Client-Side State Management (Priority: P2)

The application needs persistent client state for authentication status (logged in, tokens, user profile) and workspace context (current workspace ID, workspace preferences). This state persists across page navigations, is accessible from any component, and syncs with the API layer. When the user switches workspaces, all active queries refetch with the new workspace context.

**Why this priority**: Auth and workspace state are cross-cutting concerns but can be stubbed during early development. Core rendering (US1) and API communication (US3) can use hardcoded values initially.

**Independent Test**: Log in. Verify the auth store contains the user profile and tokens. Navigate between pages. Verify the auth state persists. Switch workspaces. Verify all cached queries invalidate and refetch with the new workspace context. Log out. Verify all client state is cleared.

**Acceptance Scenarios**:

1. **Given** a successful login, **When** the auth store is updated, **Then** the user profile, access token, and refresh token are available to all components
2. **Given** the user navigates between pages, **When** the auth store is read, **Then** the authentication state persists without re-fetching
3. **Given** a workspace switch, **When** the workspace store updates, **Then** all active server state queries are invalidated and refetched with the new workspace context
4. **Given** a user logs out, **When** the logout action is dispatched, **Then** all client state (auth, workspace, cached queries) is cleared and the user is redirected to the login page

---

### Edge Cases

- What happens when the API is unreachable? The application shows a connection error banner at the top of the page. Cached data remains visible. New requests show loading indicators followed by error states.
- What happens when the WebSocket connection fails to establish on initial load? The application functions normally without real-time updates. A subtle indicator shows the WebSocket is disconnected. Polling fallback is not included in this feature (manual refresh only).
- What happens when the user's JWT expires and the refresh token also expires? The application redirects to the login page with a "session expired" message.
- What happens when a user with no roles accesses the application? The sidebar shows no navigation items. A message indicates the user has no permissions assigned and should contact an administrator.
- What happens when the browser window is resized during a command palette search? The command palette remains centered and adjusts its width to fit the viewport.
- What happens when a component receives malformed data from the API? The component renders an error boundary with a fallback UI rather than crashing the entire page.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Application MUST render a themed user interface with brand colors, typography, and spacing in both light and dark modes
- **FR-002**: Application MUST provide a persistent app shell with collapsible sidebar, header (workspace selector, notifications, user menu), and breadcrumb navigation
- **FR-003**: Sidebar navigation MUST filter visible items based on the current user's role
- **FR-004**: Application MUST provide a keyboard-accessible command palette for quick navigation and action search
- **FR-005**: Application MUST provide a typed API client that injects authentication tokens, handles errors, and retries transient failures
- **FR-006**: Application MUST automatically refresh expired access tokens using the stored refresh token without user intervention
- **FR-007**: Server state MUST be cached and background-refetched to minimize visible loading states for previously-fetched data
- **FR-008**: Application MUST establish a persistent WebSocket connection with automatic reconnection and visual connection state
- **FR-009**: WebSocket client MUST support subscribing to specific event channels and dispatching events to subscribed components
- **FR-010**: Application MUST provide reusable shared components: DataTable (sortable, filterable, paginated), StatusBadge (color-coded), MetricCard (value + trend + sparkline), EmptyState, ConfirmDialog, CodeBlock, JsonViewer, Timeline, SearchInput, FilterBar, ScoreGauge
- **FR-011**: All shared components MUST support dark mode, keyboard navigation, and screen reader accessibility
- **FR-012**: Application MUST maintain client state for authentication (user profile, tokens) and workspace context (current workspace, preferences)
- **FR-013**: Switching workspaces MUST invalidate and refetch all active queries with the new workspace context
- **FR-014**: Application MUST be responsive across desktop (1280px+) and mobile (320px+) viewports
- **FR-015**: Application MUST display error boundaries that catch component errors and show fallback UI without crashing the page
- **FR-016**: All interactive UI elements MUST be 30+ primitives from the component library, not custom implementations

### Key Entities

- **AppShell**: The persistent layout container with sidebar, header, and content area. Wraps all pages.
- **NavigationItem**: A sidebar link with label, icon, route, and role-based visibility configuration.
- **Theme**: The design token set (colors, typography, spacing, radii) that defines the visual identity in light and dark modes.
- **ApiClient**: The communication layer that manages authentication headers, error handling, retries, and response typing.
- **WebSocketClient**: The real-time connection manager handling connection lifecycle, reconnection, and subscription routing.
- **AuthState**: Client-side representation of the authenticated user — profile, tokens, and session metadata.
- **WorkspaceState**: Client-side representation of the active workspace — ID, name, and user preferences within that workspace.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Application loads and renders the app shell within 3 seconds on standard broadband connections
- **SC-002**: Dark mode toggle applies to 100% of UI elements with no un-themed components visible
- **SC-003**: Sidebar collapse/expand animation completes within 200 milliseconds with no layout jitter
- **SC-004**: Command palette opens within 100 milliseconds of keyboard shortcut and filters results as the user types
- **SC-005**: API requests with expired tokens refresh and retry transparently — user experiences no authentication interruptions during normal usage
- **SC-006**: WebSocket reconnects within 10 seconds of connection loss and re-establishes all subscriptions
- **SC-007**: All shared components render correctly in both light and dark modes with no visual artifacts
- **SC-008**: All interactive components are navigable using keyboard only (Tab, Enter, Escape, Arrow keys as appropriate)
- **SC-009**: Data tables handle 1000+ rows with pagination without visible performance degradation
- **SC-010**: Application is responsive — all layouts render without horizontal scrolling on viewports from 320px to 2560px

## Assumptions

- The backend API (feature 013 scaffold, feature 014 auth) exists and provides the endpoints for authentication (/login, /refresh, /logout) and workspace management
- The WebSocket server endpoint is available at a configurable URL and follows the platform's event channel protocol
- The 10 RBAC roles and their navigation permissions are defined in the auth bounded context (feature 014). The frontend receives the user's roles in JWT claims and filters navigation client-side
- The component library provides all needed primitives (buttons, inputs, dialogs, dropdowns, etc.) — no alternative component libraries will be used
- Charts (sparklines in MetricCard, ScoreGauge) use the charting library mandated by the constitution. Complex visualizations (workflow DAGs, fleet topologies) are deferred to bounded context features.
- The command palette searches only navigation items and quick actions — full-text search of platform content is handled by dedicated search features
- Mobile support means a responsive layout that works on mobile browsers — there is no native mobile app in scope
- The scaffold establishes patterns and shared infrastructure only. Individual bounded context pages (agents, workflows, analytics) are implemented in separate features.
