# Data Model: Evaluation Framework and Semantic Testing

**Branch**: `034-evaluation-semantic-testing`

---

## Enums

```python
# evaluation/models.py

class EvalSetStatus(str, enum.Enum):
    active = "active"
    archived = "archived"

class RunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"

class VerdictStatus(str, enum.Enum):
    scored = "scored"
    error = "error"

class ExperimentStatus(str, enum.Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"

class ATERunStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    pre_check_failed = "pre_check_failed"

class ReviewDecision(str, enum.Enum):
    confirmed = "confirmed"
    overridden = "overridden"

# testing/models.py

class SuiteType(str, enum.Enum):
    adversarial = "adversarial"
    positive = "positive"
    mixed = "mixed"

class AdversarialCategory(str, enum.Enum):
    prompt_injection = "prompt_injection"
    jailbreak = "jailbreak"
    contradictory = "contradictory"
    malformed_data = "malformed_data"
    ambiguous = "ambiguous"
    resource_exhaustion = "resource_exhaustion"
```

---

## SQLAlchemy Models

### evaluation/ bounded context

```python
# apps/control-plane/src/platform/evaluation/models.py

from platform.common.models.base import Base
from platform.common.models.mixins import (
    UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin
)

class EvalSet(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    """Named collection of benchmark cases used to evaluate agents."""
    __tablename__ = "evaluation_eval_sets"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scorer_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {scorer_type: {enabled: bool, threshold: float, config: dict}}
    pass_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)
    status: Mapped[EvalSetStatus] = mapped_column(
        SQLEnum(EvalSetStatus), nullable=False, default=EvalSetStatus.active
    )
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    benchmark_cases: Mapped[list["BenchmarkCase"]] = relationship(
        back_populates="eval_set", cascade="all, delete-orphan", lazy="select"
    )
    runs: Mapped[list["EvaluationRun"]] = relationship(
        back_populates="eval_set", lazy="select"
    )


class BenchmarkCase(Base, UUIDMixin, TimestampMixin):
    """A single test case within an eval set."""
    __tablename__ = "evaluation_benchmark_cases"

    eval_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_eval_sets.id"), nullable=False, index=True
    )
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    scoring_criteria: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # scorer-specific overrides; merged with eval_set.scorer_config at run time
    metadata_tags: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    category: Mapped[str | None] = mapped_column(String(64))
    # e.g., "adversarial", "positive", "edge_case"
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    eval_set: Mapped["EvalSet"] = relationship(back_populates="benchmark_cases")
    verdicts: Mapped[list["JudgeVerdict"]] = relationship(
        back_populates="benchmark_case", lazy="select"
    )


class EvaluationRun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """An instance of running an eval set against a target agent."""
    __tablename__ = "evaluation_runs"

    eval_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_eval_sets.id"), nullable=False, index=True
    )
    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[RunStatus] = mapped_column(
        SQLEnum(RunStatus), nullable=False, default=RunStatus.pending, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    total_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_cases: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    aggregate_score: Mapped[float | None] = mapped_column(Float)
    error_detail: Mapped[str | None] = mapped_column(Text)

    eval_set: Mapped["EvalSet"] = relationship(back_populates="runs")
    verdicts: Mapped[list["JudgeVerdict"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", lazy="select"
    )


class JudgeVerdict(Base, UUIDMixin, TimestampMixin):
    """Individual scoring result for a single benchmark case within a run."""
    __tablename__ = "evaluation_judge_verdicts"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False, index=True
    )
    benchmark_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_benchmark_cases.id"), nullable=False, index=True
    )
    actual_output: Mapped[str] = mapped_column(Text, nullable=False)
    scorer_results: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {scorer_type: {score, passed, rationale, error, calibration_distribution, ...}}
    overall_score: Mapped[float | None] = mapped_column(Float)
    passed: Mapped[bool | None] = mapped_column(Boolean)
    error_detail: Mapped[str | None] = mapped_column(Text)
    status: Mapped[VerdictStatus] = mapped_column(
        SQLEnum(VerdictStatus), nullable=False, default=VerdictStatus.scored
    )

    run: Mapped["EvaluationRun"] = relationship(back_populates="verdicts")
    benchmark_case: Mapped["BenchmarkCase"] = relationship(back_populates="verdicts")
    human_grade: Mapped["HumanAiGrade | None"] = relationship(
        back_populates="verdict", uselist=False, lazy="select"
    )


class AbExperiment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """A/B comparison between two evaluation runs with statistical significance analysis."""
    __tablename__ = "evaluation_ab_experiments"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    run_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False
    )
    run_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_runs.id"), nullable=False
    )
    status: Mapped[ExperimentStatus] = mapped_column(
        SQLEnum(ExperimentStatus), nullable=False, default=ExperimentStatus.pending
    )
    p_value: Mapped[float | None] = mapped_column(Float)
    confidence_interval: Mapped[dict | None] = mapped_column(JSONB)
    # {lower: float, upper: float, alpha: float}
    effect_size: Mapped[float | None] = mapped_column(Float)
    winner: Mapped[str | None] = mapped_column(String(16))
    # "a", "b", "inconclusive"
    analysis_summary: Mapped[str | None] = mapped_column(Text)


class ATEConfig(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    """Accredited Testing Environment configuration — reusable evaluation protocol."""
    __tablename__ = "evaluation_ate_configs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    scenarios: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{id, name, input_data, expected_output, scorer_config, timeout_seconds}]
    scorer_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    performance_thresholds: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {latency_p95_ms: int, cost_max_usd: float}
    safety_checks: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # [{check_type: str, expected_outcome: str, ...}]
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class ATERun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """An execution of an ATE against a specific agent."""
    __tablename__ = "evaluation_ate_runs"

    ate_config_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_ate_configs.id"), nullable=False, index=True
    )
    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    simulation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    # returned by SimulationController.CreateSimulation()
    status: Mapped[ATERunStatus] = mapped_column(
        SQLEnum(ATERunStatus), nullable=False, default=ATERunStatus.pending, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_artifact_key: Mapped[str | None] = mapped_column(String(512))
    # MinIO key: evaluation-ate-evidence/{run_id}/evidence.json
    report: Mapped[dict | None] = mapped_column(JSONB)
    # structured report: {per_scenario_results, score_distribution, latency_percentiles,
    #                     cost_breakdown, safety_compliance}
    pre_check_errors: Mapped[list | None] = mapped_column(JSONB)


class RobustnessTestRun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Multi-trial evaluation run producing a statistical distribution of results."""
    __tablename__ = "evaluation_robustness_runs"

    eval_set_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_eval_sets.id"), nullable=False, index=True
    )
    benchmark_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_benchmark_cases.id")
    )
    # null means the whole eval set is tested N times; non-null means single case
    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_trials: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[RunStatus] = mapped_column(
        SQLEnum(RunStatus), nullable=False, default=RunStatus.pending, index=True
    )
    distribution: Mapped[dict | None] = mapped_column(JSONB)
    # {mean, stddev, p5, p25, p50, p75, p95, min, max}
    is_unreliable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    variance_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    trial_run_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # list of evaluation_run UUIDs


class HumanAiGrade(Base, UUIDMixin, TimestampMixin):
    """Human review record for a JudgeVerdict."""
    __tablename__ = "evaluation_human_grades"

    verdict_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("evaluation_judge_verdicts.id"),
        nullable=False, unique=True, index=True
    )
    reviewer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    decision: Mapped[ReviewDecision] = mapped_column(SQLEnum(ReviewDecision), nullable=False)
    override_score: Mapped[float | None] = mapped_column(Float)
    # null if decision == confirmed
    feedback: Mapped[str | None] = mapped_column(Text)
    original_score: Mapped[float] = mapped_column(Float, nullable=False)
    # snapshot of verdict.overall_score at review time
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    verdict: Mapped["JudgeVerdict"] = relationship(back_populates="human_grade")
```

---

### testing/ bounded context

```python
# apps/control-plane/src/platform/testing/models.py

from platform.common.models.base import Base
from platform.common.models.mixins import (
    UUIDMixin, TimestampMixin, WorkspaceScopedMixin
)

class GeneratedTestSuite(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Versioned collection of auto-generated test cases derived from an agent's configuration."""
    __tablename__ = "testing_generated_suites"

    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    suite_type: Mapped[SuiteType] = mapped_column(SQLEnum(SuiteType), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # auto-increment per (agent_fqn, suite_type) at service layer
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {adversarial_category_or_positive: count}
    artifact_key: Mapped[str | None] = mapped_column(String(512))
    # MinIO key for full payload when case_count > 500
    imported_into_eval_set_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))

    adversarial_cases: Mapped[list["AdversarialTestCase"]] = relationship(
        back_populates="suite", cascade="all, delete-orphan", lazy="select"
    )


class AdversarialTestCase(Base, UUIDMixin, TimestampMixin):
    """An auto-generated adversarial test case targeting a specific vulnerability category."""
    __tablename__ = "testing_adversarial_cases"

    suite_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("testing_generated_suites.id"),
        nullable=False, index=True
    )
    category: Mapped[AdversarialCategory] = mapped_column(
        SQLEnum(AdversarialCategory), nullable=False, index=True
    )
    input_data: Mapped[dict] = mapped_column(JSONB, nullable=False)
    expected_behavior: Mapped[str] = mapped_column(String(64), nullable=False)
    # "should_reject", "should_fail_safely", "should_handle_gracefully"
    generation_prompt_hash: Mapped[str | None] = mapped_column(String(64))
    # SHA-256 of the generation prompt for auditability (not the prompt itself)

    suite: Mapped["GeneratedTestSuite"] = relationship(back_populates="adversarial_cases")


class CoordinationTestResult(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Result of evaluating multi-agent coordination on a fleet execution."""
    __tablename__ = "testing_coordination_results"

    fleet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    completion_score: Mapped[float] = mapped_column(Float, nullable=False)
    coherence_score: Mapped[float] = mapped_column(Float, nullable=False)
    goal_achievement_score: Mapped[float] = mapped_column(Float, nullable=False)
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    per_agent_scores: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # {fqn: {completion_score, coherence_score, contribution_score}}
    insufficient_members: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # true if fleet has only 1 agent at time of test


class DriftAlert(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    """Persisted alert record for detected behavioral drift."""
    __tablename__ = "testing_drift_alerts"

    agent_fqn: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    eval_set_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float, nullable=False)
    current_value: Mapped[float] = mapped_column(Float, nullable=False)
    deviation_magnitude: Mapped[float] = mapped_column(Float, nullable=False)
    stddevs_from_baseline: Mapped[float] = mapped_column(Float, nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    acknowledged_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
```

---

## ClickHouse Table

```sql
-- apps/control-plane/src/platform/testing/clickhouse_schema.sql

CREATE TABLE IF NOT EXISTS testing_drift_metrics (
    agent_fqn       String,
    eval_set_id     UUID,
    metric_name     String,
    -- "overall_score", "pass_rate", "p50_score", or scorer-specific: "semantic_score"
    score           Float64,
    run_id          UUID,
    measured_at     DateTime('UTC'),
    workspace_id    UUID
) ENGINE = MergeTree()
ORDER BY (agent_fqn, eval_set_id, metric_name, measured_at)
PARTITION BY toYYYYMM(measured_at)
TTL measured_at + INTERVAL 365 DAY;
```

---

## Qdrant Collection

```python
# Provisioned in evaluation/scorers/semantic.py on startup

EVALUATION_EMBEDDINGS_COLLECTION = "evaluation_embeddings"

collection_config = {
    "vectors": {
        "size": 1536,
        "distance": "Cosine"
    },
    "optimizers_config": {
        "default_segment_number": 2
    }
}

# Payload fields per point:
# {
#   "verdict_id": str (UUID),
#   "run_id": str (UUID),
#   "case_id": str (UUID),
#   "type": "actual" | "expected",
#   "created_at": int (unix timestamp)
# }
```

---

## MinIO Buckets

| Bucket | Contents |
|--------|----------|
| `evaluation-ate-evidence` | ATE run full evidence payloads (JSON per run) |
| `evaluation-generated-suites` | Large generated test suite archives (>500 cases) |

---

## Pydantic Schemas

```python
# evaluation/schemas.py (key schemas — abbreviated)

class EvalSetCreate(BaseModel):
    name: str
    description: str | None = None
    scorer_config: dict = {}
    pass_threshold: float = 0.7

class EvalSetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    description: str | None
    scorer_config: dict
    pass_threshold: float
    status: EvalSetStatus
    case_count: int
    created_at: datetime
    updated_at: datetime

class BenchmarkCaseCreate(BaseModel):
    input_data: dict
    expected_output: str
    scoring_criteria: dict = {}
    metadata_tags: dict = {}
    category: str | None = None

class EvaluationRunCreate(BaseModel):
    agent_fqn: str
    agent_id: UUID | None = None

class EvaluationRunResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    eval_set_id: UUID
    agent_fqn: str
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    total_cases: int
    passed_cases: int
    failed_cases: int
    error_cases: int
    aggregate_score: float | None

class JudgeVerdictResponse(BaseModel):
    id: UUID
    run_id: UUID
    benchmark_case_id: UUID
    actual_output: str
    scorer_results: dict
    overall_score: float | None
    passed: bool | None
    status: VerdictStatus
    human_grade: "HumanAiGradeResponse | None"

class LLMJudgeConfig(BaseModel):
    judge_model: str  # e.g., "claude-opus-4-6"
    rubric: "RubricConfig"
    calibration_runs: int = 3

class RubricConfig(BaseModel):
    template: str | None = None
    # one of: correctness, helpfulness, safety, style, faithfulness_to_source,
    #         instruction_following
    custom_criteria: list["RubricCriterion"] | None = None

class RubricCriterion(BaseModel):
    name: str
    description: str
    scale: int = 5
    examples: list[str] = []

class TrajectoryScore(BaseModel):
    efficiency_score: float
    tool_appropriateness_score: float
    reasoning_coherence_score: float
    cost_effectiveness_score: float
    overall_trajectory_score: float
    llm_judge_holistic: dict | None = None

class ATEConfigCreate(BaseModel):
    name: str
    description: str | None = None
    scenarios: list[dict]
    scorer_config: dict = {}
    performance_thresholds: dict = {}
    safety_checks: list[dict] = []

class ATERunResponse(BaseModel):
    id: UUID
    ate_config_id: UUID
    agent_fqn: str
    status: ATERunStatus
    started_at: datetime | None
    completed_at: datetime | None
    report: dict | None
    pre_check_errors: list | None

class HumanGradeSubmit(BaseModel):
    decision: ReviewDecision
    override_score: float | None = None
    feedback: str | None = None

class ReviewProgressResponse(BaseModel):
    total_verdicts: int
    pending_review: int
    reviewed: int
    overridden: int

# testing/schemas.py (key schemas)

class GenerateSuiteRequest(BaseModel):
    agent_fqn: str
    agent_id: UUID | None = None
    suite_type: SuiteType = SuiteType.mixed
    cases_per_category: int = 10

class DriftAlertResponse(BaseModel):
    id: UUID
    agent_fqn: str
    eval_set_id: UUID
    metric_name: str
    baseline_value: float
    current_value: float
    stddevs_from_baseline: float
    acknowledged: bool
    created_at: datetime

class CoordinationTestRequest(BaseModel):
    fleet_id: UUID
    execution_id: UUID | None = None
```

---

## Service Interfaces

### Exported (for other bounded contexts to call)

```python
# evaluation/service_interfaces.py

class EvalSuiteServiceInterface(Protocol):
    """Read-only interface for other contexts to query evaluation results."""
    async def get_run_summary(self, run_id: UUID) -> EvalRunSummaryDTO: ...
    async def get_latest_agent_score(
        self, agent_fqn: str, eval_set_id: UUID
    ) -> float | None: ...

# testing/service_interfaces.py

class CoordinationTestServiceInterface(Protocol):
    """Called by fleets/ to evaluate a fleet execution."""
    async def run_coordination_test(
        self, fleet_id: UUID, execution_id: UUID, workspace_id: UUID
    ) -> CoordinationTestResult: ...
```

### Consumed (called from this feature)

```python
# Called in-process (via DI) — no direct DB access

class AgentRegistryQueryInterface(Protocol):
    """Provided by registry/ — used to fetch agent config for test gen."""
    async def get_agent_profile(self, agent_fqn: str) -> AgentProfileDTO: ...

class ExecutionQueryInterface(Protocol):
    """Provided by execution/ — used by TrajectoryScorer."""
    async def get_journal_events(self, execution_id: UUID) -> list[JournalEventDTO]: ...
    async def get_task_plan_record(self, execution_id: UUID) -> TaskPlanRecordDTO: ...

class FleetQueryInterface(Protocol):
    """Provided by fleets/ — used by CoordinationTestService."""
    async def get_fleet_members(self, fleet_id: UUID) -> list[FleetMemberDTO]: ...

# gRPC clients (already in common/clients/)
# - ReasoningEngineClient: get reasoning traces for trajectory scoring
# - SimulationControllerClient: create simulation for ATE execution
```

---

## Kafka Events

**Topic**: `evaluation.events`

```python
# evaluation/events.py + testing/events.py — all produced on same topic

EVENT_TYPES = [
    "evaluation.run.started",       # {run_id, eval_set_id, agent_fqn, workspace_id}
    "evaluation.run.completed",     # {run_id, aggregate_score, passed_cases, total_cases}
    "evaluation.run.failed",        # {run_id, error_detail}
    "evaluation.verdict.scored",    # {verdict_id, run_id, case_id, overall_score, passed}
    "evaluation.ab_experiment.completed",  # {experiment_id, winner, p_value, effect_size}
    "evaluation.ate.run.completed", # {ate_run_id, ate_config_id, agent_fqn, report_summary}
    "evaluation.ate.run.failed",    # {ate_run_id, ate_config_id, pre_check_errors}
    "evaluation.robustness.completed",  # {robustness_run_id, is_unreliable, distribution}
    "evaluation.drift.detected",    # {alert_id, agent_fqn, metric_name, stddevs}
    "evaluation.human.grade.submitted",  # {grade_id, verdict_id, decision}
]
```
