# Data Model: Marketplace Discovery and Intelligence

**Feature**: 030-marketplace-discovery-intelligence  
**Date**: 2026-04-12

---

## PostgreSQL Tables

All tables use the standard mixins from `apps/control-plane/src/platform/common/models/mixins.py`. Column ordering: `Base` mixin first, then behavior mixins (`UUIDMixin`, `TimestampMixin`, `SoftDeleteMixin`, `AuditMixin`, `WorkspaceScopedMixin`, `EventSourcedMixin`), then concrete columns.

---

### `marketplace_agent_ratings`

User rating + optional review text for an agent. One row per (user, agent) pair — most recent wins via upsert.

```python
class MarketplaceAgentRating(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_agent_ratings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, index=True  # FK to registry_agent_profiles.id (cross-context ref, no FK constraint)
    )
    score: Mapped[int] = mapped_column(
        Integer, nullable=False  # 1-5
    )
    review_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "agent_id", name="uq_marketplace_rating_user_agent"),
        CheckConstraint("score >= 1 AND score <= 5", name="ck_marketplace_rating_score_range"),
    )
```

**Indices**: unique on `(user_id, agent_id)`, btree on `agent_id` (for aggregate queries), btree on `user_id`.

---

### `marketplace_quality_aggregates`

Pre-computed quality profile per agent, updated by Kafka consumers and rating upserts.

```python
class MarketplaceQualityAggregate(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_quality_aggregates"

    agent_id: Mapped[uuid.UUID] = mapped_column(
        nullable=False, unique=True, index=True
    )
    has_data: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Execution quality — populated from workflow.runtime + evaluation.events
    execution_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    self_correction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quality_score_sum: Mapped[float] = mapped_column(
        Numeric(precision=12, scale=4), default=0.0, nullable=False
    )
    quality_score_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Satisfaction — populated from marketplace_agent_ratings
    satisfaction_sum: Mapped[float] = mapped_column(
        Numeric(precision=12, scale=4), default=0.0, nullable=False
    )
    satisfaction_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Trust compliance — populated from trust.events
    certification_status: Mapped[str] = mapped_column(
        String(32), default="uncertified", nullable=False
    )  # "compliant" | "non_compliant" | "uncertified"

    # Staleness tracking
    data_source_last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_unavailable_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True  # set when upstream goes silent
    )
```

**Computed properties** (Python @property, not stored):
- `success_rate` = `success_count / max(execution_count, 1)`
- `self_correction_rate` = `self_correction_count / max(execution_count, 1)`
- `quality_score_avg` = `quality_score_sum / max(quality_score_count, 1)`
- `satisfaction_avg` = `satisfaction_sum / max(satisfaction_count, 1)`

---

### `marketplace_recommendations`

Pre-computed recommendation rows per user. Multiple rows per user (one per recommended agent + type).

```python
class MarketplaceRecommendation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_recommendations"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("auth_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # "collaborative" | "content_based" | "popularity_fallback"
    score: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=6), nullable=False
    )
    reasoning: Mapped[str | None] = mapped_column(String(512), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    __table_args__ = (
        Index("ix_marketplace_recommendations_user_type", "user_id", "recommendation_type"),
    )
```

**Lifecycle**: Rows are replaced (delete + bulk insert) on each recommendation refresh cycle. `expires_at` is set to 24h for collaborative/popularity and 6h for content-based.

---

### `marketplace_trending_snapshots`

Daily trending snapshot. Old snapshots retained for 30 days for historical trending UI.

```python
class MarketplaceTrendingSnapshot(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "marketplace_trending_snapshots"

    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False)
    trending_score: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=6), nullable=False
    )
    growth_rate: Mapped[float] = mapped_column(
        Numeric(precision=10, scale=4), nullable=False
    )  # invocations_this_week / invocations_last_week
    invocations_this_week: Mapped[int] = mapped_column(Integer, nullable=False)
    invocations_last_week: Mapped[int] = mapped_column(Integer, nullable=False)
    trending_reason: Mapped[str] = mapped_column(String(256), nullable=False)
    satisfaction_delta: Mapped[float | None] = mapped_column(
        Numeric(precision=6, scale=4), nullable=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-20 within snapshot

    __table_args__ = (
        UniqueConstraint("snapshot_date", "agent_id", name="uq_marketplace_trending_date_agent"),
        Index("ix_marketplace_trending_date_rank", "snapshot_date", "rank"),
    )
```

---

## Pydantic Schemas

### Listing Projection (assembled at query time, not stored)

```python
class AgentListingProjection(BaseModel):
    """Read projection assembled from OpenSearch + QualityAggregate + Ratings."""
    agent_id: UUID
    fqn: str                          # namespace:local_name
    name: str
    description: str
    capabilities: list[str]
    tags: list[str]
    maturity_level: int               # 1-5
    trust_tier: str                   # "unverified" | "community" | "certified" | "trusted"
    certification_status: str         # "compliant" | "non_compliant" | "uncertified"
    cost_tier: str                    # "free" | "metered" | "premium"
    quality_profile: QualityProfileSchema | None
    aggregate_rating: AggregateRatingSchema | None
    relevance_score: float | None     # only for search results

class QualityProfileSchema(BaseModel):
    success_rate: float | None        # None → "No data yet"
    quality_score_avg: float | None
    self_correction_rate: float | None
    satisfaction_avg: float | None
    satisfaction_count: int
    certification_compliance: str     # "compliant" | "non_compliant" | "uncertified"
    last_updated_at: datetime | None  # None if source was never available
    source_unavailable: bool          # True if source is currently down

class AggregateRatingSchema(BaseModel):
    avg_score: float | None
    review_count: int
```

### Search Request/Response

```python
class MarketplaceSearchRequest(BaseModel):
    query: str = ""
    tags: list[str] = []
    capabilities: list[str] = []
    maturity_level_min: int | None = None
    maturity_level_max: int | None = None
    trust_tier: list[str] = []
    certification_status: list[str] = []
    cost_tier: list[str] = []
    page: int = 1
    page_size: int = Field(default=20, ge=1, le=100)

class MarketplaceSearchResponse(BaseModel):
    results: list[AgentListingProjection]
    total: int
    page: int
    page_size: int
    query: str
    has_results: bool
```

### Comparison

```python
class AgentComparisonRequest(BaseModel):
    agent_ids: list[UUID] = Field(min_length=2, max_length=4)

class ComparisonAttribute(BaseModel):
    value: Any
    differs: bool  # True if not all compared agents share the same value

class AgentComparisonRow(BaseModel):
    agent_id: UUID
    fqn: str
    name: str
    capabilities: ComparisonAttribute
    maturity_level: ComparisonAttribute
    trust_tier: ComparisonAttribute
    certification_status: ComparisonAttribute
    quality_score_avg: ComparisonAttribute
    cost_tier: ComparisonAttribute
    success_rate: ComparisonAttribute
    user_rating_avg: ComparisonAttribute

class AgentComparisonResponse(BaseModel):
    agents: list[AgentComparisonRow]
    compared_count: int
```

### Ratings

```python
class RatingCreateRequest(BaseModel):
    score: int = Field(ge=1, le=5)
    review_text: str | None = None

class RatingResponse(BaseModel):
    rating_id: UUID
    agent_id: UUID
    user_id: UUID
    score: int
    review_text: str | None
    created_at: datetime
    updated_at: datetime

class RatingsListResponse(BaseModel):
    ratings: list[RatingResponse]
    total: int
    page: int
    page_size: int
    avg_score: float | None
```

### Creator Analytics

```python
class CreatorAnalyticsResponse(BaseModel):
    agent_id: UUID
    agent_fqn: str
    invocation_count_total: int
    invocation_count_30d: int
    avg_satisfaction: float | None
    satisfaction_count: int
    common_failure_patterns: list[FailurePatternEntry]  # top-3
    invocation_trend: list[InvocationTrendPoint]        # daily for last 30 days

class FailurePatternEntry(BaseModel):
    error_type: str
    count: int
    percentage: float

class InvocationTrendPoint(BaseModel):
    date: date
    count: int
```

### Recommendations

```python
class RecommendationResponse(BaseModel):
    recommendations: list[RecommendedAgentEntry]
    recommendation_type: str  # "personalized" | "fallback"

class RecommendedAgentEntry(BaseModel):
    agent: AgentListingProjection
    score: float
    reasoning: str | None
    recommendation_type: str  # "collaborative" | "content_based" | "popularity_fallback"
```

### Contextual Suggestions

```python
class ContextualSuggestionRequest(BaseModel):
    context_type: str      # "workflow_step" | "conversation" | "fleet_config"
    context_text: str
    workspace_id: UUID
    max_results: int = Field(default=5, ge=1, le=10)

class ContextualSuggestionResponse(BaseModel):
    suggestions: list[AgentListingProjection]
    has_results: bool
    context_type: str
```

### Trending

```python
class TrendingAgentsResponse(BaseModel):
    agents: list[TrendingAgentEntry]
    snapshot_date: date
    total: int

class TrendingAgentEntry(BaseModel):
    rank: int
    agent: AgentListingProjection
    trending_score: float
    growth_rate: float
    invocations_this_week: int
    invocations_last_week: int
    trending_reason: str
    satisfaction_delta: float | None
```

---

## Key Service Interfaces

```python
class MarketplaceSearchService:
    async def search(
        self,
        request: MarketplaceSearchRequest,
        workspace_id: UUID,
        user_id: UUID,
    ) -> MarketplaceSearchResponse: ...

    async def get_listing(self, agent_id: UUID, workspace_id: UUID) -> AgentListingProjection: ...

    async def compare(
        self,
        agent_ids: list[UUID],
        workspace_id: UUID,
    ) -> AgentComparisonResponse: ...


class MarketplaceRatingService:
    async def upsert_rating(
        self,
        agent_id: UUID,
        user_id: UUID,
        request: RatingCreateRequest,
    ) -> RatingResponse: ...

    async def list_ratings(
        self,
        agent_id: UUID,
        score_filter: int | None,
        sort_by_recency: bool,
        page: int,
        page_size: int,
    ) -> RatingsListResponse: ...

    async def get_creator_analytics(
        self,
        agent_id: UUID,
        requesting_user_id: UUID,
    ) -> CreatorAnalyticsResponse: ...


class MarketplaceRecommendationService:
    async def get_recommendations(
        self,
        user_id: UUID,
        workspace_id: UUID,
        limit: int = 10,
    ) -> RecommendationResponse: ...

    async def get_contextual_suggestions(
        self,
        request: ContextualSuggestionRequest,
        user_id: UUID,
    ) -> ContextualSuggestionResponse: ...


class MarketplaceTrendingService:
    async def get_trending(
        self,
        workspace_id: UUID,
        limit: int = 20,
    ) -> TrendingAgentsResponse: ...


class MarketplaceQualityAggregateService:
    async def handle_execution_event(self, event: dict) -> None: ...
    async def handle_evaluation_event(self, event: dict) -> None: ...
    async def handle_trust_event(self, event: dict) -> None: ...
    async def update_satisfaction_aggregate(self, agent_id: UUID) -> None: ...
```

---

## Redis Keys

| Key Pattern | Type | TTL | Purpose |
|---|---|---|---|
| `rec:content:{user_id}` | JSON string | 6h | Content-based recommendation cache |
| `marketplace:trending:latest` | JSON string | 25h | Current trending list cache |

---

## Kafka Events Produced

**Topic**: `marketplace.events`, key: `agent_id`

```python
# rating.created / rating.updated
{
    "event_type": "marketplace.rating.created",
    "agent_id": "uuid",
    "user_id": "uuid",
    "score": 4,
    "workspace_id": "uuid",
    "occurred_at": "ISO8601"
}

# marketplace.trending_updated
{
    "event_type": "marketplace.trending_updated",
    "snapshot_date": "2026-04-12",
    "top_agent_fqns": ["ns:agent1", "ns:agent2"],
    "occurred_at": "ISO8601"
}
```

---

## Source File Structure

```text
apps/control-plane/src/platform/marketplace/
├── __init__.py
├── models.py              # SQLAlchemy: MarketplaceAgentRating, MarketplaceQualityAggregate,
│                          #   MarketplaceRecommendation, MarketplaceTrendingSnapshot
├── schemas.py             # Pydantic: all request/response schemas
├── repository.py          # Async CRUD: ratings upsert, quality aggregate update,
│                          #   recommendations bulk replace, trending snapshot insert
├── search_service.py      # MarketplaceSearchService: RRF orchestration (OS + Qdrant)
├── rating_service.py      # MarketplaceRatingService: upsert, list, analytics
├── recommendation_service.py  # MarketplaceRecommendationService: CF + content-based + contextual
├── trending_service.py    # MarketplaceTrendingService: read trending snapshots
├── quality_service.py     # MarketplaceQualityAggregateService: Kafka event handlers
├── jobs.py                # APScheduler jobs: run_cf_recommendations(), run_trending_computation()
├── events.py              # Kafka producer helpers + event types
├── router.py              # FastAPI router: all REST endpoints
├── exceptions.py          # MarketplaceError, AgentNotFoundError, InvocationRequiredError, etc.
└── dependencies.py        # FastAPI DI: get_search_service, get_rating_service, etc.
```
