from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class VaultStatusResponse(BaseModel):
    status: Literal["green", "yellow", "red"]
    mode: str
    auth_method: str | None = None
    token_expiry_at: datetime | None = None
    lease_count: int | None = None
    recent_failures: list[str] = Field(default_factory=list)
    cache_hit_rate: float = 0.0
    error: str | None = None
    read_counts_by_domain: dict[str, float] = Field(default_factory=dict)
    auth_failure_counts_by_method: dict[str, float] = Field(default_factory=dict)
    policy_denied_counts_by_path: dict[str, float] = Field(default_factory=dict)
    serving_stale_total: float = 0.0
    renewal_success_total: float = 0.0
    renewal_failure_total: float = 0.0
    cache_hit_total: float = 0.0
    cache_miss_total: float = 0.0


class CacheFlushRequest(BaseModel):
    path: str | None = None
    pod: str | None = None
    all_pods: bool = False


class CacheFlushResponse(BaseModel):
    flushed_count: int
    scope: Literal["current-pod"] = "current-pod"
    path: str | None = None
    pod: str | None = None
    all_pods_requested: bool = False


class ConnectivityTestResponse(BaseModel):
    success: bool
    latency_ms: float
    error: str | None = None


class TokenRotationRequest(BaseModel):
    pod: str | None = None


class TokenRotationResponse(BaseModel):
    success: bool
    status: Literal["green", "yellow", "red"]
    error: str | None = None
    pod: str | None = None
