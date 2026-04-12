# Implementation Plan: Marketplace Discovery and Intelligence

**Branch**: `030-marketplace-discovery-intelligence` | **Date**: 2026-04-12 | **Spec**: [spec.md](./spec.md)  
**Input**: Feature specification from `specs/030-marketplace-discovery-intelligence/spec.md`

## Summary

Implement the `marketplace/` bounded context providing agent discovery, search orchestration, quality signal aggregation, recommendations, ratings/reviews, contextual discovery, and trending. Search combines OpenSearch BM25 keyword matching with Qdrant semantic similarity using reciprocal rank fusion. Quality signals are aggregated from Kafka events (`workflow.runtime`, `evaluation.events`, `trust.events`). Recommendations run as daily APScheduler jobs (collaborative filtering via ClickHouse usage data) plus on-demand content-based + contextual search. Agent ratings enforce the invocation gate via ClickHouse query before accepting submissions.

## Technical Context

**Language/Version**: Python 3.12+  
**Primary Dependencies**: FastAPI 0.115+, Pydantic v2, SQLAlchemy 2.x async, aiokafka 0.11+, opensearch-py 2.x (async), qdrant-client 1.12+ (async gRPC), clickhouse-connect 0.8+, redis-py 5.x async, httpx 0.27+, APScheduler 3.x  
**Storage**: PostgreSQL (4 tables: ratings, quality aggregates, recommendations, trending snapshots) + OpenSearch (marketplace-agents index, owned by feature 021) + Qdrant (agent_embeddings, owned by feature 021) + ClickHouse (usage_events, read-only) + Redis (recommendation cache TTL 6h, trending cache TTL 25h)  
**Testing**: pytest + pytest-asyncio 8.x  
**Target Platform**: Linux server (Kubernetes, `api` + `worker` runtime profiles)  
**Project Type**: Bounded context within Python modular monolith  
**Performance Goals**: Search results < 1s (SC-003); comparison view < 1s (SC-004); quality aggregates within 5 minutes of upstream event (SC-005); ratings visible within 5s of submission (SC-009); creator analytics < 2s (SC-010)  
**Constraints**: Zero visibility leakage (SC-011); 95% test coverage (SC-012)  
**Scale/Scope**: 28 FRs, 7 user stories, 4 PostgreSQL tables, 15 REST endpoints

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| Gate | Principle | Status | Notes |
|---|---|---|---|
| G-I | Modular monolith — single Python codebase | PASS | `marketplace/` is one bounded context within `apps/control-plane/src/platform/` |
| G-III-OpenSearch | Full-text search uses OpenSearch, not PostgreSQL FTS | PASS | All keyword search via opensearch-py async client; PG FTS never used |
| G-III-Qdrant | Vector operations use Qdrant, not PostgreSQL | PASS | All semantic search and embedding kNN via qdrant-client |
| G-III-ClickHouse | Analytics/aggregations from ClickHouse | PASS | Invocation counts, creator analytics, CF usage data all from ClickHouse |
| G-III-Redis | Caching via Redis, not in-memory | PASS | Content-based rec cache `rec:content:{user_id}` + trending `marketplace:trending:latest` in Redis |
| G-III-Kafka | Async event coordination via Kafka | PASS | Quality aggregation via Kafka consumers on `workflow.runtime`, `evaluation.events`, `trust.events` |
| G-IV | No cross-boundary DB access | PASS | Feature 021 agent profiles queried via OpenSearch + Qdrant (read projections), not PostgreSQL tables; ClickHouse queried read-only |
| G-IX | Zero-trust visibility | PASS | All search, browse, trending, comparison, recommendations filter by workspace visibility FQN patterns — no agent returned outside user's scope |
| G-VI | Policy is machine-enforced | PASS | Ratings invocation gate: ClickHouse check enforced in service layer before write; visibility filter enforced in every query |
| G-XI | Secrets not in LLM context window | N/A | No LLM context windows in this feature |
| G-XII | TaskPlanRecord | N/A | No agent execution dispatch in this feature |

**All applicable gates PASS.** No constitution violations.

## Project Structure

### Documentation (this feature)

```text
specs/030-marketplace-discovery-intelligence/
├── plan.md              # This file
├── research.md          # Phase 0 output — 14 decisions
├── data-model.md        # Phase 1 output — 4 PG tables, Pydantic schemas, service signatures
├── quickstart.md        # Phase 1 output — 20 test scenarios
├── contracts/
│   └── marketplace-api.md   # Phase 1 output — 15 REST endpoints + Kafka contracts
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code

```text
apps/control-plane/src/platform/marketplace/
├── __init__.py
├── models.py              # SQLAlchemy: MarketplaceAgentRating, MarketplaceQualityAggregate,
│                          #   MarketplaceRecommendation, MarketplaceTrendingSnapshot
├── schemas.py             # Pydantic: all request/response schemas
├── repository.py          # Async CRUD: ratings upsert, quality aggregate update,
│                          #   recommendations bulk replace, trending snapshot insert
├── search_service.py      # MarketplaceSearchService: OpenSearch + Qdrant + RRF fusion
├── rating_service.py      # MarketplaceRatingService: upsert, list, analytics
├── recommendation_service.py  # MarketplaceRecommendationService: CF + content-based + contextual
├── trending_service.py    # MarketplaceTrendingService: read trending snapshots
├── quality_service.py     # MarketplaceQualityAggregateService: Kafka event handlers
├── jobs.py                # APScheduler jobs: run_cf_recommendations(), run_trending_computation()
├── events.py              # Kafka producer: marketplace.events topic
├── router.py              # FastAPI router: 15 REST endpoints
├── exceptions.py          # MarketplaceError, AgentNotFoundError, InvocationRequiredError,
│                          #   ComparisonRangeError, VisibilityDeniedError
└── dependencies.py        # FastAPI DI: get_search_service, get_rating_service, etc.

apps/control-plane/migrations/versions/
└── 030_marketplace_schema.py  # Alembic: marketplace_agent_ratings, marketplace_quality_aggregates,
                               #   marketplace_recommendations, marketplace_trending_snapshots

apps/control-plane/tests/
├── unit/marketplace/
│   ├── test_rrf_fusion.py               # RRF algorithm unit tests
│   ├── test_quality_aggregate.py        # Quality signal computation
│   ├── test_trending_computation.py     # Trending score algorithm
│   └── test_cf_recommendations.py      # Collaborative filtering logic
└── integration/marketplace/
    ├── test_search.py                   # Search + semantic + filtering
    ├── test_comparison.py               # Comparison view
    ├── test_ratings.py                  # Rating CRUD + invocation gate
    ├── test_quality_signals.py          # Kafka consumer → aggregate
    ├── test_recommendations.py          # All recommendation paths
    ├── test_contextual_suggestions.py   # Contextual discovery
    └── test_trending.py                 # Trending snapshot + API
```

## Implementation Phases

### Phase 1 — Core Data Layer (US3: Quality Signals foundation)

**Goal**: PostgreSQL tables + Alembic migration + repository layer + Kafka event handler stubs + base exceptions

**Tasks**:
- SQLAlchemy models: `MarketplaceAgentRating`, `MarketplaceQualityAggregate`, `MarketplaceRecommendation`, `MarketplaceTrendingSnapshot`
- Alembic migration `030_marketplace_schema.py` (4 tables, indices, constraints)
- `repository.py`: CRUD methods for all 4 models
- `exceptions.py`: `MarketplaceError`, `AgentNotFoundError`, `InvocationRequiredError`, `ComparisonRangeError`, `VisibilityDeniedError`
- `schemas.py`: all Pydantic request/response schemas
- `dependencies.py`: FastAPI DI stubs

### Phase 2 — Search and Browse (US1: P1)

**Goal**: Full-text + semantic search with RRF fusion, faceted filtering, empty-query browse

**Tasks**:
- `search_service.py`: `MarketplaceSearchService.search()` — parallel OpenSearch BM25 + Qdrant kNN → RRF merge → assemble `AgentListingProjection` list
- `search_service.py`: `get_listing()` — single agent listing with quality profile
- OpenSearch client query builder with workspace visibility filter + facet filters
- Qdrant query builder with payload filters
- RRF merge algorithm: `score(d) = Σ 1/(k=60 + rank_i)`
- Empty-query path: popularity-sorted OpenSearch query
- Tests: `test_search.py` (scenarios 1-5 from quickstart.md)

### Phase 3 — Comparison View (US2: P1)

**Goal**: Side-by-side comparison of 2-4 agents with difference highlighting

**Tasks**:
- `search_service.py`: `compare()` — validate 2-4 IDs, fetch listings, compute `differs` flags
- Difference detection: for each attribute, `differs = len(set(values)) > 1`
- Tests: `test_comparison.py` (scenarios 6-7)

### Phase 4 — Quality Signal Aggregation (US3: P1)

**Goal**: Kafka consumers updating quality aggregates from upstream events

**Tasks**:
- `quality_service.py`: `MarketplaceQualityAggregateService`
  - `handle_execution_event()` — `step.completed` / `step.failed` / `step.self_corrected`
  - `handle_evaluation_event()` — `evaluation.scored`
  - `handle_trust_event()` — `certification.status_changed`
  - `update_satisfaction_aggregate()` — called after rating upsert
- `router.py`: `GET /agents/{id}/quality` endpoint
- Tests: `test_quality_signals.py` (scenarios 8-10)

### Phase 5 — Ratings and Reviews (US5: P2)

**Goal**: Rating CRUD with invocation gate + creator analytics

**Tasks**:
- `rating_service.py`: `MarketplaceRatingService`
  - `upsert_rating()` — ClickHouse invocation gate check → PostgreSQL upsert (`ON CONFLICT DO UPDATE`) → update quality aggregate → produce Kafka event
  - `list_ratings()` — paginated with score + recency filters
  - `get_creator_analytics()` — namespace ownership check → ClickHouse queries
- `events.py`: Kafka producer for `marketplace.events` topic
- `router.py`: ratings + analytics endpoints
- Tests: `test_ratings.py` (scenarios 15-20)

### Phase 6 — Recommendations (US4: P2)

**Goal**: Collaborative filtering (daily batch) + content-based (on-demand) + contextual (on-demand)

**Tasks**:
- `recommendation_service.py`: `MarketplaceRecommendationService`
  - `get_recommendations()` — read from `marketplace_recommendations` + fallback to popularity if empty/expired
  - `get_contextual_suggestions()` — embed context_text → Qdrant kNN → filter by visibility
  - `_get_content_based()` — last 10 used agents → centroid → Qdrant kNN → cache in Redis
- `jobs.py`: `run_cf_recommendations()` — daily CF batch (ClickHouse query → cosine similarity → bulk upsert)
- `router.py`: recommendations + contextual suggestions endpoints
- Tests: `test_recommendations.py`, `test_contextual_suggestions.py` (scenarios 11-14)

### Phase 7 — Trending (US7: P3)

**Goal**: Daily trending snapshot computation + API

**Tasks**:
- `jobs.py`: `run_trending_computation()` — ClickHouse query for 7d vs 14d invocations → growth ratio → top-20 → upsert `marketplace_trending_snapshots`
- `trending_service.py`: `get_trending()` — read latest snapshot, apply visibility filter, return with listing projections
- `router.py`: trending endpoint
- Tests: `test_trending.py` (scenario 19)

### Phase 8 — Polish and Integration

**Goal**: Register router, register APScheduler jobs + Kafka consumers, full coverage, ruff+mypy

**Tasks**:
- Register `marketplace.router` in `apps/control-plane/src/platform/main.py`
- Register `run_cf_recommendations` (daily 02:00 UTC) + `run_trending_computation` (daily 03:00 UTC) in scheduler entrypoint
- Register Kafka consumers (`workflow.runtime`, `evaluation.events`, `trust.events`) in worker profile
- `conftest.py` fixtures: mock OpenSearch, mock Qdrant, mock ClickHouse, mock workspace service
- Validate 95%+ test coverage
- ruff + mypy strict pass

## Complexity Tracking

No constitution violations — no entries required.
