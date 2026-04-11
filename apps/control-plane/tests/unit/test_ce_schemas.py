from __future__ import annotations

from platform.context_engineering.schemas import (
    BudgetEnvelope,
    ContextQualityScore,
    ProfileAssignmentCreate,
    ProfileCreate,
    SourceConfig,
)

import pytest
from pydantic import ValidationError


def test_budget_envelope_and_profile_defaults() -> None:
    profile = ProfileCreate(name="profile")

    assert profile.budget_config.max_tokens_step == 8192
    assert profile.compaction_strategies
    assert profile.source_config == []


def test_source_config_and_quality_score_validate_ranges() -> None:
    score = ContextQualityScore(
        relevance=1.0,
        freshness=0.5,
        authority=0.5,
        contradiction_density=1.0,
        token_efficiency=0.5,
        task_brief_coverage=0.7,
        aggregate=0.7,
    )

    assert score.aggregate == 0.7
    with pytest.raises(ValidationError):
        SourceConfig(source_type="system_instructions", priority=101)


def test_profile_assignment_requires_target_for_agent_and_role() -> None:
    with pytest.raises(ValidationError):
        ProfileAssignmentCreate(assignment_level="agent")
    with pytest.raises(ValidationError):
        ProfileAssignmentCreate(assignment_level="role_type")

    workspace_assignment = ProfileAssignmentCreate(assignment_level="workspace")

    assert workspace_assignment.agent_fqn is None
    assert workspace_assignment.role_type is None


def test_budget_envelope_rejects_invalid_limits() -> None:
    with pytest.raises(ValidationError):
        BudgetEnvelope(max_tokens_step=0)
