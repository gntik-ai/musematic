from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import (
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    WorkspaceScopedMixin,
)
from typing import Any
from uuid import UUID

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class EvalSetStatus(StrEnum):
    active = "active"
    archived = "archived"


class RunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class VerdictStatus(StrEnum):
    scored = "scored"
    error = "error"


class ExperimentStatus(StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"


class ATERunStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    pre_check_failed = "pre_check_failed"


class ReviewDecision(StrEnum):
    confirmed = "confirmed"
    overridden = "overridden"


class EvalSet(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    __tablename__ = "evaluation_eval_sets"
    __table_args__ = (
        Index("ix_evaluation_eval_sets_workspace_status", "workspace_id", "status"),
        Index(
            "uq_evaluation_eval_sets_workspace_name_active",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    scorer_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    pass_threshold: Mapped[float] = mapped_column(Float(), nullable=False, default=0.7)
    status: Mapped[EvalSetStatus] = mapped_column(
        SAEnum(EvalSetStatus, name="evaluation_eval_set_status"),
        nullable=False,
        default=EvalSetStatus.active,
    )
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)

    benchmark_cases: Mapped[list[BenchmarkCase]] = relationship(
        "platform.evaluation.models.BenchmarkCase",
        back_populates="eval_set",
        order_by="platform.evaluation.models.BenchmarkCase.position.asc()",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list[EvaluationRun]] = relationship(
        "platform.evaluation.models.EvaluationRun",
        back_populates="eval_set",
    )


class BenchmarkCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "evaluation_benchmark_cases"
    __table_args__ = (
        Index("ix_evaluation_benchmark_cases_eval_set_id", "eval_set_id"),
        Index(
            "uq_evaluation_benchmark_cases_eval_set_position",
            "eval_set_id",
            "position",
            unique=True,
        ),
    )

    eval_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_eval_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    input_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    expected_output: Mapped[str] = mapped_column(Text(), nullable=False)
    scoring_criteria: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    metadata_tags: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    category: Mapped[str | None] = mapped_column(String(length=64), nullable=True)
    position: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)

    eval_set: Mapped[EvalSet] = relationship(
        "platform.evaluation.models.EvalSet",
        back_populates="benchmark_cases",
    )
    verdicts: Mapped[list[JudgeVerdict]] = relationship(
        "platform.evaluation.models.JudgeVerdict",
        back_populates="benchmark_case",
    )


class EvaluationRun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "evaluation_runs"
    __table_args__ = (
        Index("ix_evaluation_runs_eval_set_id", "eval_set_id"),
        Index("ix_evaluation_runs_workspace_status", "workspace_id", "status"),
        Index("ix_evaluation_runs_agent_fqn", "agent_fqn"),
    )

    eval_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_eval_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    agent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="evaluation_run_status"),
        nullable=False,
        default=RunStatus.pending,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    passed_cases: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    failed_cases: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    error_cases: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    aggregate_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)

    eval_set: Mapped[EvalSet] = relationship(
        "platform.evaluation.models.EvalSet",
        back_populates="runs",
    )
    verdicts: Mapped[list[JudgeVerdict]] = relationship(
        "platform.evaluation.models.JudgeVerdict",
        back_populates="run",
        cascade="all, delete-orphan",
    )


class JudgeVerdict(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "evaluation_judge_verdicts"
    __table_args__ = (
        Index("ix_evaluation_judge_verdicts_run_id", "run_id"),
        Index("ix_evaluation_judge_verdicts_case_id", "benchmark_case_id"),
        UniqueConstraint(
            "run_id",
            "benchmark_case_id",
            name="uq_evaluation_judge_verdicts_run_case",
        ),
    )

    run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    benchmark_case_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_benchmark_cases.id", ondelete="CASCADE"),
        nullable=False,
    )
    actual_output: Mapped[str] = mapped_column(Text(), nullable=False)
    scorer_results: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    overall_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean(), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text(), nullable=True)
    status: Mapped[VerdictStatus] = mapped_column(
        SAEnum(VerdictStatus, name="evaluation_verdict_status"),
        nullable=False,
        default=VerdictStatus.scored,
    )

    run: Mapped[EvaluationRun] = relationship(
        "platform.evaluation.models.EvaluationRun",
        back_populates="verdicts",
    )
    benchmark_case: Mapped[BenchmarkCase] = relationship(
        "platform.evaluation.models.BenchmarkCase",
        back_populates="verdicts",
    )
    human_grade: Mapped[HumanAiGrade | None] = relationship(
        "platform.evaluation.models.HumanAiGrade",
        back_populates="verdict",
        uselist=False,
    )


class AbExperiment(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "evaluation_ab_experiments"
    __table_args__ = (
        Index("ix_evaluation_ab_experiments_workspace_status", "workspace_id", "status"),
        Index("ix_evaluation_ab_experiments_run_a_id", "run_a_id"),
        Index("ix_evaluation_ab_experiments_run_b_id", "run_b_id"),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    run_a_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    run_b_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(
        SAEnum(ExperimentStatus, name="evaluation_experiment_status"),
        nullable=False,
        default=ExperimentStatus.pending,
    )
    p_value: Mapped[float | None] = mapped_column(Float(), nullable=True)
    confidence_interval: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )
    effect_size: Mapped[float | None] = mapped_column(Float(), nullable=True)
    winner: Mapped[str | None] = mapped_column(String(length=16), nullable=True)
    analysis_summary: Mapped[str | None] = mapped_column(Text(), nullable=True)


class ATEConfig(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin, SoftDeleteMixin):
    __tablename__ = "evaluation_ate_configs"
    __table_args__ = (
        Index("ix_evaluation_ate_configs_workspace_id", "workspace_id"),
        Index(
            "uq_evaluation_ate_configs_workspace_name_active",
            "workspace_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(length=255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text(), nullable=True)
    scenarios: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    scorer_config: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    performance_thresholds: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    safety_checks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )
    created_by: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)


class ATERun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "evaluation_ate_runs"
    __table_args__ = (
        Index("ix_evaluation_ate_runs_ate_config_id", "ate_config_id"),
        Index("ix_evaluation_ate_runs_workspace_status", "workspace_id", "status"),
        Index("ix_evaluation_ate_runs_agent_fqn", "agent_fqn"),
    )

    ate_config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_ate_configs.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    agent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    simulation_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    status: Mapped[ATERunStatus] = mapped_column(
        SAEnum(ATERunStatus, name="evaluation_ate_run_status"),
        nullable=False,
        default=ATERunStatus.pending,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_artifact_key: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    report: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )
    pre_check_errors: Mapped[list[Any] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )


class RobustnessTestRun(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "evaluation_robustness_runs"
    __table_args__ = (
        Index("ix_evaluation_robustness_runs_eval_set_id", "eval_set_id"),
        Index("ix_evaluation_robustness_runs_workspace_status", "workspace_id", "status"),
        Index("ix_evaluation_robustness_runs_agent_fqn", "agent_fqn"),
    )

    eval_set_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_eval_sets.id", ondelete="CASCADE"),
        nullable=False,
    )
    benchmark_case_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_benchmark_cases.id", ondelete="SET NULL"),
        nullable=True,
    )
    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    trial_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    completed_trials: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="evaluation_run_status"),
        nullable=False,
        default=RunStatus.pending,
    )
    distribution: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB(none_as_null=False),
        nullable=True,
    )
    is_unreliable: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    variance_threshold: Mapped[float] = mapped_column(Float(), nullable=False, default=0.15)
    trial_run_ids: Mapped[list[str]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=list,
    )


class HumanAiGrade(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "evaluation_human_grades"
    __table_args__ = (
        Index("ix_evaluation_human_grades_reviewer_id", "reviewer_id"),
        UniqueConstraint("verdict_id", name="uq_evaluation_human_grades_verdict_id"),
    )

    verdict_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluation_judge_verdicts.id", ondelete="CASCADE"),
        nullable=False,
    )
    reviewer_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    decision: Mapped[ReviewDecision] = mapped_column(
        SAEnum(ReviewDecision, name="evaluation_review_decision"),
        nullable=False,
    )
    override_score: Mapped[float | None] = mapped_column(Float(), nullable=True)
    feedback: Mapped[str | None] = mapped_column(Text(), nullable=True)
    original_score: Mapped[float] = mapped_column(Float(), nullable=False)
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    verdict: Mapped[JudgeVerdict] = relationship(
        "platform.evaluation.models.JudgeVerdict",
        back_populates="human_grade",
    )
