from __future__ import annotations

from datetime import datetime
from platform.testing.models import AdversarialCategory, SuiteType
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


class GenerateSuiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    agent_fqn: str = Field(min_length=1, max_length=512)
    agent_id: UUID | None = None
    suite_type: SuiteType = SuiteType.mixed
    cases_per_category: int = Field(default=10, ge=1, le=100)

    @field_validator("agent_fqn")
    @classmethod
    def normalize_agent_fqn(cls, value: str) -> str:
        return value.strip()


class GeneratedTestSuiteResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    agent_id: UUID | None
    suite_type: SuiteType
    version: int
    case_count: int
    category_counts: dict[str, int]
    artifact_key: str | None
    imported_into_eval_set_id: UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GeneratedTestSuiteListResponse(BaseModel):
    items: list[GeneratedTestSuiteResponse]
    total: int
    page: int = 1
    page_size: int = 20


class AdversarialCaseResponse(BaseModel):
    id: UUID
    suite_id: UUID
    category: AdversarialCategory
    input_data: dict[str, Any]
    expected_behavior: str
    generation_prompt_hash: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdversarialCaseListResponse(BaseModel):
    items: list[AdversarialCaseResponse]
    total: int
    page: int = 1
    page_size: int = 50


class ImportSuiteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    eval_set_id: UUID


class ImportSuiteResponse(BaseModel):
    imported_case_count: int
    eval_set_id: UUID


class CoordinationTestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    fleet_id: UUID
    execution_id: UUID | None = None


class CoordinationTestResultResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    fleet_id: UUID
    execution_id: UUID | None
    completion_score: float
    coherence_score: float
    goal_achievement_score: float
    overall_score: float
    per_agent_scores: dict[str, Any]
    insufficient_members: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriftAlertResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_fqn: str
    eval_set_id: UUID
    metric_name: str
    baseline_value: float
    current_value: float
    deviation_magnitude: float
    stddevs_from_baseline: float
    acknowledged: bool
    acknowledged_by: UUID | None
    acknowledged_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DriftAlertListResponse(BaseModel):
    items: list[DriftAlertResponse]
    total: int
    page: int = 1
    page_size: int = 20


class AcknowledgeDriftAlertResponse(BaseModel):
    alert: DriftAlertResponse
    message: str = "acknowledged"
