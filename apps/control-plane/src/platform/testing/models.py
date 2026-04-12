from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from platform.common.models.base import Base
from platform.common.models.mixins import TimestampMixin, UUIDMixin, WorkspaceScopedMixin
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
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship


class SuiteType(StrEnum):
    adversarial = "adversarial"
    positive = "positive"
    mixed = "mixed"


class AdversarialCategory(StrEnum):
    prompt_injection = "prompt_injection"
    jailbreak = "jailbreak"
    contradictory = "contradictory"
    malformed_data = "malformed_data"
    ambiguous = "ambiguous"
    resource_exhaustion = "resource_exhaustion"


class GeneratedTestSuite(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "testing_generated_suites"
    __table_args__ = (
        Index("ix_testing_generated_suites_agent_fqn", "agent_fqn"),
        Index("ix_testing_generated_suites_workspace_suite_type", "workspace_id", "suite_type"),
        UniqueConstraint(
            "workspace_id",
            "agent_fqn",
            "suite_type",
            "version",
            name="uq_testing_generated_suites_agent_type_version",
        ),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    agent_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    suite_type: Mapped[SuiteType] = mapped_column(
        SAEnum(SuiteType, name="testing_suite_type"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    case_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    category_counts: Mapped[dict[str, int]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    artifact_key: Mapped[str | None] = mapped_column(String(length=512), nullable=True)
    imported_into_eval_set_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), nullable=True
    )

    adversarial_cases: Mapped[list[AdversarialTestCase]] = relationship(
        "platform.testing.models.AdversarialTestCase",
        back_populates="suite",
        cascade="all, delete-orphan",
        order_by="platform.testing.models.AdversarialTestCase.created_at.asc()",
    )


class AdversarialTestCase(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "testing_adversarial_cases"
    __table_args__ = (
        Index("ix_testing_adversarial_cases_suite_id", "suite_id"),
        Index("ix_testing_adversarial_cases_category", "category"),
    )

    suite_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("testing_generated_suites.id", ondelete="CASCADE"),
        nullable=False,
    )
    category: Mapped[AdversarialCategory] = mapped_column(
        SAEnum(AdversarialCategory, name="testing_adversarial_category"),
        nullable=False,
    )
    input_data: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    expected_behavior: Mapped[str] = mapped_column(String(length=64), nullable=False)
    generation_prompt_hash: Mapped[str | None] = mapped_column(String(length=64), nullable=True)

    suite: Mapped[GeneratedTestSuite] = relationship(
        "platform.testing.models.GeneratedTestSuite",
        back_populates="adversarial_cases",
    )


class CoordinationTestResult(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "testing_coordination_results"
    __table_args__ = (
        Index("ix_testing_coordination_results_fleet_id", "fleet_id"),
        Index("ix_testing_coordination_results_workspace_id", "workspace_id"),
    )

    fleet_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    execution_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    completion_score: Mapped[float] = mapped_column(Float(), nullable=False)
    coherence_score: Mapped[float] = mapped_column(Float(), nullable=False)
    goal_achievement_score: Mapped[float] = mapped_column(Float(), nullable=False)
    overall_score: Mapped[float] = mapped_column(Float(), nullable=False)
    per_agent_scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB(none_as_null=False),
        nullable=False,
        default=dict,
    )
    insufficient_members: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)


class DriftAlert(Base, UUIDMixin, TimestampMixin, WorkspaceScopedMixin):
    __tablename__ = "testing_drift_alerts"
    __table_args__ = (
        Index("ix_testing_drift_alerts_agent_fqn", "agent_fqn"),
        Index("ix_testing_drift_alerts_eval_set_id", "eval_set_id"),
        Index("ix_testing_drift_alerts_acknowledged", "acknowledged"),
    )

    agent_fqn: Mapped[str] = mapped_column(String(length=512), nullable=False)
    eval_set_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    metric_name: Mapped[str] = mapped_column(String(length=64), nullable=False)
    baseline_value: Mapped[float] = mapped_column(Float(), nullable=False)
    current_value: Mapped[float] = mapped_column(Float(), nullable=False)
    deviation_magnitude: Mapped[float] = mapped_column(Float(), nullable=False)
    stddevs_from_baseline: Mapped[float] = mapped_column(Float(), nullable=False)
    acknowledged: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=False)
    acknowledged_by: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
