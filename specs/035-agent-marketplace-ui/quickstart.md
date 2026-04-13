# Quickstart / Test Scenarios: Agent Marketplace UI

**Branch**: `035-agent-marketplace`

These scenarios cover end-to-end flows for all 7 user stories. Each can be executed in the development environment with MSW mocks or against a live backend.

---

## T01 — Natural-language search returns results (US1)

```
1. Navigate to /marketplace
2. Type "financial analysis agent" in the search bar
3. Wait 300ms (debounce fires)
→ Agent cards grid updates to show agents matching "financial analysis"
→ URL updates to /marketplace?q=financial+analysis
→ Each visible card shows: name, short description, maturity badge, trust badge, star rating, cost indicator
→ Loading skeleton shown during fetch, replaced by cards on success
```

---

## T02 — Faceted filter narrows results (US1)

```
1. Navigate to /marketplace (with results showing)
2. In filter sidebar, click "production" under Maturity Level
→ Checkbox becomes checked
→ Grid updates immediately showing only production-maturity agents
→ URL updates to include &maturityLevels=production
→ Active filter count badge on sidebar shows "1"
3. Additionally check "certified" under Trust Tier
→ Grid updates to show only production + certified agents
→ URL shows &maturityLevels=production&trustTiers=certified
4. Click "Clear all filters"
→ All checkboxes uncheck, grid shows all agents
```

---

## T03 — Empty search state (US1 edge case)

```
1. Navigate to /marketplace
2. Type a search query that matches nothing: "zzz-nonexistent-agent"
→ After debounce, grid shows empty state:
  - Message: "No agents match your search"
  - Suggestion text to broaden query or remove filters
  - Not a blank screen or error
```

---

## T04 — Mobile filter drawer (US1 responsive)

```
1. Set viewport to 375×812 (mobile)
2. Navigate to /marketplace
→ Filter sidebar is NOT visible inline
→ A "Filters (0)" button appears above the search bar
3. Click "Filters (0)"
→ shadcn Sheet slides in from left/bottom with filter checkboxes
4. Check "beta" maturity, check "free" cost tier
→ "Filters (2)" button updates
5. Close Sheet
→ Grid updates with active filters applied
```

---

## T05 — Sort by rating (US1 sort)

```
1. Navigate to /marketplace with results
2. Open the sort dropdown and select "Rating"
→ URL updates to &sortBy=rating
→ Grid re-orders: highest-rated agents appear first
→ Sort dropdown shows "Rating" as selected value
```

---

## T06 — Infinite scroll loads more (US1 pagination)

```
1. Navigate to /marketplace (initial 20 cards loaded)
2. Scroll to bottom of card grid
→ Loading indicator appears
→ Next 20 cards append to the grid (no page reload, no back to top)
3. Continue scrolling until all results loaded
→ No loading indicator shown when no more results exist
```

---

## T07 — Agent detail page full view (US2)

```
1. Navigate to /marketplace
2. Click on an agent card (e.g., "finance-ops:kyc-verifier")
→ Browser navigates to /marketplace/finance-ops/kyc-verifier
→ Page shows all sections:
  - Header: name, FQN, current version, maturity badge, trust tier badge
  - Description: full text
  - Capabilities: list of declared capabilities
  - Trust Signals: tier, certification badges, latest eval score
  - Revision History: chronological version list
  - Policies: attached policy names with enforcement type
  - Quality Metrics: eval score, robustness score, last tested date
  - Cost: tier, estimated cost per invocation
  - Reviews section
  - "Start Conversation" button (enabled if visible to user)
```

---

## T08 — Trust signals panel (US2)

```
1. Navigate to agent detail for a certified agent
2. View Trust Signals section
→ Trust tier badge shows "Certified" with appropriate color
→ Certification badges listed with issue date and expiry
→ Latest evaluation: score 0.87, "8/10 cases passed", date shown
→ Tier progression timeline: Unverified → Basic → Standard → Certified with dates
```

---

## T09 — Archived agent detail shows unavailable state (US2 edge case)

```
1. Navigate to /marketplace/finance-ops/deleted-agent (agent no longer exists)
→ Page does NOT show a 404 error page
→ Shows: "This agent is no longer available" message
→ "Back to Marketplace" link present
```

---

## T10 — Add agents to comparison (US3)

```
1. Navigate to /marketplace
2. Click "Compare" button on agent card A
→ Floating compare bar appears at bottom: "1 agent selected"
3. Click "Compare" button on agent card B
→ Floating bar: "2 agents selected — Compare now"
4. Click "Compare" button on agent card C
→ Floating bar: "3 agents selected — Compare now"
5. Click "Compare now" button
→ Browser navigates to /marketplace/compare?agents=ns1%2Fa,ns2%2Fb,ns3%2Fc
→ Side-by-side table shows: A | B | C as columns, attributes as rows
→ Attributes: Display Name, Maturity, Trust Tier, Capabilities, Average Rating, Cost, Latest Eval Score, Active Policies
```

---

## T11 — Comparison attribute with missing value (US3 edge case)

```
1. Compare 2 agents: agent A has 3 certifications, agent B has 0
2. View comparison table "Certification Badges" row
→ Agent A: "3 certifications"
→ Agent B: "—" (N/A indicator, not blank)
```

---

## T12 — Comparison maximum limit (US3 edge case)

```
1. Select 4 agents for comparison (floating bar: "4 agents selected")
2. Attempt to click "Compare" on a 5th agent card
→ Clicking "Compare" on the 5th card is disabled or shows a tooltip:
  "Maximum of 4 agents can be compared at once"
→ The 5th agent is NOT added to the selection
```

---

## T13 — View and submit review (US4)

```
1. Navigate to agent detail page
2. Scroll to Reviews section
→ Average rating (e.g., 4.2 stars) and review count (e.g., "38 reviews") shown in header
→ Review list shows each review: star display, text, author, date
3. Scroll to "Write a Review" form
4. Click 4th star in StarRatingInput
→ 4 stars filled, 1 empty; aria-label confirms selection
5. Type review text: "Works well for KYC tasks"
6. Click "Submit Review"
→ Review appears at top of the list immediately (optimistic update or refetch)
→ Submit button shows loading state during submission
→ Average rating recalculates
```

---

## T14 — Edit existing review (US4)

```
1. Navigate to agent detail page as a user who already submitted a review
2. View Reviews section
→ Own review shows an "Edit" button (not a new "Write a Review" form)
3. Click "Edit"
→ Inline form prefilled with existing rating and text
4. Change rating from 4 to 3 stars, update text
5. Click "Save"
→ Review updates in place; "Edit" button returns
```

---

## T15 — Zero-review empty state (US4 edge case)

```
1. Navigate to agent detail for an agent with no reviews
→ Ratings section shows "No reviews yet"
→ "Be the first to review" invitation text
→ StarRatingInput and text area shown below
```

---

## T16 — Invoke agent: workspace selection (US5)

```
1. Navigate to agent detail page
2. Click "Start Conversation"
→ shadcn Dialog opens
→ Step 1 shows: list of workspaces (radio buttons or Select)
3. Select "Marketing Analytics" workspace
4. Click "Next"
→ Step 2 shows task brief textarea
5. Type: "Analyze Q1 customer churn patterns"
6. Click "Start Conversation"
→ Dialog closes
→ Browser navigates to /conversations/new?agent=finance-ops%3Akyc-verifier&workspace=<id>&brief=Analyze+Q1...
→ Conversation page shows agent pre-selected and task brief pre-filled
```

---

## T17 — Invoke agent: single workspace auto-select (US5)

```
1. As a user with only 1 workspace, click "Start Conversation" on agent detail
→ Dialog opens directly on step 2 (task brief) — workspace is auto-selected
→ "Selected workspace: Default" shown as read-only text
```

---

## T18 — Invoke blocked by visibility (US5 edge case)

```
1. View an agent card for an agent outside the user's visibility config
→ "Start Conversation" button is disabled (grayed out)
→ Hovering shows tooltip: "You don't have access to invoke this agent"
→ No dialog opens on click
```

---

## T19 — Recommendation carousel personalized (US6)

```
1. Log in as a user with prior agent interactions (multiple eval runs, conversations)
2. Navigate to /marketplace
→ "Recommended for you" carousel appears above the search bar
→ Shows 4-6 agent cards in a horizontal scroll
→ Header text: "Recommended for you"
3. Click an agent card in the carousel
→ Navigates to that agent's detail page
```

---

## T20 — Recommendation carousel fallback (US6 edge case)

```
1. Log in as a new user with no interaction history
2. Navigate to /marketplace
→ Carousel appears with header text: "Popular agents" or "Trending this week"
→ Shows ≥3 agents (popular/trending, not personalized)
```

---

## T21 — Carousel hidden when insufficient recommendations (US6 edge case)

```
1. Simulate API returning only 2 recommendation items
→ Carousel is NOT rendered at all on the page
→ No empty carousel or loading placeholder
```

---

## T22 — Creator analytics tab (US7)

```
1. Log in as agent creator ("finance-ops" namespace owner)
2. Navigate to /marketplace/finance-ops/kyc-verifier
→ Detail page shows tabs: Overview | Policies | Quality Metrics | Reviews | Analytics
3. Click "Analytics" tab
→ Usage chart: bar chart showing daily invocations for past 30 days
→ Satisfaction trend: line chart with weekly average ratings
→ Common failures: list with "timeout: 12 (40%)", "policy_violation: 8 (27%)", etc.
```

---

## T23 — Analytics tab hidden for non-owner (US7 access control)

```
1. Log in as a regular workspace member (not the agent creator)
2. Navigate to /marketplace/finance-ops/kyc-verifier
→ Tabs shown: Overview | Policies | Quality Metrics | Reviews
→ "Analytics" tab is NOT present in the tab list
→ DOM inspection confirms tab element is not rendered (not just hidden)
```

---

## T24 — Dark mode rendering (cross-cutting)

```
1. Enable dark mode (OS or theme toggle)
2. Navigate through: marketplace page, filter sidebar, agent detail, comparison, reviews
→ All text is readable
→ All badges and indicators use dark-mode-appropriate colors
→ Charts render with accessible color contrast in dark mode
→ No hardcoded light colors visible
```

---

## T25 — Keyboard navigation (cross-cutting)

```
1. Navigate to /marketplace with Tab key only (no mouse)
→ Focus moves through: search bar → filter checkboxes → sort dropdown → agent cards → "Compare" buttons → comparison bar
→ Pressing Enter on an agent card navigates to its detail page
2. Navigate to agent detail with Tab key
→ Focus moves through all tabs, within-tab content, star rating input (arrow keys change value), submit button
→ Opening InvokeAgentDialog traps focus within it
→ Pressing Escape closes Dialog and returns focus to "Start Conversation" button
```
