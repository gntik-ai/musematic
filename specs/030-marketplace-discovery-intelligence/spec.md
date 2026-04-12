# Feature Specification: Marketplace Discovery and Intelligence

**Feature Branch**: `030-marketplace-discovery-intelligence`
**Created**: 2026-04-12
**Status**: Draft
**Input**: User description: "Implement natural-language agent search, faceted filtering, comparison views, intelligent recommendation engine, quality signal aggregation, contextual discovery, trending agents, and agent ratings/reviews."

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Agent Search and Filtering (Priority: P1)

A workspace member needs to find an agent that can help with a specific task. They type a natural-language query (e.g., "agent that can analyze financial reports") into the marketplace search bar. The system returns relevant agents ranked by a combination of keyword relevance and semantic similarity — even if the query words don't exactly match the agent's description. Results can be further narrowed using faceted filters: workspace visibility, tags, capabilities, maturity level, trust tier, certification status, and cost tier.

**Why this priority**: Search is the primary entry point to the marketplace. Without it, users cannot discover agents, making all other marketplace features useless.

**Independent Test**: Search for "financial analysis" → receive agents with finance-related capabilities, including one described as "quarterly report auditor" (no keyword overlap, semantic match only). Apply maturity filter (level 2+) → subset of results returned. Apply trust tier filter → further narrowing. Search for nonsense string → empty results with helpful message.

**Acceptance Scenarios**:

1. **Given** agents registered in the marketplace, **When** a user searches "analyze sales data", **Then** agents with sales/data analysis capabilities are returned, ordered by relevance.
2. **Given** a query "invoice processor", **When** an agent's description says "automated accounts payable handler" (no keyword match), **Then** that agent still appears in results due to semantic similarity.
3. **Given** search results, **When** the user applies a maturity filter of "level 2 or higher", **Then** only agents at maturity level 2+ remain in results.
4. **Given** a user with workspace visibility restrictions, **When** they search, **Then** agents outside their visibility scope never appear in results.
5. **Given** an empty search query, **When** the user browses the marketplace, **Then** they see a curated listing of agents ordered by popularity/relevance within their visibility scope.

---

### User Story 2 — Agent Comparison (Priority: P1)

After finding several candidate agents, a user wants to compare them side-by-side before choosing one for their workflow. They select 2 to 4 agents and open a comparison view showing key attributes: capabilities, maturity level, trust tier, certification status, average quality score, cost tier, success rate, and user rating. Differences are visually highlighted to aid decision-making.

**Why this priority**: Comparison is the natural next step after search. Users who find agents need a way to evaluate which is best suited for their needs before committing.

**Independent Test**: Select 3 agents → comparison table shows all key attributes side-by-side → differences in maturity/trust highlighted → attempting to compare 5+ agents shows an error. Select 1 agent → comparison not available (minimum 2).

**Acceptance Scenarios**:

1. **Given** 3 selected agents, **When** the user opens comparison view, **Then** a side-by-side table shows capabilities, maturity, trust tier, certification, quality score, cost tier, success rate, and rating for each.
2. **Given** a comparison table, **When** maturity levels differ between agents, **Then** the difference is visually highlighted.
3. **Given** an attempt to compare fewer than 2 or more than 4 agents, **Then** the system shows an appropriate message explaining the valid range.

---

### User Story 3 — Quality Signal Aggregation (Priority: P1)

The marketplace displays a composite quality profile for each agent, aggregated from multiple signal sources: execution success rate, quality scores from evaluation suites, self-correction frequency, user satisfaction ratings, and certification compliance. This aggregated quality view is visible on every agent listing and in comparison tables, giving users a trustworthy summary before selecting an agent.

**Why this priority**: Quality signals are the trust foundation for the marketplace. Without them, users cannot make informed decisions, reducing marketplace value to a simple directory.

**Independent Test**: View an agent listing → quality profile shows success rate, quality score, self-correction frequency, satisfaction rating, and certification status. Each value sourced from the appropriate upstream system. Agent with no usage history shows "No data yet" instead of zeros.

**Acceptance Scenarios**:

1. **Given** an agent with execution history, **When** viewing its listing, **Then** the quality profile shows: execution success rate (percentage), average quality score (0–100), self-correction frequency (percentage of executions requiring correction), average user satisfaction (1–5), and certification compliance (compliant/non-compliant/uncertified).
2. **Given** an agent with no execution history, **When** viewing its listing, **Then** quality metrics show "No data yet" rather than misleading zero values.
3. **Given** new quality data arriving (e.g., a new execution result), **When** the quality profile is next viewed, **Then** the updated aggregate is reflected within a reasonable refresh interval.

---

### User Story 4 — Intelligent Recommendations (Priority: P2)

The system suggests agents that a user is likely to find useful, personalized by three dimensions: (1) collaborative filtering — "users similar to you also used these agents"; (2) content-based — agents with capabilities matching the user's recent tasks and workspace context; (3) contextual — agents relevant to the current conversation, workflow step, or workspace goal. Recommendations appear on the marketplace home page, within workbench sidebars, and when a user is building a workflow.

**Why this priority**: Recommendations increase agent adoption and discovery of niche agents that users wouldn't find through search alone. They are a significant differentiator but the marketplace is functional without them.

**Independent Test**: User A frequently uses finance agents → recommended list includes finance agents not yet used by User A. User B works in a marketing workspace → contextual recommendations show marketing-capable agents. New user with no history → fallback recommendations based on workspace popularity.

**Acceptance Scenarios**:

1. **Given** a user who frequently invokes finance-domain agents, **When** they visit the marketplace, **Then** recommended agents include finance-related agents they haven't used yet.
2. **Given** a user working in a "marketing" workspace, **When** recommendations are requested, **Then** agents with marketing-relevant capabilities are prioritized.
3. **Given** a user building a workflow step that requires "data extraction", **When** contextual recommendations are shown, **Then** agents capable of data extraction appear.
4. **Given** a new user with no usage history, **When** recommendations are requested, **Then** fallback recommendations are provided based on workspace-level popularity.

---

### User Story 5 — Agent Ratings and Reviews (Priority: P2)

Users who have invoked an agent can leave a rating (1–5 score) and optional review text. The aggregate rating (average score and review count) is visible on the agent listing. Agent creators can see analytics for their agents: invocation count, average satisfaction, common failure patterns, and usage trend. Reviews are filterable by score and recency.

**Why this priority**: Ratings create a feedback loop that improves marketplace quality over time. They are important for trust but the marketplace functions without them initially.

**Independent Test**: User invokes an agent → submits a 4-star review with text → review appears on agent listing → aggregate score updates. Another user filters reviews by "5 stars only" → only 5-star reviews shown. Creator views analytics → sees invocation count and satisfaction trend.

**Acceptance Scenarios**:

1. **Given** a user who has invoked an agent, **When** they submit a rating (4 stars, "Great for financial analysis"), **Then** the review is stored and visible on the agent listing.
2. **Given** an agent with 10 reviews averaging 4.2 stars, **When** a new user views the listing, **Then** they see "4.2 (10 reviews)" as the aggregate rating.
3. **Given** reviews of varying scores, **When** a user filters by "5 stars", **Then** only 5-star reviews are displayed.
4. **Given** an agent creator, **When** they view analytics for their agent, **Then** they see invocation count, average satisfaction, common failure patterns, and usage trend over time.
5. **Given** a user who has NOT invoked an agent, **When** they attempt to submit a review, **Then** the system rejects the submission (only users with prior invocation can rate).

---

### User Story 6 — Contextual Discovery Suggestions (Priority: P3)

While working inside a workbench (workflow builder, conversation view, fleet configuration), the system surfaces contextual agent suggestions based on the current task. For example, if a user is editing a workflow step that requires "email extraction", nearby agent suggestions show agents capable of email parsing. These suggestions appear as a non-intrusive sidebar or inline prompt, not as a full marketplace search.

**Why this priority**: Contextual discovery is a usability enhancement that reduces context-switching but is not required for core marketplace functionality.

**Independent Test**: User edits a workflow step tagged "sentiment analysis" → contextual suggestion shows agents with NLP/sentiment capabilities → user clicks suggestion → agent details open in marketplace view.

**Acceptance Scenarios**:

1. **Given** a user editing a workflow step requiring "sentiment analysis", **When** contextual suggestions are displayed, **Then** agents with NLP/sentiment capabilities are suggested.
2. **Given** no agents matching the current context, **When** contextual suggestions are requested, **Then** the suggestion area shows a helpful message or remains hidden.
3. **Given** a user in a conversation where the topic involves "data migration", **When** contextual suggestions are enabled, **Then** data migration agents are suggested.

---

### User Story 7 — Trending Agents (Priority: P3)

The marketplace shows a "trending" section highlighting agents that have seen increased adoption in recent time periods. Trending scores are computed from recent invocation counts and satisfaction ratings, normalized to avoid bias toward agents with long histories. Trending data refreshes periodically.

**Why this priority**: Trending is a discovery enhancement that surfaces popular new agents. It improves marketplace engagement but is not required for basic functionality.

**Independent Test**: Agent X receives 50 invocations this week (vs 5 last week, 10x increase) → appears in trending. Agent Y has 1000 total invocations but flat growth → does not appear in trending. Trending list refreshes daily.

**Acceptance Scenarios**:

1. **Given** an agent with a significant increase in invocations this week compared to last week, **When** the trending list is computed, **Then** that agent appears in the trending section.
2. **Given** an agent with high total invocations but no recent growth, **When** the trending list is computed, **Then** it does not appear in trending.
3. **Given** the trending list, **When** viewed, **Then** it shows the trending score reason (e.g., "3x more invocations this week") alongside each agent.

---

### Edge Cases

- What happens when a user searches in a language other than English? The system performs the search normally; semantic search handles multilingual queries to the extent the embedding model supports them. Document this as a known limitation if coverage is incomplete.
- What happens when quality signal sources are temporarily unavailable? The system displays the last known aggregate value with a "last updated" timestamp. It does not show stale data as current.
- What happens when an agent has exactly 1 review? The average rating is that single review's score. No statistical disclaimer is shown, but the review count ("1 review") provides context.
- What happens when a user attempts to review the same agent twice? The system allows updating the existing review (edit, not duplicate). Only the most recent review per user per agent is counted in the aggregate.
- What happens when all agents are filtered out? The system shows an empty state with a suggestion to broaden filter criteria.
- What happens when collaborative filtering has insufficient data for a new user? The system falls back to content-based recommendations using workspace context, then to popularity-based recommendations if context is also sparse.

## Requirements *(mandatory)*

### Functional Requirements

**Search**

- **FR-001**: System MUST support natural-language queries that return agents ranked by combined keyword and semantic relevance
- **FR-002**: System MUST return agents that are semantically related to the query even when there is zero keyword overlap between query and agent description
- **FR-003**: System MUST enforce workspace visibility restrictions on all search results — agents outside the user's visibility scope never appear
- **FR-004**: System MUST support faceted filtering on: tags, capabilities, maturity level, trust tier, certification status, and cost tier
- **FR-005**: System MUST support empty-query browsing that returns agents ordered by popularity within the user's visibility scope

**Comparison**

- **FR-006**: System MUST support side-by-side comparison of 2 to 4 agents, showing: capabilities, maturity level, trust tier, certification status, average quality score, cost tier, success rate, and user rating
- **FR-007**: System MUST visually highlight differences between compared agents in the comparison view
- **FR-008**: System MUST reject comparison requests with fewer than 2 or more than 4 agents with an informative message

**Quality Signals**

- **FR-009**: System MUST display an aggregated quality profile for each agent, including: execution success rate, average quality score, self-correction frequency, average user satisfaction, and certification compliance
- **FR-010**: System MUST show "No data yet" for agents with no execution history rather than zero values
- **FR-011**: System MUST refresh quality aggregates when new data arrives from upstream systems within a configurable refresh interval
- **FR-012**: System MUST display a "last updated" timestamp on quality data when the source is temporarily unavailable, indicating the data may be stale

**Recommendations**

- **FR-013**: System MUST generate personalized recommendations using collaborative filtering based on usage patterns of similar users
- **FR-014**: System MUST generate content-based recommendations using agent capability embeddings matched to user context
- **FR-015**: System MUST generate contextual recommendations based on the current workspace, conversation, or workflow step context
- **FR-016**: System MUST provide fallback recommendations (workspace popularity, then platform popularity) when personalization data is insufficient
- **FR-017**: System MUST surface recommendations on the marketplace home page, within workbench sidebars, and during workflow construction

**Ratings and Reviews**

- **FR-018**: System MUST allow users who have previously invoked an agent to submit a rating (1–5 integer score) and optional review text
- **FR-019**: System MUST display aggregate rating (average score, review count) on each agent listing
- **FR-020**: System MUST support filtering reviews by score range and recency
- **FR-021**: System MUST allow users to update their existing review (one review per user per agent; most recent counts in aggregate)
- **FR-022**: System MUST provide creator analytics: invocation count, average satisfaction, common failure patterns, and usage trend
- **FR-023**: System MUST reject review submissions from users who have never invoked the target agent

**Contextual Discovery**

- **FR-024**: System MUST display agent suggestions within workbenches based on the current task context (workflow step type, conversation topic, fleet configuration)
- **FR-025**: System MUST hide or show a helpful message in contextual suggestion areas when no matching agents exist

**Trending**

- **FR-026**: System MUST compute trending scores based on recent invocation growth rate and satisfaction ratings, normalized to avoid bias toward long-running agents
- **FR-027**: System MUST refresh the trending list on a periodic schedule
- **FR-028**: System MUST display the trending reason alongside each trending agent (e.g., "3x invocations this week")

### Key Entities

- **MarketplaceListingProjection**: Read-optimized view of an agent's marketplace presence — name, FQN, description, capabilities, tags, maturity level, cost tier, aggregate quality profile, aggregate rating, workspace scope.
- **TrustSignalProjection**: Read-optimized view of an agent's trust profile — trust tier, certification status, compliance state, last certification date.
- **AgentRating**: A user's rating and review of an agent — user reference, agent reference, score (1–5), review text, timestamps. One per user per agent (most recent wins).
- **QualitySignalAggregate**: Aggregated quality metrics for an agent — success rate, quality score average, self-correction frequency, satisfaction average, certification compliance. Refreshed periodically from upstream sources.
- **AgentRecommendation**: A computed recommendation for a user — recommended agent reference, recommendation type (collaborative/content-based/contextual), score, reasoning/explanation.
- **ContextualDiscoverySuggestion**: A suggestion for agents relevant to a specific workbench context — context reference (workflow step, conversation, fleet), suggested agent references, relevance scores.
- **TrendingAgentProjection**: A snapshot of trending agents — agent reference, trending score, growth rate, trending reason, time period, satisfaction delta.
- **AccessRequest**: A request from a user to gain access to an agent outside their visibility scope — user reference, agent reference, request reason, status (pending/approved/denied).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Natural-language search returns relevant results (top-5 includes at least one correct match) for 90% of test queries
- **SC-002**: Semantic search finds semantically related agents even with zero keyword overlap in at least 80% of synonym-based test queries
- **SC-003**: Users see search results within 1 second of submitting a query
- **SC-004**: Users see the comparison view within 1 second of selecting agents to compare
- **SC-005**: Quality signal aggregates reflect new data within 5 minutes of the data being available in upstream systems
- **SC-006**: Personalized recommendations show at least 2 agents the user has not previously used in 80% of cases
- **SC-007**: Contextual suggestions are relevant to the current task context (verified by manual evaluation) in 75% of cases
- **SC-008**: Trending list updates daily and reflects actual recent usage growth
- **SC-009**: Agent ratings are recorded and visible on listings within 5 seconds of submission
- **SC-010**: Creator analytics dashboard loads within 2 seconds and shows current data
- **SC-011**: All marketplace queries enforce visibility filtering — 0% of results include agents outside the user's visibility scope
- **SC-012**: Test coverage of at least 95% across all marketplace discovery components

## Assumptions

- The agent registry (feature 021) provides agent profiles, capabilities, maturity levels, and embeddings. This feature consumes that data; it does not manage agent registration.
- Quality scores, execution success rates, and self-correction frequencies are available from upstream systems (analytics, evaluation, execution). This feature aggregates and projects them; it does not compute them from scratch.
- Embedding vectors for agents are generated by the registry ingest pipeline and stored in the vector search store. This feature queries embeddings; it does not generate them.
- The full-text search store is populated by the search projection pipeline (feature 008). This feature queries it; it does not maintain the index.
- Workspace visibility configuration is managed by the workspaces and policies bounded contexts. This feature applies visibility filters; it does not configure them.
- Cost tier data is available from the analytics bounded context. This feature displays it; it does not compute pricing.
- "Common failure patterns" in creator analytics is a top-3 summary of the most frequent failure reasons from the execution journal, not a free-text analysis.
- Access requests (for agents outside visibility scope) are a P3 enhancement; the initial implementation simply enforces visibility without a request-to-access flow.
