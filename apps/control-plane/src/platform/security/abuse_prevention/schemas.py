"""Pydantic schemas for the abuse-prevention bounded context (UPD-050).

Mirrors the contracts under
``specs/100-abuse-prevention/contracts/``. TS mirrors live at
``apps/web/lib/security/types.ts`` (T040).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

ABUSE_SETTING_KEYS: tuple[str, ...] = (
    "velocity_per_ip_hour",
    "velocity_per_asn_hour",
    "velocity_per_email_domain_day",
    "captcha_enabled",
    "captcha_provider",
    "geo_block_mode",
    "geo_block_country_codes",
    "fraud_scoring_provider",
    "fraud_scoring_threshold",
    "disposable_email_blocking",
    "auto_suspension_cost_burn_multiplier",
    "auto_suspension_velocity_repeat_threshold",
)


class AbusePreventionSettingValue(BaseModel):
    """Body of `PATCH /admin/security/abuse-prevention/settings/{key}`."""

    model_config = ConfigDict(extra="forbid")

    value: Any


# ---------------------------------------------------------------------------
# Suspensions
# ---------------------------------------------------------------------------

SUSPENSION_REASONS: tuple[str, ...] = (
    "velocity_repeat",
    "fraud_score",
    "cost_burn_rate",
    "disposable_email_pattern",
    "captcha_replay",
    "geo_violation",
    "manual",
    "tenant_admin",
)
SUSPENDED_BY_VALUES: tuple[str, ...] = ("system", "super_admin", "tenant_admin")


class SuspensionView(BaseModel):
    """Row in the suspension queue."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    user_id: UUID
    tenant_id: UUID
    reason: str
    suspended_at: datetime
    suspended_by: str
    suspended_by_user_id: UUID | None = None
    lifted_at: datetime | None = None
    lifted_by_user_id: UUID | None = None


class SuspensionDetailView(SuspensionView):
    """Full suspension row including the evidence payload."""

    evidence_json: dict[str, Any] = Field(default_factory=dict)
    lift_reason: str | None = None


class SuspensionLiftRequest(BaseModel):
    """Body of `POST /admin/security/suspensions/{id}/lift`. Reason required."""

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=2000)


class SuspensionCreateRequest(BaseModel):
    """Body of `POST /admin/security/suspensions/` (manual create)."""

    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    reason: str = "manual"
    evidence: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None

    @field_validator("reason")
    @classmethod
    def _reason_in_enum(cls, value: str) -> str:
        if value not in SUSPENSION_REASONS:
            raise ValueError(f"reason must be one of {SUSPENSION_REASONS!r}")
        return value


# ---------------------------------------------------------------------------
# Disposable-email overrides
# ---------------------------------------------------------------------------


class EmailOverrideAdd(BaseModel):
    """Body of `POST /admin/security/email-overrides/`."""

    model_config = ConfigDict(extra="forbid")

    domain: str = Field(min_length=1, max_length=253)
    reason: str | None = None

    @field_validator("domain")
    @classmethod
    def _normalize(cls, value: str) -> str:
        return value.strip().lower()


# ---------------------------------------------------------------------------
# Trusted allowlist
# ---------------------------------------------------------------------------


class TrustedAllowlistAdd(BaseModel):
    """Body of `POST /admin/security/trusted-allowlist/`."""

    model_config = ConfigDict(extra="forbid")

    kind: str
    value: str = Field(min_length=1, max_length=64)
    reason: str | None = None

    @field_validator("kind")
    @classmethod
    def _kind_in_enum(cls, kind: str) -> str:
        if kind not in ("ip", "asn"):
            raise ValueError("kind must be 'ip' or 'asn'")
        return kind


# ---------------------------------------------------------------------------
# Geo policy
# ---------------------------------------------------------------------------


class GeoPolicyView(BaseModel):
    """Result of `GET /admin/security/geo-policy/`."""

    model_config = ConfigDict(extra="forbid")

    mode: str  # "disabled" | "deny" | "allow_only"
    country_codes: list[str] = Field(default_factory=list)


class GeoPolicyUpdate(BaseModel):
    """Body of `PATCH /admin/security/geo-policy/`."""

    model_config = ConfigDict(extra="forbid")

    mode: str
    country_codes: list[str] = Field(default_factory=list)

    @field_validator("mode")
    @classmethod
    def _mode_in_enum(cls, mode: str) -> str:
        if mode not in ("disabled", "deny", "allow_only"):
            raise ValueError(
                "mode must be one of 'disabled', 'deny', 'allow_only'"
            )
        return mode

    @field_validator("country_codes")
    @classmethod
    def _country_codes_format(cls, codes: list[str]) -> list[str]:
        upper = [code.strip().upper() for code in codes]
        for code in upper:
            if len(code) != 2 or not code.isalpha():
                raise ValueError(
                    f"country_codes must be ISO-3166-1 alpha-2 codes; got {code!r}"
                )
        return upper


# ---------------------------------------------------------------------------
# Signup-guard request extension
# ---------------------------------------------------------------------------


class CaptchaTokenField(BaseModel):
    """Optional field merged into the existing `RegisterRequest` schema.

    The accounts BC's existing `RegisterRequest` is preserved as-is for
    backward compatibility (brownfield rule 7); the captcha_token is
    plumbed via a separate `extra` field on the request body that the
    registration handler reads with `getattr(payload, 'captcha_token',
    None)` semantics.
    """

    model_config = ConfigDict(extra="forbid")

    captcha_token: str | None = None


# ---------------------------------------------------------------------------
# Internal types
# ---------------------------------------------------------------------------


class VelocityCounterSnapshot(BaseModel):
    """Internal type returned by the velocity service for admin display."""

    model_config = ConfigDict(extra="forbid")

    counter_key: str
    counter_window_start: datetime
    counter_value: int


class FraudScore(BaseModel):
    """Result returned by a `FraudScoringProvider` adapter (research R7)."""

    model_config = ConfigDict(extra="forbid")

    risk: float = Field(ge=0.0, le=100.0)
    evidence: dict[str, Any] = Field(default_factory=dict)
