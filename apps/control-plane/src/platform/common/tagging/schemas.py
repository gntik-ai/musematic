from __future__ import annotations

from datetime import datetime
from platform.common.tagging.constants import (
    LABEL_KEY_PATTERN,
    MAX_LABEL_KEY_LEN,
    MAX_LABEL_VALUE_LEN,
    MAX_TAG_LEN,
    TAG_PATTERN,
)
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TagAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tag: str = Field(min_length=1, max_length=MAX_TAG_LEN)

    @field_validator("tag")
    @classmethod
    def normalize_tag(cls, value: str) -> str:
        tag = value.strip()
        if not TAG_PATTERN.fullmatch(tag):
            raise ValueError("tag must match ^[a-zA-Z0-9._-]+$")
        return tag


class TagDetachRequest(TagAttachRequest):
    pass


class TagResponse(BaseModel):
    tag: str
    created_by: UUID | None
    created_at: datetime


class EntityTagsResponse(BaseModel):
    entity_type: str
    entity_id: UUID
    tags: list[TagResponse]


class LabelAttachRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str = Field(min_length=1, max_length=MAX_LABEL_KEY_LEN)
    value: str = Field(max_length=MAX_LABEL_VALUE_LEN)

    @field_validator("key")
    @classmethod
    def normalize_key(cls, value: str) -> str:
        key = value.strip()
        if not LABEL_KEY_PATTERN.fullmatch(key):
            raise ValueError("label key must match ^[a-zA-Z][a-zA-Z0-9._-]*$")
        return key

    @field_validator("value")
    @classmethod
    def normalize_value(cls, value: str) -> str:
        return value.strip()


class LabelResponse(BaseModel):
    key: str
    value: str
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime
    is_reserved: bool


class EntityLabelsResponse(BaseModel):
    entity_type: str
    entity_id: UUID
    labels: list[LabelResponse]


class LabelFilterParams(BaseModel):
    tags: list[str] = Field(default_factory=list)
    labels: dict[str, str] = Field(default_factory=dict)


class CrossEntityTagSearchRequest(BaseModel):
    tag: str
    entity_types: list[str] | None = None
    cursor: str | None = None
    limit: int = Field(default=50, ge=1, le=200)


class CrossEntityTagSearchResponse(BaseModel):
    tag: str
    entities: dict[str, list[UUID]]
    next_cursor: str | None = None


class SavedViewCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID | None = None
    name: str = Field(min_length=1, max_length=256)
    entity_type: str
    filters: dict[str, Any] = Field(default_factory=dict)
    shared: bool = False


class SavedViewUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=256)
    filters: dict[str, Any] | None = None
    shared: bool | None = None


class SavedViewResponse(BaseModel):
    id: UUID
    owner_id: UUID
    workspace_id: UUID | None
    name: str
    entity_type: str
    filters: dict[str, Any]
    is_owner: bool
    is_shared: bool
    is_orphan_transferred: bool
    is_orphan: bool = False
    version: int
    created_at: datetime
    updated_at: datetime


class SavedViewShareToggleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared: bool


class LabelExpressionValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expression: str = Field(min_length=1)


class LabelExpressionError(BaseModel):
    line: int
    col: int
    token: str
    message: str


class LabelExpressionValidationResponse(BaseModel):
    valid: bool
    error: LabelExpressionError | None = None
