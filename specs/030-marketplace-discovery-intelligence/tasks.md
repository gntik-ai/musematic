# Tasks: Marketplace Discovery and Intelligence

**Input**: Design documents from `specs/030-marketplace-discovery-intelligence/`  
**Feature**: 030-marketplace-discovery-intelligence  
**Branch**: `030-marketplace-discovery-intelligence`

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US7)
- Exact file paths included in every task description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the `marketplace/` bounded context package with exception hierarchy.

- [x] T001 Create `apps/control-plane/src/platform/marketplace/__init__.py` (empty package marker)
- [x] T002 Create `apps/control-plane/src/platform/marketplace/exceptions.py` with `MarketplaceError`, `AgentNotFoundError`, `VisibilityDeniedError`, `InvocationRequiredError`, `ComparisonRangeError` exception classes (all extend `PlatformError` from `common/exceptions.py`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data layer shared by all user stories — models, schemas, migration, repository, events, DI.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T003 Create `apps/control-plane/src/platform/marketplace/models.py` with four SQLAlchemy async models: `MarketplaceAgentRating` (UUID, user_id FK, agent_id, score 1–5 CHECK, review_text, unique on user+agent), `MarketplaceQualityAggregate` (UUID, agent_id unique, has_data bool, execution counters, quality score sum/count, satisfaction sum/count, certification_status, staleness timestamps), `MarketplaceRecommendation` (UUID, user_id FK, agent_id, agent_fqn, recommendation_type, score, reasoning, expires_at), `MarketplaceTrendingSnapshot` (UUID, snapshot_date, agent_id, agent_fqn, trending_score, growth_rate, invocations_this_week/last_week, trending_reason, satisfaction_delta, rank, unique on date+agent)
- [x] T004 [P] Create `apps/control-plane/src/platform/marketplace/schemas.py` with all Pydantic v2 schemas: `MarketplaceSearchRequest`, `MarketplaceSearchResponse`, `AgentListingProjection`, `QualityProfileSchema`, `AggregateRatingSchema`, `AgentComparisonRequest`, `AgentComparisonResponse`, `AgentComparisonRow`, `ComparisonAttribute`, `RatingCreateRequest`, `RatingResponse`, `RatingsListResponse`, `CreatorAnalyticsResponse`, `FailurePatternEntry`, `InvocationTrendPoint`, `RecommendationResponse`, `RecommendedAgentEntry`, `ContextualSuggestionRequest`, `ContextualSuggestionResponse`, `TrendingAgentsResponse`, `TrendingAgentEntry`
- [x] T005 Create `apps/control-plane/migrations/versions/030_marketplace_schema.py` Alembic migration creating all 4 tables with correct indices, constraints, and check constraints (score 1–5, unique on user+agent, unique on snapshot_date+agent)
- [x] T006 [P] Create `apps/control-plane/src/platform/marketplace/repository.py` with async repository methods: `upsert_rating()` (ON CONFLICT DO UPDATE), `get_or_create_quality_aggregate()`, `update_quality_aggregate()`, `bulk_replace_recommendations()` (delete all for user then bulk insert), `insert_trending_snapshot()`, `get_latest_trending_snapshot()`, `get_recommendations_for_user()`, `get_ratings_for_agent()` (paginated, score filter, recency sort)
- [x] T007 [P] Create `apps/control-plane/src/platform/marketplace/events.py` with async Kafka producer helpers for `marketplace.events` topic: `emit_rating_created()`, `emit_rating_updated()`, `emit_trending_updated()` — all using the canonical `EventEnvelope` from `common/events/envelope.py`, key=agent_id
- [x] T008 [P] Create `apps/control-plane/src/platform/marketplace/dependencies.py` with FastAPI DI functions: `get_search_service()`, `get_rating_service()`, `get_recommendation_service()`, `get_trending_service()`, `get_quality_service()` — each injecting the required store clients (AsyncOpenSearch, QdrantClient, AsyncClickHouseClient, AsyncRedis) from `common/dependencies.py`

**Checkpoint**: Foundation ready — all user story phases can now proceed.

---

## Phase 3: User Story 1 — Agent Search and Filtering (Priority: P1) 🎯 MVP

**Goal**: Users can search agents using natural language, receive RRF-fused keyword+semantic results, and narrow by faceted filters. Workspace visibility enforced on every query.

**Independent Test**: `POST /marketplace/search {"query": "analyze financial reports"}` → returns agents with finance capabilities (including semantic-only matches). `POST /marketplace/search {"query": ""}` → returns agents sorted by popularity. Apply `maturity_level_min=2` filter → only level 2+ agents returned. Agent outside user visibility scope never appears in any result.

- [x] T009 [P] [US1] Write `apps/control-plane/tests/unit/marketplace/test_rrf_fusion.py` — unit tests for RRF score formula (`score=Σ1/(60+rank)`), merge of two ranked lists with overlap and without overlap, correct ordering of merged results, edge case where agent appears in only one source
- [x] T010 [P] [US1] Write `apps/control-plane/tests/integration/marketplace/test_search.py` — integration tests for search scenarios 1–5 from quickstart.md: keyword match, semantic-only match (zero keyword overlap), visibility enforcement (agent outside scope absent), faceted filter narrowing (maturity + trust tier), empty-query popularity browse
- [x] T011 [US1] Implement OpenSearch BM25 query builder in `apps/control-plane/src/platform/marketplace/search_service.py`: `_build_opensearch_query()` method — `multi_match` query across `name`, `description`, `capabilities`, `tags` fields; workspace visibility `filter` clause using allowed FQN patterns from `WorkspaceService.get_visibility_config()`; facet filter clauses for tags (terms), capabilities (terms), maturity_level (range), trust_tier (term), certification_status (term), cost_tier (term); size=50 for RRF candidate pool
- [x] T012 [US1] Implement Qdrant semantic query builder in `apps/control-plane/src/platform/marketplace/search_service.py`: `_build_qdrant_query()` method — call httpx async POST to embedding API to vectorize query string, then `qdrant_client.search()` on `agent_embeddings` collection with cosine similarity, workspace visibility payload filter (FQN pattern match), facet payload filters, limit=50
- [x] T013 [US1] Implement RRF merge + AgentListingProjection assembly in `apps/control-plane/src/platform/marketplace/search_service.py`: `_rrf_merge()` method — union of agent_ids from both sources, compute `score=Σ1/(60+rank_i)` (rank N+1 for absent source), sort descending, page-slice; `_assemble_listing()` method — combine OpenSearch document fields with `MarketplaceQualityAggregate` row (from repository) and ratings aggregate (COUNT + AVG from `marketplace_agent_ratings`)
- [x] T014 [US1] Implement `MarketplaceSearchService.search()` orchestrator and `get_listing()` + empty-query browse path in `apps/control-plane/src/platform/marketplace/search_service.py`: `search()` — parallel `asyncio.gather` of OpenSearch + Qdrant calls (skip Qdrant for empty query), RRF merge, assemble projections, paginate; `get_listing()` — fetch single agent from OpenSearch by agent_id + quality aggregate + rating aggregate; empty-query path uses OpenSearch `match_all` sorted by `invocation_count_30d` desc
- [x] T015 [US1] Implement `GET /marketplace/agents/{agent_id}` and `POST /marketplace/search` endpoints in `apps/control-plane/src/platform/marketplace/router.py`: inject workspace_id from JWT, call service methods, handle `AgentNotFoundError` → 404, `VisibilityDeniedError` → 403, return paginated `MarketplaceSearchResponse`
- [x] T016 [US1] Implement `apps/control-plane/src/platform/marketplace/router.py` endpoint `GET /marketplace/agents/{agent_id}` returning single `AgentListingProjection`, calling `search_service.get_listing()`, handling 403/404 cases

**Checkpoint**: User Story 1 fully functional — search, semantic match, visibility filter, facet filter, and browse all work.

---

## Phase 4: User Story 2 — Agent Comparison (Priority: P1)

**Goal**: Users select 2–4 agents and see a side-by-side comparison table with visual difference highlighting.

**Independent Test**: `GET /marketplace/compare?agent_ids=id1,id2,id3` → comparison table with all 8 attributes and `differs=true` on differing fields. `GET /marketplace/compare?agent_ids=id1` → 400. `GET /marketplace/compare?agent_ids=id1,id2,id3,id4,id5` → 400.

- [x] T017 [P] [US2] Write `apps/control-plane/tests/integration/marketplace/test_comparison.py` — integration tests for scenarios 6–7: 3-agent comparison with correct `differs=true`/`false` per attribute, validation rejection for 1 agent and 5 agents with correct error codes
- [x] T018 [US2] Implement `MarketplaceSearchService.compare()` in `apps/control-plane/src/platform/marketplace/search_service.py`: validate `len(agent_ids)` in [2,4] → raise `ComparisonRangeError` if not; fetch `AgentListingProjection` for each agent_id in parallel via `asyncio.gather(get_listing(id) for id in agent_ids)`; for each of 8 attributes (capabilities, maturity_level, trust_tier, certification_status, quality_score_avg, cost_tier, success_rate, user_rating_avg) compute `differs = len(set(str(v) for v in values)) > 1`; return `AgentComparisonResponse`
- [x] T019 [US2] Implement `GET /marketplace/compare` endpoint in `apps/control-plane/src/platform/marketplace/router.py`: parse comma-separated `agent_ids` query param as `list[UUID]`, call `search_service.compare()`, handle `ComparisonRangeError` → 400 with `{"error":"COMPARISON_RANGE_INVALID","message":"Please select between 2 and 4 agents to compare.","provided":<count>}`

**Checkpoint**: User Story 2 fully functional — comparison view with difference highlighting and range validation work.

---

## Phase 5: User Story 3 — Quality Signal Aggregation (Priority: P1)

**Goal**: Each agent listing shows an accurate quality profile aggregated from Kafka events (executions, evaluations, trust certification). "No data yet" shown for agents with no history. Stale data indicated when upstream unavailable.

**Independent Test**: Inject 100 `step.completed` + 5 `step.failed` events → `GET /quality` returns `success_rate=0.952`. Inject 0 events → returns `has_data=false, success_rate=null`. Set `source_unavailable_since` → returns `source_unavailable=true` with `last_updated_at`.

- [x] T020 [P] [US3] Write `apps/control-plane/tests/unit/marketplace/test_quality_aggregate.py` — unit tests for `MarketplaceQualityAggregate` computed properties: `success_rate` from (95 success / 100 execution = 0.95), `self_correction_rate` from counters, `quality_score_avg` from sum/count, `satisfaction_avg` from sum/count, division-by-zero safety (all return 0.0 not ZeroDivisionError when execution_count=0)
- [x] T021 [P] [US3] Write `apps/control-plane/tests/integration/marketplace/test_quality_signals.py` — integration tests for scenarios 8–10: quality profile with execution history (success_rate, self_correction_rate, quality_score_avg computed correctly), no-data case (has_data=false, all metrics null), stale data case (source_unavailable=true, last_updated_at from past)
- [x] T022 [US3] Implement `MarketplaceQualityAggregateService.handle_execution_event()` in `apps/control-plane/src/platform/marketplace/quality_service.py`: parse event dict for `event_type` in {`step.completed`, `step.failed`, `step.self_corrected`}; call `repository.get_or_create_quality_aggregate(agent_id)`; increment appropriate counter (`success_count`, `failure_count`, `self_correction_count`, `execution_count`); set `has_data=True` and update `data_source_last_updated_at`; call `repository.update_quality_aggregate()`; clear `source_unavailable_since` if set
- [x] T023 [US3] Implement `handle_evaluation_event()` and `handle_trust_event()` and `update_satisfaction_aggregate()` in `apps/control-plane/src/platform/marketplace/quality_service.py`: `handle_evaluation_event()` — parse `evaluation.scored` event, update `quality_score_sum += score` and `quality_score_count += 1`; `handle_trust_event()` — parse `certification.status_changed`, set `certification_status`; `update_satisfaction_aggregate()` — called after rating upsert: `SELECT AVG(score), COUNT(*) FROM marketplace_agent_ratings WHERE agent_id=:id` → update `satisfaction_sum` and `satisfaction_count` in quality aggregate
- [x] T024 [US3] Implement `GET /api/v1/marketplace/agents/{agent_id}/quality` endpoint in `apps/control-plane/src/platform/marketplace/router.py`: call `repository.get_or_create_quality_aggregate(agent_id)`, serialize to `QualityProfileSchema` (return `null` for all metric fields when `has_data=False`, set `source_unavailable=True` when `source_unavailable_since` is set), handle visibility check via `search_service.get_listing()` to confirm agent is in user's scope
- [x] T025 [US3] Register three Kafka consumers in `apps/control-plane/entrypoints/worker_main.py` using `common/events/consumer.py`: consumer for `workflow.runtime` topic → `quality_service.handle_execution_event()`, consumer for `evaluation.events` topic → `quality_service.handle_evaluation_event()`, consumer for `trust.events` topic → `quality_service.handle_trust_event()`

**Checkpoint**: User Story 3 fully functional — quality signals aggregated from Kafka, "no data yet" and stale data handling work.

---

## Phase 6: User Story 4 — Intelligent Recommendations (Priority: P2)

**Goal**: Users see personalized recommendations via collaborative filtering (daily batch), content-based (on-demand via Qdrant centroid), and fallback to popularity. At least 2 non-previously-used agents recommended in 80% of cases.

**Independent Test**: User A with 5 finance-domain invocations → CF recommendations include finance agents not yet used. New user with no invocations → fallback recommendations with `recommendation_type="fallback"`.

- [x] T026 [P] [US4] Write `apps/control-plane/tests/unit/marketplace/test_cf_recommendations.py` — unit tests for CF algorithm: cosine similarity between user-agent vectors, top-K selection excluding already-used agents, minimum similar-users threshold (< 5 → fallback), correct CF score ordering
- [x] T027 [P] [US4] Write `apps/control-plane/tests/integration/marketplace/test_recommendations.py` — integration tests for scenarios 11–12: personalized recommendations for finance-domain user (CF rows in DB → response includes CF agents), new user fallback (no CF rows → returns popularity-based with `recommendation_type="fallback"`)
- [x] T028 [US4] Implement `_get_content_based()` in `apps/control-plane/src/platform/marketplace/recommendation_service.py`: query ClickHouse `usage_events` for user's last 10 distinct agent invocations → fetch their embedding vectors from Qdrant by payload filter on agent_id → compute centroid (mean of vectors) → `qdrant_client.search()` with centroid vector, exclude already-used agent_ids, apply workspace visibility filter, limit=10; cache result in Redis key `rec:content:{user_id}` (JSON, TTL 6h) and skip recompute if cache hit
- [x] T029 [US4] Implement `run_cf_recommendations()` APScheduler job in `apps/control-plane/src/platform/marketplace/jobs.py`: query ClickHouse `usage_events` last 30 days for all `(user_id, agent_fqn, invocation_count)` tuples; build user-agent invocation matrix; compute item-based cosine similarity; for each user, find top-50 similar agents not yet invoked by that user; score = cosine_similarity weighted by co-usage count; `repository.bulk_replace_recommendations()` with `recommendation_type="collaborative"`, `expires_at=now()+24h`; schedule in APScheduler with `CronTrigger(hour=2, minute=0)` UTC
- [x] T030 [US4] Implement `get_recommendations()` in `apps/control-plane/src/platform/marketplace/recommendation_service.py`: (1) load `marketplace_recommendations` for user where `recommendation_type="collaborative"` and `expires_at > now()` and agent not in user's invocation history; (2) if result < 2 non-used agents → call `_get_content_based()`; (3) if still < 2 → fallback: query OpenSearch for top agents by `invocation_count_30d` in user's visibility scope; (4) fetch `AgentListingProjection` for each recommended agent; return `RecommendationResponse` with correct `recommendation_type` ("personalized" or "fallback")
- [x] T031 [US4] Implement `RecommendedAgentEntry` assembly in `apps/control-plane/src/platform/marketplace/recommendation_service.py`: `_build_recommended_entry()` — for each recommended agent_id, call `search_service.get_listing()` and combine with score + reasoning + recommendation_type into `RecommendedAgentEntry`
- [x] T032 [US4] Implement `GET /api/v1/marketplace/recommendations` endpoint in `apps/control-plane/src/platform/marketplace/router.py`: extract workspace_id from JWT, accept `limit` query param (default 10, max 20), call `recommendation_service.get_recommendations()`, return `RecommendationResponse`

**Checkpoint**: User Story 4 fully functional — personalized recommendations (CF + content-based + fallback) all work.

---

## Phase 7: User Story 5 — Agent Ratings and Reviews (Priority: P2)

**Goal**: Users who have invoked an agent can submit/update a rating (1–5) + review text. Aggregate shown on listing. Creator analytics available to namespace owner.

**Independent Test**: POST rating after invocation → 201 + `GET /quality` updates `satisfaction_avg` within 5s. POST rating without invocation → 403. POST second rating → 200 + aggregate count unchanged. Filter reviews by `score=5` → only 5-star reviews returned. Creator analytics returns invocation trend + failure patterns.

- [x] T033 [P] [US5] Write `apps/control-plane/tests/integration/marketplace/test_ratings.py` — integration tests for scenarios 15–18: submit rating with prior invocation (mock ClickHouse returns count>0 → 201), reject rating without invocation (mock ClickHouse returns count=0 → 403 INVOCATION_REQUIRED), update existing rating (upsert returns 200, aggregate count unchanged), filter reviews by score=5 (only 5-star reviews in response)
- [x] T034 [P] [US5] Write `apps/control-plane/tests/integration/marketplace/test_creator_analytics.py` — integration test for scenario 20: namespace owner request → returns correct invocation counts + top-3 failure patterns + 30-day trend; non-owner request → 403
- [x] T035 [US5] Implement `MarketplaceRatingService.upsert_rating()` in `apps/control-plane/src/platform/marketplace/rating_service.py`: (1) query ClickHouse `usage_events` for `COUNT(*) WHERE user_id=:uid AND agent_id=:aid` → if 0, raise `InvocationRequiredError`; (2) `repository.upsert_rating()` (INSERT ... ON CONFLICT (user_id, agent_id) DO UPDATE SET score=EXCLUDED.score, review_text=EXCLUDED.review_text, updated_at=now()); (3) detect created-vs-updated from `pgresult.rowcount` or `created_at == updated_at`; (4) call `quality_service.update_satisfaction_aggregate(agent_id)`; (5) emit `emit_rating_created()` or `emit_rating_updated()` Kafka event; return `RatingResponse`
- [x] T036 [US5] Implement `list_ratings()` in `apps/control-plane/src/platform/marketplace/rating_service.py`: SELECT from `marketplace_agent_ratings` WHERE `agent_id=:aid` AND (if score filter) `score=:score`, ORDER BY `updated_at DESC` (recency) or `score DESC` (highest) or `score ASC` (lowest), paginated with LIMIT/OFFSET; compute `avg_score = SELECT AVG(score) FROM marketplace_agent_ratings WHERE agent_id=:aid`; return `RatingsListResponse`
- [x] T037 [US5] Implement `get_creator_analytics()` in `apps/control-plane/src/platform/marketplace/rating_service.py`: (1) verify namespace ownership — call `RegistryService.get_agent_namespace_owner(agent_id)` in-process; if `requesting_user_id` is not owner, raise `VisibilityDeniedError`; (2) query ClickHouse for `invocation_count_total` (all time) and `invocation_count_30d` (last 30 days); (3) query ClickHouse for top-3 `error_type` by count where `status='failed'` last 30 days → `FailurePatternEntry` list with percentages; (4) query ClickHouse for daily invocation counts last 30 days → `InvocationTrendPoint` list; (5) read `satisfaction_avg` + `satisfaction_count` from `MarketplaceQualityAggregate`; return `CreatorAnalyticsResponse`
- [x] T038 [US5] Implement three rating endpoints in `apps/control-plane/src/platform/marketplace/router.py`: `POST /agents/{agent_id}/ratings` (return 201 on create, 200 on update, 403 on `InvocationRequiredError`, 422 on validation), `GET /agents/{agent_id}/ratings` (accept `score` + `sort` query params), `GET /analytics/{agent_id}` (403 on non-owner)

**Checkpoint**: User Story 5 fully functional — rating submission with invocation gate, filtering, aggregate update, and creator analytics all work.

---

## Phase 8: User Story 6 — Contextual Discovery Suggestions (Priority: P3)

**Goal**: Workbenches call `POST /marketplace/contextual-suggestions` with a context string; the API returns relevant agents or an empty list with `has_results=false`.

**Independent Test**: POST with `context_type="workflow_step"` + `context_text="sentiment analysis"` → agents with NLP capabilities returned, `has_results=true`. POST with `context_text="quantum teleportation"` → `{"suggestions":[], "has_results":false}`.

- [x] T039 [P] [US6] Write `apps/control-plane/tests/integration/marketplace/test_contextual_discovery.py` — integration tests for scenarios 13–14 extended: all 3 `context_type` values (workflow_step, conversation, fleet_config) each return relevant agents; no-match case returns `has_results=false` (not 404); visibility filter still applied (agents outside scope absent even if semantically relevant)
- [x] T040 [US6] Implement `MarketplaceRecommendationService.get_contextual_suggestions()` in `apps/control-plane/src/platform/marketplace/recommendation_service.py`: validate `context_type` in `{"workflow_step", "conversation", "fleet_config"}` → raise `MarketplaceError` if unknown; embed `context_text` via httpx call to embedding API (same endpoint as search_service); Qdrant kNN search on `agent_embeddings` collection with visibility payload filter + limit=`max_results`; if no results → return `ContextualSuggestionResponse(suggestions=[], has_results=False)`; else assemble `AgentListingProjection` list via `search_service._assemble_listing()` and return with `has_results=True`
- [x] T041 [US6] Implement `POST /api/v1/marketplace/contextual-suggestions` endpoint in `apps/control-plane/src/platform/marketplace/router.py`: call `recommendation_service.get_contextual_suggestions()`, return `ContextualSuggestionResponse`

**Checkpoint**: User Story 6 fully functional — contextual discovery works for all 3 context types, empty state handled.

---

## Phase 9: User Story 7 — Trending Agents (Priority: P3)

**Goal**: Daily trending snapshot computed from 7-day invocation growth ratio. Trending list shows growth rate + trending reason. Only agents with ≥5 invocations this week qualify.

**Independent Test**: After running `run_trending_computation()` with Agent X (50 invocations this week, 5 last week) → Agent X appears in trending with `trending_reason="10x more invocations this week"`. Agent Y (1000 total, flat) → absent. `GET /marketplace/trending` returns today's snapshot with visibility filter applied.

- [x] T042 [P] [US7] Write `apps/control-plane/tests/unit/marketplace/test_trending_computation.py` — unit tests for trending algorithm: `growth_rate = invocations_this_week / max(invocations_last_week, 1)`, minimum threshold filter (invocations_this_week < 5 → excluded), `trending_reason` string formatting ("Nx more invocations this week"), ranking by growth_rate descending, top-20 cap
- [x] T043 [P] [US7] Write `apps/control-plane/tests/integration/marketplace/test_trending.py` — integration test for scenario 19: after `run_trending_computation()` with Agent X (10x growth) and Agent Y (flat), GET /trending returns Agent X with correct trending_reason, Agent Y absent; visibility filter test (trending agent outside user scope not returned)
- [x] T044 [US7] Implement `run_trending_computation()` APScheduler job in `apps/control-plane/src/platform/marketplace/jobs.py`: query ClickHouse for all agents' invocation counts in last 7 days (this_week) and 8–14 days ago (last_week); filter `invocations_this_week >= 5`; compute `growth_rate = invocations_this_week / max(invocations_last_week, 1)`; compute `satisfaction_delta = avg_score_this_week - avg_score_last_week` from quality aggregates; rank top-20 by growth_rate; generate `trending_reason = f"{round(growth_rate)}x more invocations this week"`; bulk insert `MarketplaceTrendingSnapshot` rows for today's date (delete today's rows first); cache JSON in Redis `marketplace:trending:latest` (TTL 25h); schedule with `CronTrigger(hour=3, minute=0)` UTC
- [x] T045 [US7] Implement `MarketplaceTrendingService.get_trending()` in `apps/control-plane/src/platform/marketplace/trending_service.py`: check Redis cache `marketplace:trending:latest` → if hit, deserialize and apply visibility filter; else query `marketplace_trending_snapshots` for most recent `snapshot_date`, fetch rows ordered by rank; for each row, call `search_service.get_listing()` to check visibility (skip agents outside user's scope); assemble `TrendingAgentEntry` list; return `TrendingAgentsResponse` with `snapshot_date` and `total`
- [x] T046 [US7] Implement `GET /api/v1/marketplace/trending` endpoint in `apps/control-plane/src/platform/marketplace/router.py`: extract workspace_id from JWT, accept `limit` (max 20), call `trending_service.get_trending()`, return `TrendingAgentsResponse`

**Checkpoint**: User Story 7 fully functional — trending computation, snapshot storage, and visibility-filtered trending API work.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Wire the bounded context into the platform, register background jobs and event consumers, enforce coverage and linting.

- [x] T047 [P] Create `apps/control-plane/tests/integration/marketplace/conftest.py` with pytest fixtures: `mock_opensearch_client` (AsyncMock returning fixture agent docs), `mock_qdrant_client` (AsyncMock returning fixture scored points), `mock_clickhouse_client` (AsyncMock returning fixture usage rows), `mock_workspace_service` (AsyncMock returning test FQN allowlist), `sample_quality_aggregate` (MarketplaceQualityAggregate factory), `sample_agent_rating` (MarketplaceAgentRating factory)
- [x] T048 Register `marketplace.router` in `apps/control-plane/src/platform/main.py`: `app.include_router(marketplace_router, prefix="/api/v1/marketplace", tags=["marketplace"])`
- [x] T049 [P] Register APScheduler jobs in `apps/control-plane/entrypoints/worker_main.py`: add `scheduler.add_job(run_cf_recommendations, CronTrigger(hour=2, minute=0, timezone="UTC"), id="marketplace_cf_recs", replace_existing=True)` and `scheduler.add_job(run_trending_computation, CronTrigger(hour=3, minute=0, timezone="UTC"), id="marketplace_trending", replace_existing=True)`
- [x] T050 [P] Register Kafka consumers in `apps/control-plane/entrypoints/worker_main.py` (alongside existing consumers): consumer group `marketplace-quality-signals` consuming `workflow.runtime` → `quality_service.handle_execution_event`, `evaluation.events` → `quality_service.handle_evaluation_event`, `trust.events` → `quality_service.handle_trust_event`
- [x] T051 [P] Validate test coverage ≥95%: run `pytest apps/control-plane/tests/unit/marketplace/ apps/control-plane/tests/integration/marketplace/ --cov=apps/control-plane/src/platform/marketplace --cov-fail-under=95 --cov-report=term-missing`
- [x] T052 [P] Run `ruff check apps/control-plane/src/platform/marketplace/` and fix all linting violations; run `ruff format apps/control-plane/src/platform/marketplace/` for consistent formatting
- [x] T053 [P] Run `mypy --strict apps/control-plane/src/platform/marketplace/` and fix all type errors; ensure all async methods have explicit return type annotations

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user stories**
- **US1 Search+Filtering (Phase 3)**: Depends on Foundational only — no story dependencies
- **US2 Comparison (Phase 4)**: Depends on Foundational + US1 (reuses `search_service` listing fetch)
- **US3 Quality Signals (Phase 5)**: Depends on Foundational only — independent of US1/US2
- **US4 Recommendations (Phase 6)**: Depends on Foundational + US1 (needs `get_listing()` for assembly)
- **US5 Ratings and Reviews (Phase 7)**: Depends on Foundational + US3 (calls `update_satisfaction_aggregate`)
- **US6 Contextual Discovery (Phase 8)**: Depends on US4 (reuses `search_service._assemble_listing()`)
- **US7 Trending (Phase 9)**: Depends on Foundational + US1 (visibility filtering via `get_listing()`)
- **Polish (Phase 10)**: Depends on all user story phases

### User Story Independence Summary

| Story | Can Start After | Integrates With |
|---|---|---|
| US1 Search+Filtering | Foundational | — |
| US2 Comparison | Foundational | US1 (`get_listing()`) |
| US3 Quality Signals | Foundational | — |
| US4 Recommendations | Foundational + US1 | US1 (`get_listing()`) |
| US5 Ratings+Reviews | Foundational + US3 | US3 (`update_satisfaction_aggregate`) |
| US6 Contextual Discovery | US4 | US4 (`recommendation_service`) |
| US7 Trending | Foundational + US1 | US1 (`get_listing()`) |

### Within Each User Story

- Tests (marked [P]) written before/alongside implementation
- Models/schemas before services
- Services before endpoints
- Story complete before moving to next priority

### Parallel Opportunities

- T004 (schemas), T006 (repository), T007 (events), T008 (dependencies) — all [P] within Phase 2
- T009+T010 (tests for US1) — parallel with T011+T012+T013+T014 (implementation)
- T017 (comparison tests) + T018 (compare() service) are independent files
- T020+T021 (US3 tests) run in parallel
- T026+T027 (US4 tests) run in parallel
- T033+T034 (US5 tests) run in parallel
- T042+T043 (US7 tests) run in parallel
- T047, T049, T050, T051, T052, T053 — all [P] in Phase 10

---

## Parallel Execution Examples

### Phase 2 — Foundational

```bash
# These 4 tasks can all run simultaneously:
Task T004: "Create schemas.py with all Pydantic schemas"
Task T006: "Create repository.py with async CRUD methods"
Task T007: "Create events.py with Kafka producer helpers"
Task T008: "Create dependencies.py with FastAPI DI"
```

### Phase 3 — User Story 1

```bash
# Tests and implementation can start in parallel (different files):
Task T009: "Write test_rrf_fusion.py — RRF unit tests"
Task T010: "Write test_search.py — search integration tests"
Task T011: "Implement OpenSearch BM25 query builder in search_service.py"
Task T012: "Implement Qdrant semantic query builder in search_service.py"
# T013/T014/T015/T016 depend on T011/T012 completing first
```

### Phase 10 — Polish

```bash
# All can run simultaneously (different files/checks):
Task T047: "Create integration test conftest.py fixtures"
Task T049: "Register APScheduler jobs in worker_main.py"
Task T050: "Register Kafka consumers in worker_main.py"
Task T051: "Validate test coverage ≥95%"
Task T052: "ruff check + format"
Task T053: "mypy --strict"
```

---

## Implementation Strategy

### MVP First (User Stories 1–3 Only)

1. Complete Phase 1: Setup (T001–T002)
2. Complete Phase 2: Foundational (T003–T008) — **critical blocker**
3. Complete Phase 3: US1 Search+Filtering (T009–T016)
4. Complete Phase 4: US2 Comparison (T017–T019)
5. Complete Phase 5: US3 Quality Signals (T020–T025)
6. **STOP and VALIDATE**: all three P1 stories work end-to-end
7. Run `POST /search`, `GET /compare`, `GET /quality` in a running environment

### Full Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → semantic + keyword search working → marketplace browse usable
3. US2 → comparison view → decision-making enabled
4. US3 → quality profiles → trust signals visible
5. US4 → recommendations → personalized discovery working
6. US5 → ratings+reviews + creator analytics → feedback loop active
7. US6 → contextual suggestions → workbench integration
8. US7 → trending → discovery of rising agents

### Parallel Team Strategy

With 3 developers after Foundational completes:
- **Dev A**: US1 Search+Filtering → US2 Comparison (sequential, US2 reuses search_service)
- **Dev B**: US3 Quality Signals → US5 Ratings+Reviews (sequential, US5 calls quality_service)
- **Dev C**: US4 Recommendations → US6 Contextual Discovery → US7 Trending (sequential)

---

## Notes

- `[P]` tasks operate on distinct files — no merge conflicts when parallelized
- Each user story phase produces a testable API surface before the next begins
- US2/US4/US7 all depend on `search_service.get_listing()` from US1 — complete US1 first
- Quality aggregate computed properties (`success_rate`, etc.) live as Python `@property` on the SQLAlchemy model, not as stored columns — avoids stale computed columns
- ClickHouse invocation gate in T035 is the only place where cross-context data is read; use `common/clients/clickhouse.py` wrapper, never raw SQL strings
- All Kafka consumer registrations in Phase 2/10 use consumer group name `marketplace-quality-signals` to prevent duplicate processing across worker instances
- Commit after each task or logical group; each phase checkpoint is a clean commit point
