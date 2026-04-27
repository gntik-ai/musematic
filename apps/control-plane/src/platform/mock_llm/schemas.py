from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class MockLLMRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_text: str = Field(min_length=1)
    context: dict[str, Any] | None = None

    @field_validator("input_text")
    @classmethod
    def normalize_input_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("input_text must not be blank")
        return stripped


class MockLLMResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    output_text: str
    completion_metadata: dict[str, Any] = Field(default_factory=dict)
    was_fallback: bool = False


class CannedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    input_hash: str = Field(min_length=16, max_length=16)
    output_text: str = Field(min_length=1)
    completion_metadata: dict[str, Any] = Field(default_factory=dict)
