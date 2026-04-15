from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

SessionStatus = Literal["active", "converged", "halted", "iteration_limit_reached"]
HypothesisStatus = Literal["active", "merged", "retired"]
Outcome = Literal["a_wins", "b_wins", "draw"]
LandscapeStatus = Literal["normal", "saturated", "low_data"]


class CorpusRef(BaseModel):
    type: Literal["dataset", "literature"]
    ref_id: str = Field(min_length=1, max_length=500)
    description: str = Field(default="", max_length=2000)


class DiscoverySessionConfig(BaseModel):
    k_factor: int = Field(default=32, gt=0)
    convergence_threshold: float = Field(default=0.05, gt=0.0, lt=1.0)
    max_cycles: int = Field(default=10, ge=1, le=100)
    min_hypotheses: int = Field(default=3, ge=2)


class DiscoverySessionCreateRequest(BaseModel):
    workspace_id: UUID
    research_question: str = Field(min_length=1, max_length=5000)
    corpus_refs: list[CorpusRef] = Field(default_factory=list)
    config: DiscoverySessionConfig = Field(default_factory=DiscoverySessionConfig)


class DiscoverySessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    session_id: UUID = Field(validation_alias="id")
    workspace_id: UUID
    research_question: str
    corpus_refs: list[dict[str, Any]]
    config: dict[str, Any]
    status: SessionStatus
    current_cycle: int
    convergence_metrics: dict[str, Any] | None
    initiated_by: UUID
    created_at: datetime
    updated_at: datetime


class DiscoverySessionListResponse(BaseModel):
    items: list[DiscoverySessionResponse]
    next_cursor: str | None = None


class HypothesisCreate(BaseModel):
    workspace_id: UUID
    session_id: UUID
    cycle_id: UUID | None = None
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1)
    reasoning: str = ""
    confidence: float = Field(ge=0.0, le=1.0)
    generating_agent_fqn: str = Field(min_length=1, max_length=255)


class HypothesisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    hypothesis_id: UUID = Field(validation_alias="id")
    session_id: UUID
    title: str
    description: str
    reasoning: str
    confidence: float = Field(ge=0.0, le=1.0)
    generating_agent_fqn: str
    status: HypothesisStatus
    elo_score: float | None = None
    rank: int | None = None
    wins: int = 0
    losses: int = 0
    draws: int = 0
    cluster_id: str | None = None
    created_at: datetime


class HypothesisListResponse(BaseModel):
    items: list[HypothesisResponse]
    next_cursor: str | None = None


class CritiqueDimensionScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = ""


class HypothesisCritiqueResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    critique_id: UUID = Field(validation_alias="id")
    hypothesis_id: UUID
    reviewer_agent_fqn: str
    is_aggregated: bool
    scores: dict[str, CritiqueDimensionScore]
    composite_summary: dict[str, Any] | None = None
    created_at: datetime


class CritiqueListResponse(BaseModel):
    items: list[HypothesisCritiqueResponse]
    aggregated: HypothesisCritiqueResponse | None = None


class LeaderboardEntryResponse(BaseModel):
    hypothesis_id: UUID
    title: str
    elo_score: float
    rank: int
    wins: int = 0
    losses: int = 0
    draws: int = 0
    cluster_id: str | None = None


class LeaderboardResponse(BaseModel):
    items: list[LeaderboardEntryResponse]
    session_id: UUID
    total_hypotheses: int


class TournamentRoundResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    round_id: UUID = Field(validation_alias="id")
    session_id: UUID
    cycle_id: UUID | None = None
    round_number: int
    pairwise_results: list[dict[str, Any]]
    elo_changes: list[dict[str, Any]]
    bye_hypothesis_id: UUID | None = None
    status: Literal["completed", "in_progress", "failed"]
    created_at: datetime


class TournamentRoundListResponse(BaseModel):
    items: list[TournamentRoundResponse]
    next_cursor: str | None = None


class GDECycleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    cycle_id: UUID = Field(validation_alias="id")
    session_id: UUID
    cycle_number: int
    status: Literal["running", "completed", "failed"]
    generation_count: int
    debate_record: dict[str, Any]
    refinement_count: int
    convergence_metric: float | None
    converged: bool
    created_at: datetime
    updated_at: datetime


class ExperimentDesignRequest(BaseModel):
    workspace_id: UUID


class DiscoveryExperimentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    experiment_id: UUID = Field(validation_alias="id")
    hypothesis_id: UUID
    session_id: UUID
    plan: dict[str, Any]
    governance_status: Literal["pending", "approved", "rejected"]
    governance_violations: list[dict[str, Any]]
    execution_status: Literal["not_started", "running", "completed", "failed", "timeout"]
    sandbox_execution_id: str | None = None
    results: dict[str, Any] | None = None
    designed_by_agent_fqn: str
    created_at: datetime
    updated_at: datetime


class ProvenanceNode(BaseModel):
    id: str
    type: Literal["hypothesis", "evidence", "agent", "experiment", "critique", "debate"]
    label: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ProvenanceEdge(BaseModel):
    from_id: str = Field(serialization_alias="from")
    to: str
    type: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ProvenanceGraphResponse(BaseModel):
    hypothesis_id: UUID
    nodes: list[ProvenanceNode]
    edges: list[ProvenanceEdge]


class HypothesisClusterResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    cluster_id: UUID = Field(validation_alias="id")
    session_id: UUID
    cluster_label: str
    centroid_description: str
    hypothesis_count: int
    density_metric: float
    classification: Literal["normal", "over_explored", "gap"]
    hypothesis_ids: list[str]
    computed_at: datetime


class ClusterListResponse(BaseModel):
    items: list[HypothesisClusterResponse]
    landscape_status: LandscapeStatus


class HaltSessionRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class PairwiseOutcome(BaseModel):
    hyp_a_id: UUID
    hyp_b_id: UUID
    outcome: Outcome
    reasoning: str = ""

    @field_validator("outcome")
    @classmethod
    def _validate_outcome(cls, value: str) -> str:
        if value not in {"a_wins", "b_wins", "draw"}:
            raise ValueError("outcome must be a_wins, b_wins, or draw")
        return value
